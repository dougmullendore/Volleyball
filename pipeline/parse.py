"""Turn the NCAA's raw scoreboard, box score and play-by-play into flat rows.

Three tables come out of here:
  games    one row per match (scheduled or finished)
  box      one row per player per match: the official box score line
  rallies  one row per point: who won it, how, and who served

The play-by-play also lists substitutions, but only the player coming in, and
libero swaps are mixed in with them, so who is on the court at any moment
cannot be worked out reliably. Those lines are ignored.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

GAME_COLS = ["game_id", "season", "date", "start_epoch", "state", "home", "away",
             "home_name", "away_name", "home_div", "away_div", "home_conf", "away_conf",
             "home_sets", "away_sets", "set_scores", "venue", "city", "round",
             "detail", "pbp_sets"]
BOX_COLS = ["game_id", "team", "is_home", "row", "first", "last", "number", "pos",
            "starter", "sets", "k", "e", "ta", "ast", "sa", "se", "sv", "d", "ra", "re",
            "bs", "ba", "be", "bhe", "pts"]
RALLY_COLS = ["game_id", "set", "n", "home_won", "hs", "vs", "type", "p1", "p2", "p3",
              "serve_home"]

# How a point ended. The player columns mean different things for each:
#   K    kill:               p1 hitter (winning team), p2 setter (winning team)
#   AE   attack error:       p1 hitter (losing team)
#   BLK  blocked attack:     p1 hitter (losing team), p2/p3 blockers (winning team)
#   ACE  service ace:        p1 passer charged with the error (losing team)
#   SE   service error:      no player is named in the feed
#   BSE  bad set:            p1 setter (losing team)
#   BHE  ball handling error p1 player (losing team)
#   OTH  anything else that changed the score
POINT_TYPES = ("K", "AE", "BLK", "ACE", "SE", "BSE", "BHE", "OTH")

_KILL = re.compile(r"^Kill by\s+(.+?)\s*(?:\(\s*from\s+(.+?)\s*\))?\s*\.?\s*$", re.I)
_ATTACK = re.compile(r"^Attack error(?:\s+by\s+(.+?))?\s*(?:\(\s*(block by|from)\s+(.+?)\s*\))?\s*\.?\s*$", re.I)
_ACE = re.compile(r"^Service ace\s*(?:\(\s*(.*?)\s*\))?", re.I)
_SERR = re.compile(r"^Service error", re.I)
_BADSET = re.compile(r"^Bad set(?:\s+by\s+(.+?))?\s*\.?\s*$", re.I)
_BHE = re.compile(r"^Ball handling error(?:\s+by\s+(.+?))?\s*\.?\s*$", re.I)
_LINEUP = re.compile(r"^(.*?)\s+(starters|subs?)\s*:\s*(.*?)\s*\.?\s*$", re.I)


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def tokens(name: str) -> frozenset:
    """A name as a set of lower-case words, so 'Lang, Kate' equals 'Kate Lang'."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s.replace("'", "").replace("-", " "))
    return frozenset(t for t in s.split() if t)


def clean_name(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s.title() if s and (s.islower() or s.isupper()) else s


def parse_scoreboard(contest: dict, season: int) -> dict | None:
    """The basics of one match from a day's scoreboard."""
    teams = contest.get("teams") or []
    home = next((t for t in teams if t.get("isHome")), None)
    away = next((t for t in teams if not t.get("isHome")), None)
    if not home or not away or not contest.get("contestId"):
        return None
    if not home.get("seoname") or not away.get("seoname"):
        return None
    m, d, y = (contest.get("startDate") or "0/0/0").split("/")
    final = contest.get("gameState") == "F"
    return {
        "game_id": int(contest["contestId"]), "season": season, "date": f"{y}-{m}-{d}",
        "start_epoch": _int(contest.get("startTimeEpoch"), None) if contest.get("hasStartTime") else None,
        "state": contest.get("gameState") or "",
        "home": home["seoname"], "away": away["seoname"],
        "home_name": home.get("nameShort") or home["seoname"],
        "away_name": away.get("nameShort") or away["seoname"],
        "home_div": None, "away_div": None,
        "home_conf": home.get("conferenceSeo") or "", "away_conf": away.get("conferenceSeo") or "",
        "home_sets": _int(home.get("score"), None) if final else None,
        "away_sets": _int(away.get("score"), None) if final else None,
        "set_scores": "", "venue": "", "city": "",
        "round": (contest.get("roundDescription") or "") if contest.get("isChampionship") else "",
        "detail": 0, "pbp_sets": 0,
    }


# ------------------------------------------------------------- box score --
def parse_box(game_id: int, box: dict, home_seo: str, away_seo: str):
    """Box score rows, plus each side's full roster for matching names later."""
    box = ((box or {}).get("data") or {}).get("boxscore") or {}
    is_home = {str(t.get("teamId")): bool(t.get("isHome")) for t in box.get("teams") or []}
    rows, rosters = [], {True: [], False: []}
    for tb in box.get("teamBoxscore") or []:
        home = is_home.get(str(tb.get("teamId")))
        if home is None:
            continue
        for i, p in enumerate(tb.get("playerStats") or []):
            first, last = clean_name(p.get("firstName")), clean_name(p.get("lastName"))
            rosters[home].append((i, tokens(first + " " + last), tokens(last)))
            nums = {k: _int(p.get(k)) for k in (
                "gamesPlayed", "kills", "attackErrors", "attackAttempts", "assists", "serviceAces",
                "serviceErrors", "serveAttempts", "digs", "receptionAttempts", "receptionErrors",
                "blockSolos", "blockAssists", "blockingErrors", "ballHandlingErrors")}
            if not (p.get("participated") or nums["gamesPlayed"] or any(nums.values())):
                continue
            rows.append([game_id, home_seo if home else away_seo, int(home), i, first, last,
                         _int(p.get("number"), None), (p.get("position") or "").strip().upper(),
                         int(bool(p.get("starter"))), nums["gamesPlayed"], nums["kills"],
                         nums["attackErrors"], nums["attackAttempts"], nums["assists"],
                         nums["serviceAces"], nums["serviceErrors"], nums["serveAttempts"],
                         nums["digs"], nums["receptionAttempts"], nums["receptionErrors"],
                         nums["blockSolos"], nums["blockAssists"], nums["blockingErrors"],
                         nums["ballHandlingErrors"], float(p.get("points") or 0) if _is_num(p.get("points")) else 0.0])
    return rows, rosters


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------ name lookup --
class Rosters:
    """Finds which player a name in the play-by-play refers to."""

    def __init__(self, rosters: dict):
        self.full = {True: {}, False: {}}
        self.rows = rosters
        for home in (True, False):
            seen = {}
            for i, full, _last in rosters[home]:
                if full:
                    seen.setdefault(full, []).append(i)
            self.full[home] = {k: v[0] for k, v in seen.items() if len(v) == 1}

    def find(self, name: str, home: bool):
        """Row number of `name` on one side, or None."""
        key = tokens(name)
        if not key or key == frozenset(["team"]):
            return None
        hit = self.full[home].get(key)
        if hit is not None:
            return hit
        # a middle name or a shortened first name: accept one clear partial match
        cands = [i for i, full, last in self.rows[home]
                 if full and last and last <= key and (full <= key or key <= full)]
        if len(cands) == 1:
            return cands[0]
        cands = [i for i, full, last in self.rows[home] if last and last <= key and len(key & full) >= 2]
        return cands[0] if len(cands) == 1 else None

    def find_any(self, name: str, prefer_home: bool):
        """(is_home, row) trying the expected side first."""
        for home in (prefer_home, not prefer_home):
            i = self.find(name, home)
            if i is not None:
                return home, i
        return None, None

    def split(self, text: str):
        """A list of names as written in the feed. 'A, B; C, D' is two people
        written surname-first; 'A B, C D' is two people written first-name-first."""
        out = []
        for piece in re.split(r"\s*;\s*", text or ""):
            piece = piece.strip(" .")
            if not piece:
                continue
            if "," in piece and self.find(piece, True) is None and self.find(piece, False) is None:
                out.extend(p.strip(" .") for p in piece.split(",") if p.strip(" ."))
            else:
                out.append(piece)
        return out


# ----------------------------------------------------------- play-by-play --
def _tidy(plays: list, any_scored: bool) -> list:
    """Clean one set's plays: drop the duplicate copy, drop repeated lines, and
    put a scored feed back in time order when it arrives shuffled."""
    out, seen = [], set()
    for play in plays:
        tid, text, hs, vs, clock = play
        if any_scored and hs is None and len(clock) == 5:
            continue                          # the unscored duplicate copy
        if clock and set(clock) <= set("0:"):
            continue                          # housekeeping entries stamped 00:00
        if not any_scored and clock:
            if (clock, text) in seen:
                continue                      # the same line sent twice
            seen.add((clock, text))
        out.append(play)
    timed = [p for p in out if len(p[4]) == 8]
    if any_scored and len(timed) >= 0.9 * len(out) and timed != sorted(timed, key=lambda p: p[4]):
        head = [p for p in out if len(p[4]) != 8]          # starters lines carry no clock
        resorted = head + sorted(timed, key=lambda p: p[4])
        totals = [p[2] + p[3] for p in resorted if p[2] is not None and p[3] is not None]
        if totals == sorted(totals):
            out = resorted
    return out


def _classify(text: str):
    """(type, [names...]) for a play that ends a rally, else None."""
    m = _KILL.match(text)
    if m:
        return "K", [m.group(1), m.group(2)]
    m = _ATTACK.match(text)
    if m:
        if (m.group(2) or "").lower().startswith("block"):
            return "BLK", [m.group(1), m.group(3)]
        return "AE", [m.group(1)]
    m = _ACE.match(text)
    if m:
        return "ACE", [m.group(1)]
    if _SERR.match(text):
        return "SE", []
    m = _BADSET.match(text)
    if m:
        return "BSE", [m.group(1)]
    m = _BHE.match(text)
    if m:
        return "BHE", [m.group(1)]
    return None


def parse_pbp(game_id: int, pbp: dict, rosters: dict, home_tid: str, linescores: list):
    """Rally rows for one match.

    Returns (rows, sets_ok, oddities). Only sets whose parsed points add up to
    the official set score are kept; `sets_ok` is how many did."""
    doc = ((pbp or {}).get("data") or {}).get("playbyplay") or {}
    periods = doc.get("periods") or []
    names = Rosters(rosters)
    odd = {}
    rows, sets_ok = [], 0

    flat = []
    for per in periods:
        plays = []
        for entry in per.get("playbyplayStats") or []:
            tid = str(entry.get("teamId"))
            for p in entry.get("plays") or []:
                text = re.sub(r"\s+", " ", (p.get("playText") or "").strip())
                if text:
                    plays.append((tid, text, p.get("homeScore"), p.get("visitorScore"), p.get("clock") or ""))
        flat.append((_int(per.get("periodNumber"), len(flat) + 1), plays))

    # Some matches carry two copies of the same plays from two scoring systems.
    # One copy has the running score; the other has only a short clock. Keep
    # the scored copy.
    any_scored = any(hs is not None and _classify(t) for _, plays in flat for _, t, hs, _, _ in plays)

    for set_no, plays in flat:
        official = None
        if 0 < set_no <= len(linescores):
            official = (_int(linescores[set_no - 1].get("home"), None), _int(linescores[set_no - 1].get("visit"), None))
        plays = _tidy(plays, any_scored)
        set_rows = []
        hs = vs = 0
        prev_home_won = None
        n = 0
        for tid, text, p_hs, p_vs, clock in plays:
            kind = _classify(text)
            if kind is None:
                if not _LINEUP.match(text):
                    key = re.sub(r"\d+", "#", text)[:60]
                    odd[key] = odd.get(key, 0) + 1
                continue

            ptype, who = kind
            # who won the point: from the running score if there is one, else
            # the feed lists the play under the team that won it
            jumped = False
            if p_hs is not None and p_vs is not None:
                p_hs, p_vs = _int(p_hs), _int(p_vs)
                dh, dv = p_hs - hs, p_vs - vs
                if dh == 0 and dv == 0:
                    continue                  # the same point listed twice
                if (dh, dv) == (1, 0):
                    home_won = True
                elif (dh, dv) == (0, 1):
                    home_won = False
                elif dh >= 0 and dv >= 0:     # the feed skipped a point or two
                    home_won = (tid == home_tid) if (dh > 0 and dv > 0) else dh > 0
                    jumped = True
                    odd["points missing from the feed"] = odd.get("points missing from the feed", 0) + dh + dv - 1
                else:
                    odd["score went backwards"] = odd.get("score went backwards", 0) + 1
                    continue
                hs, vs = p_hs, p_vs
            else:
                home_won = (tid == home_tid)
                hs, vs = hs + home_won, vs + (not home_won)
            n += 1

            p = [None, None, None]
            if ptype == "K":
                p[0] = names.find(who[0] or "", home_won)
                p[1] = names.find(who[1] or "", home_won) if who[1] else None
                if p[0] is None and who[0] and names.find(who[0], not home_won) is not None:
                    odd["kill credited to the other team"] = odd.get("kill credited to the other team", 0) + 1
            elif ptype in ("AE", "BSE", "BHE", "ACE"):
                p[0] = names.find(who[0] or "", not home_won) if who and who[0] else None
            elif ptype == "BLK":
                p[0] = names.find(who[0] or "", not home_won) if who[0] else None
                blockers = [names.find(b, home_won) for b in names.split(who[1] or "")]
                blockers = [b for b in blockers if b is not None][:2]
                p[1:1 + len(blockers)] = blockers

            # who served: the winner of the previous point, and on an ace or a
            # service error the play itself says
            if ptype == "ACE":
                serve_home = home_won
            elif ptype == "SE":
                serve_home = not home_won
            else:
                serve_home = None if jumped else prev_home_won
            if not jumped and prev_home_won is not None and serve_home != prev_home_won:
                odd["serve order mismatch"] = odd.get("serve order mismatch", 0) + 1
            prev_home_won = home_won

            set_rows.append([game_id, set_no, n, int(home_won), hs, vs, ptype, p[0], p[1], p[2],
                             None if serve_home is None else int(serve_home)])
        if official and official == (hs, vs) and hs + vs > 0:
            sets_ok += 1
            rows.extend(set_rows)
    return rows, sets_ok, odd


# ------------------------------------------------------------- whole match --
def parse_detail(basic: dict, game: dict, box: dict, pbp: dict):
    """Fill in a match from its three detail feeds.

    Returns (game_row_dict, box_rows, rally_rows, oddities)."""
    g = dict(basic)
    contest = (((game or {}).get("data") or {}).get("contests") or [None])[0] or {}
    teams = contest.get("teams") or []
    home = next((t for t in teams if t.get("isHome")), {})
    away = next((t for t in teams if not t.get("isHome")), {})
    lines = contest.get("linescores") or []
    if contest:
        g["state"] = contest.get("gameState") or g["state"]
        g["home_div"], g["away_div"] = _int(home.get("division"), None), _int(away.get("division"), None)
        loc = contest.get("location") or {}
        g["venue"] = (loc.get("venue") or "").strip()
        g["city"] = ", ".join(x for x in [(loc.get("city") or "").strip(), (loc.get("stateUsps") or "").strip()] if x)
        cg = contest.get("championshipGame") or {}
        if cg and (cg.get("round") or {}).get("title"):
            g["round"] = cg["round"]["title"]
        scores = [(_int(l.get("home"), None), _int(l.get("visit"), None)) for l in lines]
        scores = [s for s in scores if s[0] is not None and s[1] is not None and s[0] + s[1] > 0]
        g["set_scores"] = " ".join(f"{h}-{v}" for h, v in scores)
        if scores and g["state"] == "F":
            g["home_sets"] = sum(h > v for h, v in scores)
            g["away_sets"] = sum(v > h for h, v in scores)
    box_rows, rosters = parse_box(g["game_id"], box, g["home"], g["away"])
    rallies, sets_ok, odd = parse_pbp(g["game_id"], pbp, rosters, str(home.get("teamId")), lines)
    g["pbp_sets"] = sets_ok
    played = sum(r[9] for r in box_rows)
    g["detail"] = 1 if (box_rows and played > 0) else 2
    if g["detail"] == 2:
        box_rows = []
    return g, box_rows, rallies, odd


def iso_today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()
