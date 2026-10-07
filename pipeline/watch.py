"""Where to watch: the TV channel or streaming service for each upcoming match.

The NCAA scoreboard does not say, so two other public schedules are read and
matched to the NCAA's matches by team and start time:

  * ESPN's scoreboard, which lists a channel for most matches (ESPN networks,
    conference networks, B1G+, school streams), but not Big Ten Network or FS1.
  * The Big Ten's own schedule, which fills that gap for Big Ten home matches.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from . import config, poll, web

# Short codes spelled out, and different spellings of one channel made the same.
CHANNEL = {
    "BTN": "Big Ten Network", "ACCNX": "ACC Network Extra", "SECN+": "SEC Network+", "SECN": "SEC Network",
    "ESPN +": "ESPN+", "FOX OR FS1": "FOX or FS1", "ACCN": "ACC Network", "CBSSN": "CBS Sports Network",
    "B1G +": "B1G+", "Big Ten Plus": "B1G+", "BIG TEN NETWORK": "Big Ten Network",
}
NOT_A_CHANNEL = {"", "no stream", "none", "tba", "tbd", "n/a"}


def channel(name: str) -> str | None:
    name = re.sub(r"\s+", " ", name or "").strip()
    if name.lower() in NOT_A_CHANNEL:
        return None
    return CHANNEL.get(name) or CHANNEL.get(name.upper()) or name


def _epoch(text: str) -> float | None:
    try:
        t = dt.datetime.fromisoformat((text or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp()


def parse_espn(doc: dict) -> list[dict]:
    """One day of ESPN's scoreboard as [{"t": start, "teams": [names], "channels": [...]}]."""
    out = []
    for e in doc.get("events") or []:
        comp = (e.get("competitions") or [{}])[0]
        names = [n for b in comp.get("broadcasts") or [] for n in b.get("names") or []]
        teams = [(c.get("team") or {}).get("location") or "" for c in comp.get("competitors") or []]
        t = _epoch(e.get("date") or comp.get("date"))
        if t and len(teams) == 2:
            out.append({"t": t, "teams": teams, "channels": names})
    return out


def parse_bigten(rows: list) -> list[dict]:
    """The Big Ten's schedule in the same shape. When no channel is written,
    the "watch" link still says which of the conference's two outlets it is."""
    out = []
    for g in rows or []:
        media = g.get("media") or {}
        names = [media["tv"]] if media.get("tv") else []
        link = ((media.get("video") or {}).get("url") or "").lower()
        if not names and "bigtenplus.com" in link:
            names = ["B1G+"]
        elif not names and ("/btn" in link or "btn/" in link):
            names = ["Big Ten Network"]
        t = _epoch(g.get("date_utc")) if not g.get("tba") else None
        teams = [(g.get("school") or {}).get("title") or "", (g.get("opponent") or {}).get("title") or ""]
        if t and all(teams):
            out.append({"t": t, "teams": teams, "channels": names})
    return out


def assign(games: list[dict], listings: list[dict], names: dict) -> dict:
    """{match id: [channels]} for every match that has a listing. A listing
    belongs to a match when both teams are the same and the start times are
    within six hours, or one team is the same and they start within two."""
    seen = {}
    for item in listings:
        if "ids" not in item:
            for t in item["teams"]:
                if t not in seen:
                    seen[t] = poll.match_school(t, names)
            item["ids"] = {seen[t] for t in item["teams"]} - {None}
    out = {}
    for g in games:
        if not g.get("start"):
            continue
        sides = {g["away"]["id"], g["home"]["id"]}
        found = []
        for item in listings:
            n, gap = len(sides & item["ids"]), abs(item["t"] - g["start"])
            if (n == 2 and gap <= 6 * 3600) or (n == 1 and gap <= 2 * 3600):
                found.append((-n, gap, item))
        if not found:
            continue
        best = min(found, key=lambda f: f[:2])
        chans = []
        for n, gap, item in sorted(found, key=lambda f: f[:2]):
            # the same match in both sources: both teams agree, or one does and so does the start time
            if n == best[0] and (n == -2 or abs(item["t"] - best[2]["t"]) <= 3600):
                for c in item["channels"]:
                    c = channel(c)
                    if c and c not in chans:
                        chans.append(c)
        out[g["id"]] = chans
    return out


def fetch_listings(today: dt.date, log) -> tuple[list[dict], list[str]]:
    """Listings for the next WATCH_DAYS days from both sources, and the names
    of any source that could not be read."""
    listings, failed = [], []
    for i in range(-1, config.WATCH_DAYS):
        day = today + dt.timedelta(days=i)
        try:
            listings += parse_espn(json.loads(web.get_bytes(config.ESPN_SCOREBOARD + day.strftime("%Y%m%d"))))
        except Exception as e:
            failed.append(f"ESPN {day}: {e!r}"[:160])
    try:
        url = config.BIGTEN_SCHEDULE.format(start=today - dt.timedelta(days=1), end=today + dt.timedelta(days=config.WATCH_DAYS))
        listings += parse_bigten(json.loads(web.get_bytes(url)))
    except Exception as e:
        failed.append(f"Big Ten: {e!r}"[:160])
    return listings, failed
