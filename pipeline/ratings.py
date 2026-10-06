"""Team ratings, match win probabilities, and the season simulation.

A team's rating is how many points per set it is better than an average
Division I team. It is a running average of each match's point margin per
set, corrected for the opponent's rating at the time, so beating a strong
team by two points a set counts for more than beating a weak one by four.
Ratings carry over from last season, pulled part of the way back to average.

Nothing here knows about rosters: injuries, transfers and graduation only
show up once the results change.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, store

# Typical point margin per set for each final score in sets, used only when
# a match has no set-by-set scores in the feed.
SETS_TO_MARGIN = {3: 6.2, 2: 2.9, 1: 0.5}
MARGIN_CAP = 12.0


# ------------------------------------------------------------------ data --
def load_games(data: Path) -> pd.DataFrame:
    frames = [store.read(data, "games", s) for s in config.SEASONS]
    g = pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) else store.frame("games", [])
    return g.sort_values(["date", "game_id"]).reset_index(drop=True)


def margin_per_set(row) -> float | None:
    """Home points minus away points, per set played."""
    scores = [s.split("-") for s in (row["set_scores"] or "").split()]
    try:
        scores = [(int(a), int(b)) for a, b in scores]
    except ValueError:
        scores = []
    if scores:
        m = sum(a - b for a, b in scores) / len(scores)
    elif pd.notna(row["home_sets"]) and pd.notna(row["away_sets"]) and row["home_sets"] != row["away_sets"]:
        diff = int(row["home_sets"]) - int(row["away_sets"])
        m = SETS_TO_MARGIN.get(abs(diff), 3.0) * (1 if diff > 0 else -1)
    else:
        return None
    return float(max(-MARGIN_CAP, min(MARGIN_CAP, m)))


def team_info(games: pd.DataFrame) -> dict:
    """{season: {team: {"name", "conf", "d1"}}} from everything listed, played or not."""
    out = {}
    for season, g in games.groupby("season"):
        long = pd.concat([
            g[["home", "home_name", "home_conf", "home_div"]].set_axis(["team", "name", "conf", "div"], axis=1),
            g[["away", "away_name", "away_conf", "away_div"]].set_axis(["team", "name", "conf", "div"], axis=1)])
        info = {}
        for team, t in long.groupby("team"):
            div = t["div"].dropna()
            conf = t["conf"][t["conf"] != ""]
            d1 = bool((div == 1).mean() >= 0.5) if len(div) else len(t) >= config.MIN_MATCHES_D1
            info[team] = {"name": t["name"].mode().iat[0], "conf": conf.mode().iat[0] if len(conf) else "",
                          "d1": d1 and len(t) >= config.MIN_MATCHES_D1}
        out[int(season)] = info
    return out


# ---------------------------------------------------------------- ratings --
def walk(games: pd.DataFrame, info: dict, prior=None, min_step=None, keep=None):
    """Go through every finished match in date order, updating ratings as it goes.

    Returns (pregame, final): `pregame` has one row per finished match with
    each side's rating before it was played; `final` is {season: {team: rating}}."""
    prior = config.RATING_PRIOR_MATCHES if prior is None else prior
    min_step = config.RATING_MIN_STEP if min_step is None else min_step
    keep = config.RATING_SUMMER_KEEP if keep is None else keep
    rating, played = {}, {}
    final, rows = {}, []
    done = games[(games["state"] == "F") & games["home_sets"].notna()]
    for season in sorted(done["season"].unique()):
        season = int(season)
        teams = info.get(season, {})
        # over the summer: keep part of the distance from average, forget the match count
        new_rating = {}
        for team, t in teams.items():
            if team in rating:
                new_rating[team] = rating[team] * keep if t["d1"] else rating[team]
            else:
                new_rating[team] = 0.0 if (t["d1"] and not rating) else config.RATING_NEW_TEAM
                if not t["d1"]:
                    new_rating[team] = 2 * config.RATING_NEW_TEAM
        rating, played = new_rating, {team: 0 for team in new_rating}
        for r in done[done["season"] == season].to_dict("records"):
            h, a = r["home"], r["away"]
            m = margin_per_set(r)
            if m is None or h not in rating or a not in rating:
                continue
            rh, ra = rating[h], rating[a]
            same_conf = bool(teams[h]["conf"]) and teams[h]["conf"] == teams[a]["conf"] and not r["round"]
            rows.append((r["game_id"], season, r["date"], h, a, rh, ra, played[h], played[a], int(same_conf),
                         m, int(r["home_sets"] > r["away_sets"]), int(teams[h]["d1"] and teams[a]["d1"])))
            err = m - (rh - ra)
            rating[h] = rh + max(min_step, 1.0 / (played[h] + prior)) * err
            rating[a] = ra - max(min_step, 1.0 / (played[a] + prior)) * err
            played[h] += 1; played[a] += 1
        final[season] = dict(rating)
    cols = ["game_id", "season", "date", "home", "away", "r_home", "r_away", "n_home", "n_away",
            "conf_match", "margin", "home_won", "both_d1"]
    return pd.DataFrame(rows, columns=cols), final


# ---------------------------------------------------- win probability fit --
def design(pre: pd.DataFrame) -> np.ndarray:
    """Columns: rating gap, home edge in a conference match, home edge otherwise."""
    gap = (pre["r_home"] - pre["r_away"]).to_numpy(float)
    conf = pre["conf_match"].to_numpy(float)
    return np.column_stack([gap, conf, 1.0 - conf])


def fit_logit(X: np.ndarray, y: np.ndarray, ridge: float = 1e-3) -> np.ndarray:
    w = np.zeros(X.shape[1])
    for _ in range(40):
        p = 1.0 / (1.0 + np.exp(-X @ w))
        grad = X.T @ (p - y) + ridge * w
        hess = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(X.shape[1])
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def predict(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-X @ w))


def log_loss(p, y) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def backtest(pre: pd.DataFrame) -> dict:
    """Predict each season with weights fitted on the other seasons. The first
    season stored is left out: its ratings start from nothing."""
    pre = pre[pre["both_d1"] == 1]
    seasons = sorted(pre["season"].unique())[1:]
    if len(seasons) < 2:
        return {}
    ps, ys, by = [], [], {}
    for s in seasons:
        train, test = pre[(pre["season"] != s) & pre["season"].isin(seasons)], pre[pre["season"] == s]
        w = fit_logit(design(train), train["home_won"].to_numpy(float))
        p, y = predict(design(test), w), test["home_won"].to_numpy(float)
        by[str(int(s))] = {"matches": int(len(y)), "log_loss": round(log_loss(p, y), 4),
                           "accuracy": round(float(((p > 0.5) == (y > 0.5)).mean()), 4)}
        ps.append(p); ys.append(y)
    p, y = np.concatenate(ps), np.concatenate(ys)
    order = np.argsort(p)
    bins = [{"predicted": round(float(p[i].mean()), 4), "actual": round(float(y[i].mean()), 4), "n": int(len(i))}
            for i in np.array_split(order, 10)]
    base = float(y.mean())
    fav = np.maximum(p, 1 - p)
    return {"matches": int(len(y)), "log_loss": round(log_loss(p, y), 4),
            "baseline_log_loss": round(log_loss(np.full_like(p, base), y), 4),
            "accuracy": round(float(((p > 0.5) == (y > 0.5)).mean()), 4),
            "home_win_rate": round(base, 4), "avg_favorite": round(float(fav.mean()), 4),
            "by_season": by, "calibration": bins}


# -------------------------------------------------------------- simulate --
def simulate(season: int, games: pd.DataFrame, teams: dict, rating: dict, w: np.ndarray,
             today: str, rng: np.random.Generator) -> tuple[list, int]:
    """Play out the rest of the regular season many times."""
    g = games[games["season"] == season]
    d1 = sorted(t for t, v in teams.items() if v["d1"])
    idx = {t: i for i, t in enumerate(d1)}
    n = len(d1)
    conf = np.array([teams[t]["conf"] for t in d1])
    w_now, l_now, cw_now, cl_now = (np.zeros(n) for _ in range(4))
    sw_now, sl_now = np.zeros(n), np.zeros(n)
    opp_sum, opp_n = np.zeros(n), np.zeros(n)

    def is_conf(r):
        return (r["home"] in idx and r["away"] in idx and teams[r["home"]]["conf"]
                and teams[r["home"]]["conf"] == teams[r["away"]]["conf"] and not r["round"])

    done = g[(g["state"] == "F") & g["home_sets"].notna()]
    for r in done.to_dict("records"):
        hw = r["home_sets"] > r["away_sets"]
        for team, opp, won, sf, sa in ((r["home"], r["away"], hw, r["home_sets"], r["away_sets"]),
                                       (r["away"], r["home"], not hw, r["away_sets"], r["home_sets"])):
            if team not in idx:
                continue
            i = idx[team]
            w_now[i] += won; l_now[i] += not won
            sw_now[i] += sf; sl_now[i] += sa
            opp_sum[i] += rating.get(opp, 2 * config.RATING_NEW_TEAM); opp_n[i] += 1
            if is_conf(r):
                cw_now[i] += won; cl_now[i] += not won

    left = g[(g["state"] != "F") & (g["date"] >= today) & (g["round"] == "")]
    left = left[left["home"].isin(rating.keys()) & left["away"].isin(rating.keys())]
    left = left[left["home"].isin(idx.keys()) | left["away"].isin(idx.keys())]
    sims = config.PRED_SIMULATIONS
    tw, tcw = np.tile(w_now, (sims, 1)), np.tile(cw_now, (sims, 1))
    tcl = np.tile(cl_now, (sims, 1))
    if len(left):
        rec = left.to_dict("records")
        all_teams = sorted(set(left["home"]) | set(left["away"]))
        pos = {t: i for i, t in enumerate(all_teams)}
        base = np.array([rating[t] for t in all_teams])
        draw = base[None, :] + rng.normal(0.0, config.PRED_STRENGTH_DOUBT, size=(sims, len(all_teams)))
        hi = np.array([pos[r["home"]] for r in rec]); ai = np.array([pos[r["away"]] for r in rec])
        cm = np.array([bool(is_conf(r)) for r in rec])
        z = w[0] * (draw[:, hi] - draw[:, ai]) + np.where(cm, w[1], w[2])[None, :]
        home_win = rng.random(z.shape) < 1.0 / (1.0 + np.exp(-z))
        for j, r in enumerate(rec):
            hw = home_win[:, j]
            if r["home"] in idx:
                i = idx[r["home"]]; tw[:, i] += hw
                if cm[j]:
                    tcw[:, i] += hw; tcl[:, i] += ~hw
            if r["away"] in idx:
                i = idx[r["away"]]; tw[:, i] += ~hw
                if cm[j]:
                    tcw[:, i] += ~hw; tcl[:, i] += hw
    total = np.zeros(n)
    for i in range(n):
        total[i] = w_now[i] + l_now[i]
    left_n = np.zeros(n)
    for r in left.to_dict("records"):
        for t in (r["home"], r["away"]):
            if t in idx:
                left_n[idx[t]] += 1
    # conference title: best conference winning percentage, ties share it
    title = np.zeros(n)
    pct = np.where(tcw + tcl > 0, tcw / np.maximum(tcw + tcl, 1), -1.0)
    for c in sorted(set(conf)):
        members = np.where(conf == c)[0]
        if not c or len(members) < 2:
            continue
        sub = pct[:, members]
        best = sub.max(axis=1, keepdims=True)
        tied = (sub >= best - 1e-9) & (best > -0.5)
        title[members] = (tied / np.maximum(tied.sum(axis=1, keepdims=True), 1)).mean(axis=0)
    avg_gap = w[0]
    rows = []
    order = np.argsort(-np.array([rating.get(t, 0.0) for t in d1]))
    rank = {d1[i]: k + 1 for k, i in enumerate(order)}
    for t in d1:
        i = idx[t]
        games_total = total[i] + left_n[i]
        rows.append({
            "id": t, "team": teams[t]["name"], "conf": teams[t]["conf"],
            "w": int(w_now[i]), "l": int(l_now[i]), "cw": int(cw_now[i]), "cl": int(cl_now[i]),
            "sw": int(sw_now[i]), "sl": int(sl_now[i]),
            "rating": round(float(rating.get(t, 0.0)), 2), "rank": rank[t],
            "strength": round(100.0 / (1.0 + np.exp(-avg_gap * rating.get(t, 0.0))), 1),
            "sos": round(float(opp_sum[i] / opp_n[i]), 2) if opp_n[i] else None,
            "left": int(left_n[i]),
            "proj_w": round(float(tw[:, i].mean()), 1), "proj_l": round(float(games_total - tw[:, i].mean()), 1),
            "proj_cw": round(float(tcw[:, i].mean()), 1), "proj_cl": round(float(tcl[:, i].mean()), 1),
            "w_lo": int(np.percentile(tw[:, i], 10)), "w_hi": int(np.percentile(tw[:, i], 90)),
            "title": round(100 * float(title[i]), 1),
        })
    return rows, int(len(left))


def build(data: Path, out_dir: Path, log) -> dict:
    data, out_dir = Path(data), Path(out_dir)
    games = load_games(data)
    if not len(games):
        raise RuntimeError("no matches stored yet")
    info = team_info(games)
    pre, final = walk(games, info)
    if not len(pre):
        raise RuntimeError("no finished matches yet")
    d1 = pre[pre["both_d1"] == 1]
    seasons = sorted(d1["season"].unique())
    fit_on = d1[d1["season"].isin(seasons[1:])] if len(seasons) > 1 else d1
    w = fit_logit(design(fit_on), fit_on["home_won"].to_numpy(float))
    pre = pre.assign(p_home=predict(design(pre), w))
    (data / "derived").mkdir(parents=True, exist_ok=True)
    pre.to_csv(data / "derived" / "pregame.csv.gz", index=False,
               compression={"method": "gzip", "mtime": 0})
    store.write_json(data / "derived" / "ratings.json",
                     {str(s): {t: round(v, 3) for t, v in r.items()} for s, r in final.items()}, compact=True)
    model = backtest(pre)
    model["weights"] = {"per_point": round(float(w[0]), 4), "home_conference": round(float(w[1]), 4),
                        "home_other": round(float(w[2]), 4)}
    log(f"ratings: {len(pre):,} matches rated; weights {model['weights']}; "
        f"backtest log loss {model.get('log_loss')} vs {model.get('baseline_log_loss')}, accuracy {model.get('accuracy')}")

    season = max(final)
    today = dt.datetime.now(dt.timezone.utc).date()
    teams, rating = info[season], final[season]
    rows, games_left = simulate(season, games, teams, rating, w, today.isoformat(), np.random.default_rng(season))

    # the coming week, with each side's chance
    g = games[(games["season"] == season) & (games["state"] != "F") & (games["date"] >= today.isoformat())
              & (games["date"] <= (today + dt.timedelta(days=config.UPCOMING_DAYS)).isoformat())]
    upcoming = []
    for r in g.sort_values(["date", "start_epoch", "game_id"]).to_dict("records"):
        h, a = r["home"], r["away"]
        if h not in rating or a not in rating or not (teams[h]["d1"] and teams[a]["d1"]):
            continue
        same = bool(teams[h]["conf"]) and teams[h]["conf"] == teams[a]["conf"] and not r["round"]
        p = float(predict(np.array([[rating[h] - rating[a], float(same), 1.0 - same]]), w)[0])
        upcoming.append({"id": int(r["game_id"]), "date": r["date"],
                         "start": int(r["start_epoch"]) if pd.notna(r["start_epoch"]) else None,
                         "home": teams[h]["name"], "away": teams[a]["name"], "home_id": h, "away_id": a,
                         "conf": teams[h]["conf"] if same else "", "p_home": round(p, 3),
                         "r_home": round(rating[h], 2), "r_away": round(rating[a], 2)})
    store.write_json(out_dir / "odds.json", {
        "season": season, "updated": today.isoformat(), "sims": config.PRED_SIMULATIONS,
        "games_left": games_left, "teams": rows, "upcoming": upcoming, "model": model}, compact=True)
    return {"season": season, "teams": len(rows), "games_left": games_left, "upcoming": len(upcoming),
            "log_loss": model.get("log_loss"), "baseline": model.get("baseline_log_loss"),
            "accuracy": model.get("accuracy")}
