"""End-to-end check on ten real matches stored in tests/fixtures."""
import copy
import glob
import gzip
import json
from pathlib import Path

try:  # pytest is optional; tests/run_local.py works without it
    import pytest
    module_fixture = pytest.fixture(scope="module")
except ImportError:  # pragma: no cover
    def module_fixture(fn):
        return fn

from pipeline import aggregate, config, ratings, store
from pipeline.parse import parse_detail, parse_scoreboard, tokens

FIX = Path(__file__).parent / "fixtures"


def raw_matches():
    return [json.load(gzip.open(f)) for f in sorted(glob.glob(str(FIX / "match_*.json.gz")))]


def parsed(doc):
    season = int(doc["contest"]["startDate"].split("/")[2])
    basic = parse_scoreboard(doc["contest"], season)
    return parse_detail(basic, doc["game"], doc["box"], doc["pbp"])


def load_all():
    return [parsed(d) for d in raw_matches()]


@module_fixture
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    by_season = {}
    for g, b, r, _ in load_all():
        s = by_season.setdefault(g["season"], ([], [], []))
        s[0].append(g); s[1].extend(b); s[2].extend(r)
    for season, (g, b, r) in by_season.items():
        store.write(d, "games", season, store.frame("games", g))
        store.write(d, "box", season, store.frame("box", b))
        store.write(d, "rallies", season, store.frame("rallies", r))
    return d


def test_names_match_either_way_round():
    assert tokens("Lang, Kate") == tokens("Kate Lang")
    assert tokens("O'Brien, Kassie") == tokens("kassie OBRIEN")


def test_every_set_adds_up():
    for g, _, rallies, _ in load_all():
        scores = [tuple(map(int, s.split("-"))) for s in g["set_scores"].split()]
        assert g["pbp_sets"] == len(scores), g["game_id"]
        assert g["home_sets"] == sum(h > v for h, v in scores)
        last = {}
        for r in rallies:
            last[r[1]] = (r[4], r[5])
        assert [last[i + 1] for i in range(len(scores))] == scores, g["game_id"]


def test_kills_and_aces_match_the_box_score():
    for g, box, rallies, _ in load_all():
        missing = sum(sum(map(int, s.split("-"))) for s in g["set_scores"].split()) - len(rallies)
        for col, kind in ((10, "K"), (14, "ACE")):
            official = sum(b[col] for b in box)
            counted = sum(1 for r in rallies if r[6] == kind)
            assert 0 <= official - counted <= max(2, missing), (g["game_id"], kind, official, counted)


def test_hitters_are_found_on_the_right_team():
    for g, box, rallies, _ in load_all():
        kills = [r for r in rallies if r[6] == "K"]
        assert sum(r[7] is not None for r in kills) >= 0.97 * len(kills)
        rows = {(b[2], b[3]): b for b in box}
        credited = {}
        for r in kills:
            if r[7] is not None:
                credited[(r[3], r[7])] = credited.get((r[3], r[7]), 0) + 1
        for key, n in credited.items():
            assert key in rows and rows[key][10] >= n, (g["game_id"], key)


def test_server_is_the_previous_winner():
    for _, _, rallies, _ in load_all():
        known = [r for r in rallies if r[10] is not None]
        assert len(known) >= 0.95 * len(rallies)
        prev = None
        wrong = 0
        for r in rallies:
            if prev is not None and prev[1] == r[1] and r[10] is not None and r[10] != prev[3]:
                wrong += 1
            prev = r
        assert wrong <= 3


def test_teams_listed_the_other_way_round():
    """At neutral sites the play-by-play can have home and away swapped."""
    original = [d for d in raw_matches() if d["contest"]["contestId"] == 6625435][0]
    doc = copy.deepcopy(original)
    for t in doc["contest"]["teams"]:
        t["isHome"] = not t["isHome"]
    for t in doc["game"]["data"]["contests"][0]["teams"]:
        t["isHome"] = not t["isHome"]
    for l in doc["game"]["data"]["contests"][0]["linescores"]:
        l["home"], l["visit"] = l["visit"], l["home"]
    for t in doc["box"]["data"]["boxscore"]["teams"]:
        t["isHome"] = not t["isHome"]
    g, box, rallies, odd = parsed(doc)
    straight = parsed(original)
    assert odd.get("teams listed the other way round") == 1
    assert g["pbp_sets"] == straight[0]["pbp_sets"] and len(rallies) == len(straight[2])
    assert [r[3] for r in rallies] == [1 - r[3] for r in straight[2]]
    assert sum(r[7] is not None for r in rallies) == sum(r[7] is not None for r in straight[2])


def test_tables_build(data_dir, monkeypatch):
    seasons = sorted(int(p.stem.split(".")[0]) for p in (Path(data_dir) / "games").glob("*.csv.gz"))
    monkeypatch.setattr(config, "SEASONS", seasons)
    monkeypatch.setattr(config, "MIN_MATCHES_D1", 1)
    monkeypatch.setattr(config, "PRED_SIMULATIONS", 50)
    out = Path(data_dir) / "site_data"
    res = ratings.build(data_dir, out, lambda m: None)
    assert res["teams"] > 0
    res = aggregate.build_all(data_dir, lambda m: None)
    assert res["seasons"] == len(seasons) and res["cards"] > 0
    meta = store.read_json(out / "meta.json")
    newest = meta["seasons"][0]["id"]
    assert newest == max(seasons)
    teams = store.read_json(out / f"teams_{newest}.json")
    assert all(40 <= t["so_pct"] <= 80 for t in teams if t.get("so_pct") is not None)
    war = store.read_json(out / f"war_{newest}.json")
    assert {"war", "att", "srv", "rec", "blk", "dig", "set"} <= set(war["cols"])
    recent = store.read_json(out / "recent.json")
    for g in recent:
        assert len(g["sets"]) == len(g["scores"].split())
        for s, score in zip(g["sets"], g["scores"].split()):
            h, v = map(int, score.split("-"))
            assert sum(c.isupper() for c in s) == h and sum(c.islower() for c in s) == v


# ------------------------------------------------- the coaches poll (top 25) --
from pipeline import polls  # noqa: E402

FEED_NAMES = {   # id and short name exactly as the match feed gives them
    "arizona-st": "Arizona St.", "penn-st": "Penn St.", "texas-am": "Texas A&M", "michigan-st": "Michigan St.",
    "michigan": "Michigan", "north-carolina": "North Carolina", "north-carolina-st": "NC State",
    "miami-fl": "Miami (FL)", "miami-oh": "Miami (OH)", "southern-california": "Southern California",
    "western-ky": "Western Ky.", "texas": "Texas", "texas-st": "Texas St.", "washington": "Washington",
    "washington-st": "Washington St.", "ole-miss": "Ole Miss", "hawaii": "Hawaii", "iowa-st": "Iowa St.",
    "iowa": "Iowa", "florida": "Florida", "florida-st": "Florida St.", "nebraska": "Nebraska", "byu": "BYU",
}


def test_poll_page_is_read():
    page = gzip.open(FIX / "avca_poll.html.gz", "rt", encoding="utf-8").read()
    poll = polls.parse_page(page)
    assert poll["through"] == "2026-10-04"
    rows = poll["rows"]
    assert [r["rank"] for r in rows] == list(range(1, 26))
    assert rows[0] == {"rank": 1, "school": "Nebraska", "votes": 47, "points": 1559, "record": "15-0", "prev": 1}
    assert rows[21]["school"] == "Michigan State" and rows[21]["prev"] is None     # "NR": not ranked last week
    assert polls.season_of("2026-10-04") == 2026 and polls.season_of("2026-01-05") == 2025


def test_poll_names_find_the_right_team():
    teams = {t: {"name": n, "d1": True} for t, n in FEED_NAMES.items()}
    want = {"Arizona State": "arizona-st", "Penn State": "penn-st", "Texas A&M": "texas-am", "Michigan State": "michigan-st",
            "Michigan": "michigan", "North Carolina": "north-carolina", "Miami (FL)": "miami-fl", "USC": "southern-california",
            "Southern California": "southern-california", "Western Kentucky": "western-ky", "Texas": "texas",
            "Washington State": "washington-st", "Washington": "washington", "Hawai'i": "hawaii", "Iowa State": "iowa-st",
            "Florida State": "florida-st", "Florida": "florida", "Nebraska (47)": "nebraska", "BYU": "byu"}
    for school, team in want.items():
        assert polls.match_school(school, teams) == team, school
    assert polls.match_school("Slippery Rock", teams) is None


def test_final_polls_file_is_complete():
    finals = polls._final_file()
    assert set(finals) >= {2021, 2022, 2023, 2024, 2025}
    for season, rows in finals.items():
        assert len(rows) == 25 and len({r["team"] for r in rows}) == 25, season
        assert min(r["rank"] for r in rows) == 1 and max(r["rank"] for r in rows) == 25, season


def test_only_poll_teams_are_shown(data_dir, monkeypatch):
    import shutil
    import tempfile
    data = Path(tempfile.mkdtemp(prefix="top")) / "data"
    shutil.copytree(data_dir, data, ignore=shutil.ignore_patterns("site_data", "derived", "polls"))
    seasons = sorted(int(p.stem.split(".")[0]) for p in (data / "games").glob("*.csv.gz"))
    monkeypatch.setattr(config, "SEASONS", seasons)
    monkeypatch.setattr(config, "MIN_MATCHES_D1", 1)
    monkeypatch.setattr(config, "PRED_SIMULATIONS", 50)
    monkeypatch.setattr(config, "SHOW_TOP", 2)
    newest = max(seasons)
    games = store.read(data, "games", newest)
    pick = [games["home"].iat[0], games["away"].iat[0]]
    store.write_json(data / "polls" / f"{newest}.json", {
        f"{newest}-09-01": [{"rank": 1, "team": pick[1], "prev": None}, {"rank": 2, "team": pick[0], "prev": 1}],
        f"{newest}-10-01": [{"rank": 1, "team": pick[0], "prev": 2}, {"rank": 2, "team": pick[1], "prev": 1},
                            {"rank": 3, "team": "someone-else", "prev": 3}]})
    out = data / "site_data"
    ratings.build(data, out, lambda m: None)
    aggregate.build_all(data, lambda m: None)

    teams = store.read_json(out / f"teams_{newest}.json")
    assert {t["id"]: t["poll"] for t in teams} == {pick[0]: 1, pick[1]: 2}        # the newest poll wins
    odds = store.read_json(out / "odds.json")
    assert {t["id"] for t in odds["teams"]} == set(pick)
    war = store.read_json(out / f"war_{newest}.json")
    assert war["rows"] and {r[war["cols"].index("team_id")] for r in war["rows"]} <= set(pick)
    players = store.read_json(out / f"players_{newest}.json")
    assert {r[players["cols"].index("team_id")] for r in players["rows"]} <= set(pick)
    names = {t["team"] for t in teams}
    for g in store.read_json(out / f"games_{newest}.json"):
        assert g["home"] in names or g["away"] in names
    index = store.read_json(out / "player_index.json")
    shown_now = {r[0] for r in index["rows"] if r[index["cols"].index("season")] == newest}
    assert all(pid.split("~")[0] in pick for pid in shown_now)
    for f in (out / "cards").glob("*.json"):
        for team, doc in store.read_json(f)["teams"].items():
            assert team in pick or all(str(newest) not in pl["y"] for pl in doc["players"].values())
    meta = store.read_json(out / "meta.json")
    assert meta["show_top"] == 2 and meta["seasons"][0]["poll"] == {"source": "poll", "through": f"{newest}-10-01"}
    assert meta["seasons"][0]["shown"] == 2 and meta["seasons"][0]["teams"] > 2


def test_every_team_is_shown_when_switched_off(data_dir, monkeypatch):
    seasons = sorted(int(p.stem.split(".")[0]) for p in (Path(data_dir) / "games").glob("*.csv.gz"))
    monkeypatch.setattr(config, "SEASONS", seasons)
    monkeypatch.setattr(config, "MIN_MATCHES_D1", 1)
    monkeypatch.setattr(config, "PRED_SIMULATIONS", 50)
    monkeypatch.setattr(config, "SHOW_TOP", 0)
    out = Path(data_dir) / "site_data"
    ratings.build(data_dir, out, lambda m: None)
    aggregate.build_all(data_dir, lambda m: None)
    meta = store.read_json(out / "meta.json")
    teams = store.read_json(out / f"teams_{meta['seasons'][0]['id']}.json")
    assert len(teams) == meta["seasons"][0]["teams"] and "poll" not in teams[0]
