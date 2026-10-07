"""Player value: points added, then wins above replacement.

Everything is built from the official box score, in points:

  Attack     kills minus errors, compared with what an average player at the
             same position would do with the same number of swings
  Serve      aces minus service errors, compared with average on the same
             number of serves
  Receive    reception errors avoided, compared with average on the same
             number of serve receptions
  Block      the team's blocks beyond what an average team gets against the
             same number of opposing swings, shared out by who made the
             blocks (a solo counts one, an assist a half), minus blocking
             errors
  Dig        the team's digs beyond what an average team gets on the same
             number of opposing attacks, shared out by who made the digs, at
             a fraction of a point each (a dug ball keeps the rally alive;
             it does not win it)
  Set        a setter's share of her hitters' attack value, plus ball
             handling errors for everyone

The parts are then scaled so that a team's players add up to the team's
actual point margin, adjusted for the strength of the opponents faced, and
compared with what bench players produce in the same playing time (the
replacement level). Points become wins at the rate seen in team results
across Division I: the season point margin that goes with one extra win.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

PARTS = ["att", "srv", "rec", "blk", "dig", "set"]
POS_LABEL = {"S": "S", "OH": "OH", "MB": "MB", "L": "L/DS"}
POS_WORD = {"S": "setters", "OH": "outside and opposite hitters", "MB": "middle blockers", "L": "liberos and defensive specialists"}
# Players beyond these, by sets played at their position on their team, are
# the bench: the pool that defines replacement level.
REGULARS = {"S": 1, "OH": 3, "MB": 2, "L": 2}
CARD_METRICS = ["war", "att", "srv", "rec", "blk", "dig", "set",
                "k_set", "hit", "ace_set", "d_set", "blk_set", "ast_set", "re_pct"]

CONF_NAMES = {
    "acc": "ACC", "big-ten": "Big Ten", "big-12": "Big 12", "sec": "SEC", "pac-12": "Pac-12",
    "big-east": "Big East", "american": "American", "atlantic-10": "Atlantic 10", "wcc": "West Coast",
    "mountain-west": "Mountain West", "big-west": "Big West", "mvc": "Missouri Valley", "mac": "MAC",
    "sun-belt": "Sun Belt", "cusa": "Conference USA", "caa": "CAA", "ivy-league": "Ivy League",
    "big-sky": "Big Sky", "horizon": "Horizon", "southland": "Southland", "swac": "SWAC", "meac": "MEAC",
    "socon": "Southern", "ovc": "Ohio Valley", "asun": "ASUN", "summit-league": "Summit League",
    "big-south": "Big South", "nec": "Northeast", "america-east": "America East", "patriot": "Patriot",
    "metro": "MAAC", "maac": "MAAC", "wac": "WAC", "uac-": "United Athletic", "uac": "United Athletic",
    "independent": "Independent", "di-independent": "Independent",
}


def conference_name(seo: str) -> str:
    return CONF_NAMES.get(seo) or seo.replace("-", " ").strip().title()


def _r(v, nd=2):
    if v is None or pd.isna(v):
        return None
    v = float(v)
    return round(v, nd) if np.isfinite(v) else None


class Scale:
    """Collects every season, then puts all players on one scale."""

    def __init__(self):
        self.seasons = {}          # season -> player frame
        self.team_rows = []        # one per team-season: wins, losses, point margin
        self.points_per_win = config.VALUE_POINTS_PER_WIN
        self.replacement = {}
        self.credit_scale = 1.0
        self.team_check = None

    # ------------------------------------------------------------ gather --
    def add_season(self, season, p, games, box, teams, d1, rating):
        if not len(p):
            return
        p = p.copy()
        # what each team's opponents did: the chances its blockers and diggers had
        tb = box[box["sets"] > 0].groupby(["game_id", "team"])[["k", "e", "ta"]].sum().reset_index()
        tb = tb.merge(games[["game_id", "home", "away"]], on="game_id")
        tb["opp"] = np.where(tb["team"] == tb["home"], tb["away"], tb["home"])
        faced = tb.groupby("opp")[["k", "e", "ta"]].sum()
        faced = faced[faced.index.isin(d1)]
        own = p.groupby("team").agg(d=("d", "sum"), bs=("bs", "sum"), ba=("ba", "sum"))
        own["blk"] = own["bs"] + own["ba"] / 2
        own = own.join(faced.add_prefix("o_")).fillna(0)
        dig_chances = (own["o_ta"] - own["o_e"]).clip(lower=0)
        lg_dig = own["d"].sum() / max(1, dig_chances.sum())
        lg_blk = own["blk"].sum() / max(1, own["o_ta"].sum())
        own["dig_plus"] = own["d"] - lg_dig * dig_chances          # digs beyond an average team's
        own["blk_plus"] = own["blk"] - lg_blk * own["o_ta"]         # blocks beyond an average team's

        blk_pts = p["bs"] + p["ba"] / 2
        all_srv = (p["sa"] - p["se"]).sum() / max(1, p["sv"].sum())
        all_re = p["re"].sum() / max(1, p["ra"].sum())
        for part in PARTS:
            p[part] = 0.0
        for g, grp in p.groupby("pos"):
            i = grp.index
            sets = max(1, grp["sets"].sum())
            eff = (grp["k"] - grp["e"]).sum() / max(1, grp["ta"].sum())
            p.loc[i, "att"] = (grp["k"] - grp["e"]) - grp["ta"] * eff
            p.loc[i, "set"] = -(grp["bhe"] - grp["sets"] * (grp["bhe"].sum() / sets))
        p["srv"] = (p["sa"] - p["se"]) - p["sv"] * all_srv
        p["rec"] = -(p["re"] - p["ra"] * all_re)
        # blocking and digging: the team's total beyond average for the attacks it
        # faced, shared out by who made the blocks and digs
        t_blk = p["team"].map(own["blk"]).clip(lower=1)
        t_dig = p["team"].map(own["d"]).clip(lower=1)
        p["blk"] = p["team"].map(own["blk_plus"]).fillna(0) * blk_pts / t_blk - p["be"]
        p["dig"] = config.VALUE_DIG * p["team"].map(own["dig_plus"]).fillna(0) * p["d"] / t_dig
        # a setter gets a share of what her hitters did with her sets
        share = config.VALUE_SETTER_SHARE
        team_att = p.groupby("team")["att"].transform("sum")
        team_ast = p.groupby("team")["ast"].transform("sum").clip(lower=1)
        p["set"] += share * team_att * p["ast"] / team_ast
        p["att"] *= (1 - share)

        # Playing time. The box score only says which sets a player appeared in, so
        # a serving substitute and a six-rotation hitter look the same. Count a set
        # as a full one only if she touched the ball as often as a regular at her
        # position does; otherwise it counts as a fraction.
        touches = p["ta"] + p["ra"] + p["d"] + p["sv"] + p["bs"] + p["ba"] + p["ast"]
        per_set = touches / p["sets"].clip(lower=1)
        p["fse"] = 0.0
        for g, grp in p.groupby("pos"):
            rank = grp.groupby("team")["sets"].rank(method="first", ascending=False)
            regulars = per_set[grp.index][(rank <= REGULARS[g]) & (grp["sets"] >= 10)]
            typical = regulars.median() if len(regulars) >= 20 else per_set[grp.index].median()
            p.loc[grp.index, "fse"] = grp["sets"] * (per_set[grp.index] / max(typical, 1e-9)).clip(upper=1.0)

        # strength of schedule, in points: each match's opponent rating times the
        # sets played, shared out by how much of the match each player played
        b = box[box["team"].isin(d1) & (box["sets"] > 0) & box["pid"].notna()].merge(games[["game_id", "home", "away"]], on="game_id")
        opp = np.where(b["team"] == b["home"], b["away"], b["home"])
        b["opp_r"] = [rating.get(o, 2 * config.RATING_NEW_TEAM) for o in opp]
        team_sets = b.groupby(["game_id", "team"])["sets"].transform("max")
        b["w"] = b["sets"] * b["pid"].map(p["fse"] / p["sets"].clip(lower=1)).fillna(0.0)
        sum_w = b.groupby(["game_id", "team"])["w"].transform("sum").clip(lower=1e-9)
        b["sched"] = b["opp_r"] * team_sets * b["w"] / sum_w
        p["sched"] = b.groupby("pid")["sched"].sum().reindex(p.index).fillna(0.0)
        p["season"] = season
        self.seasons[season] = p

        from .aggregate import team_long
        tl = team_long(games)
        t = tl[tl["team"].isin(d1)].groupby("team").agg(w=("won", "sum"), gp=("won", "size"), pf=("pf", "sum"), pa=("pa", "sum"))
        # only matches that have a box score count toward the check of player credit
        boxed = set(box["game_id"].unique())
        tb = tl[tl["team"].isin(d1) & tl["game_id"].isin(boxed)].groupby("team").agg(bpf=("pf", "sum"), bpa=("pa", "sum"))
        t = t.join(tb).fillna(0)
        t["season"] = season
        t["paa"] = p.groupby("team")[PARTS].sum().sum(axis=1).reindex(t.index).fillna(0.0)
        t["sched"] = p.groupby("team")["sched"].sum().reindex(t.index).fillna(0.0)
        t["rating"] = [rating.get(x, np.nan) for x in t.index]
        self.team_rows.append(t.reset_index())

    # ------------------------------------------------------------- scale --
    def finish(self, per_point_weight=None):
        if not self.seasons:
            return
        teams = pd.concat(self.team_rows, ignore_index=True)
        full = teams[teams["gp"] >= 15]
        if len(full) >= 30:
            # points per win: how much season point margin goes with one extra win
            x = (full["pf"] - full["pa"]).to_numpy(float)
            y = (full["w"] - (full["gp"] - full["w"])).to_numpy(float) / 2
            slope = float((x * y).sum() / max(1e-9, (x * x).sum()))
            if slope > 0:
                self.points_per_win = 1.0 / slope
            # player credit should add up to the team's real margin
            m = (full["bpf"] - full["bpa"]).to_numpy(float)
            c = full["paa"].to_numpy(float)
            if (c * c).sum() > 0:
                self.credit_scale = float(np.clip((c * m).sum() / (c * c).sum(), 0.5, 3.0))
        for p in self.seasons.values():
            for part in PARTS:
                p[part] *= self.credit_scale
            p["paa"] = p[PARTS].sum(axis=1) + p["sched"]

        # replacement level, per set, from the bench of every finished season
        done = sorted(self.seasons)[:-1] or sorted(self.seasons)
        pool = {g: [0.0, 0.0] for g in REGULARS}
        for s in self.seasons:
            p = self.seasons[s]
            rank = p.groupby(["team", "pos"])["fse"].rank(method="first", ascending=False)
            p["regular"] = [r <= REGULARS[g] for r, g in zip(rank, p["pos"])]
            if s in done:
                bench = p[~p["regular"] & (p["fse"] >= 3)]
                for g, grp in bench.groupby("pos"):
                    pool[g][0] += grp["paa"].sum(); pool[g][1] += grp["fse"].sum()
        self.replacement = {g: (v[0] / v[1] if v[1] > 0 else 0.0) for g, v in pool.items()}
        for p in self.seasons.values():
            p["par"] = p["paa"] - p["fse"] * p["pos"].map(self.replacement)
            p["war"] = p["par"] / self.points_per_win
            p["war100"] = np.where(p["sets"] > 0, 100 * p["war"] / p["sets"].clip(lower=1), np.nan)

        # check: do a team's players add up to its results?
        chk = []
        for s, p in self.seasons.items():
            t = teams[(teams["season"] == s) & (teams["gp"] >= 15)].set_index("team")
            t = t.assign(war=p.groupby("team")["war"].sum().reindex(t.index))
            chk.append(t)
        chk = pd.concat(chk).dropna(subset=["war"])
        if len(chk) >= 30:
            wins_pct = chk["w"] / chk["gp"]
            done_seasons = sorted(self.seasons)[:-1] or sorted(self.seasons)
            full_chk = chk[chk["season"].isin(done_seasons)]
            self.team_check = {
                "team_seasons": int(len(chk)),
                # what a team made only of replacement players would be expected to win
                "replacement_win_pct": _r(0.5 - float(full_chk["war"].sum()) / max(1.0, float(full_chk["gp"].sum())), 3),
                "corr_win_pct": _r(float(np.corrcoef(chk["war"], wins_pct)[0, 1]), 3),
                "corr_rating": _r(float(np.corrcoef(chk["war"], chk["rating"].fillna(0))[0, 1]), 3),
                "credit_scale": _r(self.credit_scale, 2),
            }

    def replacement_out(self):
        return {POS_LABEL[g]: _r(v, 3) for g, v in self.replacement.items()}

    # ------------------------------------------------------------ output --
    def war_table(self, season, teams):
        p = self.seasons[season]
        cols = ["id", "name", "team", "team_id", "conf", "pos", "mp", "sp", "war", "war100",
                "att", "srv", "rec", "blk", "dig", "set", "sched", "paa", "par"]
        rows = []
        for pid, r in p.iterrows():
            rows.append([pid, r["name"], teams[r["team"]]["name"], r["team"], teams[r["team"]]["conf"],
                         POS_LABEL[r["pos"]], int(r["mp"]), int(r["sets"]), _r(r["war"]), _r(r["war100"]),
                         _r(r["att"], 1), _r(r["srv"], 1), _r(r["rec"], 1), _r(r["blk"], 1), _r(r["dig"], 1),
                         _r(r["set"], 1), _r(r["sched"], 1), _r(r["paa"], 1), _r(r["par"], 1)])
        return {"cols": cols, "rows": rows}

    def season_summary(self, season):
        p = self.seasons[season]
        top = p["war"].idxmax()
        return {"total": _r(p["war"].sum(), 0), "players": int(len(p)),
                "top": {"name": p.at[top, "name"], "war": _r(p.at[top, "war"])}}

    def _card_values(self, p):
        """Per-player rates behind the card, and which ones each player qualifies for."""
        s = p["sets"].clip(lower=1)
        v = pd.DataFrame(index=p.index)
        v["war"] = 100 * p["war"] / s
        for part in PARTS:
            v[part] = 100 * p[part] / s
        v["k_set"] = p["k"] / s
        v["hit"] = np.where(p["ta"] > 0, (p["k"] - p["e"]) / p["ta"].clip(lower=1), np.nan)
        v["ace_set"] = p["sa"] / s
        v["d_set"] = p["d"] / s
        v["blk_set"] = (p["bs"] + p["ba"] / 2) / s
        v["ast_set"] = p["ast"] / s
        v["re_pct"] = np.where(p["ra"] > 0, 100 * p["re"] / p["ra"].clip(lower=1), np.nan)
        hits = p["ta"] / s >= 1.0
        passes = p["ra"] / s >= 0.75
        serves = p["sv"] / s >= 1.0
        front = p["pos"].isin(["OH", "MB", "S"])
        setter = p["pos"] == "S"
        ok = pd.DataFrame(True, index=p.index, columns=CARD_METRICS)
        for m in ("att", "k_set", "hit"):
            ok[m] = hits
        for m in ("rec", "re_pct"):
            ok[m] = passes
        for m in ("srv", "ace_set"):
            ok[m] = serves
        for m in ("blk", "blk_set"):
            ok[m] = front
        for m in ("set", "ast_set"):
            ok[m] = setter
        return v[CARD_METRICS], ok

    def cards(self, info, shown=None):
        """{team: card document} with every player's seasons and percentiles.
        Percentiles are always against all of Division I; `shown` only limits
        which teams' cards are written ({season: {"teams": {...}}})."""
        out = {}
        for season, p in self.seasons.items():
            v, ok = self._card_values(p)
            regular = p["sets"] >= 0.35 * p["sets"].quantile(0.98)
            pct = pd.DataFrame(np.nan, index=p.index, columns=CARD_METRICS)
            for g in REGULARS:
                in_pos = p["pos"] == g
                for m in CARD_METRICS:
                    pool = in_pos & regular & ok[m] & v[m].notna()
                    if pool.sum() < 20:
                        continue
                    ranks = v.loc[pool, m].rank(pct=True, ascending=(m != "re_pct"))
                    pct.loc[pool, m] = (ranks * 100).round().clip(1, 99)
            teams = info.get(season, {})
            keep = (shown or {}).get(season, {}).get("teams") if shown else None
            for pid, r in p.iterrows():
                if keep is not None and r["team"] not in keep:
                    continue
                doc = out.setdefault(r["team"], {"team": teams.get(r["team"], {}).get("name", r["team"]),
                                                 "metrics": CARD_METRICS, "players": {}})
                doc["team"] = teams.get(r["team"], {}).get("name", doc["team"])
                pl = doc["players"].setdefault(pid, {"n": r["name"], "y": {}})
                pl["n"], pl["p"] = r["name"], POS_LABEL[r["pos"]]
                if pd.notna(r["number"]):
                    pl["num"] = int(r["number"])
                pl["y"][str(season)] = {
                    "p": POS_LABEL[r["pos"]], "mp": int(r["mp"]), "sp": int(r["sets"]),
                    "k": int(r["k"]), "e": int(r["e"]), "ta": int(r["ta"]), "ast": int(r["ast"]),
                    "sa": int(r["sa"]), "d": int(r["d"]), "blk": _r(r["bs"] + r["ba"] / 2, 1),
                    "war": _r(r["war"]), "conf": teams.get(r["team"], {}).get("conf", ""),
                    "v": [_r(x, 3) for x in v.loc[pid]],
                    "pc": [None if pd.isna(x) else int(x) for x in pct.loc[pid]],
                }
        return out

    def player_index(self, info, shown=None):
        """Everyone with a card, for the search box."""
        best = {}
        for season in sorted(self.seasons):
            p = self.seasons[season]
            teams = info.get(season, {})
            keep = (shown or {}).get(season, {}).get("teams") if shown else None
            for pid, r in p[p["sets"] >= 5].iterrows():
                if keep is not None and r["team"] not in keep:
                    continue
                best[pid] = [pid, r["name"], teams.get(r["team"], {}).get("name", r["team"]), POS_LABEL[r["pos"]],
                             season, _r(r["war"])]
        return {"cols": ["id", "name", "team", "pos", "season", "war"], "rows": list(best.values())}
