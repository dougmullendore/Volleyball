"""Download whatever matches we do not have yet and add them to the data folder.

The first run downloads every season in config.SEASONS (about 5,500 matches a
season). After that each run only picks up new matches, re-checks the last
few days for stat corrections, and refreshes the schedule of matches still to
be played."""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import pandas as pd

from . import config, ncaa_api, store
from .parse import parse_detail, parse_scoreboard

CHUNK = 400  # matches per checkpoint


def season_days(season: int) -> list[str]:
    d = dt.date(season, *config.SEASON_START)
    end = dt.date(season, *config.SEASON_END)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _replace(old: pd.DataFrame, table: str, new_rows, ids, sort_cols) -> pd.DataFrame:
    new = store.frame(table, new_rows)
    if len(old):
        old = old[~old["game_id"].isin(list(ids))]
        new = pd.concat([old, new], ignore_index=True) if len(new) else old
    return new.sort_values(sort_cols, kind="stable").reset_index(drop=True)


def update_season(data: Path, season: int, manifest: dict, today: dt.date,
                  deadline: float, log, odd: dict) -> dict:
    """Bring one season up to date. Returns a small summary dict."""
    info = manifest.setdefault(str(season), {})
    if info.get("complete"):
        return {"season": season, "skipped": "complete", "matches": info.get("matches", 0)}
    days = season_days(season)
    if days[0] > today.isoformat():
        return {"season": season, "skipped": "not started", "matches": 0}

    games = store.read(data, "games", season)
    settled = set(info.get("settled_days", []))
    cutoff = (today - dt.timedelta(days=config.REFRESH_DAYS)).isoformat()
    want = [d for d in days if d not in settled]

    # ---- 1. the scoreboard for every day not yet settled (results and schedule)
    fresh, got_days = {}, set()
    for day, raw, err in ncaa_api.get_many({d: ncaa_api.scoreboard_url(season, d) for d in want}):
        if err is not None:
            log(f"  scoreboard {day}: download failed: {err!r}")
            continue
        got_days.add(day)
        for c in ((raw or {}).get("data") or {}).get("contests") or []:
            row = parse_scoreboard(c, season)
            if row:
                fresh[row["game_id"]] = row
    old = {int(r["game_id"]): r for r in games.to_dict("records")}
    merged = {}
    for gid, r in old.items():
        if r["date"] in got_days and gid not in fresh and not (r["detail"] or 0):
            continue                      # dropped from the schedule
        merged[gid] = r
    for gid, r in fresh.items():
        if gid in merged and (merged[gid]["detail"] or 0) > 0 and r["state"] == "F":
            continue                      # already have the full version
        if gid in merged and (merged[gid]["detail"] or 0) > 0:
            r = {**merged[gid], "state": r["state"]}
        merged[gid] = r
    games = store.frame("games", list(merged.values())).sort_values(["date", "game_id"]).reset_index(drop=True)
    store.write(data, "games", season, games)

    # ---- 2. box score and play-by-play for finished matches
    recheck = (today - dt.timedelta(days=14)).isoformat()
    final = games[games["state"] == "F"]
    need = final[(final["detail"].fillna(0) == 0) | (final["date"] >= cutoff)
                 | ((final["detail"] == 2) & (final["date"] >= recheck))]
    need_ids = [int(x) for x in need["game_id"]]
    basics = {int(r["game_id"]): r for r in need.to_dict("records")}
    log(f"season {season}: {len(games)} matches listed, {len(final)} final, {len(need_ids)} to download")

    box = store.read(data, "box", season) if need_ids else None
    rallies = store.read(data, "rallies", season) if need_ids else None
    done, failed, timed_out = 0, 0, False
    for i in range(0, len(need_ids), CHUNK):
        if time.time() > deadline:
            timed_out = True
            log(f"season {season}: out of time, stopping after {done} matches")
            break
        chunk = need_ids[i:i + CHUNK]
        urls = {}
        for gid in chunk:
            urls[(gid, "game")] = ncaa_api.game_url(gid)
            urls[(gid, "box")] = ncaa_api.box_url(gid)
            urls[(gid, "pbp")] = ncaa_api.pbp_url(gid)
        raw, bad = {}, set()
        for (gid, kind), body, err in ncaa_api.get_many(urls):
            if err is not None and kind == "game":
                bad.add(gid)
            raw[(gid, kind)] = body
        g_rows, b_rows, r_rows, got = [], [], [], set()
        for gid in chunk:
            if gid in bad:
                failed += 1
                continue
            try:
                g, b, r, o = parse_detail(basics[gid], raw.get((gid, "game")), raw.get((gid, "box")), raw.get((gid, "pbp")))
            except Exception as ex:
                failed += 1
                log(f"  match {gid}: could not parse: {ex!r}")
                continue
            for k, v in o.items():
                odd[k] = odd.get(k, 0) + v
            g_rows.append(g); b_rows.extend(b); r_rows.extend(r); got.add(gid)
        games = _replace(games, "games", g_rows, got, ["date", "game_id"])
        box = _replace(box, "box", b_rows, got, ["game_id", "is_home", "row"])
        rallies = _replace(rallies, "rallies", r_rows, got, ["game_id", "set", "n"])
        store.write(data, "games", season, games)
        store.write(data, "box", season, box)
        store.write(data, "rallies", season, rallies)
        done += len(got)
        log(f"  season {season}: {done}/{len(need_ids)} downloaded, {len(rallies):,} points stored")

    # ---- 3. bookkeeping: a day is settled once it is a week old and nothing on it is pending
    final = games[games["state"] == "F"]
    waiting = set(final[final["detail"].fillna(0) == 0]["date"])
    week_ago = (today - dt.timedelta(days=7)).isoformat()
    for d in got_days:
        if d < week_ago and d not in waiting:
            settled.add(d)
    info["settled_days"] = sorted(settled)
    info["matches"] = int(len(final))
    info["with_box"] = int((final["detail"] == 1).sum())
    info["with_points"] = int((final["pbp_sets"].fillna(0) > 0).sum())
    season_over = today > dt.date(season, *config.SEASON_END) + dt.timedelta(days=10)
    info["complete"] = bool(season_over and not timed_out and not failed and not waiting
                            and settled >= set(days) and len(final) > 0)
    return {"season": season, "matches": info["matches"], "downloaded": done, "failed": failed,
            "with_box": info["with_box"], "with_points": info["with_points"],
            "complete": info["complete"], "timed_out": timed_out}


def update_all(data: Path, log, max_minutes: float = 150.0) -> dict:
    data = Path(data)
    manifest = store.read_json(data / "manifest.json", {})
    today = dt.datetime.now(dt.timezone.utc).date()
    deadline = time.time() + max_minutes * 60
    odd, out = {}, []
    # newest season first, so the current season is usable even if time runs out
    for season in reversed(config.SEASONS):
        try:
            out.append(update_season(data, season, manifest, today, deadline, log, odd))
        finally:
            store.write_json(data / "manifest.json", manifest)
    top = dict(sorted(odd.items(), key=lambda kv: -kv[1])[:150])
    if top:
        store.write_json(data / "logs" / "oddities.json", top)
    return {"seasons": out, "oddities": dict(list(top.items())[:8])}
