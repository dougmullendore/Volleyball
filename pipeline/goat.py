"""The GOAT ranking: the site's own top 25, where beating a team counts.

It starts from the order of the team ratings behind the odds (results, sets
won and lost, strength of opponents) and then asks: which order agrees with
the most head-to-head results while staying close to the ratings?

Every pair of teams has a price for being ranked the "wrong" way round:
  * ranking a team above one that has beaten it this season costs 1 for each
    win the other team is ahead by (a 1-1 split costs nothing either way);
  * ranking a team above one with a better rating costs their rating gap
    divided by GOAT_HEAD_TO_HEAD.
The GOAT order is the one with the lowest total price, found by moving one
team at a time to wherever it lowers the total most, until no move helps.

So one head-to-head win can overturn up to GOAT_HEAD_TO_HEAD points of
rating: the winner climbs over the team it beat when they are close, but not
when the ratings say the gap is wide, and not over teams in between unless
the total still comes out lower. Results that form a circle (A beat B, B beat
C, C beat A) cannot all be honored; it keeps as many as it can.
"""
from __future__ import annotations

from . import config


def head_to_head(games: list[dict]) -> dict:
    """{(team, opponent): [wins, losses, [dates won]]} from finished matches."""
    out = {}
    for g in sorted(games, key=lambda g: (g["date"], g["id"])):
        hs, vs = g["home"].get("sets"), g["away"].get("sets")
        if g["state"] != "final" or hs is None or vs is None or hs == vs:
            continue
        w, l = (g["home"]["id"], g["away"]["id"]) if hs > vs else (g["away"]["id"], g["home"]["id"])
        a = out.setdefault((w, l), [0, 0, []])
        a[0] += 1
        a[2].append(g["date"])
        out.setdefault((l, w), [0, 0, []])[1] += 1
    return out


def rank(games: list[dict], rating: dict, teams: set) -> dict:
    """Rank `teams` (ids). Returns {"order": [ids, best first], "base": {id: place
    by rating alone}, "beaten": {id: [ids it has the better of, head to head]}}."""
    base_order = sorted(teams, key=lambda t: (-rating.get(t, -99.0), t))
    base = {t: i + 1 for i, t in enumerate(base_order)}
    h2h = head_to_head(games)
    net = {}                                    # net[(a, b)] > 0: a has beaten b more than b has beaten a
    for (a, b), (wins, losses, _) in h2h.items():
        if a in base and b in base and wins > losses:
            net[(a, b)] = wins - losses

    # Only the top of the order is rearranged; a win counts wherever the teams stand.
    pool = base_order[:config.GOAT_POOL]
    n = len(pool)
    r = [rating.get(t, -99.0) for t in pool]
    # price[i][j]: what it costs to rank pool[i] above pool[j]
    price = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                price[i][j] = net.get((pool[j], pool[i]), 0) + max(0.0, r[j] - r[i]) / config.GOAT_HEAD_TO_HEAD

    order = list(range(n))                       # positions hold indexes into pool
    for _ in range(10 * n):                      # each round makes the single best move; stops when none helps
        best = (-1e-9, None, None)
        for src in range(n):
            x = order[src]
            delta = 0.0
            for dst in range(src - 1, -1, -1):   # move x up, passing order[dst]
                t = order[dst]
                delta += price[x][t] - price[t][x]
                if delta < best[0]:
                    best = (delta, src, dst)
            delta = 0.0
            for dst in range(src + 1, n):        # move x down, passing order[dst]
                t = order[dst]
                delta += price[t][x] - price[x][t]
                if delta < best[0]:
                    best = (delta, src, dst)
        if best[1] is None:
            break
        x = order.pop(best[1])
        order.insert(best[2], x)
    final = [pool[i] for i in order] + base_order[n:]
    beaten = {}
    for (a, b) in net:
        beaten.setdefault(a, []).append(b)
    return {"order": final, "base": base, "beaten": beaten}


def contradictions(order: list, games: list[dict], among: set) -> int:
    """How many head-to-head results between teams in `among` the order gets
    the wrong way round (a team ranked below one it has the better of)."""
    place = {t: i for i, t in enumerate(order)}
    return sum(1 for (a, b), (wins, losses, _) in head_to_head(games).items()
               if a in among and b in among and a in place and b in place and wins > losses and place[a] > place[b])
