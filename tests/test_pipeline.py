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
