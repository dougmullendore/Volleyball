# GOAT Volleyball

One page: every match played by the top 25 teams in Division I women's college
volleyball, week by week.

You do not need to run anything. GitHub does it all on a schedule.

## What the page shows

- **This week's top 25**: the AVCA coaches poll, with each team's record and
  how far it moved from last week. Choose a team to see its whole season.
- **The matches**: every match this week involving a ranked team, grouped by
  day. Upcoming matches show the start time in the reader's own time zone;
  finished ones show the score in sets and link to the NCAA's box score. A
  match between two ranked teams has a yellow edge. Buttons step to earlier
  and later weeks.

## When it updates

The file `.github/workflows/update.yml` tells GitHub when to run:

| When | What it does |
| --- | --- |
| Every Monday about 4pm Central, and again about 9pm | Looks for the new top 25, then refreshes scores and schedule |
| Every night about 5:47am Central | Refreshes scores and schedule |
| Whenever the code changes, or you press **Run workflow** on the **Actions** tab | Everything, straight away |

The poll normally comes out on Monday afternoon. If both Monday looks miss it
(a late poll, or the page being down), the nightly run notices that the newest
poll it has is more than eight days old and looks again every night until it
finds the new one. In between, the page keeps showing the last poll it has.

Scores are refreshed once a night, so a match played this evening shows its
result tomorrow morning.

## Where things are

| Path | What it is |
| --- | --- |
| `pipeline/config.py` | Every setting: which poll, which day it is checked, season dates |
| `pipeline/poll.py` | Reads the poll and decides when to look for a new one |
| `pipeline/web.py` | Downloads the poll page and the NCAA scoreboard |
| `pipeline/run.py` | The job: update the poll, update the scoreboard, build the page |
| `site/` | The page itself (plain HTML, CSS and JavaScript, no build step) |
| `tests/` | A saved poll page and a saved day of scores, with checks that both are read correctly |

Run the tests with `python tests/run_local.py`.

Two side branches of this repository hold what the job produces:

- `state`: every poll seen so far (`polls.json`), the season's matches
  (`scoreboard.json`), and what happened on the last run (`status.json`,
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
