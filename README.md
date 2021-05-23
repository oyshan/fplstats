# FPL Mini League Statistics
Get fun and mind-blowing statistics about your FPL mini league season

Built with state of the art algorithms and data structures, and, of course, powered by AI. Loljk, this is as simple (and ugly/hacky) as it gets, done with vanilla Python. TODO: make better/prettier

Shout out to `https://github.com/amosbastian/fpl` for making my life easier.

## Installing

Create virtual env
```
virtualenv env
```

Activate virtual env
```
source env/bin/activate
```

Install requirements
```
pip install -r requirements.txt
```

## Fetch data
Before analyzing, you need to fetch data. To fetch data for the current season up to the latest gameweek for your league, run:
```
python fpl-stats/scripts/fetch_data.py --league
```

This will fetch data from `fantasy.premierleague.com` and output the following files:
* `data/<season>/<league_id>/<league__gw<latest_gameweek_number>`  # league info up to the latest gameweek
* `data/<season>/<league_id>/<gameweeks__gw<latest_gameweek_number>`  # gameweeks up to the latest gameweek
* `data/<season>/<league_id>/<users__gw<latest_gameweek_number>`  # user info up to the latest gameweek
* `data/<season>/<league_id>/<players__gw<latest_gameweek_number>`  # player info for all players selected by at least one of the users in the mini league in at least one gameweek
These are more or less the raw json responses returned from `fantasy.premierleague.com` dumped to file

## Analyze data
After fecthing data you can analyze your mini league season data by running:
```
python fpl-stats/scripts/analyze_data.py --season --league --gameweek
```
This will output all statistics for your league.
If you don't want to press Enter to continue between each statistic, add the `--disable-prompt` argument.
You could also output the results to file by adding `> output.txt` if you want to store the results.

You could also start your own python shell and get the statistics you are interested in, e.g.
```
python
>>> from fpl-stats.models import FPLStatistics
>>> # Init
>>> fpl_stats = FPLStatistics(season=<season_id>, league=<league_id>, gameweek=<gameweek_number>)
>>> # Get the statistics you want, e.g.
>>> fpl_stats.get_captain_hindsight()
TEAM          CAPTAIN POINTS
Soccer MC's   1413
CHANGE NAME   1337
>>> # Etc.
```