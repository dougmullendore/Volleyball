"""The scheduled job. It keeps two things up to date and builds the page:

  1. the coaches poll (looked for on Mondays; see poll.why_check)
  2. the season's scoreboard: every match, played or still to come

Usage:  python -m pipeline.run <state_dir> <site_output_dir>

<state_dir> is the repository's `state` branch:
  polls.json        every poll seen, by the date it runs through
  scoreboard.json   the latest copy of each day's matches
  status.json       what happened on the last run
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import traceback
from pathlib import Path

from . import config, poll, web

SITE_SRC = Path(__file__).resolve().parents[1] / "site"


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def read_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, obj, indent=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=indent, separators=None if indent else (",", ":"), allow_nan=False))


def season_for(day: dt.date) -> int:
    """A season is named by the year it is played in. Before mid-August the
    newest season is last year's."""
    return day.year if (day.month, day.day) >= config.SEASON_START else day.year - 1


def season_days(season: int) -> list[str]:
    d, end = dt.date(season, *config.SEASON_START), dt.date(season, *config.SEASON_END)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def parse_contest(c: dict) -> dict | None:
    """One match from a day's scoreboard, or None if it is unusable."""
    teams = c.get("teams") or []
    home = next((t for t in teams if t.get("isHome")), None)
    away = next((t for t in teams if not t.get("isHome")), None)
    if not home or not away or not c.get("contestId") or not home.get("seoname") or not away.get("seoname"):
        return None
    try:
        m, d, y = (c.get("startDate") or "").split("/")
        date = dt.date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None
    state = {"F": "final", "P": "upcoming", "I": "live"}.get(c.get("gameState"), "other")

    def side(t):
        score = t.get("score")
        return {"id": t["seoname"], "name": t.get("nameShort") or t["seoname"],
                "sets": int(score) if state != "upcoming" and str(score).isdigit() else None}

    return {"id": int(c["contestId"]), "date": date,
            "start": int(c["startTimeEpoch"]) if c.get("hasStartTime") and c.get("startTimeEpoch") else None,
            "state": state, "note": "" if state != "other" else (c.get("statusCodeDisplay") or c.get("finalMessage") or "").strip(),
            "round": (c.get("roundDescription") or "") if c.get("isChampionship") else "",
            "away": side(away), "home": side(home)}


# ----------------------------------------------------------------- stages --
def update_poll(state: Path, now: dt.datetime, forced: bool) -> dict:
    polls = read_json(state / "polls.json", {})
    why = poll.why_check(polls, now, forced)
    if not why:
        return {"checked": False, "newest": max(polls)}
    page = web.get_bytes(config.POLL_URL).decode("utf-8", "replace")
    found = poll.parse_page(page)
    if len(found["rows"]) < config.POLL_SIZE or not found["through"]:
        raise RuntimeError(f"the poll page did not read cleanly: {len(found['rows'])} rows, dated {found['through']}")
    is_new = found["through"] not in polls
    polls[found["through"]] = found["rows"]
    write_json(state / "polls.json", dict(sorted(polls.items())), indent=0)
    log(f"poll: looked because {why}; found the poll through {found['through']}" + (" (new)" if is_new else " (already had it)"))
    return {"checked": True, "why": why, "found": found["through"], "new": is_new, "newest": max(polls)}


def update_scoreboard(state: Path, season: int) -> dict:
    stored = read_json(state / "scoreboard.json", {})
    if stored.get("season") != season:
        stored = {"season": season, "days": {}}
    days = season_days(season)
    failed = []
    for date, contests, err in web.get_days(season, days):
        if err is not None:
            failed.append(date)      # keep the copy already stored for that day
            continue
        stored["days"][date] = [g for g in (parse_contest(c) for c in contests) if g]
    if len(failed) == len(days):
        raise RuntimeError("the scoreboard could not be reached for any day")
    write_json(state / "scoreboard.json", stored)
    n = sum(len(v) for v in stored["days"].values())
    log(f"scoreboard: {len(days) - len(failed)} of {len(days)} days read, {n:,} matches in season {season}"
        + (f"; kept the old copy of {len(failed)} days" if failed else ""))
    return {"season": season, "days": len(days), "days_failed": len(failed), "matches": n}


def build_site(state: Path, out: Path, now: dt.datetime) -> dict:
    polls = read_json(state / "polls.json", {})
    board = read_json(state / "scoreboard.json", {})
    if not polls or not board.get("days"):
        raise RuntimeError("nothing to build yet: " + ("no poll" if not polls else "no scoreboard"))
    through = max(polls)
    games = {}
    for day in board["days"].values():
        for g in day:
            games[g["id"]] = g      # a match moved to another day is listed once, on its newest day
    names = {}
    for g in games.values():
        for s in (g["away"], g["home"]):
            names[s["id"]] = s["name"]
    ranked, unmatched = [], []
    for r in sorted(polls[through], key=lambda r: r["rank"])[:config.POLL_SIZE]:
        tid = poll.match_school(r["school"], names)
        if not tid:
            unmatched.append(r["school"])
        ranked.append({"rank": r["rank"], "id": tid, "name": names.get(tid, r["school"]), "record": r.get("record"),
                       "prev": r.get("prev"), "points": r.get("points"), "votes": r.get("votes") or 0})
    rank = {t["id"]: t["rank"] for t in ranked if t["id"]}
    listed = sorted((g for g in games.values() if g["away"]["id"] in rank or g["home"]["id"] in rank),
                    key=lambda g: (g["date"], g["start"] or 0, g["id"]))
    for g in listed:
        for s in (g["away"], g["home"]):
            s["rank"] = rank.get(s["id"])
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE_SRC, out)
    write_json(out / "data.json", {
        "site": config.SITE_NAME, "updated": now.isoformat(timespec="seconds"), "season": board["season"],
        "poll": {"name": config.POLL_NAME, "through": through, "teams": ranked, "polls_seen": len(polls)},
        "game_page": config.GAME_PAGE, "games": listed})
    (out / ".nojekyll").write_text("")
    log(f"site: poll through {through}, {len(listed)} matches listed for {len(rank)} ranked teams"
        + (f"; NOT MATCHED to a scoreboard team: {unmatched}" if unmatched else ""))
    return {"poll_through": through, "matches_listed": len(listed), "teams_matched": len(rank), "unmatched": unmatched}


def main(state_dir: str, out_dir: str) -> int:
    state, out = Path(state_dir), Path(out_dir)
    state.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    status = {"started_utc": now.isoformat(timespec="seconds"),
              "commit": os.environ.get("GITHUB_SHA", "local")[:12], "stages": {}}
    offline = os.environ.get("SKIP_FETCH") == "1"       # rebuild the page from what is stored

    def stage(name, fn):
        try:
            status["stages"][name] = {"ok": True, "result": fn()}
        except Exception as e:
            log(f"STAGE {name} FAILED: {e!r}")
            traceback.print_exc()
            status["stages"][name] = {"ok": False, "error": repr(e)}
        write_json(state / "status.json", status, indent=1)

    if not offline:
        # a failed look at the poll or the scoreboard leaves the stored copy in use
        stage("poll", lambda: update_poll(state, now, os.environ.get("CHECK_POLL") == "1"))
        stage("scoreboard", lambda: update_scoreboard(state, season_for(now.date())))
    stage("site", lambda: build_site(state, out, now))
    status["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    status["ok"] = all(s["ok"] for s in status["stages"].values())
    write_json(state / "status.json", status, indent=1)
    log("run finished: " + ("OK" if status["ok"] else "WITH ERRORS"))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
