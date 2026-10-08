"""Box scores: each player's official stat line in each match.

Only matches involving a ranked team are downloaded. They are kept in
<state>/box.json so each match is fetched once; matches from the last few days
are fetched again because schools send in corrections.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import config, web

# One stored row per player per match, in this order.
COLS = ["first", "last", "number", "pos", "starter", "sets", "k", "e", "ta", "ast", "sa", "se", "sv",
        "d", "ra", "re", "bs", "ba", "be", "bhe"]
_FEED = {"sets": "gamesPlayed", "k": "kills", "e": "attackErrors", "ta": "attackAttempts", "ast": "assists",
         "sa": "serviceAces", "se": "serviceErrors", "sv": "serveAttempts", "d": "digs", "ra": "receptionAttempts",
         "re": "receptionErrors", "bs": "blockSolos", "ba": "blockAssists", "be": "blockingErrors",
         "bhe": "ballHandlingErrors"}


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def clean_name(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s.title() if s and (s.islower() or s.isupper()) else s


def box_url(game_id: int) -> str:
    ext = json.dumps({"persistedQuery": {"version": 1, "sha256Hash": config.BOX_QUERY}}, separators=(",", ":"))
    variables = json.dumps({"contestId": str(game_id), "staticTestEnv": None}, separators=(",", ":"))
    return config.FEED + "?extensions=" + urllib.parse.quote(ext) + "&variables=" + urllib.parse.quote(variables)


def parse_box(doc: dict) -> dict:
    """{"home": [rows], "away": [rows]} from the feed's box score. A player is
    kept only if she started or has at least one stat: some schools list the
    whole roster and credit everyone with every set."""
    box = ((doc or {}).get("data") or {}).get("boxscore") or {}
    is_home = {str(t.get("teamId")): bool(t.get("isHome")) for t in box.get("teams") or []}
    out = {"home": [], "away": [], "status": box.get("status") or "", "tsets": {}}
    for tb in box.get("teamBoxscore") or []:
        home = is_home.get(str(tb.get("teamId")))
        if home is None:
            continue
        # each team's attack set by set: [kills, errors, attempts]
        out["tsets"]["home" if home else "away"] = [[_int(s.get("kills")), _int(s.get("attackErrors")), _int(s.get("attackAttempts"))]
                                                    for s in ((tb.get("teamStats") or {}).get("sets") or [])]
        for p in tb.get("playerStats") or []:
            n = {k: _int(p.get(f)) for k, f in _FEED.items()}
            touched = any(v for k, v in n.items() if k != "sets")
            if not (touched or p.get("starter")):
                continue
            row = {"first": clean_name(p.get("firstName")), "last": clean_name(p.get("lastName")),
                   "number": _int(p.get("number"), None), "pos": (p.get("position") or "").strip().upper(),
                   "starter": int(bool(p.get("starter"))), **n}
            out["home" if home else "away"].append([row[c] for c in COLS])
    return out


def update(stored: dict, finals: list[dict], today: dt.date, log) -> dict:
    """Fetch the box score of every finished match in `finals` that is not
    stored yet, and again for the last few days' matches. Changes `stored`."""
    recent = (today - dt.timedelta(days=config.BOX_REFRESH_DAYS)).isoformat()
    want = []
    for g in finals:
        have = stored.get(str(g["id"]))
        empty = have is not None and not (have["home"] or have["away"])
        older_format = have is not None and "tsets" not in have      # stored before hitting by set was kept
        if have is None or older_format or g["date"] >= recent or (empty and g["date"] >= (today - dt.timedelta(days=10)).isoformat()):
            want.append(g)

    def one(g):
        try:
            return g, parse_box(json.loads(web.get_bytes(box_url(g["id"])))), None
        except Exception as e:
            return g, None, e

    failed = 0
    with ThreadPoolExecutor(max_workers=config.FETCH_THREADS) as pool:
        for g, parsed, err in pool.map(one, want):
            if err is not None:
                failed += 1
                continue
            if parsed["home"] or parsed["away"] or str(g["id"]) not in stored:
                stored[str(g["id"])] = {"date": g["date"], **parsed}
    with_box = sum(1 for g in finals if (stored.get(str(g["id"])) or {}).get("home"))
    log(f"box scores: {len(want)} fetched ({failed} failed); {with_box} of {len(finals)} finished matches have one")
    return {"fetched": len(want), "failed": failed, "finished": len(finals), "with_box": with_box}


def update_live(stored: dict, games: list[dict], log) -> dict:
    """Fetch the box scores of matches under way or just finished, whatever
    is stored for them already (the match-night runs)."""
    def one(g):
        try:
            return g, parse_box(json.loads(web.get_bytes(box_url(g["id"])))), None
        except Exception as e:
            return g, None, e

    failed = 0
    with ThreadPoolExecutor(max_workers=config.FETCH_THREADS) as pool:
        for g, parsed, err in pool.map(one, games):
            if err is not None:
                failed += 1
            elif parsed["home"] or parsed["away"]:
                stored[str(g["id"])] = {"date": g["date"], **parsed}
    log(f"box scores now: {len(games)} matches under way or just finished, {failed} could not be read")
    return {"fetched": len(games), "failed": failed}

