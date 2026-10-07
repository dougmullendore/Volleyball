"""Checks on a saved copy of the poll page and of one day's scoreboard.
Run with:  python tests/run_local.py   (or pytest)"""
import datetime as dt
import gzip
import json
import tempfile
from pathlib import Path

from pipeline import poll, run

FIX = Path(__file__).parent / "fixtures"
UTC = dt.timezone.utc


def poll_page():
    return gzip.open(FIX / "avca_poll.html.gz", "rt", encoding="utf-8").read()


def contests():
    return json.load(gzip.open(FIX / "scoreboard_20261003.json.gz"))["data"]["contests"]


def test_poll_page_is_read():
    found = poll.parse_page(poll_page())
    assert found["through"] == "2026-10-04"
    rows = found["rows"]
    assert [r["rank"] for r in rows] == list(range(1, 26))
    assert rows[0] == {"rank": 1, "school": "Nebraska", "votes": 47, "points": 1559, "record": "15-0", "prev": 1}
    assert rows[21]["school"] == "Michigan State" and rows[21]["prev"] is None     # "NR": not ranked last week


def test_poll_names_find_the_right_team():
    teams = {"arizona-st": "Arizona St.", "penn-st": "Penn St.", "texas-am": "Texas A&M", "michigan-st": "Michigan St.",
             "michigan": "Michigan", "north-carolina": "North Carolina", "north-carolina-st": "NC State",
             "miami-fl": "Miami (FL)", "miami-oh": "Miami (OH)", "southern-california": "Southern California",
             "western-ky": "Western Ky.", "texas": "Texas", "texas-st": "Texas St.", "washington": "Washington",
             "washington-st": "Washington St.", "iowa-st": "Iowa St.", "iowa": "Iowa", "florida": "Florida",
             "florida-st": "Florida St.", "nebraska": "Nebraska", "byu": "BYU", "hawaii": "Hawaii"}
    want = {"Arizona State": "arizona-st", "Penn State": "penn-st", "Texas A&M": "texas-am", "Michigan State": "michigan-st",
            "Michigan": "michigan", "North Carolina": "north-carolina", "Miami (FL)": "miami-fl", "USC": "southern-california",
            "Western Kentucky": "western-ky", "Texas": "texas", "Washington State": "washington-st", "Washington": "washington",
            "Hawai'i": "hawaii", "Iowa State": "iowa-st", "Florida State": "florida-st", "Florida": "florida",
            "Nebraska (47)": "nebraska", "BYU": "byu"}
    for school, team in want.items():
        assert poll.match_school(school, teams) == team, school
    assert poll.match_school("Slippery Rock", teams) is None


def test_the_poll_is_looked_for_on_mondays():
    have = {"2026-10-04": []}
    at = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=UTC)
    assert poll.why_check({}, at("2026-10-07T10:47")) == "no poll stored yet"
    assert poll.why_check(have, at("2026-10-07T10:47")) is None                 # Wednesday, poll is fresh
    assert poll.why_check(have, at("2026-10-07T10:47"), forced=True) == "asked to"
    assert poll.why_check(have, at("2026-10-12T21:13")) == "it is Monday"       # Monday afternoon in Chicago
    assert poll.why_check(have, at("2026-10-13T02:13")) == "it is Monday"       # Tuesday in UTC, still Monday evening in Chicago
    assert poll.why_check(have, at("2026-10-13T10:47")) == "the newest poll is 9 days old"   # Monday's look was missed
    assert poll.why_check({"2026-10-11": []}, at("2026-10-13T10:47")) is None   # Tuesday morning, new poll already in


def test_scoreboard_matches_are_read():
    games = [run.parse_contest(c) for c in contests()]
    assert len(games) == 113 and all(games)
    g = next(g for g in games if g["id"] == 6627461)
    assert g["date"] == "2026-10-03" and g["state"] == "final" and g["start"] == 1791039600
    assert (g["home"]["id"], g["home"]["name"], g["home"]["sets"]) == ("east-tenn-st", "ETSU", 3)
    assert (g["away"]["id"], g["away"]["sets"]) == ("mercer", 0)
    assert all(g["home"]["sets"] is None and g["away"]["sets"] is None for g in games if g["state"] == "upcoming")
    finals = [g for g in games if g["state"] == "final"]
    # the feed has the odd wrong score (one 2-2 "final" on this day), so not quite all
    assert sum(max(g["home"]["sets"], g["away"]["sets"]) == 3 for g in finals) >= len(finals) - 1 > 50


def test_the_page_lists_only_ranked_teams_matches():
    state, out = Path(tempfile.mkdtemp(prefix="state")), Path(tempfile.mkdtemp(prefix="site")) / "dist"
    found = poll.parse_page(poll_page())
    older = [dict(r, rank=26 - r["rank"]) for r in found["rows"]]              # an older poll must be ignored
    run.write_json(state / "polls.json", {"2026-09-27": older, found["through"]: found["rows"]})
    games = [run.parse_contest(c) for c in contests()]
    run.write_json(state / "scoreboard.json", {"season": 2026, "days": {"2026-10-03": games}})
    res = run.build_site(state, out, dt.datetime(2026, 10, 7, tzinfo=UTC))
    data = json.loads((out / "data.json").read_text())
    assert (out / "index.html").exists() and (out / "app.js").exists()
    page = (out / "index.html").read_text()        # script and stylesheet addresses change when the files do
    assert 'src="app.js?v=' in page and 'href="styles.css?v=' in page
    assert data["poll"]["through"] == "2026-10-04" and len(data["poll"]["teams"]) == 25
    ranked = {t["id"]: t["rank"] for t in data["poll"]["teams"] if t["id"]}
    assert ranked["nebraska"] == 1 and ranked["penn-st"] == 18
    assert data["games"] and res["matches_listed"] == len(data["games"]) < len(games)
    for g in data["games"]:
        assert g["home"]["id"] in ranked or g["away"]["id"] in ranked
        for side in (g["home"], g["away"]):
            assert side["rank"] == ranked.get(side["id"])
    listed = {g["id"] for g in data["games"]}
    for g in games:      # and none was left out
        assert (g["id"] in listed) == (g["home"]["id"] in ranked or g["away"]["id"] in ranked)


# ------------------------------------------------------------ where to watch --
from pipeline import watch  # noqa: E402


def listings():
    espn = json.load(gzip.open(FIX / "espn_20261003.json.gz"))
    bigten = json.load(gzip.open(FIX / "bigten_20261003.json.gz"))
    return watch.parse_espn(espn) + watch.parse_bigten(bigten)


def test_channels_are_matched_to_matches():
    games = [run.parse_contest(c) for c in contests()]
    names = {s["id"]: s["name"] for g in games for s in (g["away"], g["home"])}
    found = watch.assign(games, listings(), names)
    assert len(found) >= 105                                   # nearly every match that day is in a listing
    by_teams = {(g["away"]["id"], g["home"]["id"]): found.get(g["id"]) for g in games}
    assert by_teams[("louisville", "notre-dame")] == ["ACC Network Extra"]     # ESPN writes "ACCNX"
    assert by_teams[("virginia", "stanford")] == ["ACC Network Extra"]
    assert by_teams[("nebraska", "maryland")] == ["B1G+"]      # both sources list it; shown once
    assert by_teams[("mercer", "east-tenn-st")] == []          # in the listing, but no channel announced


def test_channel_names_are_tidied():
    assert watch.channel("BTN") == watch.channel("Big Ten Network") == "Big Ten Network"
    assert watch.channel("ESPN +") == "ESPN+" and watch.channel("SECN+") == "SEC Network+"
    assert watch.channel("No Stream") is None and watch.channel("") is None
    rows = [{"date_utc": "2026-10-08T22:30:00", "tba": False, "school": {"title": "Indiana"}, "opponent": {"title": "Nebraska"},
             "media": {"tv": "BTN", "video": {"url": "https://www.foxsports.com/live"}}},
            {"date_utc": "2026-10-09T23:00:00", "tba": False, "school": {"title": "Ohio State"}, "opponent": {"title": "Washington"},
             "media": {"tv": None, "video": {"url": "https://www.bigtenplus.com/en-int/livestream/x/1"}}},
            {"date_utc": None, "tba": True, "school": {"title": "Penn State"}, "opponent": {"title": "Northwestern"}, "media": {"tv": None}}]
    got = watch.parse_bigten(rows)
    assert [(g["teams"], g["channels"]) for g in got] == [(["Indiana", "Nebraska"], ["BTN"]), (["Ohio State", "Washington"], ["B1G+"])]


def test_the_page_carries_channels_for_matches_not_yet_played():
    state, out = Path(tempfile.mkdtemp(prefix="state")), Path(tempfile.mkdtemp(prefix="site")) / "dist"
    found = poll.parse_page(poll_page())
    run.write_json(state / "polls.json", {found["through"]: found["rows"]})
    games = [run.parse_contest(c) for c in contests()]
    for g in games:                                            # pretend the day has not been played yet
        g["state"] = "upcoming"
    played = next(g for g in games if g["home"]["id"] == "penn-st")
    played["state"] = "final"
    run.write_json(state / "scoreboard.json", {"season": 2026, "days": {"2026-10-03": games}})
    ranked = run.ranked_matches(state)
    where = watch.assign(ranked["games"], listings(), ranked["names"])
    run.write_json(state / "watch.json", {str(k): v for k, v in where.items()})
    run.build_site(state, out, dt.datetime(2026, 10, 2, tzinfo=UTC))
    data = json.loads((out / "data.json").read_text())
    shown = {(g["away"]["id"], g["home"]["id"]): g.get("watch") for g in data["games"]}
    assert shown[("nebraska", "maryland")] == ["B1G+"] and shown[("louisville", "notre-dame")] == ["ACC Network Extra"]
    assert shown[("iowa", "penn-st")] is None                  # finished: no channel shown
