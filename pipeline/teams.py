"""Team stats for the ranked teams, from the official box scores.

Each ranked team's own numbers per set and its opponents' numbers against it,
plus the site's rating of the team (the one behind the odds) and how hard its
schedule has been (the average rating of the teams it has played).
"""
from __future__ import annotations

from .box import COLS

I = {c: i for i, c in enumerate(COLS)}
SUM = ["k", "e", "ta", "ast", "sa", "se", "sv", "d", "ra", "re", "bs", "ba", "be", "bhe"]


def _totals(rows: list) -> dict:
    t = {s: 0 for s in SUM}
    for r in rows:
        for s in SUM:
            t[s] += r[I[s]] or 0
    return t


def compute(ranked: list[dict], games: list[dict], boxes: dict, rating: dict) -> dict:
    """{"teams": [...], "through": date}. `games` are the season's matches of
    the ranked teams; `rating` is every team's rating from pipeline/odds.py."""
    rank = {t["id"]: t for t in ranked if t.get("id")}
    power = {t: i + 1 for i, t in enumerate(sorted(rating, key=lambda x: -rating[x]))}
    acc = {t: {"w": 0, "l": 0, "sw": 0, "sl": 0, "sets": 0, "boxed": 0, "opp_r": [], "own": {s: 0 for s in SUM},
               "opp": {s: 0 for s in SUM}} for t in rank}
    through = None
    for g in games:
        if g["state"] != "final" or g["away"].get("sets") is None or g["home"].get("sets") is None:
            continue
        through = max(through or g["date"], g["date"])
        box = boxes.get(str(g["id"])) or {}
        for side, other in (("home", "away"), ("away", "home")):
            t = g[side]["id"]
            if t not in acc:
                continue
            a, mine, theirs = acc[t], g[side]["sets"], g[other]["sets"]
            a["w" if mine > theirs else "l"] += 1
            a["sw"] += mine
            a["sl"] += theirs
            if g[other]["id"] in rating:
                a["opp_r"].append(rating[g[other]["id"]])
            if box.get(side) and box.get(other):            # stats only from matches with a box score
                a["boxed"] += 1
                a["sets"] += mine + theirs
                own, opp = _totals(box[side]), _totals(box[other])
                for s in SUM:
                    a["own"][s] += own[s]
                    a["opp"][s] += opp[s]
    out = []
    for t, a in acc.items():
        o, p, n = a["own"], a["opp"], a["sets"]

        def per(x):
            return round(x / n, 2) if n else None

        def hit(x):
            return round((x["k"] - x["e"]) / x["ta"], 3) if x["ta"] else None

        out.append({
            "id": t, "name": rank[t]["name"], "rank": rank[t]["rank"], "w": a["w"], "l": a["l"],
            "sw": a["sw"], "sl": a["sl"], "set_pct": round(a["sw"] / (a["sw"] + a["sl"]), 3) if a["sw"] + a["sl"] else None,
            "matches": a["boxed"], "sets": n,
            "hit": hit(o), "opp_hit": hit(p), "k_set": per(o["k"]), "opp_k_set": per(p["k"]),
            "ast_set": per(o["ast"]), "sa_set": per(o["sa"]), "se_set": per(o["se"]),
            "blk_set": per(o["bs"] + o["ba"] / 2), "d_set": per(o["d"]),
            "re_pct": round(100 * o["re"] / o["ra"], 1) if o["ra"] else None,
            "power": power.get(t), "sos": round(sum(a["opp_r"]) / len(a["opp_r"]), 3) if a["opp_r"] else None,
        })
    # strength of schedule as a rank among the teams given: 1 is the hardest
    for i, r in enumerate(sorted((r for r in out if r["sos"] is not None), key=lambda r: -r["sos"])):
        r["sos_rank"] = i + 1
    for r in out:
        r.pop("sos")
    out.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["name"]))
    return {"teams": out, "through": through}
