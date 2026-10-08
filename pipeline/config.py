"""Every setting in one place."""

SITE_NAME = "GOAT Volleyball"

# The ranking that decides which teams' matches are listed.
POLL_NAME = "AVCA coaches poll"
POLL_URL = "https://www.ncaa.com/rankings/volleyball-women/d1/avca-rankings"
POLL_SIZE = 25

# The poll comes out on Monday afternoons. The job looks for a new one on
# this weekday (0 = Monday), judged by the clock in this time zone. It also
# looks on any other day if the newest poll it has is more than
# POLL_OVERDUE_DAYS old, which means Monday's look was missed or came too early.
POLL_WEEKDAY = 0
POLL_TIMEZONE = "America/Chicago"
POLL_OVERDUE_DAYS = 8

# Matches are looked for between these dates (month, day) each year: late
# August through the national final just before Christmas.
SEASON_START = (8, 15)
SEASON_END = (12, 24)

# The NCAA's public scoreboard feed (the one the ncaa.com scoreboard page uses).
FEED = "https://sdataprod.ncaa.com/"
SCOREBOARD_QUERY = "7287cda610a9326931931080cb3a604828febe6fe3c9016a7e4a36db99efdb7c"
BOX_QUERY = "4320484382257c2a7ac3be318db2dee09a7fb74029448825c285d5dbdda365ae"
BOX_REFRESH_DAYS = 3    # box scores this recent are fetched again: schools send in corrections
SPORT_CODE = "WVB"      # women's volleyball
DIVISION = 1
GAME_PAGE = "https://www.ncaa.com/game/"

# Team logos are not stored here: the page shows them straight from ncaa.com,
# which has one for every school under the same id the scoreboard uses. The
# site shows every logo in white (dark ink on a light page): it takes
# ncaa.com's dark-page set ("bgd"), which is white for many schools but not
# all, and the page turns each one white while keeping its inner detail (see
# the filters at the top of site/index.html). Set to "" to show none.
LOGO_URL = "https://www.ncaa.com/sites/default/files/images/logos/schools/bgd/{team}.svg"

# Player photos come from each school's own roster page (rosters/pages.csv)
# and are shown from the school's site, not copied. A page is read again after
# this many days. Set SHOW_PHOTOS = False to show none.
SHOW_PHOTOS = True
PHOTO_REFRESH_DAYS = 7
# For a school not in rosters/pages.csv the job finds the roster page itself:
# ncaa.com's page for the school gives its athletics website, and these are
# the places schools keep a volleyball roster. The one that names the players
# we know from the box scores is the right one.
SCHOOL_PAGE = "https://www.ncaa.com/schools/{team}"
ROSTER_PATHS = ["/sports/womens-volleyball/roster", "/sports/volleyball/roster", "/sports/wvball/roster/",
                "/sports/w-volley/roster", "/sports/wvb/roster", "/sports/womens-volleyball/roster/",
                "/sports/volleyball/roster/"]

# Odds: each team's chance of winning, from this site's own ratings (see
# pipeline/odds.py). These settings were chosen by testing on 2022-2026 results.
ODDS_STEP = 0.18          # how far a rating moves per surprising set, early in the season
ODDS_SETTLE = 4           # after about this many matches the moves get smaller
ODDS_MIN_STEP = 0.04      # and never smaller than this
ODDS_KEEP = 0.95          # share of last season's rating a team starts with
ODDS_HOME = 0.14          # home court, in the same units as a rating
ODDS_NEW = -1.2           # starting rating of a school with no history and few matches
ODDS_FEW_MATCHES = 8
ODDS_STRETCH = 0.9        # pulls chances slightly toward 50-50; made them match results better
ODDS_TESTED = {"matches": 23008, "favorite_won": 0.768, "seasons": "2022 to 2026"}

# The GOAT ranking (pipeline/goat.py): the rating order, rearranged to agree
# with head-to-head results. One head-to-head win may overturn up to this much
# rating difference; raise it and head-to-head counts for more.
GOAT_HEAD_TO_HEAD = 1.5
GOAT_POOL = 80           # how far down the rating order teams can be rearranged
GOAT_MIN_MATCHES = 12    # a school with fewer matches listed is not a Division I team and is not ranked

# Where to watch. Channels are looked up for matches in the next WATCH_DAYS
# days; further out, networks have usually not been announced.
WATCH_DAYS = 14
# While a ranked team's match is being played, the page itself re-reads ESPN's
# scoreboard this often (in seconds) and shows the score as it changes.
LIVE_SECONDS = 20
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/volleyball/womens-college-volleyball/scoreboard?limit=500&dates="
BIGTEN_SCHEDULE = "https://bigten.org/services/responsive-calendar.ashx?start={start}&end={end}%2023:59:59&sport_id=28&school_id=0"

# Be polite to the servers.
FETCH_THREADS = 6
FETCH_RETRIES = 4
USER_AGENT = "Mozilla/5.0 (compatible; volleyball-stats-site/2.0)"

# ---- news: the week's most widely covered stories about the ranked teams (pipeline/news.py) ----
# (name, kind, address). kind "espn" is ESPN's news feed, anything else plain RSS.
NEWS_FEEDS = [
    ("ESPN", "espn", "https://site.api.espn.com/apis/site/v2/sports/volleyball/womens-college-volleyball/news?limit=50"),
    ("NCAA.com", "rss", "https://www.ncaa.com/news/volleyball-women/d1/rss.xml"),
    ("Volleyball Magazine", "rss", "https://volleyballmag.com/feed/"),
]
# A Google News search run for each ranked team: "{team}" is the school's name.
NEWS_TEAM_SEARCH = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q=%22{team}%22+volleyball+when:7d"
NEWS_KEEP_DAYS = 10      # items are kept this long between runs
NEWS_STORIES = 30        # stories shown on the News page
