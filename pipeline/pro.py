"""The pro leagues: League One Volleyball (LOVB) and Major League Volleyball (MLV).

Their results and box scores come from the volleydata project
(github.com/awosoga/volleydata), which collects them from the leagues' own
match centres and publishes them as CSV files. Each league gets its own copy
of the site, in a folder of the published site (lovb/, mlv/), built from the
same pages as the college site: matches, standings with the GOAT ranking,
team stats, players and box scores.

A league's standings take the place of the college poll: every team in the
league is "ranked", by wins and then by set ratio.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from pathlib import Path

from . import box, config, goat, odds, players, teams, web

LEAGUES = {
    # site folder: (volleydata name, league name, standings name)
    "lovb": ("lovb", "LOVB", "LOVB standings"),
    "mlv": ("pvf", "MLV", "MLV standings"),
}
FILES = ["schedule", "player_boxscore", "player_info", "pbp"]
DATA_URL = "https://github.com/awosoga/volleydata/releases/download/{lg}-{tag}/{lg}_{kind}{season}.csv"
# badge colours, one per team
COLORS = ["#1d4ed8", "#b91c1c", "#047857", "#7c3aed", "#c2410c", "#0e7490", "#a21caf", "#4d7c0f", "#be123c", "#334155"]
# volleystation's position numbers
POSITION = {"1": "L", "2": "OH", "3": "OPP", "4": "MB", "5": "S"}


def slug(name: str) -> str:
    name = re.sub(r"^LOVB\s+", "", name.strip())
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def short_name(name: str) -> str:
    return re.sub(r"^LOVB\s+", "", name.strip())


def _f(v) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def download(state: Path, log) -> dict:
    """Fetch each league's CSV files into <state>/pro/. A failed download keeps
    the copy from the last run."""
    folder = state / "pro"
    folder.mkdir(parents=True, exist_ok=True)
    got, failed = 0, []
    for site, (lg, *_rest) in LEAGUES.items():
        for kind in FILES:
            # play-by-play comes one file per season: only the newest is needed (for set scores)
            season = ""
            if kind == "pbp":
                sched = folder / f"{lg}_schedule.csv"
                if not sched.exists():
                    continue
                season = "_" + max(r["season"] for r in csv.DictReader(sched.open(encoding="utf-8")))
            url = DATA_URL.format(lg=lg, tag=kind.replace("_", "-"), kind=kind, season=season)
            try:
                raw = web.get_bytes(url, timeout=60, tries=2)
                if not raw.startswith(b"match_id") and not raw.startswith(b"season") and b"," not in raw[:200]:
                    raise ValueError("not a CSV file")
                if kind == "pbp":      # only the set scores are kept from the (large) play-by-play file
                    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8", "replace"))))
                    (folder / f"{lg}_sets.json").write_text(json.dumps(_set_scores(rows)), encoding="utf-8")
                else:
                    (folder / f"{lg}_{kind}.csv").write_bytes(raw)
                got += 1
            except Exception as e:
                failed.append(f"{lg}_{kind}: {e!r}"[:120])
    log(f"pro leagues: {got} data files downloaded" + (f"; kept the old copy of {failed}" if failed else ""))
    return {"downloaded": got, "failed": failed}


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def _set_scores(pbp: list[dict]) -> dict:
    """{match id: {"home": [points per set], "away": [...]}} from play-by-play:
    the score after the last rally of each set."""
    out = {}
    if not pbp:
        return out
    cols = pbp[0].keys()
    hk = next((c for c in ("home_team_score", "home_score", "score_home") if c in cols), None)
    ak = next((c for c in ("away_team_score", "away_score", "score_away") if c in cols), None)
    sk = next((c for c in ("set_number", "set") if c in cols), None)
    if not (hk and ak and sk):
        return out
    last = {}
    for r in pbp:
        try:
            key = (r["match_id"], int(float(r[sk])))
            last[key] = (_f(r[hk]), _f(r[ak]))
        except (KeyError, ValueError):
            continue
    for (mid, s), (h, a) in sorted(last.items()):
        d = out.setdefault(mid, {"home": [], "away": []})
        d["home"].append(h)
        d["away"].append(a)
    return out


def load(state: Path, site: str) -> dict | None:
    """One league's season: games (in the college site's shape), box scores,
    team names and the season. None if its files are missing."""
    lg = LEAGUES[site][0]
    folder = state / "pro"
    sched = _rows(folder / f"{lg}_schedule.csv")
    if not sched:
        return None
    season = max(r["season"] for r in sched)
    sched = [r for r in sched if r["season"] == season and "all" not in (r["phase"] or "").lower().replace("-", "")]   # not the All-Star match
    ids = {r["match_id"] for r in sched}
    boxrows = [r for r in _rows(folder / f"{lg}_player_boxscore.csv") if r["match_id"] in ids]
    info = {}
    for r in _rows(folder / f"{lg}_player_info.csv"):
        if r["match_id"] in ids:
            info[(r["match_id"], r["player_name"])] = r
    sets_file = folder / f"{lg}_sets.json"
    scores = json.loads(sets_file.read_text(encoding="utf-8")) if sets_file.exists() else {}

    # the start time and each side's full team name come from the box scores
    start, side_name = {}, {}
    for r in boxrows:
        if r["match_id"] not in start and r.get("match_datetime"):
            try:
                start[r["match_id"]] = int(dt.datetime.fromisoformat(r["match_datetime"].replace("Z", "+00:00")).timestamp())
            except ValueError:
                pass
        side_name[(r["match_id"], r["team_involved"])] = r["team_name"]

    names, games = {}, []
    for r in sched:
        h, a = _f(r["home_team_set_wins"]), _f(r["away_team_set_wins"])
        played = h + a > 0
        g = {"id": int(r["match_id"]), "date": r["date"], "start": start.get(r["match_id"]),
             "state": "final" if played else "upcoming", "note": "",
             "round": "" if re.match(r"(?i)week|regular", r["phase"] or "") else (r["phase"] or "").title()}
        for side, col in (("home", "home_team"), ("away", "away_team")):
            nm = short_name(side_name.get((r["match_id"], side)) or r[col])
            tid = slug(nm)
            names[tid] = nm
            g[side] = {"id": tid, "name": nm, "sets": (h if side == "home" else a) if played else None}
        games.append(g)
    games.sort(key=lambda g: (g["date"], g["start"] or 0, g["id"]))

    # box scores, one row per player per match in pipeline/box.py's columns
    per = {}
    for r in boxrows:
        key = (r["match_id"], r["team_involved"], r["player_name"])
        p = per.setdefault(key, {"r": r, "sets": 0, **{c: 0 for c in box.COLS[6:]}})
        if _f(r.get("serves")) + _f(r.get("attack_attempts")) + _f(r.get("receptions")) + _f(r.get("successful_digs")) \
                + _f(r.get("assists")) + _f(r.get("block_points")) + _f(r.get("block_touches")) > 0 or r.get("set_starting_position") not in ("", None):
            p["sets"] += 1
        p["k"] += _f(r["attack_kills"]); p["e"] += _f(r["attack_errors"]); p["ta"] += _f(r["attack_attempts"])
        p["ast"] += _f(r["assists"]); p["sa"] += _f(r["serve_aces"]); p["se"] += _f(r["serve_errors"])
        p["sv"] += _f(r["serves"]); p["d"] += _f(r["successful_digs"]); p["ra"] += _f(r["receptions"])
        p["re"] += _f(r["reception_errors"]); p["bs"] += _f(r["block_points"])
    boxes = {}
    for (mid, side, pname), p in per.items():
        r, i = p["r"], info.get((mid, pname)) or {}
        pos = POSITION.get(str(i.get("primary_position", "")).split(".")[0], "")
        if (i.get("is_libero") or r.get("is_libero")) == "True":
            pos = "L"
        starter = 1 if (i.get("set_1_is_starter") == "True" or (r.get("set_number") == "1" and r.get("set_starting_position") not in ("", "*", None))) else 0
        num = _f(r.get("player_number")) if r.get("player_number") not in ("", None) else None
        row = [r["first_name"] or "", r["last_name"] or pname, num, pos, starter, p["sets"]] + [p[c] for c in box.COLS[6:]]
        b = boxes.setdefault(mid, {"home": [], "away": [], "status": "F", "tsets": {}})
        b[side].append(row)
    for mid, s in scores.items():
        if mid in boxes:
            boxes[mid]["setpts"] = s
    # each team's short code (HOU, IND...), for the badge shown in place of a logo
    abbr = {}
    for (mid, pname), i in info.items():
        tid = slug(i.get("team_name") or "")
        if tid in names and i.get("team_code"):
            abbr[tid] = i["team_code"][:3].upper()
    return {"season": int(season), "games": games, "boxes": boxes, "names": names, "abbr": abbr}


def standings(games: list[dict], names: dict, through: str | None = None, points: bool = False) -> list[dict]:
    """Every team by wins, then win share, then set ratio, from finals up to `through`.
    With `points` (MLV's table): by points first, 3 for a win in three or four sets,
    2 for a win in five, 1 for a loss in five."""
    rec = {t: {"w": 0, "l": 0, "sw": 0, "sl": 0, "pts": 0} for t in names}
    for g in games:
        if g["state"] != "final" or (through and g["date"] > through) or g.get("round"):   # the regular season only
            continue
        for s, o in (("home", "away"), ("away", "home")):
            x = rec[g[s]["id"]]
            x["w" if g[s]["sets"] > g[o]["sets"] else "l"] += 1
            x["sw"] += g[s]["sets"]; x["sl"] += g[o]["sets"]
            five = g[s]["sets"] + g[o]["sets"] >= 5
            x["pts"] += (2 if five else 3) if g[s]["sets"] > g[o]["sets"] else (1 if five else 0)
    order = sorted(names, key=lambda t: (-(rec[t]["pts"] if points else 0), -rec[t]["w"], -(rec[t]["w"] / max(1, rec[t]["w"] + rec[t]["l"])),
                                         -(rec[t]["sw"] / max(1, rec[t]["sl"])), names[t]))
    return [{"rank": i + 1, "id": t, "name": names[t], "record": f"{rec[t]['w']}-{rec[t]['l']}", "pts": rec[t]["pts"]} for i, t in enumerate(order)]


def build(state: Path, out: Path, site: str, now: dt.datetime, words: dict, write_json, match_files, log) -> dict:
    """Write one league's site into out/<site>/ (the page files are copied by the caller)."""
    lg, league, poll_name = LEAGUES[site]
    s = load(state, site)
    if not s:
        log(f"{league}: no data yet")
        return {"teams": 0}
    games, boxes, names = s["games"], s["boxes"], s["names"]
    finals = [g for g in games if g["state"] == "final"]
    through = max((g["date"] for g in finals if not g.get("round")), default=None)
    table = standings(games, names, through, points=site == "mlv")
    week_ago = (dt.date.fromisoformat(through) - dt.timedelta(days=7)).isoformat() if through else None
    before = {t["id"]: t["rank"] for t in standings(games, names, week_ago, points=site == "mlv")} if week_ago and any(g["date"] <= week_ago for g in finals) else {}
    for t in table:
        t["prev"] = before.get(t["id"])
    rank = {t["id"]: t["rank"] for t in table}
    for g in games:
        for side in ("home", "away"):
            g[side]["rank"] = rank.get(g[side]["id"])

    rating, pregame = odds.rate(games, {})
    for g in games:
        if g["state"] != "final" and g["home"]["id"] in rating and g["away"]["id"] in rating:
            g["p"] = round(odds.match_chance(rating[g["home"]["id"]], rating[g["away"]["id"]], False), 3)
        elif g["id"] in pregame:
            g["p0"] = round(pregame[g["id"]], 3)

    # the GOAT order of the league's teams, and each team's results against the others
    ranking = goat.rank(games, rating, set(names), rank)
    results = goat.head_to_head(finals)
    place = {t: i + 1 for i, t in enumerate(ranking["order"])}

    def versus(tid, among):
        beat, lost = [], []
        for other in sorted(among, key=among.get):
            wins, losses, _ = results.get((tid, other), (0, 0, []))
            if wins:
                beat.append([among[other], names[other], wins, other])
            if losses:
                lost.append([among[other], names[other], losses, other])
        return beat, lost

    for t in table:
        t["goat"] = place.get(t["id"])
        t["beat"], t["lost"] = versus(t["id"], rank)
    top = []
    for i, tid in enumerate(ranking["order"]):
        won = sum(v[0] for (a, _), v in results.items() if a == tid)
        lost = sum(v[1] for (a, _), v in results.items() if a == tid)
        b, l = versus(tid, place)
        top.append({"rank": i + 1, "id": tid, "name": names[tid], "avca": rank.get(tid), "score_rank": ranking["base"][tid],
                    "factors": ranking["factors"][tid], "record": f"{won}-{lost}", "beat": b, "lost": l})

    rated = players.compute(table, games, boxes)
    rated["through"] = max((g["date"] for g in finals), default=None)
    media_file = state / "pro" / f"{site}_media.json"
    media = json.loads(media_file.read_text(encoding="utf-8")) if media_file.exists() else {}
    found = media.get("players") or {}
    others = {}                     # the other league's site, for players who have played in both
    for other in LEAGUES:
        f = state / "pro" / f"{other}_media.json"
        if other != site and f.exists():
            others.update(json.loads(f.read_text(encoding="utf-8")).get("players") or {})
    for p in rated["players"]:
        m = found.get(name_key(p["name"]))
        if not (m and m.get("photo")) and (others.get(name_key(p["name"])) or {}).get("photo"):
            m = {**others[name_key(p["name"])], "bio": {**(others[name_key(p["name"])].get("bio") or {}), **((m or {}).get("bio") or {})}}
        if m:
            if m.get("photo"):
                p["photo"] = m["photo"]
            if m.get("bio"):
                p["bio"] = m["bio"]
    logos = {t: v["logo"] for t, v in (media.get("teams") or {}).items() if v.get("logo") and t in names}
    dest = out / site
    with_box = match_files(dest, games, boxes, rated)
    for g in games:              # set by set, for the match page
        b = boxes.get(str(g["id"])) or {}
        if b.get("setpts"):
            g["setpts"] = [b["setpts"]["away"], b["setpts"]["home"]]
    write_json(dest / "data.json", {
        "site": config.SITE_NAME, "league": site, "league_name": league, "pro": True,
        "updated": now.isoformat(timespec="seconds"), "season": s["season"],
        "poll": {"name": poll_name, "through": through, "teams": table, "polls_seen": []},
        "game_page": None, "live_feed": None, "live_seconds": config.LIVE_SECONDS, "logo": None,
        "odds_tested": None, "goat": {"top": [], "weight": config.GOAT_HEAD_TO_HEAD, "weights": config.GOAT_WEIGHTS,
                                      "poll_wrong": goat.contradictions([t["id"] for t in table], finals, set(names)),
                                      "goat_wrong": goat.contradictions(ranking["order"], finals, set(names))},
        "nr": {}, "words": words, "logos": logos,
        "abbr": {t: [((media.get("teams") or {}).get(t) or {}).get("abbr") or s["abbr"].get(t) or names[t][:3].upper(),
                     ((media.get("teams") or {}).get(t) or {}).get("color") or COLORS[i % len(COLORS)]] for i, t in enumerate(sorted(names))}, "d1": [[t["id"], t["name"]] for t in table], "games": games})
    write_json(dest / "players.json", rated)
    write_json(dest / "teams.json", teams.compute(table, games, boxes, rating))
    log(f"{league}: {s['season']} season, {len(games)} matches ({len(finals)} played), {len(names)} teams, "
        f"{len(rated['players'])} players, {with_box} box scores")
    return {"season": s["season"], "matches": len(games), "played": len(finals), "teams": len(names),
            "players": len(rated["players"]), "box_scores": with_box}


# ---- logos, photos and player details, from the leagues' own websites ----
LOVB_SITE = "https://www.lovb.com"
MLV_SITE = "https://provolleyball.com"
MEDIA_DAYS = 7                     # read again after this many days


def name_key(s: str) -> str:
    return players._norm(s or "")


def _next_data(page: str) -> str:
    """The text of a Next.js page's data chunks (self.__next_f.push([1, "..."]))."""
    out = []
    for c in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', page, re.S):
        try:
            out.append(json.loads('"' + c + '"'))
        except ValueError:
            continue
    return "".join(out)


def _inertia(page: str) -> dict:
    import html as _html
    m = re.search(r'data-page="([^"]*)"', page)
    return json.loads(_html.unescape(m.group(1))).get("props", {}) if m else {}


def _plain(src: str | None) -> str | None:
    """The original picture behind a provolleyball.com image-service address (its
    last part is the original address in base64). The service's own addresses are
    signed, so they cannot be resized."""
    if not src:
        return None
    import base64
    tail = src.rsplit("/", 1)[-1].split(".")[0]
    try:
        url = base64.urlsafe_b64decode(tail + "=" * (-len(tail) % 4)).decode()
        if url.startswith("https://"):
            return url
    except Exception:
        pass
    return src


def _small(img: dict | None) -> str | None:
    """The smallest size the image service offers (its addresses are signed, so
    only the sizes it lists will load), else the original picture."""
    best = None
    for part in ((img or {}).get("srcset") or "").split(","):
        bits = part.strip().split(" ")
        if len(bits) == 2 and bits[1].endswith("w") and bits[1][:-1].isdigit():
            if best is None or int(bits[1][:-1]) < best[0]:
                best = (int(bits[1][:-1]), bits[0])
    return best[1] if best else _plain((img or {}).get("src"))


def _height(v) -> str | None:
    m = re.match(r"\s*(\d)\s*[-' ]\s*(\d{1,2})", str(v or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _social(links: dict) -> dict:
    out = {}
    for net, url in links.items():
        if isinstance(url, str) and url.startswith("http"):
            out[net] = url.split("?")[0].rstrip("/#")
    return out


# players whose page uses another form of their name than the statistics do
ALIASES = {"madirishel": "madi-kingdon-rishel"}


def _lovb_athletes(text: str) -> dict:
    people = {}
    for m in re.finditer(r'\{"id":"\d+","audioUrl":.*?"xTwitter":(?:null|"[^"]*")\}', text):
        try:
            a = json.loads(m.group(0))
        except ValueError:
            continue
        if not a.get("fullName"):
            continue
        bio = {}
        if _height(a.get("height")):
            bio["ht"] = _height(a.get("height"))
        if a.get("collegeOrClub"):
            bio["col"] = a["collegeOrClub"].strip()[:60]
        soc = _social({"instagram": a.get("instagram"), "twitter": a.get("xTwitter"), "tiktok": a.get("tiktok")})
        if soc:
            bio["social"] = soc
        photo = (LOVB_SITE + a["headshotUrl"]) if a.get("headshotUrl") and "filler" not in a["headshotUrl"] else None
        people[name_key(a["fullName"])] = {"photo": photo, "bio": bio}
    return people


def lovb_media(fetch, log, wanted: dict | None = None) -> dict:
    """Team logos and every listed athlete's headshot, height, college and
    social links, from the team roster pages on lovb.com."""
    home = _next_data(fetch(LOVB_SITE + "/teams/lovb-houston-volleyball/roster"))
    teams, people = {}, {}
    for m in re.finditer(r'\{"id":\d+,"fullName":"(LOVB [^"]+)","href":"(/teams/[a-z-]+)","squareLogoUrl":"([^"]+)"', home):
        teams[slug(m.group(1))] = {"logo": LOVB_SITE + m.group(3), "href": m.group(2)}
    for tid, t in teams.items():
        try:
            text = home if t["href"].endswith("houston-volleyball") else _next_data(fetch(LOVB_SITE + t["href"] + "/roster"))
        except Exception as e:
            log(f"LOVB roster of {tid}: {e!r}"[:120])
            continue
        people.update(_lovb_athletes(text))
    # a player who has moved on since: her page under the team she played for
    for full, tid in (wanted or {}).items():
        if name_key(full) in people or tid not in teams:
            continue
        page = None
        plain = re.sub(r"['’.]", "", full.lower())                 # "Brie O'Reilly" -> brie-oreilly
        words = plain.split()
        cands = [ALIASES.get(name_key(full))] + [re.sub(r"[^a-z0-9]+", "-", c).strip("-") for c in
                                                   dict.fromkeys([plain, full.lower(), " ".join([words[0], words[-1]]) if len(words) > 2 else plain])]
        for cand in [c for c in cands if c]:
            for base in (LOVB_SITE + teams[tid]["href"] + "/athletes/", LOVB_SITE + "/athletes/"):
                try:
                    page = fetch(base + cand)
                    break
                except Exception:
                    continue
            if page is not None:
                break
        if page is None:
            continue
        found = _lovb_athletes(_next_data(page))
        if found:
            people.update(found)
            continue
        # an older athlete page: only her picture, as the page's share image
        title = re.search(r"<title>([^<]+)</title>", page)
        img = re.search(r'<meta property="og:image" content="([^"]+)"', page)
        same = title and (name_key(title.group(1)) == name_key(full) or ALIASES.get(name_key(full)) or
                          (name_key(title.group(1).split()[0]) == name_key(full.split()[0]) and name_key(title.group(1).split()[-1]) == name_key(full.split()[-1])))
        if same and img and "/api/media/" in img.group(1):
            people[name_key(full)] = {"photo": img.group(1).replace("&amp;", "&"), "bio": {}}
    return {"teams": {k: {"logo": v["logo"]} for k, v in teams.items()}, "players": people}


def mlv_media(fetch, names: list[str], log, extra: list[str] = ()) -> dict:
    """Team logos and colours from provolleyball.com, and each player's headshot,
    height, hometown, college and social links from her page there."""
    teams = {}
    api = web.get_bytes(MLV_SITE + "/api/teams", timeout=20, tries=2, headers={"Accept": "application/json"})
    for t in json.loads(api).get("data", []):
        if not t.get("current_roster_id"):
            continue
        logo = None
        try:
            team = _inertia(fetch(MLV_SITE + t["permalink"] + "/roster")).get("team") or {}
            logo = _small(team.get("logo"))
        except Exception:
            pass
        teams[slug(t["name"])] = {"logo": logo, "color": t.get("color"), "abbr": t.get("abbreviation")}
    # every player the league lists, to find each one's page address (slug)
    listed, page_no = {}, 1
    while page_no < 20:
        try:
            got = json.loads(web.get_bytes(f"{MLV_SITE}/api/players?per_page=200&page={page_no}", timeout=20, tries=2,
                                           headers={"Accept": "application/json"})).get("data") or []
        except Exception:
            break
        for p in got:
            listed.setdefault(name_key(p.get("full_name")), p["slug"])
            for w in re.split(r"[\s-]+", p.get("last_name") or ""):      # each part of a double surname
                if len(name_key(w)) >= 3:
                    listed.setdefault("~" + name_key(w) + name_key(p.get("first_name"))[:3], p["slug"])
        if len(got) < 200:
            break
        page_no += 1
    people = {}
    # players from the other league who also have a page here (many have played in both)
    names = list(names) + [n for n in extra if name_key(n) in listed]
    for full in names:
        first, _, rest = full.partition(" ")
        tries = [listed.get(name_key(full))] + [listed.get("~" + name_key(w) + name_key(first)[:3])
                                               for w in reversed(re.split(r"[\s-]+", rest)) if len(name_key(w)) >= 3]
        page_slug = next((t for t in tries if t), None) or re.sub(r"[^a-z0-9]+", "-", full.lower()).strip("-")
        try:
            p = _inertia(fetch(MLV_SITE + "/player/" + page_slug)).get("player")
        except Exception:
            continue
        if not p:
            continue
        bio = {}
        if p.get("height_feet"):
            bio["ht"] = f'{p["height_feet"]}-{p.get("height_inches") or 0}'
        if p.get("weight") and str(p["weight"]).isdigit():
            bio["wt"] = int(p["weight"])
        if p.get("hometown"):
            bio["home"] = p["hometown"][:60]
        if p.get("college"):
            bio["col"] = p["college"][:60]
        if p.get("birth_date"):
            bio["born"] = str(p["birth_date"])[:10]
        links = {}
        for s in p.get("social_links") or []:
            net = ((s.get("social_network") or {}).get("name") or "").lower()
            net = "twitter" if net in ("x", "twitter") else net
            if net in ("instagram", "twitter", "tiktok"):
                links[net] = s.get("account")
        if _social(links):
            bio["social"] = _social(links)
        photo = _small(p.get("headshot_image"))
        people[name_key(full)] = {"photo": photo, "bio": bio}
    return {"teams": teams, "players": people}


def update_media(state: Path, today: dt.date, log) -> dict:
    """Read the leagues' websites for logos, photos and player details, once a week."""
    fetch = lambda url: web.get_bytes(url, timeout=20, tries=2).decode("utf-8", "replace")
    res = {}
    for site in LEAGUES:
        path = state / "pro" / f"{site}_media.json"
        have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if have.get("finder") != 5:          # this file has learned a new way to find players since: read again
            have = {k: v for k, v in have.items() if k != "checked"}
        no_logos = not any(v.get("logo") for v in (have.get("teams") or {}).values())
        if have.get("checked") and (today - dt.date.fromisoformat(have["checked"])).days < MEDIA_DAYS and not no_logos:
            res[site] = "up to date"
            continue
        try:
            s = load(state, site)
            if site == "lovb":
                wanted = {}
                for mid, b in (s or {}).get("boxes", {}).items():
                    g = next((g for g in s["games"] if str(g["id"]) == mid), None)
                    for side in ("home", "away"):
                        for r in b[side]:
                            if g:
                                wanted[(r[0] + " " + r[1]).strip()] = g[side]["id"]
                got = lovb_media(fetch, log, wanted)
            else:
                names = sorted({(r[0] + " " + r[1]).strip() for b in (s or {}).get("boxes", {}).values() for side in ("home", "away") for r in b[side]})
                other = load(state, "lovb") or {}
                extra = sorted({(r[0] + " " + r[1]).strip() for b in other.get("boxes", {}).values() for side in ("home", "away") for r in b[side]})
                got = mlv_media(fetch, names, log, extra)
        except Exception as e:
            log(f"{site} logos and photos: {e!r}"[:160])
            res[site] = f"failed: {e!r}"[:120]
            continue
        # keep what an earlier reading found for anyone this one missed
        got["players"] = {**(have.get("players") or {}), **{k: v for k, v in got["players"].items() if v.get("photo") or v.get("bio")}}
        got["teams"] = {**(have.get("teams") or {}), **{k: v for k, v in got["teams"].items() if v.get("logo") or k not in (have.get("teams") or {})}}
        got["checked"] = today.isoformat()
        got["finder"] = 5
        path.write_text(json.dumps(got), encoding="utf-8")
        res[site] = {"teams": len(got["teams"]), "players": len(got["players"]),
                     "with_photo": sum(1 for v in got["players"].values() if v.get("photo"))}
        log(f"{site}: logos for {len(got['teams'])} teams, details for {len(got['players'])} players")
    return res
