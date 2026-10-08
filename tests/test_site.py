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
    by_teams = {(g["away"]["id"], g["home"]["id"]): (found.get(g["id"]) or {}).get("channels") for g in games}
    assert sum(1 for f in found.values() if f["espn"]) >= 105 and not any(f["flip"] for f in found.values())
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
    assert where[next(g["id"] for g in games if g["home"]["id"] == "maryland")]["espn"]
    run.build_site(state, out, dt.datetime(2026, 10, 2, tzinfo=UTC))
    data = json.loads((out / "data.json").read_text())
    shown = {(g["away"]["id"], g["home"]["id"]): g.get("watch") for g in data["games"]}
    assert shown[("nebraska", "maryland")] == ["B1G+"] and shown[("louisville", "notre-dame")] == ["ACC Network Extra"]
    assert shown[("iowa", "penn-st")] is None                  # finished: no channel shown
    followed = [g for g in data["games"] if g.get("espn")]
    assert followed and all(len(g["espn"]) == 2 and g["espn"][0].isdigit() for g in followed)
    assert data["live_feed"].startswith("https://site.api.espn.com/")


# ------------------------------------------------------------------ players --
from pipeline import box, players  # noqa: E402


def one_box():
    return box.parse_box(json.load(gzip.open(FIX / "box_6627461.json.gz")))


def test_box_score_is_read():
    b = one_box()                      # Mercer at ETSU, 3 October 2026: ETSU won 3-0
    home = [dict(zip(box.COLS, r)) for r in b["home"]]
    away = [dict(zip(box.COLS, r)) for r in b["away"]]
    assert sum(r["k"] for r in home) == 40 and sum(r["e"] for r in home) == 18 and sum(r["ta"] for r in home) == 116
    assert sum(r["sa"] for r in home) == 8 and sum(r["d"] for r in home) == 47 and sum(r["sv"] for r in home) == 75
    assert max(r["sets"] for r in home) == 3 and len(home) >= 7 and len(away) >= 7
    aylward = next(r for r in home if r["last"] == "Aylward")
    assert (aylward["pos"], aylward["number"], aylward["k"], aylward["e"], aylward["ta"]) == ("OH", 20, 6, 3, 22)


def test_players_are_rated_against_each_other():
    ranked = [{"id": "east-tenn-st", "rank": 1, "name": "ETSU"}, {"id": "mercer", "rank": 2, "name": "Mercer"},
              {"id": None, "rank": 3, "name": "Nobody"}]
    game = next(g for g in (run.parse_contest(c) for c in contests()) if g["id"] == 6627461)
    res = players.compute(ranked, [game], {"6627461": one_box()})
    ps = res["players"]
    assert {p["team_id"] for p in ps} == {"east-tenn-st", "mercer"} and len(ps) >= 14
    assert sum(p["tot"]["k"] for p in ps if p["team_id"] == "east-tenn-st") == 40
    assert [t["sets"] for t in res["teams"][:2]] == [3, 3]
    regs = [p for p in ps if p["regular"]]
    assert [p["rank"] for p in regs] == list(range(1, len(regs) + 1)) == [p["rank"] for p in ps[:len(regs)]]
    assert all(regs[i]["impact"] >= regs[i + 1]["impact"] for i in range(len(regs) - 1))
    assert {p["pos"] for p in ps} <= {"OH", "MB", "S", "L", "DS"} and any(p["pos"] == "S" for p in ps)
    i = res["metrics"].index("impact_set")
    parts = [res["metrics"].index(k) for k in players.PARTS]
    for p in ps:                       # the six parts add up to the whole
        assert abs(sum(p["v"][j] for j in parts) - p["v"][i]) < 0.01
        assert len(p["v"]) == len(p["pct"]) == len(res["metrics"])
    # attack is measured against the position's average, so a position's attack parts cancel out
    hitters = [p for p in ps if p["pos"] == "OH" and p["regular"]]
    att = res["metrics"].index("att")
    assert abs(sum(p["v"][att] * p["sp"] for p in hitters)) < 3.0
    # with only two teams there are too few players at any position for percentiles
    assert all(x is None for p in ps for x in p["pct"])


def test_percentiles_run_from_low_to_high():
    # twenty outside hitters on twenty teams, each a little better than the last
    ranked, games, boxes = [], [], {}
    for n in range(20):
        ranked.append({"id": f"t{n}", "rank": n + 1, "name": f"Team {n}"})
        games.append({"id": n, "state": "final", "date": "2026-10-01", "home": {"id": f"t{n}"}, "away": {"id": "x"}})
        row = dict.fromkeys(box.COLS, 0) | {"first": "A", "last": f"Hitter{n}", "number": 1, "pos": "OH", "starter": 1,
                                             "sets": 10, "k": 20 + 2 * n, "e": 10, "ta": 100, "sv": 30, "sa": 1, "d": 20}
        boxes[str(n)] = {"home": [[row[c] for c in box.COLS]], "away": []}
    res = players.compute(ranked, games, boxes)
    by = {p["name"]: p for p in res["players"]}
    hit = res["metrics"].index("hit")
    pcts = [by[f"A Hitter{n}"]["pct"][hit] for n in range(20)]
    assert pcts == sorted(pcts) and pcts[0] <= 5 and pcts[-1] >= 95
    assert by["A Hitter19"]["rank"] == 1 and by["A Hitter0"]["rank"] == 20
    assert by["A Hitter5"]["pct"][res["metrics"].index("ast_set")] is None      # hitters are not ranked on setting


# ------------------------------------------------------------- player photos --
from pipeline import photos  # noqa: E402

NAMES = {"t~reilly~ber": "Bergen Reilly", "t~jackson~and": "Andi Jackson", "t~obrien~kas": "Kassie O'Brien",
         "t~krickovic~teo": "Teodora Kričković"}
BASE = "https://school.example/sports/volleyball/roster"


def test_photo_with_its_own_description():
    page = ('<img alt="School logo" src="/images/logo.png">'
            '<img alt="Bergen Reilly" src="/images/2026/reilly.jpg">'
            '<picture><source type="image/webp" srcset="https://cdn.example/a.webp 1x"><source srcset="https://cdn.example/a.jpg 1x">'
            '<img alt="Kassie O&#39;Brien headshot" src="data:image/gif;base64,AAAA"></picture>'
            '<img alt="Andi Jackson and Bergen Reilly celebrate" src="/images/both.jpg">')
    got = photos.find(page, BASE, NAMES)
    assert got == {"t~reilly~ber": "https://school.example/images/2026/reilly.jpg", "t~obrien~kas": "https://cdn.example/a.jpg"}


def test_photo_described_by_the_link_around_it():
    page = ('<a href="/roster/andi-jackson/1" aria-label="Andi Jackson jersey number 15 full bio"><picture>'
            '<source srcset="https://images.example/crop?url=x%2FJackson.png&amp;width=100"><img alt="" src="data:image/gif;base64,AA">'
            '</picture></a><a href="/x" aria-label="Teodora Kričković jersey number 3 full bio"><img alt src="/i/tk.png"></a>')
    got = photos.find(page, BASE, NAMES)
    assert got == {"t~jackson~and": "https://images.example/crop?url=x%2FJackson.png&width=100",
                   "t~krickovic~teo": "https://school.example/i/tk.png"}


def test_photo_kept_in_the_pages_data_block():
    data = [{"photo": 1, "sound": 8},
            {"url": 2, "srcset": 3, "original_name": 4, "title": 4, "alt": 5, "mime_type": 6},
            "https://school.example/imgproxy/big/1980.jpg",
            "https://school.example/imgproxy/s/160.jpg 160w, https://school.example/imgproxy/m/480.jpg 480w, https://school.example/imgproxy/l/960.jpg 960w",
            "Reilly_Bergen 2026.JPG", "Nebraska setter Bergen Reilly #2", "image/jpeg",
            "audio/wav", {"url": 9, "original_name": 10, "mime_type": 7}, "https://school.example/say/jackson.wav", "Andi Jackson name.wav"]
    block = '<script type="application/json" id="__NUXT_DATA__">' + json.dumps(data) + "</script>"
    table_only = "<table><tr><th>Bergen Reilly</th></tr><tr><th>Andi Jackson</th></tr></table>" + block
    assert photos.find(table_only, BASE, NAMES) == {"t~reilly~ber": "https://school.example/imgproxy/m/480.jpg"}
    lazy = '<img src="data:image/gif;base64,AA" alt="Bergen Reilly" title="Reilly_Bergen 2026.JPG">' + block
    assert photos.find(lazy, BASE, NAMES) == {"t~reilly~ber": "https://school.example/imgproxy/m/480.jpg"}


def test_roster_pages_are_read_weekly_and_old_photos_kept():
    teams = {"nebraska": {"nebraska~reilly~ber": "Bergen Reilly", "nebraska~jackson~and": "Andi Jackson"}}
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return '<img alt="Bergen Reilly" src="/r.jpg"><img alt="Andi Jackson" src="/j.jpg">'
        return '<img alt="Bergen Reilly" src="/r2.jpg">'

    stored, day = {}, dt.date(2026, 10, 7)
    res = photos.update(stored, teams, day, fetch, lambda m: None)
    assert res["with_photo"] == 2 and res["no_page"] == [] and calls == ["https://huskers.com/sports/volleyball/roster"]
    photos.update(stored, teams, day + dt.timedelta(days=3), fetch, lambda m: None)
    assert len(calls) == 1                                    # everyone has a photo: wait for the weekly look
    photos.update(stored, teams, day + dt.timedelta(days=7), fetch, lambda m: None)
    assert len(calls) == 2 and stored["nebraska"]["photos"]["nebraska~reilly~ber"].endswith("/r2.jpg")
    assert stored["nebraska"]["photos"]["nebraska~jackson~and"].endswith("/j.jpg")      # missed this time, kept


def test_a_new_schools_roster_page_is_found_by_itself():
    # a school that is not in rosters/pages.csv: its site comes from ncaa.com, and the
    # roster address is the one that shows photos of the players we already know
    names = {f"newcomer-st~p{i}~a": f"Ann Player{chr(97 + i)}" for i in range(9)}
    roster = "".join(f'<img alt="{n}" src="/photos/{i}.jpg">' for i, n in enumerate(names.values()))
    web_pages = {
        "https://www.ncaa.com/schools/newcomer-st":
            '<div class="school-links"><ul><li><a href="https://gonewcomers.example" target="_blank"> <span class="icon-web">&nbsp;</span></a></li></ul></div>',
        "https://gonewcomers.example/sports/volleyball/roster": roster,
        "https://gonewcomers.example/sports/wvball/roster/": "<p>men's roster</p>",
    }
    calls = []

    def fetch(url):
        calls.append(url)
        if url not in web_pages:
            raise RuntimeError("404")
        return web_pages[url]

    stored, day = {}, dt.date(2026, 10, 12)
    res = photos.update(stored, {"newcomer-st": names}, day, fetch, lambda m: None)
    assert res["found_page_for"] == ["newcomer-st"] and res["with_photo"] == 9 and res["no_page"] == []
    assert stored["newcomer-st"]["page"] == "https://gonewcomers.example/sports/volleyball/roster"
    assert calls[0] == "https://www.ncaa.com/schools/newcomer-st"
    calls.clear()                                             # next week it goes straight to the page it found
    photos.update(stored, {"newcomer-st": names}, day + dt.timedelta(days=7), fetch, lambda m: None)
    assert calls == ["https://gonewcomers.example/sports/volleyball/roster"]
    # a school whose site cannot be found is reported, and looked for again the next day, not every run
    stored2, calls2 = {}, []
    look = lambda url: calls2.append(url) or "<html></html>"
    res = photos.update(stored2, {"nowhere-st": {"x": "A B"}}, day, look, lambda m: None)
    assert res["no_page"] == ["nowhere-st"] and len(calls2) == 1
    photos.update(stored2, {"nowhere-st": {"x": "A B"}}, day, look, lambda m: None)
    assert len(calls2) == 1
    photos.update(stored2, {"nowhere-st": {"x": "A B"}}, day + dt.timedelta(days=1), look, lambda m: None)
    assert len(calls2) == 2


def test_an_unmatched_ranked_school_fails_the_run():
    status = {"stages": {"site": {"ok": True, "result": {"unmatched": [], "teams_matched": 25}}}}
    assert run.check_teams(status) == {"teams_matched": 25}
    status["stages"]["site"]["result"]["unmatched"] = ["Atlantis Tech"]
    try:
        run.check_teams(status)
        raise AssertionError("should have failed")
    except RuntimeError as e:
        assert "Atlantis Tech" in str(e)


def test_poll_spellings_of_shortened_names():
    teams = {"south-fla": "South Fla.", "northern-colo": "Northern Colo.", "western-mich": "Western Mich.", "ga-southern": "Ga. Southern",
             "middle-tenn": "Middle Tenn.", "uni": "UNI", "georgia": "Georgia", "florida": "Florida", "michigan": "Michigan",
             "la-lafayette": "Louisiana", "california": "California", "st-johns-ny": "St. John's (NY)", "eastern-ky": "Eastern Ky."}
    want = {"South Florida": "south-fla", "Northern Colorado": "northern-colo", "Western Michigan": "western-mich",
            "Georgia Southern": "ga-southern", "Middle Tennessee": "middle-tenn", "Northern Iowa": "uni", "Georgia": "georgia",
            "Florida": "florida", "Michigan": "michigan", "Louisiana": "la-lafayette", "Cal": "california",
            "St. John's": "st-johns-ny", "Eastern Kentucky": "eastern-ky"}
    for school, team in want.items():
        assert poll.match_school(school, teams) == team, school


def test_photo_tied_to_the_player_in_the_data_block():
    # the <img> says only "head shot"; the data block says whose it is
    data = [{"first_name": 1, "last_name": 2, "full_name": 3, "photo": 4},
            "Andi", "Jackson", "Andi Jackson",
            {"url": 5, "mime_type": 6, "title": 7, "original_name": 7}, "https://school.example/imgproxy/aj.jpg", "image/jpeg", "head shot",
            {"first_name": 9, "last_name": 10, "photo": 11}, "Dani", "Coach", None]
    page = ('<img src="data:image/gif;base64,AA" alt="head shot">'
            '<script type="application/json" id="__NUXT_DATA__">' + json.dumps(data) + "</script>")
    assert photos.find(page, BASE, NAMES) == {"t~jackson~and": "https://school.example/imgproxy/aj.jpg"}
