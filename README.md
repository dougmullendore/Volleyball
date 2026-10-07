# GOAT Volleyball

A stats website for the top 25 teams in Division I women's college
volleyball. Every night it downloads the NCAA's public scores, box scores and
play-by-play, reads the national coaches poll, rates every team, values every
player, and rebuilds the site for the 25 ranked teams.

You do not need to run anything. GitHub does it all on a schedule.

## What is on the site

| Page | What it shows |
| --- | --- |
| Home | A point-by-point chart of each recent top match, plus season leaders |
| Matches | Every result involving a ranked team, with how likely it looked beforehand; win probabilities for the next week |
| Standings | Projected wins and conference-title odds for the ranked teams, from simulating the rest of the regular season |
| Teams | Poll place, rating, strength of schedule, sideout and break rates, hitting, serving, blocking |
| WAR | Wins above replacement for every player on a ranked team, split into attack, serve, receive, block, dig and set |
| Cards | One card per player: where she ranks among all Division I players at her position in each part of the game |
| Players | Box-score tables: attacking, serving and passing, blocking and defense |
| About | How the numbers work and how well the predictions tested |

Seasons covered: 2021 to today for team results and ratings, 2022 to today for
player numbers (the NCAA's feed has no box scores before that). A new season
is added automatically each August.

## Which teams are shown

Only the 25 teams in the AVCA coaches poll, with their players and matches.

- **This season:** the current poll, read every night from ncaa.com's rankings
  page. When a new poll comes out (usually Monday) the teams on the site change
  with it. Each poll is kept in `polls/` on the `data` branch, so the last one
  of the year becomes that season's final list by itself.
- **2021 to 2025:** the final poll of each season, in `polls/final_polls.csv`.
  It was taken once from the coaches association's own archive spreadsheet and
  never needs updating.
- If no poll can be found for a season, the site falls back to the top 25 by
  its own rating and says so on the page.

Every Division I match is still downloaded and used. Ratings, strength of
schedule, replacement level and card percentiles all compare a team or player
with the whole division, not just with the 25 shown.

To show every Division I team again, set `SHOW_TOP = 0` in
`pipeline/config.py`. To show a different number, change the 25 (the poll only
ranks 25, so a bigger number has no effect).

## How it runs

The file `.github/workflows/update.yml` tells GitHub to run the pipeline:

- every night at about 5:45am Central
- whenever the code changes (these runs download for a few minutes only)
- whenever you press **Run workflow** on the repository's **Actions** tab

Each run does these things, in order:

1. **Fetch**: download any finished matches not stored yet, re-check the last
   three days for stat corrections, and refresh the schedule of matches still
   to be played.
2. **Poll**: read the current coaches poll. If the page cannot be read, the
   last poll stored is used and the run carries on.
3. **Ratings**: rate every team from its point margins and opponents, work out
   win probabilities for the coming week, and simulate the rest of the season.
4. **Stats**: build the team, player, WAR, match and card tables for the
   ranked teams.
5. **Site**: put the pages and tables together.

Results are stored on two side branches of this repository:

- `data`: the downloaded matches, the stored polls and `status.json` (what happened on the last
  run). `logs/last_run.log` has the full log, and `logs/oddities.json` counts
  play-by-play lines the reader did not understand.
- `gh-pages`: the finished website.

## Turning the website on

One-time setup in the repository's **Settings**:

**Settings → Pages → Build and deployment → Source: "Deploy from a branch"**,
then choose branch `gh-pages` and folder `/ (root)`, and save.

A minute or two later the site is live at
`https://dougmullendore.github.io/Volleyball/`.

## Where things are

| Path | What it is |
| --- | --- |
| `pipeline/config.py` | Every setting: first season, site name, rating and value weights |
| `pipeline/ncaa_api.py` | Talks to the NCAA's feed |
| `pipeline/parse.py` | Turns raw scoreboards, box scores and play-by-play into rows |
| `pipeline/fetch.py` | Decides what to download and stores it |
| `pipeline/polls.py` | Reads the coaches poll and decides which teams the site shows |
| `polls/final_polls.csv` | The final top 25 of each season from 2021 to 2025 |
| `pipeline/ratings.py` | Team ratings, win probabilities, season simulation |
| `pipeline/value.py` | Player value (points added and WAR) and player cards |
| `pipeline/aggregate.py` | Builds the tables the site shows |
| `site/` | The web pages (plain HTML, CSS and JavaScript, no build step) |
| `tests/` | Ten real matches and a saved copy of the poll page, with checks that they are read correctly |

Run the tests with `python tests/run_local.py`.

## Things the public data cannot do

- There is no shot-location data, so there is no expected-points model.
- The play-by-play does not name the server and lists substitutions too
  loosely to know who is on the court, so there are no lineup or
  with-or-without numbers.
- The poll shows a team's place today (or at the end of a finished season),
  not its place on the day of each match. The small number beside a team in
  the match list is that current or final place.
- A team that drops out of the poll leaves the site until it is ranked again;
  its matches against ranked teams stay in the match list.
- Players have no ID in the feed. A player is matched by school and name, so
  a transfer shows up as two players.

Not affiliated with or endorsed by the NCAA, the AVCA or any school.
