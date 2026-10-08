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
import time
import unicodedata
import urllib.parse
from pathlib import Path

from . import config

PAGES_FILE = Path(__file__).resolve().parents[1] / "rosters" / "pages.csv"
# Copies of roster pages saved by hand from a browser, for schools whose sites
# turn the job away ("prove you are human"). Used only when the live page
# cannot be read. Save a fresh copy as rosters/saved/<team id>.html when the
# roster changes.
SAVED_DIR = PAGES_FILE.parent / "saved"

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
FINDER = 6


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

    # pages that describe each player for search engines ({"@type":"Person","image":{"url":...},"name":...})
    for m in re.finditer(r'"image"\s*:\s*\{[^{}]*?"url"\s*:\s*"([^"]+)"[^{}]*\}\s*,\s*"name"\s*:\s*"([^"]+)"', page):
        media.append({"name": "", "text": _html.unescape(m.group(2)), "url": m.group(1).replace("http://", "https://", 1), "sure": True})
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
    for pid, url in table_photos(page, base, names).items():
        if pid not in out:
            out[pid] = url
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


_SOCIAL = {"instagram": "https://www.instagram.com/{}", "twitter": "https://x.com/{}", "tiktok": "https://www.tiktok.com/@{}"}
_PLAYERS_LIST = re.compile(r'"players"\s*:\s*\[')


def _bio(d: dict) -> dict:
    """Height, weight, class, hometown, birth date and social links from one
    roster entry, whichever of the two usual spellings the site uses."""
    def g(*keys):
        for k in keys:
            v = d.get(k)
            if v not in (None, "", -1):
                return v
        return None
    out = {}
    ft, inch = g("heightFeet", "height_feet"), g("heightInches", "height_inches")
    if isinstance(ft, int) and 4 <= ft <= 7:
        out["ht"] = f"{ft}-{inch if isinstance(inch, int) else 0}"
    w = g("weight")
    if isinstance(w, (int, str)) and str(w).strip().isdigit() and 80 < int(w) < 350:
        out["wt"] = int(w)
    for key, k2 in (("yr", ("academicYearLong", "academic_year_long")), ("home", ("hometown",)), ("hs", ("highSchool", "highschool")),
                    ("prev", ("previousSchool", "previous_school")), ("born", ("birthDate", "birthdate"))):
        v = g(*k2)
        if isinstance(v, str) and v.strip():
            out[key] = _html.unescape(v.strip())[:80]
    if "born" in out and not re.match(r"\d{4}-\d\d-\d\d", out["born"]):
        del out["born"]
    elif "born" in out:
        out["born"] = out["born"][:10]
    socials = d.get("socials") if isinstance(d.get("socials"), dict) else {}
    links = {}
    for net, url in _SOCIAL.items():
        h = g(net + "Username", net + "_username")
        if not h:
            h = next((v.get("handle") for k, v in socials.items() if k.lower() == net and isinstance(v, dict)), None)
        if isinstance(h, str) and h.strip():
            h = h.strip()
            if h.startswith("http"):
                links[net] = h if urllib.parse.urlsplit(h).hostname and net[:5] in h.replace("x.com", "twitter") else None
            else:
                h = re.sub(r"[^\w.]", "", h.lstrip("@").split("/")[-1])
                links[net] = url.format(h) if h else None
            if not links[net]:
                links.pop(net)
    if links:
        out["social"] = links
    return out


def bios(page: str, names: dict) -> dict:
    """{player id: her height, class, hometown, social links...} for the
    players in `names` whose entry is in the roster page's data."""
    want = {pid: _words(n) for pid, n in names.items()}
    entries = []
    m = _PAYLOAD.search(page)
    if m:
        try:
            data = json.loads(m.group(1))
        except ValueError:
            data = None
        if isinstance(data, list):
            def at(i):
                return data[i] if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(data) else None
            for d in data:
                if isinstance(d, dict) and ("lastName" in d or "last_name" in d):
                    r = {k: (at(v) if not isinstance(at(v), (dict, list)) else None) for k, v in d.items()}
                    soc = at(d.get("socials"))
                    if isinstance(soc, dict):
                        r["socials"] = {k: {kk: at(vv) for kk, vv in (at(v) or {}).items()} for k, v in soc.items() if isinstance(at(v), dict)}
                    links = at(d.get("social_links"))
                    if isinstance(links, list):          # WMT sites: a list of {social_network: {name}, account}
                        for ref in links:
                            e = at(ref)
                            if not isinstance(e, dict):
                                continue
                            net, acct = at(e.get("social_network")), at(e.get("account"))
                            name = (at(net.get("name")) if isinstance(net, dict) else "") or ""
                            key = {"instagram": "instagram", "twitter": "twitter", "x": "twitter", "tiktok": "tiktok"}.get(str(name).strip().lower())
                            if key and isinstance(acct, str) and acct.strip():
                                r.setdefault(key + "Username", acct.strip())
                    entries.append(r)
    dec = json.JSONDecoder()
    for m in _PLAYERS_LIST.finditer(page):
        try:
            lst, _ = dec.raw_decode(page, m.end() - 1)
        except ValueError:
            continue
        entries += [d for d in lst if isinstance(d, dict)]
    out = {}
    for d in entries:
        full = " ".join(str(d.get(k) or "") for k in ("firstName", "first_name", "lastName", "last_name"))
        words = set(_words(full))
        hits = [pid for pid, w in want.items() if w and w[0] in words and w[-1] in words]
        if len(hits) == 1 and hits[0] not in out:
            b = _bio(d)
            if b:
                out[hits[0]] = b
    return out


_ROW = re.compile(r"<tr\b.*?</tr>", re.I | re.S)
_CELL = re.compile(r"""<t[dh]\b(?:[^>"']|"[^"]*"|'[^']*')*>(.*?)</t[dh]>""", re.I | re.S)


def _text(h: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def table_photos(page: str, base: str, names: dict) -> dict:
    """Photos from a roster table whose rows show each player's picture as a
    background image (or an <img>) beside her name."""
    want = {pid: _words(n) for pid, n in names.items()}
    out = {}
    for row in _ROW.findall(page):
        words = set(_words(_text(row)))
        hits = [pid for pid, w in want.items() if w and w[0] in words and w[-1] in words]
        if len(hits) != 1 or hits[0] in out:
            continue
        m = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", row) or re.search(r'<img\b[^>]*\bsrc="([^"]+)"', row)
        url = _usable(urllib.parse.urljoin(base, _html.unescape(m.group(1))), base) if m else None
        if url:
            out[hits[0]] = url
    return out


def table_bios(page: str, names: dict) -> dict:
    """Bios from a roster drawn as a plain table (Num, Name, Pos, Yr, Ht,
    Hometown...), with any Instagram/X/TikTok links in the player's row."""
    want = {pid: _words(n) for pid, n in names.items()}
    cols, out = None, {}
    for row in _ROW.findall(page):
        cells = _CELL.findall(row)
        if "<th" in row.lower() and "<td" not in row.lower():
            cols = [_text(c).lower() for c in cells]
            continue
        if not cols or len(cells) < 3:
            continue
        cell = {}
        for col, c in zip(cols, cells):
            v = _text(c)
            if col and v.lower().startswith(col.rstrip(":") + ":"):     # a label shown only on phones
                v = v[len(col.rstrip(":")) + 1:].strip()
            cell[col] = v
        words = set(_words(" ".join(cell.values())))
        hits = [pid for pid, w in want.items() if w and w[0] in words and w[-1] in words]
        if len(hits) != 1:
            continue
        d = {}
        ht = re.match(r"(\d)\s*[-'′]\s*(\d{1,2})", cell.get("ht") or cell.get("ht.") or cell.get("height") or "")
        if ht:
            d["heightFeet"], d["heightInches"] = int(ht.group(1)), int(ht.group(2))
        yr = cell.get("yr") or cell.get("yr.") or cell.get("cl.") or cell.get("class") or cell.get("year") or ""
        d["academicYearLong"] = {"fr.": "Freshman", "so.": "Sophomore", "jr.": "Junior", "sr.": "Senior", "gr.": "Graduate", "1": "Freshman",
                                 "2": "Sophomore", "3": "Junior", "4": "Senior", "5": "Graduate"}.get(yr.lower().strip(), yr)
        home = [x.strip() for x in next((v for k, v in cell.items() if k.startswith("hometown")), "").split(" /")]
        d["hometown"] = home[0].rstrip("/ ")
        prev = home[1].strip("/ ") if len(home) > 1 else ""
        if re.search(r"\b(University|College|State|Univ)\b", prev):    # a college she transferred from
            d["previousSchool"] = prev
        for net, host in (("instagram", "instagram.com/"), ("twitter", "twitter.com/"), ("twitter", "x.com/"), ("tiktok", "tiktok.com/@")):
            m = re.search(r'href="https?://(?:www\.)?' + re.escape(host) + r'([\w.]+)', row)
            if m:
                d[net + "Username"] = m.group(1)
        b = _bio(d)
        if b:
            out[hits[0]] = b
    return out


_BIO_LINK = re.compile(r'<a\b[^>]*href="([^"#?]*/roster/[^"#?]+)"[^>]*>(.*?)</a>', re.I | re.S)


def from_bio_pages(page: str, base: str, names: dict, fetch, limit: int = 30) -> dict:
    """For a roster page that shows no photos, open each missing player's own
    page (linked from her name) and take her photo from there."""
    want = {pid: _words(n) for pid, n in names.items()}
    out = {}
    for href, label in _BIO_LINK.findall(page):
        if len(out) >= limit:
            break
        words = set(_words(_text(label)))
        hits = [pid for pid, w in want.items() if w and w[0] in words and w[-1] in words and pid not in out]
        if len(hits) != 1:
            continue
        url = urllib.parse.urljoin(base, href)
        try:
            got = find(fetch(url), url, {hits[0]: names[hits[0]]})
        except Exception:
            continue
        out.update(got)
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
        missing = any(pid not in (have.get("photos") or {}) for pid in names) or "bios" not in have \
            or (have.get("finder") or 0) < 6            # read once more for social links on WMT sites
        improved = have.get("finder") != FINDER     # this file has learned a new way to find photos since
        again = 1 if team in ranked else 3
        moved = bool(listed.get(team)) and listed[team] != have.get("page")   # a page just added to rosters/pages.csv
        if age >= config.PHOTO_REFRESH_DAYS or moved or (missing and (age >= again or improved)):
            due.append((team not in ranked, have.get("checked") is not None, -age, team))
    due.sort()
    left = len(due) - config.PHOTO_PAGES_PER_RUN
    stop_at = time.monotonic() + config.PHOTO_SECONDS
    for n_done, (*_, team) in enumerate(due[:config.PHOTO_PAGES_PER_RUN]):
        if time.monotonic() > stop_at:          # out of time: the rest wait for the next run
            left = len(due) - n_done
            break
        names, have = teams[team], stored.get(team) or {}
        page = listed.get(team) or have.get("page")
        try:
            saved = SAVED_DIR / f"{team}.html"
            if page:
                try:
                    text = fetch(page)
                    if saved.exists() and "Human Verification" in text[:3000]:
                        raise ValueError("verification page")
                except Exception:
                    if not saved.exists():
                        raise
                    text = saved.read_text(encoding="utf-8", errors="ignore")
                found = find(text, page, names)
                if len(found) < len(names) // 3:          # a roster with no pictures: try each player's own page
                    found.update(from_bio_pages(text, page, {p: n for p, n in names.items() if p not in found}, fetch))
            else:                                    # a school not read before: find its roster page
                page, found = discover(team, names, fetch)
                text = fetch(page) if page else ""
                if page:
                    discovered.append(team)
        except Exception as e:
            failed.append(f"{team}: {e!r}"[:120])
            continue
        read += 1
        # keep what was found before for anyone this reading missed
        stored[team] = {"checked": today.isoformat(), "finder": FINDER, "page": page, "photos": {**(have.get("photos") or {}), **found},
                       "bios": {**(have.get("bios") or {}), **table_bios(text, names), **bios(text, names)}}
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
