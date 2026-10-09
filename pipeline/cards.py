"""What a player's card shows beyond her ratings: every match she has played,
her season highs, how she has done against ranked teams, and her career.

These are written one file per team (cards/<team>.json), so a card loads only
its own team's lines.
"""
from __future__ import annotations

# positions in a match line (see players.compute): the stats start after the result
M, DATE, OPP, OPP_NAME, HOME, RESULT, SETS, K, E, TA, AST, SA, SE, D, RE, BS, BA = range(17)
HIGHS = [("Kills", lambda r: r[K]), ("Assists", lambda r: r[AST]), ("Digs", lambda r: r[D]), ("Blocks", lambda r: r[BS] + r[BA]),
         ("Aces", lambda r: r[SA]), ("Points", lambda r: r[K] + r[SA] + r[BS] + r[BA] / 2)]
DOUBLE = [lambda r: r[K], lambda r: r[AST], lambda r: r[D], lambda r: r[BS] + r[BA], lambda r: r[SA]]     # ten or more in two of these is a double-double
# one season of a career: [season, team, matches, sets, k, e, ta, ast, sa, se, d, re, bs, ba]
CAREER = ["k", "e", "ta", "ast", "sa", "se", "d", "re", "bs", "ba"]


def _split(rows: list[list]) -> dict | None:
    if not rows:
        return None
    return {"mp": len(rows), "sp": sum(r[SETS] for r in rows), "k": sum(r[K] for r in rows), "e": sum(r[E] for r in rows),
            "ta": sum(r[TA] for r in rows), "ast": sum(r[AST] for r in rows), "sa": sum(r[SA] for r in rows), "d": sum(r[D] for r in rows),
            "blk": sum(r[BS] + r[BA] / 2 for r in rows), "w": sum(1 for r in rows if r[RESULT].startswith("W"))}


def one(lines: list[list], player: dict, earlier: list[list], season: int, ranked: set, known: bool) -> dict:
    """One player's part of her team's file. `lines` are her matches, oldest
    first; `earlier` her seasons before this one; `known` says whether the
    earlier seasons have all been read yet."""
    highs = []
    for label, get in HIGHS:
        best = max(lines, key=lambda r: (get(r), r[DATE]), default=None)
        if best is not None and get(best) > 0:
            highs.append([label, get(best), best[OPP], best[OPP_NAME], best[DATE], best[M]])
    tens = [sum(1 for get in DOUBLE if get(r) >= 10) for r in lines]
    tot = player["tot"]
    now = [season, player["team"], player["mp"], player["sp"]] + [tot[k] for k in CAREER]
    seasons = [r for r in (earlier or []) if r[0] < season] + [now]
    out = {"games": lines[::-1], "highs": highs, "dd": sum(1 for n in tens if n == 2), "td": sum(1 for n in tens if n >= 3),
           "career": {"seasons": seasons, "total": ["", ""] + [sum(r[i] for r in seasons) for i in range(2, 14)], "known": known}}
    against = _split([r for r in lines if r[OPP] in ranked])
    if against:
        out["ranked"] = against
    return out


def build(rated: dict, logs: dict, careers: dict, season: int, ranked: set, known: bool = True) -> dict:
    """{team: {player id: her card's extra lines}} for everyone in `rated`.
    `careers` is {player id: [her earlier seasons]}."""
    out = {}
    for p in rated["players"]:
        out.setdefault(p["team_id"], {})[p["id"]] = one(logs.get(p["id"]) or [], p, careers.get(p["id"]) or [], season, ranked, known)
    return out
