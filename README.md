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
  where to watch; finished ones show the score in sets and link to the NCAA's
  box score. A
  match between two ranked teams has a yellow edge. Buttons step to earlier
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

There are no player photos. No public feed carries them for college
volleyball; they exist only on each school's own roster page.

## Team logos

Logos appear beside team names. They are not stored in this repository: the
page shows them straight from ncaa.com, which has one for every school. They
belong to the schools. To remove them, set `LOGO_URL = ""` in
`pipeline/config.py`.

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

## Where things are

| Path | What it is |
| --- | --- |
| `pipeline/config.py` | Every setting: which poll, which day it is checked, season dates |
| `pipeline/poll.py` | Reads the poll and decides when to look for a new one |
| `pipeline/box.py` | Downloads and stores the box score of each ranked team's match |
| `pipeline/players.py` | Rates the players against each other and works out percentiles |
| `pipeline/watch.py` | Finds the TV channel or stream for each upcoming match |
| `pipeline/web.py` | Downloads the poll page and the NCAA scoreboard |
| `pipeline/run.py` | The job: update the poll, update the scoreboard, build the page |
| `site/` | The page itself (plain HTML, CSS and JavaScript, no build step) |
| `tests/` | A saved poll page, a saved day of scores and that day's TV listings, with checks that all are read correctly |

Run the tests with `python tests/run_local.py`.

Two side branches of this repository hold what the job produces:

- `state`: every poll seen so far (`polls.json`), the season's matches
  (`scoreboard.json`), the channels found (`watch.json`), the box scores (`box.json`), and what happened on the last run (`status.json`,
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
