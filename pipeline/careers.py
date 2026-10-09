"""Career stats for college players: their earlier seasons at the same school.

The site keeps box scores for the current season only, so earlier seasons are
read once from the NCAA's feed, added up player by player, and kept in
<state>/careers.json. That is about 5,000 box scores a season, so it is done a
few thousand at a time (CAREER_BOXES_PER_RUN), newest season first; until a
season is finished it is not shown.

A player is the same player from one season to the next when she is at the
same school under the same name. A transfer starts again at her new school,
as she does everywhere else on the site.
"""
from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor

from . import box, config, players, web

VERSION = 1
KEYS = ["k", "e", "ta", "ast", "sa", "se", "d", "re", "bs", "ba"]      # after [team, matches, sets]
I = {c: i for i, c in enumerate(box.COLS)}


def season_days(season: int) -> list[str]:
    d, end = dt.date(season, *config.SEASON_START), dt.date(season, *config.SEASON_END)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def add_box(into: dict, parsed: dict, teams: dict) -> None:
    """Add one match's player lines to a season's totals. `teams` is
    {"home": [team id, name], "away": [...]}."""
    for side in ("home", "away"):
        team, name = teams[side]
        for row in parsed.get(side) or []:
            first, last, sets = box.fix_text(row[I["first"]]), box.fix_text(row[I["last"]]), row[I["sets"]]
            if not first and " " in last.strip():
                first, last = last.strip().split(" ", 1)
            if not (first or last) or sets <= 0:
                continue
            p = into.setdefault(players.player_id(team, first, last), [name, 0, 0] + [0] * len(KEYS))
            p[1] += 1
            p[2] += sets
            for n, key in enumerate(KEYS):
                p[3 + n] += row[I[key]] or 0


def update(stored: dict, season: int, parse_contest, log, limit: int | None = None) -> dict:
    """Read some more of the earlier seasons. Changes `stored`:
    {"v", "seasons": {"2025": {"todo": [[match, home id, home, away id, away], ...] or None when not listed yet,
                               "done": bool, "players": {player id: [team, matches, sets, k, ...]}}}}"""
    if stored.get("v") != VERSION:
        stored.clear()
        stored.update(v=VERSION, seasons={})
    limit = config.CAREER_BOXES_PER_RUN if limit is None else limit
    wanted = [season - n for n in range(1, config.CAREER_SEASONS + 1)]
    stored["seasons"] = {k: v for k, v in stored["seasons"].items() if int(k) in wanted}
    read = failed = 0
    for year in wanted:
        s = stored["seasons"].setdefault(str(year), {"todo": None, "done": False, "players": {}})
        if s["done"] or read >= limit:
            continue
        if s["todo"] is None:                       # list the season's finished matches
            todo, missed = [], 0
            for _, contests, err in web.get_days(year, season_days(year)):
                if err is not None:
                    missed += 1
                    continue
                for c in contests:
                    g = parse_contest(c)
                    if g and g["state"] == "final":
                        todo.append([g["id"], g["home"]["id"], g["home"]["name"], g["away"]["id"], g["away"]["name"]])
            if missed > 5:
                log(f"careers: {year} could not be listed ({missed} days failed); it will be tried again")
                continue
            s["todo"] = [list(x) for x in {t[0]: t for t in todo}.values()]
        batch, s["todo"] = s["todo"][:limit - read], s["todo"][limit - read:]

        def one(t):
            try:
                return t, box.parse_box(json.loads(web.get_bytes(box.box_url(t[0]), tries=2))), None
            except Exception as e:
                return t, None, e

        again = []
        with ThreadPoolExecutor(max_workers=config.FETCH_THREADS) as pool:
            for t, parsed, err in pool.map(one, batch):
                if err is not None:
                    failed += 1
                    if len(t) == 5:
                        again.append(t + [1])      # one more try on a later run, then it is left out
                    continue
                add_box(s["players"], parsed, {"home": [t[1], t[2]], "away": [t[3], t[4]]})
                read += 1
        s["todo"] += again
        if not s["todo"]:
            s["done"] = True
        log(f"careers: season {year}: {len(batch) - len(again)} box scores added, {len(s['todo'])} to go"
            + (" (finished)" if s["done"] else ""))
    done = [k for k, v in stored["seasons"].items() if v["done"]]
    return {"read": read, "failed": failed, "seasons_done": sorted(done), "seasons_wanted": len(wanted)}


def by_player(stored: dict) -> tuple[dict, bool]:
    """({player id: [[season, team, matches, sets, k, ...], ...] oldest first}, whether every earlier season is in)."""
    out = {}
    seasons = stored.get("seasons") or {}
    for year in sorted(seasons, key=int):
        if not seasons[year]["done"]:
            continue
        for pid, row in seasons[year]["players"].items():
            out.setdefault(pid, []).append([int(year)] + row)
    return out, bool(seasons) and all(v["done"] for v in seasons.values())
