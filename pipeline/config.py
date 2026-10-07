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
SPORT_CODE = "WVB"      # women's volleyball
DIVISION = 1
GAME_PAGE = "https://www.ncaa.com/game/"

# Be polite to the NCAA's servers.
FETCH_THREADS = 6
FETCH_RETRIES = 4
USER_AGENT = "Mozilla/5.0 (compatible; volleyball-stats-site/2.0)"
