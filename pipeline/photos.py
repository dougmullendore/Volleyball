"""Player photos, from each school's public roster page.

No feed carries photos for college volleyball, so the job reads the roster
page of each ranked school (listed in rosters/pages.csv) and looks for the
picture whose description names a player we already know from the box scores.
Photos are not copied: the page shows them from the school's own site. They
belong to the schools.
"""
from __future__ import annotations

import csv
import datetime as dt
import html as _html
import json
import re
import unicodedata
import urllib.parse
from pathlib import Path

from . import config

PAGES_FILE = Path(__file__).resolve().parents[1] / "rosters" / "pages.csv"

_IMG = re.compile(r"<img\b[^>]*>", re.I)
_LINK = re.compile(r"(<a\b[^>]*>)(?:(?!</a>).){0,6000}?</a>", re.I | re.S)
_PICTURE = re.compile(r"<picture\b.*?</picture>", re.I | re.S)
_ATTR = re.compile(r"""([a-zA-Z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_NOT_A_FACE = re.compile(r"logo|sponsor|icon|placeholder|default|silhouette|headshot[-_]?generic|blank", re.I)


def pages() -> dict:
    """{team id: roster page address} from rosters/pages.csv."""
    if not PAGES_FILE.exists():
        return {}
    with PAGES_FILE.open(newline="", encoding="utf-8") as f:
        return {r["team"].strip(): r["url"].strip() for r in csv.DictReader(f) if r.get("team") and r.get("url")}


def _words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", _html.unescape(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]+", " ", s.replace("'", "").replace("-", " ")).split()


def _attrs(tag: str) -> dict:
    return {m.group(1).lower(): _html.unescape(m.group(2) if m.group(2) is not None else m.group(3)) for m in _ATTR.finditer(tag)}


def _first_url(srcset: str) -> str:
    return (srcset or "").strip().split(",")[0].strip().split(" ")[0]


def _images(page: str):
    """Every picture on the page as (description, addresses to try). A
    lazy-loading <img> often has no real address of its own; the <source>
    beside it does. A picture with no description of its own takes the label
    of the link it sits in ("Chloe Chicoine jersey number 7 full bio")."""
    links = [(m.start(), m.end(), _attrs(m.group(1)).get("aria-label") or _attrs(m.group(1)).get("title") or "")
             for m in _LINK.finditer(page)]

    def label_at(pos):
        return next((lab for lo, hi, lab in links if lo <= pos < hi and lab), "")

    taken = []
    for m in _PICTURE.finditer(page):
        block = m.group(0)
        img = _IMG.search(block)
        if not img:
            continue
        taken.append((m.start(), m.end()))
        a = _attrs(img.group(0))
        a["alt"] = a.get("alt") or label_at(m.start()) or a.get("title")
        urls = [a.get("data-src"), a.get("src"), _first_url(a.get("data-srcset") or a.get("srcset") or "")]
        for s in re.finditer(r"<source\b[^>]*>", block, re.I):
            sa = _attrs(s.group(0))
            if "webp" not in (sa.get("type") or ""):
                urls.append(_first_url(sa.get("data-srcset") or sa.get("srcset") or ""))
        for s in re.finditer(r"<source\b[^>]*>", block, re.I):
            sa = _attrs(s.group(0))
            urls.append(_first_url(sa.get("data-srcset") or sa.get("srcset") or ""))
        yield a.get("alt") or "", urls, a.get("title") or ""
    for m in _IMG.finditer(page):
        if any(lo <= m.start() < hi for lo, hi in taken):
            continue
        a = _attrs(m.group(0))
        yield (a.get("alt") or label_at(m.start()) or a.get("title") or "",
               [a.get("data-src"), a.get("src"), _first_url(a.get("data-srcset") or a.get("srcset") or "")], a.get("title") or "")


def _usable(url: str | None, base: str) -> str | None:
    if not url or url.startswith("data:"):
        return None
    url = urllib.parse.urljoin(base, url.strip())
    if not url.startswith("https://") or _NOT_A_FACE.search(urllib.parse.unquote(url)):
        return None
    if re.search(r"\.(?:wav|mp3|mp4|m4a|mov|svg|pdf)(?:$|[?#])", url, re.I):
        return None
    return url


_PAYLOAD = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _stored_media(page: str) -> list[dict]:
    """Pictures described in the page's data block rather than in its markup.
    Some sites draw the roster in the browser: the <img> is an empty
    placeholder and the real address sits in a block of data, where every
    value is a position in one long list. Returns [{"name": file name,
    "text": everything said about it, "url": a medium-sized address}]."""
    m = _PAYLOAD.search(page)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return []
    if not isinstance(data, list):
        return []

    def at(i):
        v = data[i] if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(data) else None
        return v if isinstance(v, str) else ""

    out = []
    for d in data:
        if not (isinstance(d, dict) and "url" in d and ("original_name" in d or "mime_type" in d)):
            continue
        if "mime_type" in d and not at(d["mime_type"]).startswith("image/"):
            continue                                 # rosters also carry sound clips of how to say a name
        url, sizes = at(d.get("url")), []
        for part in at(d.get("srcset")).split(","):
            bits = part.strip().split(" ")
            if len(bits) == 2 and bits[1].endswith("w") and bits[1][:-1].isdigit():
                sizes.append((int(bits[1][:-1]), bits[0]))
        medium = sorted(w for w in sizes if w[0] >= 300)
        if medium:
            url = medium[0][1]                       # the smallest that is still sharp at card size
        if url:
            out.append({"name": at(d.get("original_name")) or at(d.get("title")),
                        "text": " ".join(at(d.get(k)) for k in ("title", "alt", "caption", "description")), "url": url})
    return out


def find(page: str, base: str, names: dict) -> dict:
    """{player id: photo address} for the players in `names` ({id: name}) whose
    photo is on this roster page. A picture is hers when its description
    contains her first and last names and no other listed player's."""
    want = {pid: _words(n) for pid, n in names.items()}
    media = _stored_media(page)
    by_file = {m["name"]: m["url"] for m in media if m["name"]}

    def whose(text):
        words = set(_words(text))
        hits = [pid for pid, w in want.items() if w and w[0] in words and w[-1] in words]
        return hits[0] if len(hits) == 1 else None

    out = {}
    for alt, urls, file_name in _images(page):
        pid = whose(alt)
        if not pid or pid in out:
            continue
        url = next((u for u in (_usable(u, base) for u in urls + [by_file.get(file_name)]) if u), None)
        if url:
            out[pid] = url
    for m in media:                  # a roster shown as a table has no <img> at all: go by the data block
        pid = whose(m["text"])
        url = _usable(m["url"], base)
        if pid and pid not in out and url:
            out[pid] = url
    return out


def update(stored: dict, teams: dict, today: dt.date, fetch, log) -> dict:
    """Refresh the photos of each team in `teams` ({team id: {player id: name}}).
    A roster page is read again after PHOTO_REFRESH_DAYS, or the next day if
    some of the team's players still have no photo. `fetch(url)` returns the
    page's text. Changes `stored` ({team: {"checked": date, "photos": {...}}})."""
    listed, no_page, failed, read = pages(), [], [], 0
    for team, names in teams.items():
        if team not in listed:
            no_page.append(team)
            continue
        have = stored.get(team) or {}
        age = (today - dt.date.fromisoformat(have["checked"])).days if have.get("checked") else 10 ** 6
        missing = any(pid not in (have.get("photos") or {}) for pid in names)
        if age < config.PHOTO_REFRESH_DAYS and not (missing and age >= 1):
            continue
        try:
            found = find(fetch(listed[team]), listed[team], names)
        except Exception as e:
            failed.append(f"{team}: {e!r}"[:120])
            continue
        read += 1
        # keep what was found before for anyone this reading missed
        stored[team] = {"checked": today.isoformat(), "photos": {**(have.get("photos") or {}), **found}}
    total = sum(len(n) for n in teams.values())
    with_photo = sum(1 for t, names in teams.items() for pid in names if pid in ((stored.get(t) or {}).get("photos") or {}))
    log(f"photos: {read} roster pages read; {with_photo} of {total} players have a photo"
        + (f"; no roster page listed for {no_page}" if no_page else "") + (f"; could not read {failed}" if failed else ""))
    return {"pages_read": read, "players": total, "with_photo": with_photo, "no_page": no_page, "failed": failed}
