"""Rate the ranked teams' players against each other.

Everything here compares a player with the other players on this week's top
25 teams, and usually with those at her own position.

Impact is points added: how many more points a player produced than an
average top-25 player at her position would have, given the same chances.
  attack    kills minus errors, against the position's average on her swings; the
            hitter keeps three quarters of it and her setters get the rest
  serve     aces minus errors, against the average on her serves
  receive   reception errors avoided, against the position's average on her receptions
  block     blocks (solo, plus half of each assist) beyond the position's average per set
  dig       digs beyond the position's average per set, at 0.3 of a point each
  set       a quarter of what the team's hitters added, shared among its setters by
            assists (so two setters who split the job are not marked down for
            it); for everyone, ball-handling errors
It is a box-score measure. It cannot see pass quality, who was on the court,
or the strength of the opponent.
"""
from __future__ import annotations

import re
import unicodedata

from .box import COLS, fix_text

STATS = ["sets", "k", "e", "ta", "ast", "sa", "se", "sv", "d", "ra", "re", "bs", "ba", "be", "bhe"]
POS_GROUPS = {"S": "S", "OH": "OH", "O": "OH", "OPP": "OH", "RS": "OH", "RH": "OH", "OH/OPP": "OH",
              "MB": "MB", "MH": "MB", "M": "MB", "L": "L", "DS": "L", "L/DS": "L", "LIB": "L", "DS/L": "L"}
POS_LABEL = {"S": "S", "OH": "OH", "MB": "MB", "L": "L", "DS": "DS"}
PARTS = ["att", "srv", "rec", "blk", "dig", "set"]
DIG_WEIGHT = 0.3             # a dig keeps a rally alive; it does not win it
SETTER_SHARE = 0.25          # of what hitters add, the part credited to whoever set them
REGULAR_SHARE = 0.4          # a regular has played at least this share of her team's sets
MIN_POOL = 8                 # no percentile unless at least this many players qualify

# (key, higher is better, who is ranked on it)
METRICS = [
    ("impact_set", True, "all"), ("att", True, "hits"), ("srv", True, "serves"), ("rec", True, "passes"),
    ("blk", True, "front"), ("dig", True, "all"), ("set", True, "setter"),
    ("k_set", True, "hits"), ("hit", True, "hits"), ("kill_pct", True, "hits"), ("err_pct", False, "hits"),
    ("load", True, "hits"), ("pts_set", True, "front"),
    ("ace_set", True, "serves"), ("ace_pct", True, "serves"), ("se_pct", False, "serves"),
    ("re_pct", False, "passes"), ("d_set", True, "all"), ("blk_set", True, "front"), ("ast_set", True, "setter"),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def player_id(team: str, first: str, last: str) -> str:
    """The same player in different matches: same team, surname, and start of
    the first name (box scores spell first names several ways)."""
    return f"{team}~{_norm(last)}~{_norm(first)[:3]}"


def position(votes: dict, r: dict) -> str:
    """One of S, OH, MB, L: the position the school lists most often, corrected
    by what the player actually does; from her numbers alone if none is listed."""
    if votes:
        listed = max(votes, key=votes.get)
        if listed == "S" and r["ast"] < 3.0:        # listed as a setter but does not set: go by her numbers
            return position({}, dict(r, ast=0.0))
        if listed == "L" and r["ta"] >= 1.5:
            return "MB" if r["blk"] >= 0.7 and r["ra"] < 0.4 else "OH"
        if listed in ("OH", "MB") and r["ta"] < 0.4 and r["ast"] < 3.0 and r["d"] + r["ra"] >= 1.0:
            return "L"
        if listed != "S" and r["ast"] >= 5.0:
            return "S"
        return listed
    if r["ast"] >= 3.0:
        return "S"
    if r["ta"] < 0.8 and (r["d"] >= 1.2 or r["ra"] >= 1.0):
        return "L"
    if r["blk"] >= 0.6 and r["ra"] < 0.4:
        return "MB"
    return "OH"


def _r(v, nd=2):
    return None if v is None else round(v, nd)


def compute(ranked: list[dict], games: list[dict], boxes: dict) -> dict:
    """Every player on the given teams (the ranked 25, or all of Division I), with totals,
    rates, impact and percentiles, each measured against the players of those teams."""
    rank = {t["id"]: t for t in ranked if t["id"]}
    players, team_sets, team_matches = {}, {t: 0 for t in rank}, {t: 0 for t in rank}
    same_player = {}
    for g in games:
        box = boxes.get(str(g["id"]))
        if g["state"] != "final" or not box:
            continue
        for side in ("home", "away"):
            team = g[side]["id"]
            rows = [dict(zip(COLS, row)) for row in box.get(side) or []]
            for r in rows:
                r["first"], r["last"] = fix_text(r["first"]), fix_text(r["last"])
            if team not in rank or not rows:
                continue
            sets = max(r["sets"] for r in rows)
            team_ta = sum(r["ta"] for r in rows)
            team_sets[team] += sets
            team_matches[team] += 1
            names = {}
            for r in rows:                      # a row with only a jersey number takes that number's name
                if (r["first"] or r["last"]) and r["number"] is not None:
                    names[r["number"]] = (r["first"], r["last"])
            for r in rows:
                if not (r["first"] or r["last"]):
                    r["first"], r["last"] = names.get(r["number"], ("", ""))
                if not (r["first"] or r["last"]) or r["sets"] <= 0:
                    continue
                if not r["first"] and " " in r["last"].strip():   # "", "Anna Bardaro": the whole name in one field
                    r["first"], r["last"] = r["last"].strip().split(" ", 1)
                pid = player_id(team, r["first"], r["last"])
                # one player under two first names ("Antonina" and "Tosia"): same team, surname and number
                pid = same_player.setdefault((team, _norm(r["last"]), r["number"]), pid) if r["number"] is not None else pid
                p = players.setdefault(pid, {"id": pid, "team_id": team, "names": {}, "numbers": {}, "votes": {},
                                             "mp": 0, "starts": 0, "team_ta": 0, **{s: 0 for s in STATS}})
                name = (r["first"] + " " + r["last"]).strip()
                p["names"][name] = p["names"].get(name, 0) + 1
                if r["number"] is not None:
                    p["numbers"][r["number"]] = p["numbers"].get(r["number"], 0) + 1
                key = POS_GROUPS.get(r["pos"]) or POS_GROUPS.get(r["pos"].split("/")[0])
                if key:
                    p["votes"][key] = p["votes"].get(key, 0) + max(1, r["sets"])
                p["mp"] += 1
                p["starts"] += r["starter"]
                p["team_ta"] += team_ta
                for s in STATS:
                    p[s] += r[s]

    for p in players.values():
        s = max(1, p["sets"])
        p["blocks"] = p["bs"] + p["ba"] / 2
        p["pos"] = position(p["votes"], {"ast": p["ast"] / s, "ta": p["ta"] / s, "d": p["d"] / s,
                                         "ra": p["ra"] / s, "blk": p["blocks"] / s})

    # What an average top-25 player does: per swing, per serve, per reception, per set.
    def rate(group, num, den):
        d = sum(den(p) for p in group)
        return sum(num(p) for p in group) / d if d else 0.0

    # Schools list liberos and defensive specialists alike as "L/DS", but the
    # jobs differ: a libero is in the back row nearly all match and digs far
    # more. On each team, back-row players who dig at least three quarters as
    # often as the team's busiest one are liberos; the rest are specialists.
    for team in rank:
        back = [p for p in players.values() if p["team_id"] == team and p["pos"] == "L"]
        busy = [p["d"] / p["sets"] for p in back if p["sets"] >= REGULAR_SHARE * team_sets[team]] or [p["d"] / max(1, p["sets"]) for p in back]
        for p in back:
            if p["d"] / max(1, p["sets"]) < 0.75 * max(busy):
                p["pos"] = "DS"

    # The averages come from regulars only: someone who appears for a rotation
    # or two is credited with the whole set, which would drag the per-set
    # averages down and flatter every starter.
    everyone = list(players.values())
    for p in everyone:
        p["regular"] = p["sets"] >= REGULAR_SHARE * team_sets[p["team_id"]] and p["sets"] >= 6
    base = {"srv": rate(everyone, lambda p: p["sa"] - p["se"], lambda p: p["sv"])}
    for pos in POS_LABEL:
        grp = [p for p in everyone if p["pos"] == pos and p["regular"]] or [p for p in everyone if p["pos"] == pos]
        base[pos] = {"att": rate(grp, lambda p: p["k"] - p["e"], lambda p: p["ta"]),
                     "rec": rate(grp, lambda p: p["re"], lambda p: p["ra"]),
                     "blk": rate(grp, lambda p: p["blocks"], lambda p: p["sets"]),
                     "dig": rate(grp, lambda p: p["d"], lambda p: p["sets"]),
                     "ast": rate(grp, lambda p: p["ast"], lambda p: p["sets"]),
                     "bhe": rate(grp, lambda p: p["bhe"], lambda p: p["sets"])}

    # What each team's hitters added in all, and each team's assists, for the setters' share.
    team_att, team_ast = {t: 0.0 for t in rank}, {t: 0 for t in rank}
    for p in everyone:
        team_att[p["team_id"]] += (p["k"] - p["e"]) - p["ta"] * base[p["pos"]]["att"]
        team_ast[p["team_id"]] += p["ast"]

    out = []
    for p in everyone:
        b, s = base[p["pos"]], p["sets"]
        setting = SETTER_SHARE * team_att[p["team_id"]] * p["ast"] / team_ast[p["team_id"]] if team_ast[p["team_id"]] else 0.0
        part = {"att": (1 - SETTER_SHARE) * ((p["k"] - p["e"]) - p["ta"] * b["att"]),
                "srv": (p["sa"] - p["se"]) - p["sv"] * base["srv"],
                "rec": -(p["re"] - p["ra"] * b["rec"]),
                "blk": p["blocks"] - s * b["blk"],
                "dig": DIG_WEIGHT * (p["d"] - s * b["dig"]),
                "set": setting - (p["bhe"] - s * b["bhe"])}
        impact = sum(part.values())
        pts = p["k"] + p["sa"] + p["blocks"]
        v = {"impact_set": impact / s, **{k: part[k] / s for k in PARTS},
             "k_set": p["k"] / s, "hit": (p["k"] - p["e"]) / p["ta"] if p["ta"] else None,
             "kill_pct": 100 * p["k"] / p["ta"] if p["ta"] else None,
             "err_pct": 100 * p["e"] / p["ta"] if p["ta"] else None,
             "load": 100 * p["ta"] / p["team_ta"] if p["team_ta"] else None,
             "pts_set": pts / s, "ace_set": p["sa"] / s,
             "ace_pct": 100 * p["sa"] / p["sv"] if p["sv"] else None,
             "se_pct": 100 * p["se"] / p["sv"] if p["sv"] else None,
             "re_pct": 100 * p["re"] / p["ra"] if p["ra"] else None,
             "d_set": p["d"] / s, "blk_set": p["blocks"] / s, "ast_set": p["ast"] / s}
        can = {"all": True, "hits": p["ta"] / s >= 1.0, "serves": p["sv"] / s >= 1.0, "passes": p["ra"] / s >= 0.75,
               "front": p["pos"] in ("OH", "MB", "S"), "setter": p["pos"] == "S"}
        regular = p["regular"]
        t = rank[p["team_id"]]
        out.append({"id": p["id"], "name": max(p["names"], key=p["names"].get), "team": t["name"], "team_id": p["team_id"],
                    "team_rank": t["rank"], "num": max(p["numbers"], key=p["numbers"].get) if p["numbers"] else None,
                    "pos": POS_LABEL[p["pos"]], "_pos": p["pos"], "mp": p["mp"], "starts": p["starts"], "sp": s,
                    "regular": regular, "impact": impact, "_v": v, "_can": can,
                    "tot": {k: p[k] for k in STATS if k != "sets"} | {"blk": p["blocks"], "pts": pts}})

    # Percentiles: against regulars at the same position who do that job.
    keys = [m[0] for m in METRICS]
    for pos in POS_LABEL:
        for key, higher, who in METRICS:
            pool = [q for q in out if q["_pos"] == pos and q["regular"] and q["_can"][who] and q["_v"][key] is not None]
            if len(pool) < MIN_POOL:
                continue
            vals = sorted(q["_v"][key] for q in pool)
            for q in pool:
                x = q["_v"][key]
                below = sum(1 for y in vals if y < x) + 0.5 * sum(1 for y in vals if y == x)
                pct = 100 * below / len(vals)
                q.setdefault("_pct", {})[key] = int(min(99, max(1, round(pct if higher else 100 - pct))))

    # Ranks: by impact per set among regulars, overall and at the position, so a player
    # is not ranked higher just for having played more sets.
    regulars = sorted((q for q in out if q["regular"]), key=lambda q: (-q["_v"]["impact_set"], -q["impact"]))
    seen = {}
    for i, q in enumerate(regulars):
        q["rank"] = i + 1
        seen[q["_pos"]] = seen.get(q["_pos"], 0) + 1
        q["pos_rank"] = seen[q["_pos"]]
    rows = []
    for q in sorted(out, key=lambda q: (q.get("rank") or 10**6, -q["_v"]["impact_set"])):
        rows.append({"id": q["id"], "name": q["name"], "team": q["team"], "team_id": q["team_id"], "team_rank": q["team_rank"],
                     "num": q["num"], "pos": q["pos"], "mp": q["mp"], "starts": q["starts"], "sp": q["sp"],
                     "regular": q["regular"], "rank": q.get("rank"), "pos_rank": q.get("pos_rank"),
                     "impact": _r(q["impact"], 1), "tot": {k: _r(x, 1) for k, x in q["tot"].items()},
                     "v": [_r(q["_v"][k], 3) for k in keys], "pct": [q.get("_pct", {}).get(k) for k in keys]})
    return {"metrics": keys, "players": rows, "regulars": len(regulars), "pos_regulars": {POS_LABEL[k]: n for k, n in seen.items()},
            "teams": [{"id": t, "name": rank[t]["name"], "rank": rank[t]["rank"], "matches": team_matches[t], "sets": team_sets[t]}
                      for t in sorted(rank, key=lambda t: (rank[t]["rank"] is None, rank[t]["rank"] or 0, rank[t]["name"]))],
            "baseline": {"serve": _r(base["srv"], 4), **{POS_LABEL[k]: {a: _r(b, 4) for a, b in base[k].items()} for k in POS_LABEL}},
            "weights": {"dig": DIG_WEIGHT, "setter_share": SETTER_SHARE, "regular_share": REGULAR_SHARE}}
