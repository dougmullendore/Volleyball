"""The week's most-covered stories about the ranked teams.

Articles and highlight videos are read from free feeds: ESPN's women's college
volleyball news, NCAA.com, Volleyball Magazine, and a Google News search for
each ranked team (config.NEWS_FEEDS, config.NEWS_TEAM_SEARCH). None of them
says how many people read or shared an item, so a story's standing is how
widely it was covered: the number of different outlets that ran it, plus a
little for how highly ranked its teams are.

Items about the same match are grouped into one story, found by the teams a
headline names and the schedule (a recap, the highlights and an interview of
Florida's win over Kentucky are one story). Other items about one team join
when their headlines share most of their words.

Posts from X, Instagram and TikTok are not included: none of them offers a free
way to find a week's most popular posts, and their sites block collection.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import config

# Other names a school goes by in headlines, beyond its scoreboard name.
ALSO = {
    "pittsburgh": ["Pitt"], "north-carolina": ["UNC", "Tar Heels"], "byu": ["Brigham Young"],
    "smu": ["Southern Methodist"], "tcu": ["Texas Christian"], "southern-california": ["USC", "Southern California"],
    "ole-miss": ["Ole Miss"], "miami-fl": ["Miami"], "nc-state": ["NC State", "N.C. State"], "uconn": ["UConn"],
    "boston-college": ["Boston College"], "lsu": ["LSU"], "ucla": ["UCLA"],
}
# A school's name followed or preceded by one of these words is another school:
# "Texas" in "Texas Tech", "Kentucky" in "Western Kentucky".
NEXT_OTHER = {"state", "st", "tech", "a&m", "christian", "gulf", "atlantic", "international", "southern", "central",
              "wesleyan", "baptist", "lutheran", "omaha", "kearney", "fort", "arlington", "rio", "el", "martin",
              "wilmington", "greensboro", "asheville", "charlotte", "pembroke", "city", "duluth", "pacific", "mines",
              "tyler", "permian", "valley", "mesa", "college", "and", "&", "adventist", "southwestern", "methodist",
              "a&t", "upstate", "sound", "springs", "university"}
PREV_OTHER = {"north", "south", "east", "west", "central", "northern", "southern", "eastern", "western", "middle",
              "upper", "southeast", "southwest", "northwest", "northeast", "mid", "ut", "arkansas", "george"}
# Headlines about other parts of the sport, or that only sell a stream or list a schedule.
LEAVE_OUT = re.compile(r"\b(men's volleyball|boys|high school|prep|club|beach|sand|live stream|how to watch|"
                       r"watch online|free stream|tv channels?|schedule \d{4}|tickets?|box score)\b", re.I)
# Feeds that only carry women's college volleyball; anything else must say it is about volleyball.
ONLY_VOLLEYBALL = {"ESPN", "NCAA.com"}
ABOUT_VOLLEYBALL = re.compile(r"volleyball|\bNo\. ?\d+\b|#\d+\b|\bsweeps?\b|\bset\b|\bkills?\b|\bdigs?\b|\baces?\b", re.I)
NATIONAL = {"ESPN", "NCAA.com", "Volleyball Magazine", "The Athletic", "USA Today", "Yahoo Sports", "CBS Sports", "On3",
            "FOX Sports", "Big Ten Network", "SEC Network", "Associated Press", "AP News", "Sports Illustrated"}
WORD = re.compile(r"[a-z0-9&']+")
STOP = set("the a an and of to in at on for vs vs. with as by from no is its it's after over volleyball women's "
           "womens college win wins beat beats match sweep sweeps falls fall set sets".split())


def team_phrases(teams) -> list[tuple[str, str]]:
    """(phrase, team id) pairs from {"id", "name"} rows, longest first so
    "Texas A&M" is found before "Texas"."""
    out = set()
    for t in teams:
        if not t.get("id") or not t.get("name"):
            continue
        name = re.sub(r"\s*\((\w+)\)$", "", t["name"])                # "Miami (FL)" is written "Miami"
        for n in {name, name.replace("St.", "State")} | set(ALSO.get(t["id"], [])):
            if len(n) >= 3:
                out.add((n, t["id"]))
    return sorted(out, key=lambda p: (-len(p[0]), p))


def teams_in(text: str, phrases: list[tuple[str, str]]) -> list[str]:
    """The teams a headline names, in the order they appear."""
    starts = {p.split(" ")[0].lower() for p, _ in phrases}
    found, taken = [], []
    for phrase, tid in phrases:
        for m in re.finditer(r"(?<![\w&])" + re.escape(phrase) + r"(?![\w&])", text):
            a, b = m.span()
            if any(a < y and x < b for x, y in taken):
                continue                                  # part of a longer name already found
            if text[b:b + 1] == "-" and text[b + 1:].split(" ", 1)[0].lower() not in starts:
                continue                                  # "Pitt-Bradford", "Nebraska-Kearney"
            if text[a - 1:a] == "-":
                continue
            after = text[b:].lstrip().split(" ", 1)[0].lower().rstrip(".,:;!?")
            before = text[:a].rstrip().rsplit(" ", 1)[-1].lower() if text[:a].strip() else ""
            if after in NEXT_OTHER or before in PREV_OTHER:
                continue
            taken.append((a, b))
            found.append((a, tid))
    order = []
    for _, tid in sorted(found):
        if tid not in order:
            order.append(tid)
    return order


def clean(text: str | None) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def when(text: str | None) -> str | None:
    """A feed's date as an ISO time in UTC."""
    if not text:
        return None
    try:
        d = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def parse_espn(body: bytes) -> list[dict]:
    out = []
    for a in json.loads(body).get("articles", []):
        url = ((a.get("links") or {}).get("web") or {}).get("href")
        if not url or not a.get("headline"):
            continue
        img = next((i.get("url") for i in a.get("images") or [] if i.get("url")), None)
        out.append({"title": clean(a["headline"]), "url": url, "source": "ESPN", "t": when(a.get("published")),
                    "video": a.get("type") == "Media", "img": img, "blurb": clean(a.get("description"))[:240]})
    return out


def parse_rss(body: bytes, source: str | None) -> list[dict]:
    """An RSS feed. With source None the outlet is read from each item (Google News)."""
    out = []
    for it in ET.fromstring(body).iter("item"):
        title, url = clean(it.findtext("title")), (it.findtext("link") or "").strip()
        if not title or not url:
            continue
        src = source or clean(it.findtext("source")) or "News"
        if source is None and title.endswith(" - " + src):
            title = title[: -len(" - " + src)].rstrip()       # Google News adds the outlet to the headline
        img = None
        enc = it.find("enclosure")
        if enc is not None and (enc.get("type") or "").startswith("image"):
            img = enc.get("url")
        blurb = "" if source is None else clean(it.findtext("description"))[:240]   # Google's is the headline again
        out.append({"title": title, "url": url, "source": src, "t": when(it.findtext("pubDate")),
                    "video": "/video/" in url, "img": img, "blurb": blurb})
    return out


def search_name(team: dict) -> str:
    return re.sub(r"\s*\(\w+\)$", "", team["name"]).replace("St.", "State")


def fetch(get, ranked: list[dict]) -> tuple[list[dict], list[str], int]:
    """The fixed feeds and a Google News search per ranked team. A feed that
    fails is reported and skipped. Returns (items, failures, feeds read)."""
    jobs = [(name, kind, url) for name, kind, url in config.NEWS_FEEDS]
    jobs += [(f"Google News: {t['name']}", "google",
              config.NEWS_TEAM_SEARCH.replace("{team}", urllib.parse.quote_plus(search_name(t))))
             for t in ranked if t.get("id")]
    items, failed = [], []
    for name, kind, url in jobs:
        try:
            body = get(url)
            items += parse_espn(body) if kind == "espn" else parse_rss(body, None if kind == "google" else name)
        except Exception as e:                       # noqa: BLE001 - one feed's trouble should not stop the rest
            failed.append(f"{name}: {e}"[:160])
    return items, failed, len(jobs) - len(failed)


def update(stored: dict, items: list[dict], ranked: list[dict], now: dt.datetime) -> dict:
    """Add newly read items about ranked teams to `stored` (keyed by address) and
    drop ones older than config.NEWS_KEEP_DAYS. Items are kept between runs so a
    story stays listed for its week after it drops off a feed."""
    phrases = team_phrases(ranked)
    added = 0
    for it in items:
        text = it["title"] + " " + it.get("blurb", "")
        if not it["t"] or LEAVE_OUT.search(it["title"]):
            continue
        if it["source"] not in ONLY_VOLLEYBALL and not ABOUT_VOLLEYBALL.search(text):
            continue                                  # "Pitt reaches 1,000 digs" passes; "Three matches in Texas" does not
        on = teams_in(text, phrases)
        if not on:
            continue
        key = it["url"]
        if key not in stored:
            added += 1
        stored[key] = {**{k: v for k, v in it.items() if v not in (None, "", False)}, "teams": on}
    cut = (now - dt.timedelta(days=config.NEWS_KEEP_DAYS)).isoformat()
    for key in [k for k, v in stored.items() if v["t"] < cut]:
        del stored[key]
    return {"items": len(stored), "added": added}


def _words(title: str) -> set[str]:
    return {w for w in WORD.findall(title.lower()) if w not in STOP and not w.isdigit()}


def _match_for(it: dict, named: list[str], games_by_team: dict, t: dt.datetime) -> dict | None:
    """The match a headline is about: one a ranked team it names played against
    another team it names, from a day before the item to three days after."""
    best = None
    for tid in it["teams"]:
        for g in games_by_team.get(tid, []):
            other = g["home"]["id"] if g["away"]["id"] == tid else g["away"]["id"]
            if other not in named:
                continue
            start = dt.datetime.fromtimestamp(g["start"], dt.timezone.utc) if g.get("start") else \
                dt.datetime.fromisoformat(g["date"] + "T23:00:00+00:00")
            gap = (t - start).total_seconds() / 86400
            if -1.5 <= gap <= 3.5 and (best is None or abs(gap) < best[0]):
                best = (abs(gap), g)
    return best[1] if best else None


def stories(stored: dict, ranked: list[dict], games: list[dict], names: dict, now: dt.datetime) -> list[dict]:
    """The past week's items grouped into stories, most widely covered first."""
    rank = {t["id"]: t["rank"] for t in ranked if t.get("id")}
    all_phrases = team_phrases([{"id": k, "name": v} for k, v in names.items()])
    games_by_team: dict[str, list] = {}
    for g in games:
        for s in (g["away"], g["home"]):
            if s["id"] in rank:
                games_by_team.setdefault(s["id"], []).append(g)
    since = (now - dt.timedelta(days=7)).isoformat()
    week = sorted((dict(v, teams=[x for x in v["teams"] if x in rank]) for v in stored.values() if v["t"] >= since),
                  key=lambda v: v["t"])
    groups: dict = {}
    loose: list[dict] = []
    seen_titles: set[str] = set()
    for it in week:
        if not it["teams"]:
            continue                                   # every team it names has since left the poll
        title = re.sub(r"\W+", " ", it["title"].lower()).strip()
        if title in seen_titles:
            continue                                   # the same article reached through two feeds
        seen_titles.add(title)
        t = dt.datetime.fromisoformat(it["t"])
        named = teams_in(it["title"] + " " + it.get("blurb", ""), all_phrases)
        g = _match_for(it, named, games_by_team, t)
        if g:
            home = groups.setdefault(("match", g["id"]), {"teams": [x for x in (g["away"]["id"], g["home"]["id"]) if x in rank],
                                                          "match": g, "items": []})
            home["items"].append(it)
            continue
        words = _words(it["title"])
        home = None
        for grp in loose:
            if set(grp["teams"]) != set(it["teams"]) or abs((t - grp["t"]).total_seconds()) > 3 * 86400:
                continue
            if len(it["teams"]) >= 3 or len(words & grp["words"]) >= 0.5 * max(1, min(len(words), len(grp["words"]))):
                home = grp
                break
        if home is None:
            home = {"teams": it["teams"], "t": t, "words": set(), "items": []}
            loose.append(home)
        home["items"].append(it)
        home["words"] |= words
    out = []
    for g in list(groups.values()) + loose:
        sources = {i["source"] for i in g["items"]}
        heads = sorted(g["teams"], key=lambda x: rank[x])[:2]
        score = 2 * len(sources) + sum((26 - rank[x]) / 25 for x in heads) + (1 if NATIONAL & sources else 0)
        # the lead: a written article from a national outlet if there is one, else the newest written one
        lead = max(g["items"], key=lambda i: (not i.get("video"), i["source"] in NATIONAL, bool(i.get("img")), i["t"]))
        img = lead.get("img") or next((i["img"] for i in g["items"] if i.get("img")), None)
        rest = sorted((i for i in g["items"] if i is not lead), key=lambda i: i["t"], reverse=True)
        story = {"score": round(score, 2), "teams": sorted(g["teams"], key=lambda x: rank[x]), "sources": len(sources),
                 "t": max(i["t"] for i in g["items"]),
                 "lead": {k: lead[k] for k in ("title", "url", "source", "t", "video", "blurb") if lead.get(k)}
                 | ({"img": img} if img else {}),
                 "more": [{k: i[k] for k in ("title", "url", "source", "t", "video") if i.get(k)} for i in rest]}
        m = g.get("match")
        if m:
            story["match"] = {"id": m["id"], "date": m["date"], "state": m["state"],
                              "away": {k: m["away"].get(k) for k in ("id", "name", "sets")},
                              "home": {k: m["home"].get(k) for k in ("id", "name", "sets")}}
        out.append(story)
    out.sort(key=lambda s: (s["score"], s["t"]), reverse=True)     # ties: the newer story first
    return out[:config.NEWS_STORIES]
