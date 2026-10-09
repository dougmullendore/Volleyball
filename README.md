# GOAT Volleyball

Every Division I women's college volleyball match, week by week, with the
AVCA poll, a GOAT ranking of all D1 teams, team and player stats, and a page
for every team and match. A Top 25 / All D1 switch narrows any page to the
ranked teams.

You do not need to run anything. GitHub does it all on a schedule.

## What the site shows

- **Players** (third page): see below.
- **Rankings** (second page): the AVCA coaches poll, with each team's record
  and how far it moved from last week. Choose a team to see its matches.
- **Matches** (first page): every match this week involving a ranked team, grouped by
  day. Upcoming matches show the start time in the reader's own time zone and
  where to watch; and each team's chance of winning; finished ones show the score in sets and link to the NCAA's
  box score. A
  match between two ranked teams has a blue edge. Buttons step to earlier
  and later weeks, and a menu narrows the list to one team's whole season.

## Beat and Lost to

On the Rankings page each team's Beat and Lost to boxes list its results
against the other ranked teams. In the AVCA poll view they count only matches
played through the poll's date, so they change with the poll each Monday,
and so do the boxes on team pages. The GOAT view's boxes are redone every
night.

## Team pages

Every team name on the site links to that team's page (`#/team/<id>`): its
poll and GOAT ranks, Beat / Lost to boxes, the next five matches and latest
five results, its team stats (each with its place among the 25), and its
players with their per-set stats. Teams outside the top 25 get the same
full page.

## Match pages and live box scores

At the top of each match page is a **match card**: the score and each
set's points, each team's chance of winning (before the match, for a finished
one) and a side-by-side team comparison (hitting, kills, aces, blocks, digs,
assists, errors).

Every match on the Matches page links to its own page (`#/match/<id>`) with
the set-by-set score and both teams' full box scores: each player's kills,
errors, attempts, hitting efficiency, assists, aces, service errors, digs,
reception errors, blocks and points, starters first, plus each team's hitting
set by set. Player names link to their cards.

- Set scores are read by the page itself from ESPN, every 15 seconds while a
  match is on.
- The NCAA's box score cannot be read by a web page directly, so the GitHub
  job fetches it: on match nights (August to December, about 11am to 1am
  Central) it runs every 5 minutes, and when any D1 match is under way it
  refreshes the box scores of matches under way and rebuilds the site. When
  nothing is being played it stops within seconds. GitHub's scheduled runs
  are often a few minutes late.
- Matches in progress show a red LIVE tag on the Matches page.

## Teams

The **Teams** page is a sortable table of each ranked team's stats from the
official box scores (`pipeline/teams.py`): match and set record, hitting
efficiency for and against, kills, assists, aces, service errors, blocks and
digs per set, reception error rate, where the site's rating places the team
among all Division I teams, and strength of schedule (the average rating of
its opponents, ranked among the 25).

## Top 25 or all of Division I

The Matches, Teams and Players pages, each team's page and each player card
have a **Top 25 / All D1** switch. The site remembers the choice. With Top 25,
matches are those of ranked teams and players and teams are measured against
the ranked 25 only (`players.json`, `teams.json`); with All D1, every Division I
match is listed and every player and team is measured against all of Division I
(`players_d1.json`, `teams_d1.json`). A team outside the top 25, and its
players, are always shown against all of Division I. The Rankings page is the
top 25 either way.

Box scores, channels and live scores are collected for every Division I match.
Player photos are looked up for every school, at most `PHOTO_PAGES_PER_RUN`
roster pages a night (ranked teams first), so they fill in over the first few
nights.

## Players

The **Players** page ranks every regular on the 25 ranked teams against the
rest, and each name opens a card with her percentiles.

- **Impact per set** is the ranking number. Impact is the points a player has added over an
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

Logos appear beside team names everywhere on the site, and stand in for the
names in the Beat and Lost to boxes. Each is the school's colour logo from
ncaa.com, shown in a white circle with a blue ring (`.logo` in
`site/styles.css`). They are not stored in this repository: the
page shows them straight from ncaa.com, which has one for every school. They
belong to the schools. To remove them, set `LOGO_URL = ""` in
`pipeline/config.py`.

## GOAT ranking

The Rankings page's GOAT tab is the site's own ranking of every Division I
team (`pipeline/goat.py`), redone every night. Four things decide it, most
important first:

1. **Head to head.** A team is ranked above one it has beaten, unless the
   other three factors say the gap between them is wide
   (`GOAT_HEAD_TO_HEAD`). Results that form a circle cannot all be honored;
   the ranking keeps as many as it can.
2. **Strength of schedule:** the average rating of the teams it has played
   (the ratings behind the odds).
3. **The AVCA poll:** a ranked team gets credit for its place in it.
4. **Record:** its share of matches won.

Factors 2 to 4 are combined with the weights in `GOAT_WEIGHTS` (0.5, 0.3,
0.2). Everywhere else on the site a team's number is its AVCA rank, or, for a
team outside the poll, its place from 26 onward in GOAT order, so no two teams
share a number.

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
public scoreboard every 15 seconds and updates that match's row: sets won in
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
| Every night about 5:47am Central, and again about 11:47am | Refreshes scores, schedule, channels, ratings, GOAT ranking and player photos |
| Every night about 11:47pm Central | A third full refresh, so the night's results are complete by morning |
| Every 5 minutes, 11am to 1am Central, January to May and August to December | Live scores and box scores of matches under way (college, LOVB, MLV) |
| Whenever the code changes, or you press **Run workflow** on the **Actions** tab | Everything, straight away |

The poll normally comes out on Monday afternoon. If both Monday looks miss it
(a late poll, or the page being down), the nightly run notices that the newest
poll it has is more than eight days old and looks again every night until it
finds the new one. In between, the page keeps showing the last poll it has.

The stored scores are refreshed twice a day. In between, matches in
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

## Changing the wording

All the site's headings, intro lines, notes, button labels and the footer are
in one file, `site/words.txt`, one `name = words` line each. Change the words
after the `=` on GitHub (open the file, click the pencil, then Commit changes)
and the site updates in about two minutes. A broken line stops the update and
leaves the old site up; GitHub emails you, and the run log names the line.

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
  this repository's history, last at commit `17ce558`.
- The repository has three branches: `main` (the code), `state` (what the
  nightly job stores) and `gh-pages` (the published site, rebuilt each run).
- GitHub switches off scheduled jobs in a repository with no activity for 60
  days. Each run switches the job back on, so the nightly update keeps going
  through the off-season without anyone committing.

Not affiliated with or endorsed by the NCAA, the AVCA or any school.

## Player details

Each player card also shows her height, class, hometown and links to her
Instagram, X and TikTok, read from the same roster page as her photo. Weight
and age appear only when the school lists them, which few volleyball rosters
do.

## Schools without player photos

Arkansas's roster page shows no photos, so its photos come from each
player's own page. Tennessee Tech's and Central Connecticut's sites put a
"prove you are human" check in front of every page, so their players have no
photos or details. Each school's roster address is in `rosters/pages.csv`.

## LOVB and MLV

The site also has a copy for each of the two pro leagues, League One Volleyball
(the `lovb/` folder of the site) and Major League Volleyball (`mlv/`), reached
from the College / LOVB / MLV tabs at the top of every page. They have the same
pages: matches, standings, team stats, players with their
cards, team pages and box scores. Every team in the league is "ranked", by the
standings: wins, then share of matches won, then sets won to sets lost, regular
season only.

Their results and statistics come from the volleydata project
(github.com/awosoga/volleydata), which collects them from the leagues' own
match centres and publishes them as files; `pipeline/pro.py` reads them every
night. Until the new seasons start in January they show the 2026 seasons. The
leagues have no logos or player photos on the site yet: each team is shown with
its short code in a coloured circle, and players with their initials.
