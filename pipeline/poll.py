"""The national coaches poll: reading it, and deciding when to look for a new one."""
from __future__ import annotations

import datetime as dt
import html as _html
import re
import unicodedata
from zoneinfo import ZoneInfo

from . import config

# Poll spellings that cannot be worked out by rule. Left: the poll's name with
# everything but letters removed. Right: the team's id in the scoreboard feed.
ALIASES = {
    "usc": "southern-california", "southerncal": "southern-california", "pitt": "pittsburgh",
    "olemiss": "ole-miss", "mississippi": "ole-miss", "miami": "miami-fl", "miamifla": "miami-fl",
    "miamiohio": "miami-oh", "westernkentucky": "western-ky", "wku": "western-ky",
    "loyolamarymount": "loyola-marymount", "lmu": "loyola-marymount", "centralflorida": "ucf",
    "floridagulfcoast": "fgcu", "southernmethodist": "smu", "texaschristian": "tcu",
    "brighamyoung": "byu", "ncstate": "north-carolina-st", "louisianastate": "lsu",
    "nevadalasvegas": "unlv", "texasrgv": "utrgv", "utriograndevalley": "utrgv", "utsanantonio": "utsa",
    "stmarys": "st-marys-ca", "saintmarys": "st-marys-ca", "northerniowa": "uni", "ucsb": "uc-santa-barbara",
    "cal": "california", "stjohns": "st-johns-ny", "texasaandmcorpuschristi": "am-corpus-chris",
    "louisiana": "la-lafayette", "ull": "la-lafayette", "sfa": "stephen-f-austin", "etsu": "east-tenn-st",
    "uconn": "uconn", "connecticut": "uconn", "umass": "massachusetts", "unc": "north-carolina",
}

# The scoreboard shortens state names ("South Fla.", "Northern Colo.", id `western-mich`);
# the poll spells them out. Each short form is tried spelled out as well.
SHORT = {"fla": "florida", "mich": "michigan", "colo": "colorado", "ky": "kentucky", "ill": "illinois", "ariz": "arizona",
         "tenn": "tennessee", "caro": "carolina", "ga": "georgia", "la": "louisiana", "ala": "alabama", "miss": "mississippi",
         "wash": "washington", "ark": "arkansas", "conn": "connecticut", "ind": "indiana", "tex": "texas", "okla": "oklahoma",
         "ore": "oregon", "neb": "nebraska", "minn": "minnesota", "wis": "wisconsin", "mo": "missouri", "kan": "kansas",
         "val": "valley", "ky.": "kentucky", "so": "southern", "caro.": "carolina", "u": "university", "dak": "dakota",
         "mex": "mexico", "nev": "nevada", "ia": "iowa", "va": "virginia", "pa": "pennsylvania", "st": "state"}


def _spelled_out(s: str) -> str:
    words = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower().replace("&", " and ")).split()
    return "".join(SHORT.get(w, w) for w in words)

_ROW = re.compile(r"<tr[^>]*>\s*" + r"\s*".join([r"<td[^>]*>(.*?)</td>"] * 5) + r"\s*</tr>", re.S | re.I)
_THROUGH = re.compile(r"Through Games\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


def parse_page(page: str) -> dict:
    """The poll table on ncaa.com's rankings page:
    {"through": "2026-10-04", "rows": [{"rank", "school", "votes", "points", "record", "prev"}]}"""
    def text(cell):
        return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", cell))).strip()

    rows = []
    for m in _ROW.finditer(page):
        rank, school, points, record, prev = (text(c) for c in m.groups())
        if not rank.isdigit() or not school:
            continue
        votes = re.search(r"\((\d+)\)\s*$", school)       # "Nebraska (47)": first-place votes
        points = points.replace(",", "")
        rows.append({"rank": int(rank), "school": re.sub(r"\s*\(\d+\)\s*$", "", school),
                     "votes": int(votes.group(1)) if votes else 0,
                     "points": int(points) if points.isdigit() else None,
                     "record": record, "prev": int(prev) if prev.isdigit() else None})
    when = _THROUGH.search(page)
    through = None
    if when and when.group(1).lower() in _MONTHS:
        through = dt.date(int(when.group(3)), _MONTHS[when.group(1).lower()], int(when.group(2))).isoformat()
    return {"through": through, "rows": rows}


def why_check(polls: dict, now: dt.datetime, forced: bool = False) -> str | None:
    """Why the job should look for a new poll right now, or None if it should not.
    `polls` is {through date: rows}; `now` is any time-zone-aware datetime."""
    if forced:
        return "asked to"
    if not polls:
        return "no poll stored yet"
    local = now.astimezone(ZoneInfo(config.POLL_TIMEZONE))
    if local.weekday() == config.POLL_WEEKDAY:
        return "it is " + local.strftime("%A")
    age = (local.date() - dt.date.fromisoformat(max(polls))).days
    if age > config.POLL_OVERDUE_DAYS:
        return f"the newest poll is {age} days old"
    return None


# ------------------------------------------- poll names to scoreboard teams --
def _letters(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s.replace("&", " and "))


def match_school(name: str, teams: dict) -> str | None:
    """The scoreboard id of the school the poll calls `name` ("Arizona State"
    is `arizona-st`, shown as "Arizona St."). `teams` is {id: short name}."""
    index = {}
    for tid, short in teams.items():
        for k in (_letters(tid), _letters(short), _letters(tid.replace("-st", "-state")),
                  _letters(re.sub(r"\bSt\.", "State", short)), _spelled_out(short), _spelled_out(tid.replace("-", " "))):
            if k:
                index.setdefault(k, set()).add(tid)
    name = re.sub(r"\s*\(\d+\)\s*$", "", name or "").strip()
    for k in dict.fromkeys([_letters(name), _letters(re.sub(r"\bState\b", "St", name)), _spelled_out(name)]):
        if ALIASES.get(k) in teams:
            return ALIASES[k]
        hit = index.get(k)
        if hit and len(hit) == 1:
            return next(iter(hit))
    return None
