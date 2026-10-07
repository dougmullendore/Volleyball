"""The national coaches poll (AVCA Top 25), which decides which teams the site shows.

Where each season's top 25 comes from, in this order:
  1. The newest poll this job has stored for that season. Every night the
     current poll is read from ncaa.com and kept in <data>/polls/<season>.json,
     so the last one stored in December is that season's final poll.
  2. `polls/final_polls.csv` in the repository: the final poll of each season
     that was over before this site existed.
  3. If neither exists, the top 25 by this site's own rating.

Schools are named differently in the poll ("Arizona State") and in the NCAA's
match feed ("Arizona St.", id `arizona-st`); `match_school` joins the two.
"""
from __future__ import annotations

import csv
import datetime as dt
import html as _html
import re
import unicodedata
from pathlib import Path

from . import config, ncaa_api, store

FINAL_FILE = Path(__file__).resolve().parents[1] / "polls" / "final_polls.csv"

# Poll spellings that cannot be worked out by rule. Left: the poll's name with
# everything but letters removed. Right: the team's id in the match feed.
ALIASES = {
    "usc": "southern-california", "southerncal": "southern-california",
    "pitt": "pittsburgh", "olemiss": "ole-miss", "mississippi": "ole-miss",
    "hawaii": "hawaii", "miami": "miami-fl", "miamifl": "miami-fl", "miamifla": "miami-fl",
    "miamiohio": "miami-oh", "miamioh": "miami-oh",
    "westernkentucky": "western-ky", "wku": "western-ky",
    "loyolamarymount": "loyola-marymount", "lmu": "loyola-marymount",
    "centralflorida": "ucf", "floridagulfcoast": "fgcu", "southernmethodist": "smu",
    "texaschristian": "tcu", "brighamyoung": "byu", "ncstate": "north-carolina-st",
    "louisianastate": "lsu", "nevadalasvegas": "unlv", "utep": "utep",
    "texasrgv": "utrgv", "utriograndevalley": "utrgv", "utsanantonio": "utsa",
    "stmarys": "st-marys-ca", "saintmarys": "st-marys-ca", "stmarysca": "st-marys-ca",
    "loyolachicago": "loyola-chicago", "calpoly": "cal-poly", "california": "california",
    "longbeachstate": "long-beach-st", "sandiegostate": "san-diego-st",
}


def _letters(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s.replace("&", " and "))


def _keys(name: str) -> list[str]:
    """Spellings of a school name to try, most exact first."""
    name = re.sub(r"\s*\(\d+\)\s*$", "", name or "").strip()      # "Nebraska (47)": first-place votes
    plain = _letters(name)
    out = [plain, _letters(re.sub(r"\bState\b", "St", name)), _letters(re.sub(r"\bSt\.?(?=\s|$)", "State", name))]
    return list(dict.fromkeys(k for k in out if k))


def match_school(name: str, teams: dict) -> str | None:
    """The feed id of the school a poll calls `name`, or None. `teams` is one
    season's {id: {"name": ...}} from the match feed."""
    index = {}
    for tid, t in teams.items():
        for k in (_letters(tid), _letters(t.get("name", "")), _letters(tid.replace("-st", "-state")),
                  _letters(re.sub(r"\bSt\.", "State", t.get("name", "")))):
            if k:
                index.setdefault(k, set()).add(tid)
    for k in _keys(name):
        alias = ALIASES.get(k)
        if alias in teams:
            return alias
        hit = index.get(k)
        if hit and len(hit) == 1:
            return next(iter(hit))
    return None


# ------------------------------------------------------------ the web page --
_ROW = re.compile(r"<tr[^>]*>\s*" + r"\s*".join([r"<td[^>]*>(.*?)</td>"] * 5) + r"\s*</tr>", re.S | re.I)
_THROUGH = re.compile(r"Through Games\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_page(page: str) -> dict:
    """The poll table on ncaa.com's rankings page."""
    def text(cell):
        return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", cell))).strip()

    rows = []
    for m in _ROW.finditer(page):
        rank, school, points, record, prev = (text(c) for c in m.groups())
        if not rank.isdigit() or not school:
            continue
        votes = re.search(r"\((\d+)\)\s*$", school)
        rows.append({"rank": int(rank), "school": re.sub(r"\s*\(\d+\)\s*$", "", school),
                     "votes": int(votes.group(1)) if votes else 0,
                     "points": int(points.replace(",", "")) if points.replace(",", "").isdigit() else None,
                     "record": record, "prev": int(prev) if prev.isdigit() else None})
    when = _THROUGH.search(page)
    through = None
    if when and when.group(1).lower() in _MONTHS:
        through = dt.date(int(when.group(3)), _MONTHS[when.group(1).lower()], int(when.group(2))).isoformat()
    return {"through": through, "rows": rows}


def season_of(date: str) -> int:
    """A poll dated January to mid-August belongs to the season before."""
    y, m, d = (int(x) for x in date.split("-"))
    return y if (m, d) >= config.SEASON_START else y - 1


def update(data: Path, info: dict, log) -> dict:
    """Read tonight's poll and add it to the stored ones."""
    page = ncaa_api.get_bytes(config.POLL_URL).decode("utf-8", "replace")
    poll = parse_page(page)
    if len(poll["rows"]) < config.SHOW_TOP or not poll["through"]:
        raise RuntimeError(f"the poll page did not read cleanly: {len(poll['rows'])} rows, dated {poll['through']}")
    season = season_of(poll["through"])
    teams = info.get(season) or {}
    unmatched = []
    for r in poll["rows"]:
        r["team"] = match_school(r["school"], {t: v for t, v in teams.items() if v.get("d1")})
        if not r["team"]:
            unmatched.append(r["school"])
    path = Path(data) / "polls" / f"{season}.json"
    stored = store.read_json(path, {}) or {}
    is_new = poll["through"] not in stored
    stored[poll["through"]] = poll["rows"]
    store.write_json(path, dict(sorted(stored.items())), compact=True)
    log(f"poll: season {season}, through {poll['through']}, {len(poll['rows'])} teams"
        + (", new" if is_new else "") + (f"; NOT MATCHED to a team: {unmatched}" if unmatched else ""))
    return {"season": season, "through": poll["through"], "teams": len(poll["rows"]), "new": is_new,
            "unmatched": unmatched, "polls_stored": len(stored)}


# ------------------------------------------------------ who the site shows --
def _final_file() -> dict:
    out = {}
    if FINAL_FILE.exists():
        with FINAL_FILE.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out.setdefault(int(r["season"]), []).append({"rank": int(r["rank"]), "team": r["team"], "school": r["school"]})
    return out


def shown(data: Path, info: dict, ratings: dict) -> dict:
    """{season: {"teams": {id: {"rank", "prev"}}, "source", "through"}} for every
    season, or {} when the site is set to show every team.

    source is "poll" (a poll this job stored), "final" (the repository's file
    of past final polls) or "rating" (no poll: the site's own top 25)."""
    if not config.SHOW_TOP:
        return {}
    finals = _final_file()
    out = {}
    for season, teams in info.items():
        d1 = {t for t, v in teams.items() if v.get("d1")}
        stored = store.read_json(Path(data) / "polls" / f"{season}.json", {}) or {}
        rows, source, through = [], None, None
        if stored:
            through = max(stored)
            rows, source = stored[through], "poll"
        elif season in finals:
            rows, source = finals[season], "final"
        picked = {r["team"]: {"rank": r["rank"], "prev": r.get("prev")}
                  for r in rows if r.get("team") in d1 and r["rank"] <= config.SHOW_TOP}
        if len(picked) < min(config.SHOW_TOP, 20):     # no usable poll: fall back to the ratings
            rating = ratings.get(season) or {}
            best = sorted((t for t in d1 if t in rating), key=lambda t: -rating[t])[:config.SHOW_TOP]
            picked, source, through = {t: {"rank": i + 1, "prev": None} for i, t in enumerate(best)}, "rating", None
        out[season] = {"teams": picked, "source": source, "through": through}
    return out
