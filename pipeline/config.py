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
# which has one for every school under the same id the scoreboard uses, drawn
# for a light page ("bgl") and for a dark one ("bgd"). Set to "" to show none.
LOGO_URL = "https://www.ncaa.com/sites/default/files/images/logos/schools/{theme}/{team}.svg"

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
