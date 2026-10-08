"""Each team's chance of winning a match, from a rating built on results.

There are no public betting lines for college volleyball, so the odds on the
site are this site's own estimate.

A rating says how likely a team is to win a set against an average Division I
team. Before each match the two ratings (and home court) give an expected
share of the sets; afterwards both teams move toward what actually happened,
quickly early in the season and slowly later. A team starts a season on most
of last season's rating. The chance of winning the match follows from the
chance of winning each set, first to three.

Tested on 23,008 matches from 2022 to 2026, always predicting a match from
what was known before it: the favorite won 76.8% of them (the home team wins
57.8%), and teams given 70-80% won 74%. The settings in config.py were chosen
on those same matches, so expect slightly worse on new ones.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import config

SEED_FILE = Path(__file__).resolve().parents[1] / "ratings" / "seed.json"


def seed() -> dict:
    """{"season": the season these ratings finished, "ratings": {team: rating}}:
    where teams stood before this site kept its own ratings."""
    return json.loads(SEED_FILE.read_text()) if SEED_FILE.exists() else {}


def set_chance(gap: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, gap))))


def match_chance(home: float, away: float, neutral: bool = False) -> float:
    """The home team's chance of winning a best-of-five match."""
    gap = home - away + (0.0 if neutral else config.ODDS_HOME)
    p = set_chance(config.ODDS_STRETCH * gap)
    q = 1.0 - p
    return p ** 3 * (1.0 + 3.0 * q + 6.0 * q * q)


def rate(games: list[dict], before: dict) -> tuple[dict, dict]:
    """Walk through a season's matches in order. `before` is last season's
    final ratings. Returns (ratings now, {match id: the home team's chance as
    it stood before that match was played})."""
    listed = {}
    for g in games:
        for side in ("home", "away"):
            listed[g[side]["id"]] = listed.get(g[side]["id"], 0) + 1
    rating, played, pregame = {}, {}, {}

    def start(team):
        if team in before:
            return config.ODDS_KEEP * before[team]
        # a school with only a handful of matches listed is from outside Division I
        return config.ODDS_NEW if listed.get(team, 0) < config.ODDS_FEW_MATCHES else config.ODDS_NEW / 2

    for g in sorted(games, key=lambda g: (g["date"], g["start"] or 0, g["id"])):
        h, a = g["home"]["id"], g["away"]["id"]
        for t in (h, a):
            if t not in rating:
                rating[t] = start(t)
        hs, vs = g["home"].get("sets"), g["away"].get("sets")
        if g["state"] != "final" or hs is None or vs is None or max(hs, vs) != 3 or hs + vs < 3:
            continue
        pregame[g["id"]] = match_chance(rating[h], rating[a])
        surprise = hs - (hs + vs) * set_chance(rating[h] - rating[a] + config.ODDS_HOME)
        for t, sign in ((h, 1.0), (a, -1.0)):
            step = config.ODDS_STEP / (1.0 + played.get(t, 0) / config.ODDS_SETTLE) + config.ODDS_MIN_STEP
            rating[t] += sign * step * surprise
            played[t] = played.get(t, 0) + 1
    return rating, pregame
