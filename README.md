# GOAT Volleyball

Every match played by the top 25 teams in Division I women's college
volleyball, week by week, with the rankings on a second page.

You do not need to run anything. GitHub does it all on a schedule.

## What the site shows

- **Players** (third page): see below.
- **Rankings** (second page): the AVCA coaches poll, with each team's record
  and how far it moved from last week. Choose a team to see its matches.
- **Matches** (first page): every match this week involving a ranked team, grouped by
  day. Upcoming matches show the start time in the reader's own time zone and
  where to watch; and each team's chance of winning; finished ones show the score in sets and link to the NCAA's
  box score. A
  match between two ranked teams has a green edge. Buttons step to earlier
  and later weeks, and a menu narrows the list to one team's whole season.

## Players

The **Players** page ranks every regular on the 25 ranked teams against the
rest, and each name opens a card with her percentiles.

- **Impact** is the ranking number: the points a player has added over an
  average top-25 player at her position, from official box scores. It is the
  sum of six parts: attack (kills minus errors against her position's average
  on the same swings), serve, serve receive, block, dig, and setting. A
  hitter keeps three quarters of her attack value and her setters share the
  rest by assists; a dig counts 0.3 of a point. The reasoning is at the top of
  `pipeline/players.py`.
- **Percentiles** compare a player with regulars at her own position on the
  ranked teams, and only on jobs she does: a libero is not ranked on hitting.
- **A regular** has played at least 40% of her team's sets. Part-time players
  are listed (tick the box) but not ranked.
- **Positions** are outside/opposite hitter, middle blocker, setter, libero and
  defensive specialist. Schools list the last two together, so the libero is
  worked out from who digs the most.

What it cannot do: it sees only the box score, so it knows nothing about pass
quality, who was on the court, or how strong the opponent was. When the poll
changes, players on teams that dropped out disappear and everyone's averages
shift a little, because the comparison is always with the current top 25.

## Player photos

No feed carries player photos for college volleyball, so they come from each
school's own public roster page.

- `rosters/pages.csv` lists the roster pages already known. For a school
  that is not in it, the job finds the page itself: it takes the school's
  athletics website from ncaa.com, tries the usual roster addresses, and keeps
  the one that shows the players it knows from the box scores. If that fails,
  the log says `NO ROSTER PAGE FOUND` and the players show their initials
  until a line is added to the file (team id as the NCAA writes it, such as
  `texas-am`, then the address).
- The job reads each page about once a week, finds the picture described with
  a player's name, and keeps only the picture's address. The photos are not
  copied into this repository: the site shows them from the school's site.
- A player is left without a photo if the page spells her name differently
  from the box score or has no picture for her.
- The photos belong to the schools. To remove them all, set
  `SHOW_PHOTOS = False` in `pipeline/config.py`.

## Team logos

Logos appear beside team names. They are not stored in this repository: the
page shows them straight from ncaa.com, which has one for every school. They
belong to the schools. To remove them, set `LOGO_URL = ""` in
`pipeline/config.py`.

## GOAT ranking

The Rankings page shows the AVCA poll with a second column: the site's own
GOAT ranking, which gives head-to-head results more say than the poll does.

- Under each team the page lists who it has beaten and lost to among the
  other 24 ranked teams this season, with their poll places.
- It ranks every Division I team, so a poll team's GOAT number can be past 25,
  and the page lists GOAT top-25 teams the poll leaves out.
- It starts from the team ratings behind the odds. Then it looks for the
  order that agrees with the most head-to-head results while staying close to
  those ratings. A team climbs over one it has beaten when the two are close;
  it does not when the ratings say the gap is wide, and it does not jump teams
  in between that it has no claim on. A 1-1 split settles nothing.
- `GOAT_HEAD_TO_HEAD` in `pipeline/config.py` sets how much one head-to-head
  win can overturn (1.5 rating points now). Raise it and head-to-head counts
  for more; at 0 the GOAT ranking is just the rating order.
- The page reports the score: among the poll's 25 teams, how many times each
  ranking has a team below one it has beaten. On 7 October 2026 the poll did
  18 times and the GOAT ranking 7.
- It is redone every night, not only on Mondays. The method is at the top of
  `pipeline/goat.py`.

## Odds

Each match not yet played shows both teams' chance of winning, the favorite
in bold. There are no public betting lines for college volleyball, so these
are the site's own estimate, not a sportsbook's.

- Every Division I team has a rating, built from sets won and lost and who
  they were against. It moves after each match, quickly early in the season
  and slowly later, and a team starts each season on 95% of where it finished
  the last one. Home court is worth a little; at neutral sites (as ESPN marks
  them) it is left out.
- Tested on 23,008 matches from 2022 to 2026, always predicting from what was
  known beforehand, the favorite won 76.8% of the time (the home team wins
  57.8%), and the percentages were honest: teams given 70 to 80% won 74%.
- It knows results, not rosters: an injury only shows once the scores change.
- Ratings are kept in `ratings.json` on the `state` branch, so next season
  starts from this one by itself. `ratings/seed.json` holds where teams
  finished 2025, for this first season. The settings are in
  `pipeline/config.py` and the method at the top of `pipeline/odds.py`.

## Where to watch

Each match in the next two weeks shows its TV channel or streaming service
(ESPN+, Big Ten Network, B1G+, SEC Network+, ACC Network Extra and so on).
The NCAA's scoreboard does not carry this, so it comes from two other public
schedules, matched to the NCAA's matches by team and start time:

- **ESPN's scoreboard**, which lists a channel for most matches.
- **The Big Ten's schedule**, because ESPN leaves out Big Ten Network and FS1.

"No broadcast listed" means neither schedule names a channel yet. Matches more
than two weeks away show nothing, because networks are usually not announced
that far ahead. Channels are refreshed every night and can change late; the
page says so in its footer.

## Live scores

While a ranked team's match is being played, the page itself re-reads ESPN's
public scoreboard every 20 seconds and updates that match's row: sets won in
big numbers, points in the current set in small ones, and "Final" when it
ends. This happens in the reader's browser, so it needs no extra runs on
GitHub. It starts 15 minutes before a match's listed start time, pauses while
the tab is in the background, and covers every match the nightly job managed
to find in ESPN's schedule (nearly all of them). If ESPN cannot be reached,
the row simply stays as it was.

## When it updates

The file `.github/workflows/update.yml` tells GitHub when to run:

| When | What it does |
| --- | --- |
| Every Monday about 4pm Central, and again about 9pm | Looks for the new top 25, then refreshes scores, schedule and channels |
| Every night about 5:47am Central | Refreshes scores, schedule, channels and player ratings |
| Whenever the code changes, or you press **Run workflow** on the **Actions** tab | Everything, straight away |

The poll normally comes out on Monday afternoon. If both Monday looks miss it
(a late poll, or the page being down), the nightly run notices that the newest
poll it has is more than eight days old and looks again every night until it
finds the new one. In between, the page keeps showing the last poll it has.

The stored scores are refreshed once a night. In between, matches in
progress are followed live as described above; a reader who opens the page
after a match has ended still sees its final score that evening.

## When a new school enters the top 25

Nothing needs doing. On the run that picks up the new poll:

| Part | What happens |
| --- | --- |
| Rankings | The new poll replaces the old one; the GOAT ranking already covers every Division I team |
| Matches | The school's whole season is listed; a school that dropped out is removed |
| Where to watch, live scores | Looked up for its matches in the next two weeks, like everyone else's |
| Players | Its box scores for the season so far are downloaded, and every player is re-rated against the new 25 |
| Photos | Its roster page is found and read |
| Logo | Shown from ncaa.com under the school's id |

This was rehearsed against a made-up poll with ten new schools (Creighton,
Baylor, Dayton, Utah, USC, Western Kentucky, Miami, Cal Poly, Iowa State,
Northern Iowa): all ten came through with matches, channels, players and
photos.

The one thing that can go wrong is the poll spelling a school in a way the
job cannot match to the scoreboard. The site is still published with the
other 24, but **the run is marked failed**, so it shows red on the Actions
tab and GitHub emails you. The message names the school; the fix is one line
in `ALIASES` in `pipeline/poll.py`. A run also fails if the poll page, the
scoreboard or the box scores cannot be read at all.

## Where things are

| Path | What it is |
| --- | --- |
| `pipeline/config.py` | Every setting: which poll, which day it is checked, season dates |
| `pipeline/poll.py` | Reads the poll and decides when to look for a new one |
| `pipeline/box.py` | Downloads and stores the box score of each ranked team's match |
| `pipeline/players.py` | Rates the players against each other and works out percentiles |
| `pipeline/photos.py` | Finds each player's photo on her school's roster page |
| `rosters/pages.csv` | The roster page of each ranked school; add a line when a new school is ranked |
| `pipeline/goat.py` | The GOAT ranking: the rating order rearranged to respect head-to-head results |
| `pipeline/odds.py` | Rates every team from results and turns two ratings into a chance of winning |
| `pipeline/watch.py` | Finds the TV channel or stream for each upcoming match |
| `pipeline/web.py` | Downloads the poll page and the NCAA scoreboard |
| `pipeline/run.py` | The job: update the poll, update the scoreboard, build the page |
| `site/` | The page itself (plain HTML, CSS and JavaScript, no build step) |
| `tests/` | A saved poll page, a saved day of scores and that day's TV listings, with checks that all are read correctly |

Run the tests with `python tests/run_local.py`.

Two side branches of this repository hold what the job produces:

- `state`: every poll seen so far (`polls.json`), the season's matches
  (`scoreboard.json`), the channels found (`watch.json`), the box scores (`box.json`), photo addresses (`photos.json`), and what happened on the last run (`status.json`,
  `logs/last_run.log`).
- `gh-pages`: the finished page.

## Turning the website on

One-time setup in the repository's **Settings**:

**Settings → Pages → Build and deployment → Source: "Deploy from a branch"**,
then choose branch `gh-pages` and folder `/ (root)`, and save.

A minute or two later the page is live at
`https://dougmullendore.github.io/Volleyball/`.

## Good to know

- The numbers beside teams are this week's rankings, including on earlier
  weeks' matches. A team that drops out of the poll drops off the page.
- The scoreboard only says "home" and "away"; at neutral-site tournaments those
  are just labels.
- The earlier, larger version of this site (ratings, WAR, player cards) is in
  this repository's history, last at commit `17ce558`. Its downloaded matches
  are still on the `data` branch, which nothing uses any more.

Not affiliated with or endorsed by the NCAA, the AVCA or any school.
