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


# Raised whenever find() learns something new, so teams with players still
# missing a photo are read again straight away rather than the next day.
FINDER = 2


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

    def picture(d):
        """{"name", "text", "url"} for one picture entry, or None."""
        if not (isinstance(d, dict) and "url" in d and ("original_name" in d or "mime_type" in d)):
            return None
        if "mime_type" in d and not at(d["mime_type"]).startswith("image/"):
            return None                              # rosters also carry sound clips of how to say a name
        url, sizes = at(d.get("url")), []
        for part in at(d.get("srcset")).split(","):
            bits = part.strip().split(" ")
            if len(bits) == 2 and bits[1].endswith("w") and bits[1][:-1].isdigit():
                sizes.append((int(bits[1][:-1]), bits[0]))
        medium = sorted(w for w in sizes if w[0] >= 300)
        if medium:
            url = medium[0][1]                       # the smallest that is still sharp at card size
        if not url:
            return None
        return {"name": at(d.get("original_name")) or at(d.get("title")),
                "text": " ".join(at(d.get(k)) for k in ("title", "alt", "caption", "description")), "url": url}

    out = []
    for d in data:
        if not isinstance(d, dict):
            continue
        # a person's entry points straight at her photo: the surest link there is
        if "last_name" in d or "full_name" in d:
            name = at(d.get("full_name")) or (at(d.get("first_name")) + " " + at(d.get("last_name"))).strip()
            for key in ("photo", "master_photo"):
                ref = d.get(key)
                pic = picture(data[ref]) if isinstance(ref, int) and not isinstance(ref, bool) and 0 <= ref < len(data) else None
                if name and pic:
                    out.append({"name": "", "text": name, "url": pic["url"], "sure": True})
                    break
            continue
        pic = picture(d)
        if pic:
            out.append(pic)
    return out


def find(page: str, base: str, names: dict) -> dict:
    """{player id: photo address} for the players in `names` ({id: name}) whose
    photo is on this roster page. A picture is hers when its description
    contains her first and last names and no other listed player's. A player
    the roster lists under a nickname ("Kiki" for Keondreya, "KJ" for Kelli Jo)
    is matched by surname, when hers is the only listed player's with that
    surname and every picture naming it is the same one."""
    want = {pid: _words(n) for pid, n in names.items()}
    media = _stored_media(page)
    by_file = {m["name"]: m["url"] for m in media if m["name"]}

    def whose(text):
        words = set(_words(text))
        hits = [pid for pid, w in want.items() if w and w[0] in words and w[-1] in words]
        return hits[0] if len(hits) == 1 else None

    out = {}
    for m in media:                  # first, players the page's data ties directly to a photo
        pid = whose(m["text"]) if m.get("sure") else None
        url = _usable(m["url"], base)
        if pid and pid not in out and url:
            out[pid] = url
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
    # last, players still without a photo: by surname alone, when that cannot be anyone else's
    pics = [(m["text"] + " " + m["name"], _usable(m["url"], base)) for m in media]
    pics += [(alt + " " + file_name, next((u for u in (_usable(u, base) for u in urls + [by_file.get(file_name)]) if u), None))
             for alt, urls, file_name in _images(page)]
    for pid, w in want.items():
        if pid in out or not w or len(w[-1]) < 3 or sum(1 for v in want.values() if v and v[-1] == w[-1]) > 1:
            continue
        others = {v[-1] for q, v in want.items() if v and q != pid}
        hits = {_image_key(url): url for text, url in pics
                if url and w[-1] in _words(text) and not others & set(_words(text))}   # not a group photo
        if len(hits) == 1 and next(iter(hits.values())) not in out.values():
            out[pid] = next(iter(hits.values()))
    return out


def _image_key(url: str) -> str:
    """The picture behind an address, so two sizes of one photo count once:
    its file name, from inside an image service's address if need be."""
    u = urllib.parse.unquote(url)
    inner = re.findall(r"https?://[^?&\s]+\.(?:jpe?g|png|webp)", u[8:], re.I)
    path = inner[-1] if inner else urllib.parse.urlsplit(u).path
    return path.rsplit("/", 1)[-1].lower()


_WEBSITE = re.compile(r'''<a\b[^>]*href="(https?://[^"]+)"[^>]*>\s*<span[^>]*class="icon-web"''', re.I)


def discover(team: str, names: dict, fetch) -> tuple[str | None, dict]:
    """Find a school's roster page without being told where it is: take its
    athletics website from ncaa.com, try the usual roster addresses, and keep
    the first one that shows photos for a fair share of the players we know.
    Returns (address or None, photos found there)."""
    m = _WEBSITE.search(fetch(config.SCHOOL_PAGE.format(team=team)))
    if not m:
        return None, {}
    site = m.group(1).rstrip("/")
    need = max(3, len(names) // 3)
    best = (None, {})
    for path in config.ROSTER_PATHS:
        try:
            found = find(fetch(site + path), site + path, names)
        except Exception:
            continue                       # no such page on this site: try the next
        if len(found) >= need:
            return site + path, found
        if len(found) > len(best[1]):
            best = (site + path, found)
    return best if len(best[1]) >= 3 else (None, {})


def update(stored: dict, teams: dict, today: dt.date, fetch, log, ranked: set | None = None) -> dict:
    """Refresh the photos of each team in `teams` ({team id: {player id: name}}).
    A roster page is read again after PHOTO_REFRESH_DAYS; sooner if some of the
    team's players still have no photo (the next day for a ranked team, every
    few days for the rest). At most PHOTO_PAGES_PER_RUN schools are read in one
    run, ranked teams first, then schools never read, then the longest unread,
    so all of Division I fills in over a few nights. `fetch(url)` returns the
    page's text. Changes `stored` ({team: {"checked": date, "photos": {...}}})."""
    ranked = ranked or set()
    listed, no_page, failed, read, discovered = pages(), [], [], 0, []
    due = []
    for team, names in teams.items():
        have = stored.get(team) or {}
        age = (today - dt.date.fromisoformat(have["checked"])).days if have.get("checked") else 10 ** 6
        missing = any(pid not in (have.get("photos") or {}) for pid in names)
        improved = have.get("finder") != FINDER     # this file has learned a new way to find photos since
        again = 1 if team in ranked else 3
        if age >= config.PHOTO_REFRESH_DAYS or (missing and (age >= again or improved)):
            due.append((team not in ranked, have.get("checked") is not None, -age, team))
    due.sort()
    left = len(due) - config.PHOTO_PAGES_PER_RUN
    for *_, team in due[:config.PHOTO_PAGES_PER_RUN]:
        names, have = teams[team], stored.get(team) or {}
        page = listed.get(team) or have.get("page")
        try:
            if page:
                found = find(fetch(page), page, names)
            else:                                    # a school not read before: find its roster page
                page, found = discover(team, names, fetch)
                if page:
                    discovered.append(team)
        except Exception as e:
            failed.append(f"{team}: {e!r}"[:120])
            continue
        read += 1
        # keep what was found before for anyone this reading missed
        stored[team] = {"checked": today.isoformat(), "finder": FINDER, "page": page, "photos": {**(have.get("photos") or {}), **found}}
    for team in [t for t, v in stored.items() if t not in teams]:   # a school no longer listed, for a month
        if not v.get("checked") or (today - dt.date.fromisoformat(v["checked"])).days > 30:
            del stored[team]
    no_page = [t for t in teams if not (listed.get(t) or (stored.get(t) or {}).get("page"))]
    total = sum(len(n) for n in teams.values())
    with_photo = sum(1 for t, names in teams.items() for pid in names if pid in ((stored.get(t) or {}).get("photos") or {}))
    log(f"photos: {read} roster pages read; {with_photo} of {total} players have a photo"
        + (f"; {left} more schools wait for the next run" if left > 0 else "")
        + (f"; found the roster page of {len(discovered)} schools" if discovered else "")
        + (f"; no roster page found yet for {len(no_page)} schools, e.g. {no_page[:8]} (add them to rosters/pages.csv)" if no_page else "")
        + (f"; could not read {failed[:8]}" if failed else ""))
    return {"pages_read": read, "players": total, "with_photo": with_photo, "found_page_for": discovered[:50],
            "no_page": no_page[:50], "no_page_count": len(no_page), "waiting": max(0, left), "failed": failed[:20]}
