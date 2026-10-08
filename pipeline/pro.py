"""The pro leagues: League One Volleyball (LOVB) and Major League Volleyball (MLV).

Their results and box scores come from the volleydata project
(github.com/awosoga/volleydata), which collects them from the leagues' own
match centres and publishes them as CSV files. Each league gets its own copy
of the site, in a folder of the published site (lovb/, mlv/), built from the
same pages as the college site: matches, standings with the GOAT ranking,
team stats, players and box scores.

A league's standings take the place of the college poll: every team in the
league is "ranked", by wins and then by set ratio.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from pathlib import Path

from . import box, config, goat, odds, players, teams, web

LEAGUES = {
    # site folder: (volleydata name, league name, standings name)
    "lovb": ("lovb", "LOVB", "LOVB standings"),
    "mlv": ("pvf", "MLV", "MLV standings"),
}
FILES = ["schedule", "player_boxscore", "player_info", "pbp"]
DATA_URL = "https://github.com/awosoga/volleydata/releases/download/{lg}-{kind}/{lg}_{kind}{season}.csv"
# badge colours, one per team
COLORS = ["#1d4ed8", "#b91c1c", "#047857", "#7c3aed", "#c2410c", "#0e7490", "#a21caf", "#4d7c0f", "#be123c", "#334155"]
# volleystation's position numbers
POSITION = {"1": "L", "2": "OH", "3": "OPP", "4": "MB", "5": "S"}


def slug(name: str) -> str:
    name = re.sub(r"^LOVB\s+", "", name.strip())
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def short_name(name: str) -> str:
    return re.sub(r"^LOVB\s+", "", name.strip())


def _f(v) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def download(state: Path, log) -> dict:
    """Fetch each league's CSV files into <state>/pro/. A failed download keeps
    the copy from the last run."""
    folder = state / "pro"
    folder.mkdir(parents=True, exist_ok=True)
    got, failed = 0, []
    for site, (lg, *_rest) in LEAGUES.items():
        for kind in FILES:
            # play-by-play comes one file per season: only the newest is needed (for set scores)
            season = ""
            if kind == "pbp":
                sched = folder / f"{lg}_schedule.csv"
                if not sched.exists():
                    continue
                season = "_" + max(r["season"] for r in csv.DictReader(sched.open(encoding="utf-8")))
            url = DATA_URL.format(lg=lg, kind=kind.replace("_", "-"), season=season)
            try:
                raw = web.get_bytes(url, timeout=60, tries=2)
                if not raw.startswith(b"match_id") and not raw.startswith(b"season") and b"," not in raw[:200]:
                    raise ValueError("not a CSV file")
                if kind == "pbp":      # only the set scores are kept from the (large) play-by-play file
                    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8", "replace"))))
                    (folder / f"{lg}_sets.json").write_text(json.dumps(_set_scores(rows)), encoding="utf-8")
                else:
                    (folder / f"{lg}_{kind}.csv").write_bytes(raw)
                got += 1
            except Exception as e:
                failed.append(f"{lg}_{kind}: {e!r}"[:120])
    log(f"pro leagues: {got} data files downloaded" + (f"; kept the old copy of {failed}" if failed else ""))
    return {"downloaded": got, "failed": failed}


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def _set_scores(pbp: list[dict]) -> dict:
    """{match id: {"home": [points per set], "away": [...]}} from play-by-play:
    the score after the last rally of each set."""
    out = {}
    if not pbp:
        return out
    cols = pbp[0].keys()
    hk = next((c for c in ("home_team_score", "home_score", "score_home") if c in cols), None)
    ak = next((c for c in ("away_team_score", "away_score", "score_away") if c in cols), None)
    sk = next((c for c in ("set_number", "set") if c in cols), None)
    if not (hk and ak and sk):
        return out
    last = {}
    for r in pbp:
        try:
            key = (r["match_id"], int(float(r[sk])))
            last[key] = (_f(r[hk]), _f(r[ak]))
        except (KeyError, ValueError):
            continue
    for (mid, s), (h, a) in sorted(last.items()):
        d = out.setdefault(mid, {"home": [], "away": []})
        d["home"].append(h)
        d["away"].append(a)
    return out


def load(state: Path, site: str) -> dict | None:
    """One league's season: games (in the college site's shape), box scores,
    team names and the season. None if its files are missing."""
    lg = LEAGUES[site][0]
    folder = state / "pro"
    sched = _rows(folder / f"{lg}_schedule.csv")
    if not sched:
        return None
    season = max(r["season"] for r in sched)
    sched = [r for r in sched if r["season"] == season and "all" not in (r["phase"] or "").lower().replace("-", "")]   # not the All-Star match
    ids = {r["match_id"] for r in sched}
    boxrows = [r for r in _rows(folder / f"{lg}_player_boxscore.csv") if r["match_id"] in ids]
    info = {}
    for r in _rows(folder / f"{lg}_player_info.csv"):
        if r["match_id"] in ids:
            info[(r["match_id"], r["player_name"])] = r
    sets_file = folder / f"{lg}_sets.json"
    scores = json.loads(sets_file.read_text(encoding="utf-8")) if sets_file.exists() else {}

    # the start time and each side's full team name come from the box scores
    start, side_name = {}, {}
    for r in boxrows:
        if r["match_id"] not in start and r.get("match_datetime"):
            try:
                start[r["match_id"]] = int(dt.datetime.fromisoformat(r["match_datetime"].replace("Z", "+00:00")).timestamp())
            except ValueError:
                pass
        side_name[(r["match_id"], r["team_involved"])] = r["team_name"]

    names, games = {}, []
    for r in sched:
        h, a = _f(r["home_team_set_wins"]), _f(r["away_team_set_wins"])
        played = h + a > 0
        g = {"id": int(r["match_id"]), "date": r["date"], "start": start.get(r["match_id"]),
             "state": "final" if played else "upcoming", "note": "",
             "round": "" if re.match(r"(?i)week|regular", r["phase"] or "") else (r["phase"] or "").title()}
        for side, col in (("home", "home_team"), ("away", "away_team")):
            nm = short_name(side_name.get((r["match_id"], side)) or r[col])
            tid = slug(nm)
            names[tid] = nm
            g[side] = {"id": tid, "name": nm, "sets": (h if side == "home" else a) if played else None}
        games.append(g)
    games.sort(key=lambda g: (g["date"], g["start"] or 0, g["id"]))

    # box scores, one row per player per match in pipeline/box.py's columns
    per = {}
    for r in boxrows:
        key = (r["match_id"], r["team_involved"], r["player_name"])
        p = per.setdefault(key, {"r": r, "sets": 0, **{c: 0 for c in box.COLS[6:]}})
        if _f(r.get("serves")) + _f(r.get("attack_attempts")) + _f(r.get("receptions")) + _f(r.get("successful_digs")) \
                + _f(r.get("assists")) + _f(r.get("block_points")) + _f(r.get("block_touches")) > 0 or r.get("set_starting_position") not in ("", None):
            p["sets"] += 1
        p["k"] += _f(r["attack_kills"]); p["e"] += _f(r["attack_errors"]); p["ta"] += _f(r["attack_attempts"])
        p["ast"] += _f(r["assists"]); p["sa"] += _f(r["serve_aces"]); p["se"] += _f(r["serve_errors"])
        p["sv"] += _f(r["serves"]); p["d"] += _f(r["successful_digs"]); p["ra"] += _f(r["receptions"])
        p["re"] += _f(r["reception_errors"]); p["bs"] += _f(r["block_points"])
    boxes = {}
    for (mid, side, pname), p in per.items():
        r, i = p["r"], info.get((mid, pname)) or {}
        pos = POSITION.get(str(i.get("primary_position", "")).split(".")[0], "")
        if (i.get("is_libero") or r.get("is_libero")) == "True":
            pos = "L"
        starter = 1 if (i.get("set_1_is_starter") == "True" or (r.get("set_number") == "1" and r.get("set_starting_position") not in ("", "*", None))) else 0
        num = _f(r.get("player_number")) if r.get("player_number") not in ("", None) else None
        row = [r["first_name"] or "", r["last_name"] or pname, num, pos, starter, p["sets"]] + [p[c] for c in box.COLS[6:]]
        b = boxes.setdefault(mid, {"home": [], "away": [], "status": "F", "tsets": {}})
        b[side].append(row)
    for mid, s in scores.items():
        if mid in boxes:
            boxes[mid]["setpts"] = s
    # each team's short code (HOU, IND...), for the badge shown in place of a logo
    abbr = {}
    for (mid, pname), i in info.items():
        tid = slug(i.get("team_name") or "")
        if tid in names and i.get("team_code"):
            abbr[tid] = i["team_code"][:3].upper()
    return {"season": int(season), "games": games, "boxes": boxes, "names": names, "abbr": abbr}


def standings(games: list[dict], names: dict, through: str | None = None) -> list[dict]:
    """Every team by wins, then win share, then set ratio, from finals up to `through`."""
    rec = {t: {"w": 0, "l": 0, "sw": 0, "sl": 0} for t in names}
    for g in games:
        if g["state"] != "final" or (through and g["date"] > through) or g.get("round"):   # the regular season only
            continue
        for s, o in (("home", "away"), ("away", "home")):
            x = rec[g[s]["id"]]
            x["w" if g[s]["sets"] > g[o]["sets"] else "l"] += 1
            x["sw"] += g[s]["sets"]; x["sl"] += g[o]["sets"]
    order = sorted(names, key=lambda t: (-rec[t]["w"], -(rec[t]["w"] / max(1, rec[t]["w"] + rec[t]["l"])),
                                         -(rec[t]["sw"] / max(1, rec[t]["sl"])), names[t]))
    return [{"rank": i + 1, "id": t, "name": names[t], "record": f"{rec[t]['w']}-{rec[t]['l']}"} for i, t in enumerate(order)]


def build(state: Path, out: Path, site: str, now: dt.datetime, words: dict, write_json, match_files, log) -> dict:
    """Write one league's site into out/<site>/ (the page files are copied by the caller)."""
    lg, league, poll_name = LEAGUES[site]
    s = load(state, site)
    if not s:
        log(f"{league}: no data yet")
        return {"teams": 0}
    games, boxes, names = s["games"], s["boxes"], s["names"]
    finals = [g for g in games if g["state"] == "final"]
    through = max((g["date"] for g in finals if not g.get("round")), default=None)
    table = standings(games, names, through)
    week_ago = (dt.date.fromisoformat(through) - dt.timedelta(days=7)).isoformat() if through else None
    before = {t["id"]: t["rank"] for t in standings(games, names, week_ago)} if week_ago and any(g["date"] <= week_ago for g in finals) else {}
    for t in table:
        t["prev"] = before.get(t["id"])
    rank = {t["id"]: t["rank"] for t in table}
    for g in games:
        for side in ("home", "away"):
            g[side]["rank"] = rank.get(g[side]["id"])

    rating, pregame = odds.rate(games, {})
    for g in games:
        if g["state"] != "final" and g["home"]["id"] in rating and g["away"]["id"] in rating:
            g["p"] = round(odds.match_chance(rating[g["home"]["id"]], rating[g["away"]["id"]], False), 3)
        elif g["id"] in pregame:
            g["p0"] = round(pregame[g["id"]], 3)

    # the GOAT order of the league's teams, and each team's results against the others
    ranking = goat.rank(games, rating, set(names), rank)
    results = goat.head_to_head(finals)
    place = {t: i + 1 for i, t in enumerate(ranking["order"])}

    def versus(tid, among):
        beat, lost = [], []
        for other in sorted(among, key=among.get):
            wins, losses, _ = results.get((tid, other), (0, 0, []))
            if wins:
                beat.append([among[other], names[other], wins, other])
            if losses:
                lost.append([among[other], names[other], losses, other])
        return beat, lost

    for t in table:
        t["goat"] = place.get(t["id"])
        t["beat"], t["lost"] = versus(t["id"], rank)
    top = []
    for i, tid in enumerate(ranking["order"]):
        won = sum(v[0] for (a, _), v in results.items() if a == tid)
        lost = sum(v[1] for (a, _), v in results.items() if a == tid)
        b, l = versus(tid, place)
        top.append({"rank": i + 1, "id": tid, "name": names[tid], "avca": rank.get(tid), "score_rank": ranking["base"][tid],
                    "factors": ranking["factors"][tid], "record": f"{won}-{lost}", "beat": b, "lost": l})

    rated = players.compute(table, games, boxes)
    rated["through"] = max((g["date"] for g in finals), default=None)
    dest = out / site
    with_box = match_files(dest, games, boxes, rated)
    for g in games:              # set by set, for the match page
        b = boxes.get(str(g["id"])) or {}
        if b.get("setpts"):
            g["setpts"] = [b["setpts"]["away"], b["setpts"]["home"]]
    write_json(dest / "data.json", {
        "site": config.SITE_NAME, "league": site, "league_name": league, "pro": True,
        "updated": now.isoformat(timespec="seconds"), "season": s["season"],
        "poll": {"name": poll_name, "through": through, "teams": table, "polls_seen": []},
        "game_page": None, "live_feed": None, "live_seconds": config.LIVE_SECONDS, "logo": None,
        "odds_tested": None, "goat": {"top": top, "weight": config.GOAT_HEAD_TO_HEAD, "weights": config.GOAT_WEIGHTS,
                                      "poll_wrong": goat.contradictions([t["id"] for t in table], finals, set(names)),
                                      "goat_wrong": goat.contradictions(ranking["order"], finals, set(names))},
        "nr": {}, "words": words, "abbr": {t: [s["abbr"].get(t) or names[t][:3].upper(), COLORS[i % len(COLORS)]] for i, t in enumerate(sorted(names))}, "d1": [[t["id"], t["name"]] for t in table], "games": games})
    write_json(dest / "players.json", rated)
    write_json(dest / "teams.json", teams.compute(table, games, boxes, rating))
    log(f"{league}: {s['season']} season, {len(games)} matches ({len(finals)} played), {len(names)} teams, "
        f"{len(rated['players'])} players, {with_box} box scores")
    return {"season": s["season"], "matches": len(games), "played": len(finals), "teams": len(names),
            "players": len(rated["players"]), "box_scores": with_box}
