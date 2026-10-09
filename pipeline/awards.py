"""The awards race: who leads for player of the year, freshman of the year and
the best at each position, and who leads the country in each statistic.

The statistical leaders are counts, shown as they stand, among players who
play regularly (and, for hitting percentage, who take at least MIN_SWINGS
swings a set, as the NCAA requires of its own leaders).

The awards themselves are voted on, so nobody can know them. For each, every
eligible regular gets a score from 0 to 100: her Impact added this season (see
pipeline/players.py) as a share of the leader's, and how strong her team is
among the teams, mixed with the weights in RECIPE. These are a reading of the numbers,
not a forecast of the vote. Impact here always measures a player against
everyone in the pool (all of Division I, or the whole league).

A freshman is anyone her school lists as a freshman or first-year player,
redshirt freshmen included.
"""
from __future__ import annotations

import bisect
import datetime as dt
import re

TOP = 10
RECIPE = {"impact": 0.7, "team": 0.3}
MIN_SWINGS = 3.33
POSITIONS = [("oh", ("OH",), "Outside or Opposite Hitter"), ("mb", ("MB",), "Middle Blocker"), ("s", ("S",), "Setter"),
             ("l", ("L", "DS"), "Libero or Defensive Specialist")]
LEADERS = [   # key, title, value from a player row, how to show it, who may lead
    ("kills", "Kills per Set", lambda p: p["tot"]["k"] / p["sp"], "{:.2f} a set", None),
    ("hitting", "Hitting Percentage", lambda p: (p["tot"]["k"] - p["tot"]["e"]) / p["tot"]["ta"] if p["tot"]["ta"] else 0.0, "{:.3f}",
     lambda p: p["tot"]["ta"] >= MIN_SWINGS * p["sp"]),
    ("assists", "Assists per Set", lambda p: p["tot"]["ast"] / p["sp"], "{:.2f} a set", None),
    ("digs", "Digs per Set", lambda p: p["tot"]["d"] / p["sp"], "{:.2f} a set", None),
    ("blocks", "Blocks per Set", lambda p: p["tot"]["blk"] / p["sp"], "{:.2f} a set", None),
    ("aces", "Aces per Set", lambda p: p["tot"]["sa"] / p["sp"], "{:.2f} a set", None),
    ("points", "Points per Set", lambda p: p["tot"]["pts"] / p["sp"], "{:.2f} a set", None),
]


def _places(values: dict) -> dict:
    """Each value's place among all of them, 0 (lowest) to 1 (highest); ties share."""
    xs = sorted(values.values())
    n = len(xs) or 1
    return {k: (bisect.bisect_left(xs, v) + 0.5 * (bisect.bisect_right(xs, v) - bisect.bisect_left(xs, v))) / n
            for k, v in values.items()}


def is_freshman(year: str | None) -> bool:
    """"Freshman", "Fr.", "First Year", "1st", "R-Fr.", "Redshirt Freshman" ..."""
    y = re.sub(r"[^a-z0-9 ]", " ", (year or "").lower())
    y = re.sub(r"^\s*(r|rs|redshirt)\s+", "", y).strip()
    return bool(re.match(r"(fr|freshman|first|1st)\b", y))


def _stats(p: dict) -> list[str]:
    t, s = p["tot"], p["sp"]
    out = []
    if t["k"] >= s:
        out.append(f"{t['k'] / s:.2f} kills")
    if t["ta"] >= 2 * s:
        out.append(f"{(t['k'] - t['e']) / t['ta']:.3f}".replace("0.", ".", 1) + " hitting")
    if t["ast"] >= 2 * s:
        out.append(f"{t['ast'] / s:.2f} assists")
    if t["d"] >= s:
        out.append(f"{t['d'] / s:.2f} digs")
    if t["blk"] >= 0.5 * s:
        out.append(f"{t['blk'] / s:.2f} blocks")
    if t["sa"] >= 0.25 * s:
        out.append(f"{t['sa'] / s:.2f} aces")
    return out[:4] + [f"{s} sets"]


def compute(rated: dict, strength: dict, pro: str | None = None) -> list[dict]:
    """Every race, best first. `rated` is players.compute()'s result for the
    whole pool; `strength` is {team: 0 to 1, how strong it is among the teams};
    `pro` is the league's name for a pro league (no freshman award)."""
    regulars = [p for p in rated["players"] if p["regular"] and p["sp"] > 0]

    def line(p, score, stats):
        return {"id": p["id"], "name": p["name"], "team": p["team_id"], "team_name": p["team"], "pos": p["pos"], "photo": p.get("photo"),
                "score": None if score is None else round(score, 1), "stats": stats}

    def voted(pool):
        team = {p["id"]: strength.get(p["team_id"], 0.0) for p in pool}
        best = max([p["impact"] for p in pool] + [0.0]) or 1.0      # against the leader, so the top of the list spreads out
        mine = {p["id"]: max(0.0, p["impact"]) / best for p in pool}
        scored = [(100 * (RECIPE["impact"] * mine[p["id"]] + RECIPE["team"] * team[p["id"]]), p) for p in pool]
        scored.sort(key=lambda x: (-x[0], -x[1]["impact"], x[1]["id"]))
        return [line(p, s, [f"{p['impact']:+.1f} Impact"] + _stats(p)) for s, p in scored[:TOP]]

    out = [{"key": "poy", "title": "Most Valuable Player" if pro else "National Player of the Year",
            "for": f"The best player in {'the ' + pro if pro else 'Division I'}", "counted": False, "rows": voted(regulars)}]
    if not pro:
        out.append({"key": "foy", "title": "Freshman of the Year", "for": "The best first-year player in Division I", "counted": False,
                    "rows": voted([p for p in regulars if is_freshman((p.get("bio") or {}).get("yr"))])})
    for key, pos, name in POSITIONS:
        rows = voted([p for p in regulars if p["pos"] in pos])
        if rows:
            out.append({"key": key, "title": f"Best {name}", "for": f"The best {name.lower()} in {'the ' + pro if pro else 'Division I'}",
                        "counted": False, "rows": rows})
    for key, title, value, show, may in LEADERS:
        pool = [p for p in regulars if may is None or may(p)]
        pool.sort(key=lambda p: (-value(p), -p["sp"], p["id"]))
        rows = [line(p, None, [show.format(value(p)).replace("0.", ".", 1) if key == "hitting" else show.format(value(p)),
                               f"{p['sp']} sets", f"{p['mp']} matches"]) for p in pool[:TOP] if value(p) > 0]
        out.append({"key": key, "title": title, "for": "Statistical leader", "counted": True, "rows": rows})
    return out


def movement(races: list[dict], history: dict, today: str, days: int = 7) -> None:
    """Mark each row with where it stood a week ago ("was": an earlier place,
    or 0 if it was not in the top ten), from the kept daily snapshots."""
    earlier = sorted(d for d in history if d < today)
    if not earlier:
        return
    target = (dt.date.fromisoformat(today) - dt.timedelta(days=days)).isoformat()
    older = [d for d in earlier if d <= target]
    then = history[older[-1] if older else earlier[0]]
    for race in races:
        was = then.get(race["key"])
        if was is None:
            continue
        for row in race["rows"]:
            row["was"] = was.index(row["id"]) + 1 if row["id"] in was else 0


def snapshot(races: list[dict]) -> dict:
    return {race["key"]: [row["id"] for row in race["rows"]] for race in races}


def track(races: list[dict], history: dict, today: str) -> dict:
    """Mark the movement, then return the history with today's leaders added (the last 60 days are kept)."""
    movement(races, history, today)
    history = {**history, today: snapshot(races)}
    return dict(sorted(history.items())[-60:])
