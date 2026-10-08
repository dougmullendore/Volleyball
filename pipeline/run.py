"""The scheduled job. It keeps two things up to date and builds the page:

  1. the coaches poll (looked for on Mondays; see poll.why_check)
  2. the season's scoreboard: every match, played or still to come
  3. where to watch each of the ranked teams' matches in the next two weeks
  4. the box scores behind the player ratings

Usage:  python -m pipeline.run <state_dir> <site_output_dir>

<state_dir> is the repository's `state` branch:
  polls.json        every poll seen, by the date it runs through
  scoreboard.json   the latest copy of each day's matches
  watch.json        the TV channel for each upcoming match, and ESPN's id for each match
  box.json          the box score of every finished match involving a ranked team
  photos.json       the address of each player's photo on her school's roster page
  ratings.json      every team's rating, this season and last (behind the odds)
  status.json       what happened on the last run
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import traceback
from pathlib import Path

from . import box, config, goat, odds, photos, players, poll, teams, watch, web

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


def update_scoreboard(state: Path, season: int, only: list[str] | None = None) -> dict:
    stored = read_json(state / "scoreboard.json", {})
    if stored.get("season") != season:
        stored = {"season": season, "days": {}}
    days = only or season_days(season)
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


def ranked_matches(state: Path) -> dict:
    """The newest poll joined to the scoreboard: the ranked teams and every
    match any of them plays."""
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
    every = sorted(games.values(), key=lambda g: (g["date"], g["start"] or 0, g["id"]))
    for g in every:
        for s in (g["away"], g["home"]):
            s["rank"] = rank.get(s["id"])
    listed = [g for g in every if g["away"]["id"] in rank or g["home"]["id"] in rank]
    # Division I: the scoreboard also lists the odd match against a school from
    # another division; those schools play only a match or two, so a team counts
    # once it has played a fair share of what a typical team has.
    count = {}
    for g in every:
        for s in (g["away"], g["home"]):
            count[s["id"]] = count.get(s["id"], 0) + 1
    typical = sorted(n for n in count.values() if n >= 3)
    need = max(2, 0.4 * typical[len(typical) // 2]) if typical else 1
    d1 = sorted(({"id": t, "name": names[t], "rank": rank.get(t)} for t, n in count.items() if n >= need or t in rank),
                key=lambda t: (t["rank"] is None, t["rank"] or 0, t["name"]))
    return {"through": through, "polls_seen": len(polls), "season": board["season"], "teams": ranked,
            "games": listed, "all_games": every, "d1_teams": d1, "names": names, "unmatched": unmatched}


def update_watch(state: Path, now: dt.datetime) -> dict:
    """Look up the channel for each match in the next two weeks.
    A channel found on an earlier night is kept if tonight's look finds nothing."""
    sel = ranked_matches(state)
    lo = (now - dt.timedelta(days=1)).timestamp()
    hi = (now + dt.timedelta(days=config.WATCH_DAYS)).timestamp()
    soon = [g for g in sel["all_games"] if g["state"] != "final" and g["start"] and lo <= g["start"] <= hi]
    listings, failed = watch.fetch_listings(now.date(), log)
    found = watch.assign(soon, listings, sel["names"])
    stored = read_json(state / "watch.json", {})
    keep = {str(g["id"]) for g in sel["all_games"]}
    stored = {k: v for k, v in stored.items() if k in keep}           # matches no longer listed are dropped
    # Finished matches keep ESPN's id: the match page reads the set scores with it.
    # Matches played before ESPN's id was kept are looked up once, a day's listings at a time.
    past = [g for g in sel["all_games"] if g["state"] == "final" and not (stored.get(str(g["id"])) or {}).get("espn")
            and str(g["id"]) not in stored]
    if past:
        days = sorted({dt.date.fromisoformat(g["date"]) for g in past})
        older, _ = watch.espn_days(days)
        for gid, w in watch.assign(past, older, sel["names"]).items():
            if w.get("espn"):
                stored[str(gid)] = {"channels": [], "espn": w["espn"], "flip": w["flip"], "neutral": w["neutral"]}
        for g in past:
            stored.setdefault(str(g["id"]), {"channels": [], "espn": None, "flip": False, "neutral": False})   # looked: none
    for g in soon:
        old = stored.get(str(g["id"])) or {}
        if isinstance(old, list):                    # the first version stored only the channels
            old = {"channels": old}
        new = found.get(g["id"]) or {}
        stored[str(g["id"])] = {"channels": new.get("channels") or old.get("channels") or [],
                                "espn": new.get("espn") or old.get("espn"),
                                "flip": new["flip"] if new.get("espn") else bool(old.get("flip")),
                                "neutral": new["neutral"] if new.get("espn") else bool(old.get("neutral"))}
    write_json(state / "watch.json", stored, indent=0)
    have = sum(1 for g in soon if stored[str(g["id"])]["channels"])
    followable = sum(1 for g in soon if stored[str(g["id"])]["espn"])
    log(f"watch: {len(listings):,} listings read; a channel for {have} of {len(soon)} matches in the next {config.WATCH_DAYS} days"
        + (f"; could not read: {failed}" if failed else ""))
    if failed and not listings:
        raise RuntimeError("no TV listings could be read: " + "; ".join(failed)[:300])
    return {"matches_soon": len(soon), "with_channel": have, "with_live_score": followable, "listings": len(listings), "failed": failed}


def update_boxes(state: Path, now: dt.datetime) -> dict:
    """Fetch the box scores the player ratings need. When a new team enters
    the poll, its earlier matches are fetched on the next run."""
    sel = ranked_matches(state)
    stored = read_json(state / "box.json", {})
    finals = [g for g in sel["all_games"] if g["state"] == "final"]
    res = box.update(stored, finals, now.date(), log)
    start = dt.date(sel["season"], *config.SEASON_START).isoformat()
    for gid in [k for k, v in stored.items() if v.get("date", "") < start]:
        del stored[gid]                         # earlier seasons' box scores are not used again
    write_json(state / "box.json", stored)
    return res


def update_photos(state: Path, now: dt.datetime) -> dict:
    """Find each player's photo on her school's roster page."""
    sel = ranked_matches(state)
    rated = players.compute(sel["d1_teams"], sel["all_games"], read_json(state / "box.json", {}))
    teams = {}
    for p in rated["players"]:
        teams.setdefault(p["team_id"], {})[p["id"]] = p["name"]
    stored = read_json(state / "photos.json", {})
    res = photos.update(stored, teams, now.date(), lambda url: web.get_bytes(url).decode("utf-8", "replace"), log,
                        ranked={t["id"] for t in sel["teams"] if t["id"]})
    write_json(state / "photos.json", stored, indent=0)
    return res


def live_now(state: Path, now: dt.datetime) -> list[str]:
    """The scoreboard days to read again on a match-night run: those with a
    Division I match that has started in the last five hours, or starts in
    the next twenty minutes, and is not known to be over with its box score in.
    Empty when there is nothing to do."""
    try:
        sel = ranked_matches(state)
    except RuntimeError:
        return []
    boxes = read_json(state / "box.json", {})
    t = now.timestamp()
    days = set()
    for g in sel["all_games"]:
        if not g.get("start") or not (t - 5 * 3600 <= g["start"] <= t + 20 * 60):
            continue
        done = g["state"] == "final" and (boxes.get(str(g["id"])) or {}).get("status") == "F"
        if not done:
            days.add(g["date"])
    return sorted(days)


def update_live_boxes(state: Path, now: dt.datetime) -> dict:
    """Box scores of matches under way, or finished in the last
    five hours without a final box score yet."""
    sel = ranked_matches(state)
    stored = read_json(state / "box.json", {})
    t = now.timestamp()
    games = [g for g in sel["all_games"] if g.get("start") and t - 5 * 3600 <= g["start"] <= t
             and (g["state"] == "live" or (g["state"] == "final" and (stored.get(str(g["id"])) or {}).get("status") != "F"))]
    res = box.update_live(stored, games, log)
    write_json(state / "box.json", stored)
    return res


def match_files(out: Path, listed: list[dict], boxes: dict, rated: dict) -> int:
    """One small file per match with a box score, for the match page:
    match/<id>.json with both teams' players (linked to their cards when rated)
    and each team's attack set by set."""
    ids = {p["id"] for p in rated["players"]}
    by_number = {}
    for p in rated["players"]:
        if p.get("num") is not None:
            by_number[(p["team_id"], p["num"], players._norm(p["name"].split()[-1]))] = p["id"]
    photo = {p["id"]: p.get("photo") for p in rated["players"] if p.get("photo")}
    (out / "match").mkdir(exist_ok=True)
    n = 0
    for g in listed:
        b = boxes.get(str(g["id"]))
        if not b or not (b.get("home") or b.get("away")):
            continue
        doc = {"id": g["id"], "status": b.get("status", ""), "tsets": b.get("tsets") or {}}
        for side in ("away", "home"):
            team, rows = g[side]["id"], []
            for r in b.get(side) or []:
                row = dict(zip(box.COLS, r))
                pid = players.player_id(team, row["first"], row["last"])
                if pid not in ids:
                    pid = by_number.get((team, row["number"], players._norm(row["last"].split()[-1] if row["last"] else "")))
                rows.append([row["number"], (row["first"] + " " + row["last"]).strip(), row["pos"], row["starter"],
                             *[row[c] for c in ("sets", "k", "e", "ta", "ast", "sa", "se", "d", "ra", "re", "bs", "ba", "bhe")],
                             pid if pid in ids else None, photo.get(pid)])
            doc[side] = rows
        write_json(out / "match" / f"{g['id']}.json", doc)
        g["box"] = 1
        n += 1
    return n


def read_words(src: Path = SITE_SRC) -> dict:
    """The site's wording from site/words.txt ("name = words" lines). Fails,
    before anything is published, if a line is broken or a name the pages use
    is missing, so a slip in the file leaves yesterday's site up."""
    words, bad = {}, []
    for n, line in enumerate((src / "words.txt").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, text = line.partition("=")
        key = key.strip()
        if not sep or not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", key):
            bad.append(f"line {n}: {line.strip()[:60]!r}")
            continue
        words[key] = text.strip()
    used = set(re.findall(r'W\("([a-z0-9_.]+)"', (src / "app.js").read_text()))
    used |= set(re.findall(r'data-w="([a-z0-9_.]+)"', (src / "index.html").read_text()))
    missing = sorted(used - set(words))
    if bad or missing:
        raise RuntimeError("site/words.txt needs fixing; the site was not updated. "
                           + (f"Lines not in the form 'name = words': {bad}. " if bad else "")
                           + (f"Missing names (put these lines back): {missing}." if missing else ""))
    return words


def build_site(state: Path, out: Path, now: dt.datetime) -> dict:
    sel = ranked_matches(state)
    through, ranked, listed, unmatched = sel["through"], sel["teams"], sel["games"], sel["unmatched"]
    rank = {t["id"]: t["rank"] for t in ranked if t["id"]}
    # Odds: rate every Division I team from this season's results, starting from
    # where each finished last season, and give each coming match a chance.
    season = sel["season"]
    kept = read_json(state / "ratings.json", {})
    start = kept.get(str(season - 1))
    if start is None:
        first = odds.seed()
        start = first.get("ratings", {}) if first.get("season", season) < season else {}
    rating, pregame = odds.rate(sel["all_games"], start)
    kept = {k: v for k, v in kept.items() if int(k) >= season - 1}
    kept[str(season)] = {t: round(v, 3) for t, v in rating.items()}
    write_json(state / "ratings.json", kept)

    # The GOAT ranking of every Division I team: head to head, then strength of
    # schedule, the AVCA poll and record (see pipeline/goat.py).
    in_poll = {t["id"]: t["rank"] for t in ranked if t["id"]}
    division = {t["id"] for t in sel["d1_teams"]} | set(in_poll)
    ranking = goat.rank(sel["all_games"], rating, division, in_poll)
    place = {t: i + 1 for i, t in enumerate(ranking["order"])}
    polled = [t["id"] for t in ranked if t["id"]]
    for t in ranked:
        t["goat"] = place.get(t["id"])
    # The number shown beside a team everywhere: its poll rank if it has one,
    # otherwise 26 and on, in GOAT order, so no two teams share a number.
    shown, n = {}, config.POLL_SIZE
    for t in ranking["order"]:
        if t not in in_poll:
            n += 1
            shown[t] = n
    # Each ranked team's results against the other ranked teams, best opponent first.
    # Only matches the poll has seen (played through its date), so this view changes
    # when the poll does, on Mondays; the GOAT view below is redone every night.
    results = goat.head_to_head([g for g in sel["all_games"] if g["date"] <= through])
    for t in ranked:
        t["beat"], t["lost"] = [], []
        for other in sorted(in_poll, key=in_poll.get):
            wins, losses, _ = results.get((t["id"], other), (0, 0, []))
            if wins:
                t["beat"].append([in_poll[other], sel["names"][other], wins, other])
            if losses:
                t["lost"].append([in_poll[other], sel["names"][other], losses, other])
    goat_top = [{"rank": i + 1, "id": t, "name": sel["names"].get(t, t), "avca": in_poll.get(t),
                 "score_rank": ranking["base"][t], "factors": ranking["factors"][t]} for i, t in enumerate(ranking["order"])]
    # For the GOAT view: each team's record, and its results against the GOAT top 25.
    in_goat = {x["id"]: x["rank"] for x in goat_top[:config.POLL_SIZE]}
    results = goat.head_to_head(sel["all_games"])          # every result so far, not only the poll's
    for x in goat_top:
        won = sum(v[0] for (a, _), v in results.items() if a == x["id"])
        lost = sum(v[1] for (a, _), v in results.items() if a == x["id"])
        x["record"], x["beat"], x["lost"] = f"{won}-{lost}", [], []
        for other in sorted(in_goat, key=in_goat.get):
            wins, losses, _ = results.get((x["id"], other), (0, 0, []))
            if wins:
                x["beat"].append([in_goat[other], sel["names"][other], wins, other])
            if losses:
                x["lost"].append([in_goat[other], sel["names"][other], losses, other])
    goat_info = {"top": goat_top, "weight": config.GOAT_HEAD_TO_HEAD, "weights": config.GOAT_WEIGHTS,
                 # among the poll's own 25 teams: results each order has the wrong way round
                 "poll_wrong": goat.contradictions(polled, sel["all_games"], set(polled)),
                 "goat_wrong": goat.contradictions(ranking["order"], sel["all_games"], set(polled))}

    every, d1 = sel["all_games"], sel["d1_teams"]
    where = read_json(state / "watch.json", {})
    for g in every:
        w = where.get(str(g["id"]))
        if g["state"] in ("upcoming", "live") and g["home"]["id"] in rating and g["away"]["id"] in rating:
            neutral = isinstance(w, dict) and bool(w.get("neutral"))
            g["p"] = round(odds.match_chance(rating[g["home"]["id"]], rating[g["away"]["id"]], neutral), 3)   # the home team's chance
        elif g["id"] in pregame:
            g["p0"] = round(pregame[g["id"]], 3)     # what the home team's chance was before a finished match
        if isinstance(w, list):
            w = {"channels": w}
        if g["state"] != "final" and w is not None:
            g["watch"] = w.get("channels") or []      # an empty list means: looked, nothing announced
        if w and w.get("espn"):
            g["espn"] = [w["espn"], 1 if w.get("flip") else 0]   # live score, and the match page's set scores
    words = read_words()                       # checked before anything is written
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE_SRC, out, ignore=shutil.ignore_patterns("words.txt"))
    # Give the script and stylesheet an address that changes whenever they do.
    # Otherwise a browser can pair a new page with the copy of the old script
    # it kept, and the page breaks until that copy expires.
    page = (out / "index.html").read_text()
    for name in ("app.js", "styles.css"):
        stamp = hashlib.sha256((out / name).read_bytes()).hexdigest()[:10]
        assert f'"{name}"' in page, f"index.html no longer refers to {name}"
        page = page.replace(f'"{name}"', f'"{name}?v={stamp}"')
    (out / "index.html").write_text(page)
    # Players and team stats twice: against the ranked 25 only, and against all of
    # Division I. The site's "Top 25 / All D1" switch chooses which file it reads.
    boxes = read_json(state / "box.json", {})
    rated = players.compute(ranked, listed, boxes)
    rated_d1 = players.compute(d1, every, boxes)
    found = read_json(state / "photos.json", {}) if config.SHOW_PHOTOS else {}
    for r, games in ((rated, listed), (rated_d1, every)):
        r["through"] = max((g["date"] for g in games if g["state"] == "final"), default=None)
        for p in r["players"]:
            url = ((found.get(p["team_id"]) or {}).get("photos") or {}).get(p["id"])
            if url:
                p["photo"] = url
    with_box = match_files(out, every, boxes, rated_d1)
    write_json(out / "data.json", {
        "site": config.SITE_NAME, "updated": now.isoformat(timespec="seconds"), "season": sel["season"],
        "poll": {"name": config.POLL_NAME, "through": through, "teams": ranked, "polls_seen": sel["polls_seen"]},
        "game_page": config.GAME_PAGE, "live_feed": config.ESPN_SCOREBOARD, "live_seconds": config.LIVE_SECONDS,
        "logo": config.LOGO_URL, "odds_tested": config.ODDS_TESTED, "goat": goat_info, "nr": shown, "words": words,
        "d1": [[t["id"], t["name"]] for t in d1], "games": every})
    write_json(out / "players.json", rated)
    write_json(out / "players_d1.json", rated_d1)
    write_json(out / "teams.json", teams.compute(ranked, listed, boxes, rating))
    write_json(out / "teams_d1.json", teams.compute(d1, every, boxes, rating))
    (out / ".nojekyll").write_text("")
    log(f"site: poll through {through}, {len(listed)} matches of {len(rank)} ranked teams and {len(every)} in all of Division I "
        f"({len(d1)} teams); {rated['regulars']} top-25 regulars rated, {rated_d1['regulars']} in Division I"
        + (f"; NOT MATCHED to a scoreboard team: {unmatched}" if unmatched else ""))
    return {"poll_through": through, "matches_listed": len(listed), "teams_matched": len(rank), "unmatched": unmatched,
            "with_channel": sum(1 for g in listed if g.get("watch")),
            "players": len(rated["players"]), "regulars": rated["regulars"], "d1_teams": len(d1),
            "d1_matches": len(every), "d1_players": len(rated_d1["players"]), "d1_regulars": rated_d1["regulars"],
            "with_odds": sum(1 for g in listed if "p" in g), "teams_rated": len(rating), "match_pages": with_box}


def check_teams(status: dict) -> dict:
    """Make the run fail, so GitHub sends an email, if a ranked school could
    not be matched to a scoreboard team. The site is still published, but
    without that school's matches and players until its name is added to
    ALIASES in pipeline/poll.py."""
    site = (status["stages"].get("site") or {}).get("result") or {}
    if site.get("unmatched"):
        raise RuntimeError(f"ranked but not found on the scoreboard: {site['unmatched']}. "
                           "Add the poll's spelling to ALIASES in pipeline/poll.py.")
    return {"teams_matched": site.get("teams_matched")}


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

    if os.environ.get("RUN_MODE") == "live" and not offline:
        # a match-night run: only the matches under way or just finished
        todo = live_now(state, now)
        if not todo:
            log("match-night run: no ranked team is playing right now; nothing to do")
            return 0
        stage("scores now", lambda: update_scoreboard(state, season_for(now.date()), todo))
        stage("box scores now", lambda: update_live_boxes(state, now))
        stage("site", lambda: build_site(state, out, now))
        status["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        status["ok"] = all(s["ok"] for s in status["stages"].values())
        write_json(state / "status.json", status, indent=1)
        log("match-night run finished: " + ("OK" if status["ok"] else "WITH ERRORS"))
        return 0 if status["ok"] else 1

    if not offline:
        # a failed look at the poll or the scoreboard leaves the stored copy in use
        stage("poll", lambda: update_poll(state, now, os.environ.get("CHECK_POLL") == "1"))
        stage("scoreboard", lambda: update_scoreboard(state, season_for(now.date())))
        stage("watch", lambda: update_watch(state, now))
        stage("boxes", lambda: update_boxes(state, now))
        if config.SHOW_PHOTOS:
            stage("photos", lambda: update_photos(state, now))
    stage("site", lambda: build_site(state, out, now))
    stage("every ranked team found", lambda: check_teams(status))
    status["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    status["ok"] = all(s["ok"] for s in status["stages"].values())
    write_json(state / "status.json", status, indent=1)
    log("run finished: " + ("OK" if status["ok"] else "WITH ERRORS"))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
