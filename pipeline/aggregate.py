"""Build every table the website shows, from the stored matches.

Output goes to <data>/site_data/ as small JSON files:
  meta.json                 seasons, conferences, coverage, how value is scaled
  teams_<season>.json       one row per Division I team
  players_<season>.json     one row per player (box score totals and rates)
  war_<season>.json         player value, split into its parts
  games_<season>.json       every finished match
  cards/<team>.json         each team's players, every season, with percentiles
  recent.json               point-by-point flow of the latest notable matches
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, ratings, store, value

STAT = ["sets", "k", "e", "ta", "ast", "sa", "se", "sv", "d", "ra", "re", "bs", "ba", "be", "bhe"]
POS_GROUPS = {"S": "S", "OH": "OH", "O": "OH", "OPP": "OH", "RS": "OH", "RH": "OH", "OH/OPP": "OH",
              "MB": "MB", "MH": "MB", "M": "MB", "L": "L", "DS": "L", "L/DS": "L", "LIB": "L", "DS/L": "L"}
POS_LABEL = {"S": "S", "OH": "OH", "MB": "MB", "L": "L/DS"}


def _r(v, nd=1):
    """Round for output; NaN and infinities become None."""
    if v is None or pd.isna(v):
        return None
    v = float(v)
    return round(v, nd) if np.isfinite(v) else None


def _div(a, b, scale=1.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, scale * a / np.where(b > 0, b, 1), np.nan)


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def player_id(team: str, first: str, last: str) -> str:
    """The same player in different matches: same team, surname, and start of
    the first name (box scores spell first names several ways)."""
    return f"{team}~{norm(last)}~{norm(first)[:3]}"


# ----------------------------------------------------------- season load --
def load_season(data: Path, season: int, info: dict):
    games = store.read(data, "games", season)
    games = games[(games["state"] == "F") & games["home_sets"].notna() & games["away_sets"].notna()].copy()
    box = store.read(data, "box", season)
    rallies = store.read(data, "rallies", season)
    teams = info.get(season, {})
    d1 = {t for t, v in teams.items() if v["d1"]}
    return games, box, rallies, teams, d1


def team_long(games: pd.DataFrame) -> pd.DataFrame:
    """Two rows per match, one from each side's point of view."""
    def pts(scores):
        h = v = close_h = close_v = 0
        for s in (scores or "").split():
            a, b = s.split("-"); a, b = int(a), int(b)
            h += a; v += b
            if abs(a - b) == 2:
                close_h += a > b; close_v += b > a
        return h, v, close_h, close_v
    p = np.array([pts(s) for s in games["set_scores"]]).reshape(-1, 4)
    g = games.assign(hp=p[:, 0], vp=p[:, 1], hc=p[:, 2], vc=p[:, 3])
    cols = ["game_id", "date", "team", "opp", "sf", "sa", "pf", "pa", "cw", "cl", "is_home", "round"]
    home = g[["game_id", "date", "home", "away", "home_sets", "away_sets", "hp", "vp", "hc", "vc"]].assign(is_home=1, round=g["round"])
    away = g[["game_id", "date", "away", "home", "away_sets", "home_sets", "vp", "hp", "vc", "hc"]].assign(is_home=0, round=g["round"])
    home.columns = cols; away.columns = cols
    out = pd.concat([home, away], ignore_index=True)
    out["won"] = (out["sf"] > out["sa"]).astype(int)
    return out


# ------------------------------------------------------------------ teams --
def rally_team_stats(rallies: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Serving and receiving results and how points were won, per team."""
    if not len(rallies):
        return pd.DataFrame()
    r = rallies.merge(games[["game_id", "home", "away"]], on="game_id")
    frames = []
    for side, team_col in ((1, "home"), (0, "away")):
        won = (r["home_won"] == side)
        known = r["serve_home"].notna()
        serving = known & (r["serve_home"] == side)
        receiving = known & (r["serve_home"] != side)
        t = pd.DataFrame({
            "team": r[team_col], "game_id": r["game_id"], "rallies": 1,
            "srv": serving.astype(int), "srv_won": (serving & won).astype(int),
            "rcv": receiving.astype(int), "rcv_won": (receiving & won).astype(int),
            "p_kill": (won & (r["type"] == "K")).astype(int),
            "p_ace": (won & (r["type"] == "ACE")).astype(int),
            "p_block": (won & (r["type"] == "BLK")).astype(int),
            "p_opp_err": (won & r["type"].isin(["AE", "SE", "BSE", "BHE", "OTH"])).astype(int),
            "won": won.astype(int),
        })
        frames.append(t)
    t = pd.concat(frames, ignore_index=True)
    out = t.groupby("team").sum(numeric_only=True).drop(columns="game_id")
    out["pbp_matches"] = t.groupby("team")["game_id"].nunique()
    return out


def team_table(games, box, rallies, teams, d1, rating, odds_rows) -> list[dict]:
    tl = team_long(games)
    agg = tl.groupby("team").agg(gp=("won", "size"), w=("won", "sum"), sw=("sf", "sum"), sl=("sa", "sum"),
                                 pf=("pf", "sum"), pa=("pa", "sum"), cw=("cw", "sum"), cl=("cl", "sum"))
    own = box.groupby("team")[STAT].sum()
    opp = box.merge(games[["game_id", "home", "away"]], on="game_id")
    opp["opp"] = np.where(opp["team"] == opp["home"], opp["away"], opp["home"])
    opp = opp.groupby("opp")[STAT].sum().add_prefix("o_")
    rs = rally_team_stats(rallies, games)
    odds = {r["id"]: r for r in odds_rows or []}
    rank = {t: i + 1 for i, t in enumerate(sorted(d1, key=lambda t: -rating.get(t, -99)))}
    rows = []
    for team in sorted(d1):
        if team not in agg.index:
            continue
        a = agg.loc[team]
        sets = a["sw"] + a["sl"]
        row = {"id": team, "team": teams[team]["name"], "conf": teams[team]["conf"],
               "gp": int(a["gp"]), "w": int(a["w"]), "l": int(a["gp"] - a["w"]),
               "sw": int(a["sw"]), "sl": int(a["sl"]),
               "rating": _r(rating.get(team), 2), "rank": rank.get(team),
               "sos": (odds.get(team) or {}).get("sos"),
               "cw": (odds.get(team) or {}).get("cw"), "cl": (odds.get(team) or {}).get("cl"),
               "pt_pct": _r(100 * a["pf"] / (a["pf"] + a["pa"]), 1) if a["pf"] + a["pa"] else None,
               "margin": _r((a["pf"] - a["pa"]) / sets, 2) if sets else None,
               "close": f"{int(a['cw'])}-{int(a['cl'])}", "close_pct": _r(100 * a["cw"] / (a["cw"] + a["cl"]), 1) if a["cw"] + a["cl"] else None}
        if team in own.index and team in opp.index:
            o, x = own.loc[team], opp.loc[team]
            ts = float(box[box["team"] == team].groupby("game_id")["sets"].max().sum()) or np.nan   # team sets with a box score
            row.update({
                "hit": _r((o["k"] - o["e"]) / o["ta"], 3) if o["ta"] else None,
                "opp_hit": _r((x["o_k"] - x["o_e"]) / x["o_ta"], 3) if x["o_ta"] else None,
                "k_set": _r(o["k"] / ts, 2), "ast_set": _r(o["ast"] / ts, 2),
                "ace_set": _r(o["sa"] / ts, 2), "se_set": _r(o["se"] / ts, 2),
                "ace_pct": _r(100 * o["sa"] / o["sv"], 1) if o["sv"] else None,
                "se_pct": _r(100 * o["se"] / o["sv"], 1) if o["sv"] else None,
                "blk_set": _r((o["bs"] + o["ba"] / 2) / ts, 2), "dig_set": _r(o["d"] / ts, 2),
                "re_pct": _r(100 * o["re"] / o["ra"], 1) if o["ra"] else None,
            })
        if len(rs) and team in rs.index:
            q = rs.loc[team]
            row.update({
                "so_pct": _r(100 * q["rcv_won"] / q["rcv"], 1) if q["rcv"] else None,
                "bp_pct": _r(100 * q["srv_won"] / q["srv"], 1) if q["srv"] else None,
                "k_share": _r(100 * q["p_kill"] / q["won"], 1) if q["won"] else None,
                "ace_share": _r(100 * q["p_ace"] / q["won"], 1) if q["won"] else None,
                "blk_share": _r(100 * q["p_block"] / q["won"], 1) if q["won"] else None,
                "err_share": _r(100 * q["p_opp_err"] / q["won"], 1) if q["won"] else None,
                "pbp_gp": int(q["pbp_matches"]),
            })
        rows.append(row)
    return rows


# ---------------------------------------------------------------- players --
def position_group(listed: pd.Series, sets: pd.Series, rates: dict) -> str:
    """One of S, OH, MB, L. Uses the position the school lists most often; when
    none is listed, goes by what the player does."""
    votes = {}
    for pos, n in zip(listed, sets):
        key = POS_GROUPS.get(pos) or POS_GROUPS.get((pos or "").split("/")[0])
        if key:
            votes[key] = votes.get(key, 0) + max(1, n)
    if votes:
        listed_as = max(votes, key=votes.get)
        # a few schools list a hitter as a defensive specialist, or the other way round
        if listed_as == "L" and rates["ta"] >= 1.5:
            return "MB" if rates["blk"] >= 0.7 and rates["ra"] < 0.4 else "OH"
        if listed_as in ("OH", "MB") and rates["ta"] < 0.4 and rates["ast"] < 3.0 and rates["d"] + rates["ra"] >= 1.0:
            return "L"
        if listed_as != "S" and rates["ast"] >= 5.0:
            return "S"
        return listed_as
    if rates["ast"] >= 3.0:
        return "S"
    if rates["ta"] < 0.8 and (rates["d"] >= 1.2 or rates["ra"] >= 1.0):
        return "L"
    if rates["blk"] >= 0.6 and rates["ra"] < 0.4:
        return "MB"
    return "OH"


def player_table(games, box, rallies, teams, d1) -> pd.DataFrame:
    """One row per player with season totals. Every match counts, including
    those against schools outside Division I."""
    if not len(box):
        return pd.DataFrame()
    b = box[box["team"].isin(d1)].copy()
    b["pid"] = [player_id(t, f, l) for t, f, l in zip(b["team"], b["first"], b["last"])]
    b["name"] = (b["first"].str.strip() + " " + b["last"].str.strip()).str.strip()
    played = b[b["sets"] > 0]
    tot = played.groupby("pid")[STAT + ["starter"]].sum()
    tot["mp"] = played.groupby("pid")["game_id"].nunique()
    tot["team"] = played.groupby("pid")["team"].first()
    tot["name"] = played.groupby("pid")["name"].agg(lambda s: s.mode().iat[0])
    tot["number"] = played.groupby("pid")["number"].agg(lambda s: s.mode().iat[0] if s.notna().any() else pd.NA)
    pos = {}
    for pid, grp in played.groupby("pid"):
        s = max(1, grp["sets"].sum())
        rates = {"ast": grp["ast"].sum() / s, "ta": grp["ta"].sum() / s, "d": grp["d"].sum() / s,
                 "ra": grp["ra"].sum() / s, "blk": (grp["bs"].sum() + grp["ba"].sum() / 2) / s}
        pos[pid] = position_group(grp["pos"], grp["sets"], rates)
    tot["pos"] = pd.Series(pos)

    # from the play-by-play: kills while receiving serve and while serving, and
    # how many of a hitter's errors were blocks
    extra = pd.DataFrame(0, index=tot.index, columns=["k_so", "k_tr", "blocked", "pbp_k"])
    if len(rallies):
        key = b.set_index(["game_id", "is_home", "row"])["pid"]
        r = rallies.dropna(subset=["p1"])
        kills = r[r["type"] == "K"]
        k_pid = key.reindex(pd.MultiIndex.from_arrays([kills["game_id"], kills["home_won"], kills["p1"]])).to_numpy()
        recv = (kills["serve_home"].notna() & (kills["serve_home"] != kills["home_won"])).to_numpy()
        serv = (kills["serve_home"].notna() & (kills["serve_home"] == kills["home_won"])).to_numpy()
        kk = pd.DataFrame({"pid": k_pid, "k_so": recv.astype(int), "k_tr": serv.astype(int), "pbp_k": 1}).dropna()
        blk = r[r["type"] == "BLK"]
        b_pid = key.reindex(pd.MultiIndex.from_arrays([blk["game_id"], 1 - blk["home_won"], blk["p1"]])).to_numpy()
        bb = pd.DataFrame({"pid": b_pid, "blocked": 1}).dropna()
        add = pd.concat([kk.groupby("pid").sum(), bb.groupby("pid").sum()], axis=1).fillna(0)
        extra = extra.add(add.reindex(extra.index).fillna(0), fill_value=0)
    return tot.join(extra.astype(int))


def player_rows(p: pd.DataFrame, teams: dict) -> dict:
    """The players table as columns plus rows, to keep the file small."""
    cols = ["id", "name", "team", "team_id", "conf", "pos", "mp", "sp", "k", "e", "ta", "hit", "k_set", "kill_pct",
            "err_pct", "blocked", "so_share", "ast", "ast_set", "sa", "se", "sv", "sa_set", "ace_pct", "se_pct",
            "ra", "re", "re_pct", "d", "d_set", "bs", "ba", "blk", "blk_set", "pts", "pts_set"]
    rows = []
    for pid, r in p.iterrows():
        s = r["sets"]
        blk = r["bs"] + r["ba"] / 2
        pts = r["k"] + r["sa"] + blk
        rows.append([
            pid, r["name"], teams[r["team"]]["name"], r["team"], teams[r["team"]]["conf"], POS_LABEL[r["pos"]],
            int(r["mp"]), int(s), int(r["k"]), int(r["e"]), int(r["ta"]),
            _r((r["k"] - r["e"]) / r["ta"], 3) if r["ta"] else None, _r(r["k"] / s, 2),
            _r(100 * r["k"] / r["ta"], 1) if r["ta"] else None, _r(100 * r["e"] / r["ta"], 1) if r["ta"] else None,
            int(r["blocked"]) if r["pbp_k"] or r["blocked"] else None,
            _r(100 * r["k_so"] / (r["k_so"] + r["k_tr"]), 1) if (r["k_so"] + r["k_tr"]) >= 10 else None,
            int(r["ast"]), _r(r["ast"] / s, 2), int(r["sa"]), int(r["se"]), int(r["sv"]), _r(r["sa"] / s, 2),
            _r(100 * r["sa"] / r["sv"], 1) if r["sv"] else None, _r(100 * r["se"] / r["sv"], 1) if r["sv"] else None,
            int(r["ra"]), int(r["re"]), _r(100 * r["re"] / r["ra"], 1) if r["ra"] else None,
            int(r["d"]), _r(r["d"] / s, 2), int(r["bs"]), int(r["ba"]), _r(blk, 1), _r(blk / s, 2),
            _r(pts, 1), _r(pts / s, 2)])
    return {"cols": cols, "rows": rows}


# ------------------------------------------------------------------ games --
def games_table(games, teams, pre) -> list[dict]:
    p = pre.set_index("game_id")["p_home"].to_dict() if len(pre) else {}
    out = []
    for r in games.sort_values(["date", "game_id"], ascending=False).to_dict("records"):
        ph = p.get(r["game_id"])
        hw = r["home_sets"] > r["away_sets"]
        hp = sum(int(s.split("-")[0]) for s in r["set_scores"].split()) if r["set_scores"] else None
        vp = sum(int(s.split("-")[1]) for s in r["set_scores"].split()) if r["set_scores"] else None
        out.append({"id": int(r["game_id"]), "date": r["date"],
                    "away": teams[r["away"]]["name"], "as": int(r["away_sets"]),
                    "home": teams[r["home"]]["name"], "hs": int(r["home_sets"]),
                    "scores": r["set_scores"], "ap": vp, "hp": hp,
                    "pd": (hp - vp) if hp is not None else None,
                    "p_win": _r(100 * (ph if hw else 1 - ph), 0) if ph is not None else None,
                    "round": r["round"],
                    "conf": teams[r["home"]]["conf"] if teams[r["home"]]["conf"] == teams[r["away"]]["conf"] else ""})
    return out


def recent_matches(games, box, rallies, teams, d1, rating, pre, limit=14) -> list[dict]:
    """The latest matches between Division I teams that have every point, best matchups first."""
    if not len(rallies):
        return []
    n_sets = games["set_scores"].str.split().str.len()
    g = games[(games["pbp_sets"] == n_sets) & (n_sets > 0) & games["home"].isin(d1) & games["away"].isin(d1)]
    # only matches where no point is missing from the feed
    points = games["set_scores"].map(lambda s: sum(int(x) for part in s.split() for x in part.split("-")))
    have = rallies.groupby("game_id").size()
    g = g[g["game_id"].map(have).fillna(0).astype(int) == points[g.index]]
    if not len(g):
        return []
    last = sorted(g["date"].unique())[-3:]
    g = g[g["date"].isin(last)].copy()
    g["quality"] = [rating.get(h, -9) + rating.get(a, -9) for h, a in zip(g["home"], g["away"])]
    g = g.sort_values(["quality"], ascending=False).head(limit).sort_values(["date", "quality"], ascending=[False, False])
    p = pre.set_index("game_id")["p_home"].to_dict() if len(pre) else {}
    letter = {"K": "k", "ACE": "a", "BLK": "b", "AE": "e", "SE": "s", "BSE": "e", "BHE": "e", "OTH": "e"}
    out = []
    for r in g.to_dict("records"):
        rr = rallies[rallies["game_id"] == r["game_id"]].sort_values(["set", "n"])
        sets = []
        for _, s in rr.groupby("set"):
            # one character per point: upper case when the home team won it
            sets.append("".join(letter[t].upper() if hw else letter[t] for t, hw in zip(s["type"], s["home_won"])))
        bx = box[box["game_id"] == r["game_id"]]
        lead = []
        for side in (0, 1):
            t = bx[bx["is_home"] == side].sort_values("k", ascending=False).head(1)
            lead.append(None if not len(t) else {"name": (t["first"].iat[0] + " " + t["last"].iat[0]).strip(),
                                                 "k": int(t["k"].iat[0]), "e": int(t["e"].iat[0]), "ta": int(t["ta"].iat[0])})
        tot = {}
        for side in (0, 1):
            t = bx[bx["is_home"] == side][["k", "e", "ta", "sa", "se", "bs", "ba", "d"]].sum()
            tot[side] = {"hit": _r((t["k"] - t["e"]) / t["ta"], 3) if t["ta"] else None, "k": int(t["k"]),
                         "sa": int(t["sa"]), "se": int(t["se"]), "blk": _r(t["bs"] + t["ba"] / 2, 1), "d": int(t["d"])}
        out.append({"id": int(r["game_id"]), "date": r["date"],
                    "home": teams[r["home"]]["name"], "away": teams[r["away"]]["name"],
                    "hs": int(r["home_sets"]), "as": int(r["away_sets"]), "scores": r["set_scores"],
                    "p_home": _r(p.get(r["game_id"]), 3), "sets": sets,
                    "lead": {"away": lead[0], "home": lead[1]}, "tot": {"away": tot[0], "home": tot[1]}})
    return out


# ------------------------------------------------------------------- main --
def build_all(data: Path, log) -> dict:
    data = Path(data)
    out = data / "site_data"
    (out / "cards").mkdir(parents=True, exist_ok=True)
    all_games = ratings.load_games(data)
    info = ratings.team_info(all_games)
    final = {int(k): v for k, v in (store.read_json(data / "derived" / "ratings.json", {}) or {}).items()}
    pre_path = data / "derived" / "pregame.csv.gz"
    pre = pd.read_csv(pre_path) if pre_path.exists() else pd.DataFrame(columns=["game_id", "season", "p_home"])
    odds = store.read_json(out / "odds.json", {}) or {}
    weights = (odds.get("model") or {}).get("weights") or {}

    seasons_meta, player_seasons, summary = [], {}, {}
    conf_names = {}
    scale = value.Scale()
    loaded = {}
    for season in config.SEASONS:
        games, box, rallies, teams, d1 = load_season(data, season, info)
        if not len(games):
            continue
        loaded[season] = (games, box, rallies, teams, d1)
        if len(box):
            p = player_table(games, box, rallies, teams, d1)
            scale.add_season(season, p, games, box, teams, d1, final.get(season, {}))
            player_seasons[season] = p
    scale.finish(weights.get("per_point"))

    for season in sorted(loaded, reverse=True):
        games, box, rallies, teams, d1 = loaded[season]
        rating = final.get(season, {})
        spre = pre[pre["season"] == season] if len(pre) else pre
        is_current = season == max(loaded)
        trows = team_table(games, box, rallies, teams, d1, rating, odds.get("teams") if is_current and odds.get("season") == season else None)
        store.write_json(out / f"teams_{season}.json", trows, compact=True)
        store.write_json(out / f"games_{season}.json", games_table(games[games["home"].isin(d1) | games["away"].isin(d1)], teams, spre), compact=True)
        n_sets = games["set_scores"].str.split().str.len()
        smeta = {"id": season, "label": str(season), "matches": int(len(games)), "teams": len(d1),
                 "through": str(games["date"].max()),
                 "with_box": int((games["detail"] == 1).sum()),
                 "with_points": int(((games["pbp_sets"] == n_sets) & (n_sets > 0)).sum()),
                 "players": season in player_seasons and len(player_seasons[season]) > 0}
        for t in d1:
            c = teams[t]["conf"]
            if c:
                conf_names.setdefault(c, value.conference_name(c))
        if smeta["players"]:
            p = player_seasons[season]
            store.write_json(out / f"players_{season}.json", player_rows(p, teams), compact=True)
            war = scale.war_table(season, teams)
            store.write_json(out / f"war_{season}.json", war, compact=True)
            summary[season] = scale.season_summary(season)
        seasons_meta.append(smeta)
        if is_current:
            store.write_json(out / "recent.json", recent_matches(games, box, rallies, teams, d1, rating, spre), compact=True)
        log(f"stats {season}: {len(games):,} matches, {len(trows)} teams, "
            f"{len(player_seasons.get(season, []))} players, {len(rallies):,} points")

    cards = scale.cards(info)
    for old in (out / "cards").glob("*.json"):
        old.unlink()
    for team, doc in cards.items():
        store.write_json(out / "cards" / f"{team}.json", doc, compact=True)
    index = scale.player_index(info)
    store.write_json(out / "player_index.json", index, compact=True)

    meta = {
        "site": config.SITE_NAME, "tagline": config.SITE_TAGLINE,
        "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "seasons": seasons_meta, "conferences": dict(sorted(conf_names.items(), key=lambda kv: kv[1])),
        "value": {"points_per_win": _r(scale.points_per_win, 1), "dig_weight": config.VALUE_DIG,
                  "setter_share": config.VALUE_SETTER_SHARE, "replacement": scale.replacement_out(),
                  "team_check": scale.team_check, "seasons": summary},
    }
    store.write_json(out / "meta.json", meta)
    return {"seasons": len(seasons_meta), "cards": len(cards), "players": len(index["rows"]),
            "points_per_win": meta["value"]["points_per_win"], "team_check": scale.team_check}
