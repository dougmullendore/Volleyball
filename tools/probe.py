"""One-off look at what the NCAA's public feeds return for women's volleyball.
Saves raw responses so the real pipeline can be written against real data."""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (compatible; volleyball-stats-site/1.0)"
G = "https://sdataprod.ncaa.com/"
H = {"scoreboard": "7287cda610a9326931931080cb3a604828febe6fe3c9016a7e4a36db99efdb7c",
     "schedule": "a25ad021179ce1d97fb951a49954dc98da150089f9766e7e85890e439516ffbf",
     "game": "93a02c7193c89d85bcdda8c1784925d9b64657f73ef584382e2297af555acd4b",
     "box": "4320484382257c2a7ac3be318db2dee09a7fb74029448825c285d5dbdda365ae",
     "teamstats": "9b4d5dcdc81e3df6a8388700f2d54c43a4cf9680ee85eab5b89e4c0e17bedbb2",
     "pbp": "57f922d56d60d88326b62202b3d88e8cd3cfb6687931bc0b5b3dfab089b84faa"}
report = []

def get(url, name):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read(); code = r.status
    except urllib.error.HTTPError as e:
        body = e.read(); code = e.code
    except Exception as e:
        body = repr(e).encode(); code = 0
    (OUT / name).write_bytes(body)
    report.append(f"{code} {len(body):>8} {time.time()-t0:5.2f}s {name}")
    print(report[-1], flush=True)
    try:
        return json.loads(body)
    except Exception:
        return None

def gql(kind, variables, name, extra=""):
    ext = json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H[kind]}}, separators=(",", ":"))
    url = G + "?" + extra + "extensions=" + urllib.parse.quote(ext) + "&variables=" + urllib.parse.quote(json.dumps(variables, separators=(",", ":")))
    return get(url, name)

for season in (2026, 2025, 2021, 2018):
    gql("schedule", {"sportCode": "WVB", "division": 1, "seasonYear": season}, f"schedule_{season}.json", "queryName=NCAA_schedules_today_web&")

dates = ["2026/10/03", "2026/10/10", "2026/08/28", "2025/10/04", "2025/12/21", "2024/10/05", "2023/10/07",
         "2022/10/08", "2021/10/09", "2019/10/05", "2017/10/07"]
for d in dates:
    y, m, _ = d.split("/")
    tag = d.replace("/", "")
    sb = gql("scoreboard", {"sportCode": "WVB", "division": 1, "seasonYear": int(y), "contestDate": d}, f"sb_{tag}.json")
    # also the other date spelling, in case the feed wants it
    mm = d[5:] + "/" + y
    gql("scoreboard", {"sportCode": "WVB", "division": 1, "seasonYear": int(y), "contestDate": mm}, f"sb_alt_{tag}.json")
    get(f"https://data.ncaa.com/casablanca/scoreboard/volleyball-women/d1/{d}/scoreboard.json", f"old_sb_{tag}.json")
    contests = ((sb or {}).get("data") or {}).get("contests") or []
    finals = [c for c in contests if c.get("gameState") == "F"][:3]
    for c in finals:
        cid = c.get("contestId")
        gql("game", {"id": str(cid), "week": None, "staticTestEnv": None}, f"game_{cid}.json", "meta=GetGamecenterGameById_web&")
        gql("box", {"contestId": str(cid), "staticTestEnv": None}, f"box_{cid}.json")
        gql("teamstats", {"contestId": str(cid), "staticTestEnv": None}, f"teamstats_{cid}.json")
        gql("pbp", {"contestId": str(cid), "staticTestEnv": None}, f"pbp_{cid}.json")
        get(f"https://data.ncaa.com/casablanca/game/{cid}/pbp.json", f"old_pbp_{cid}.json")
        get(f"https://data.ncaa.com/casablanca/game/{cid}/boxscore.json", f"old_box_{cid}.json")

for path, name in [("https://www.ncaa.com/json/schools", "schools.json"),
                   ("https://www.ncaa.com/rankings/volleyball-women/d1/ncaa-womens-volleyball-rpi", "rpi.html"),
                   ("https://www.ncaa.com/rankings/volleyball-women/d1/avca-coaches", "avca.html"),
                   ("https://www.ncaa.com/standings/volleyball-women/d1", "standings.html"),
                   ("https://data.ncaa.com/casablanca/schedule/volleyball-women/d1/2025/10/schedule-all-conf.json", "old_schedule_2025_10.json"),
                   ("https://stats.ncaa.org/rankings/change_sport_year_div", "statsncaa.html")]:
    get(path, name)

# speed test: 30 quick requests, to see whether the feed throttles
t0 = time.time(); codes = {}
for i in range(30):
    try:
        ext = json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H["scoreboard"]}}, separators=(",", ":"))
        v = json.dumps({"sportCode": "WVB", "division": 1, "seasonYear": 2025, "contestDate": f"2025/09/{i+1:02d}"}, separators=(",", ":"))
        req = urllib.request.Request(G + "?extensions=" + urllib.parse.quote(ext) + "&variables=" + urllib.parse.quote(v), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            n = len(json.loads(r.read()).get("data", {}).get("contests") or []); codes[i + 1] = n
    except Exception as e:
        codes[i + 1] = repr(e)[:60]
report.append(f"speed: 30 requests in {time.time()-t0:.1f}s -> {codes}")
(OUT / "REPORT.txt").write_text("\n".join(report) + "\n")
