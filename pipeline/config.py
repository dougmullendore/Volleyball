"""Settings for the whole pipeline. Change things here, not in the other files."""

import datetime as _dt

# The first season the site covers. A season is named by the year it is
# played in: 2025 is the fall 2025 season. The NCAA's public feed has box
# scores and play-by-play from 2021 on.
FIRST_SEASON = 2021

# Matches are looked for between these dates (month, day) each year: late
# August through the national final just before Christmas.
SEASON_START = (8, 15)
SEASON_END = (12, 24)


def _seasons_through_today() -> list[int]:
    today = _dt.datetime.now(_dt.timezone.utc).date()
    last = today.year if (today.month, today.day) >= SEASON_START else today.year - 1
    return list(range(FIRST_SEASON, last + 1))


# Every season from FIRST_SEASON to the current one, oldest first. A new
# season is picked up automatically each August.
SEASONS = _seasons_through_today()

SPORT_CODE = "WVB"      # the NCAA's code for women's volleyball
DIVISION = 1

# Raise this when the play-by-play reader improves: matches whose points did
# not all add up are then downloaded and read again.
PARSER_VERSION = 2

# Matches from the last few days are re-downloaded every night because
# schools send in stat corrections after the match.
REFRESH_DAYS = 3

# Be polite to the NCAA's servers.
FETCH_THREADS = 6
FETCH_RETRIES = 5
USER_AGENT = "Mozilla/5.0 (compatible; volleyball-stats-site/1.0)"

API = "https://sdataprod.ncaa.com/"
# The feed answers only to these fixed query ids (they are the same ones the
# ncaa.com pages use). If the NCAA changes its site they will need updating.
QUERY = {
    "scoreboard": "7287cda610a9326931931080cb3a604828febe6fe3c9016a7e4a36db99efdb7c",
    "game": "93a02c7193c89d85bcdda8c1784925d9b64657f73ef584382e2297af555acd4b",
    "box": "4320484382257c2a7ac3be318db2dee09a7fb74029448825c285d5dbdda365ae",
    "pbp": "57f922d56d60d88326b62202b3d88e8cd3cfb6687931bc0b5b3dfab089b84faa",
}

# A school counts as Division I in a season if it plays at least this many
# matches on the Division I scoreboard.
MIN_MATCHES_D1 = 12

# --- Team ratings and predictions ---------------------------------------
# A rating is points per set better than an average Division I team.
RATING_PRIOR_MATCHES = 4.0     # matches of "last year's team" mixed in at the start
RATING_MIN_STEP = 0.07         # once a team has played a lot, each match still moves it this much
RATING_SUMMER_KEEP = 0.95      # share of its distance from average a team keeps over the summer
# (These three were chosen by testing a grid of values against 2022-2026
# results. Programs change little from year to year: keeping more than 90% of
# last season's rating predicted better than pulling teams toward average.)
RATING_NEW_TEAM = -3.0         # starting rating for a school with no history
PRED_STRENGTH_DOUBT = 0.6      # doubt about each team's true rating in the simulation (points per set)
PRED_SIMULATIONS = 5000
UPCOMING_DAYS = 7

# --- Player value ---------------------------------------------------------
# How much of the gap between a dug ball and a kill allowed is credited to the
# digger, and how a kill is split between the hitter and the setter.
VALUE_DIG = 0.5
VALUE_SETTER_SHARE = 0.25
# Fallback until there is a full season to measure it from.
VALUE_POINTS_PER_WIN = 20.0

# --- Which teams the site shows -------------------------------------------
# The site shows only the teams in the national coaches poll (AVCA Top 25)
# and their players and matches. Every Division I match is still downloaded
# and used behind the scenes, because ratings, schedule strength and
# replacement level all need the full field.
# Set SHOW_TOP = 0 to show every Division I team again.
SHOW_TOP = 25
POLL_NAME = "AVCA coaches poll"
POLL_URL = "https://www.ncaa.com/rankings/volleyball-women/d1/avca-rankings"

SITE_NAME = "GOAT Volleyball"
SITE_TAGLINE = "The top 25 in women's college volleyball: ratings, projections and player value"
