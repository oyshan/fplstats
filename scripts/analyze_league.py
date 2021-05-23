#!/usr/bin/env python3
"""
Usage: python fpl-stats/scripts/analyze_league.py \
    --season=<startyear_endyear> \
    --league=<fpl_league_id> \
    [--disable-prompt] \
    [> <output_file>]
"""
import os
import sys
import argparse

# Add base path to path to allow import of fplstats module
base_path = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, base_path)


def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--season",
        "-s",
        help="Season to analyze, e.g. '2020_2021' ",
        type=str,
        required=True,
    )
    parser.add_argument("--league", "-l", help="FPL league id", type=int, required=True)
    parser.add_argument(
        "--disable-prompt",
        help="Print league statistics immeditaly without prompts to continue",
        action="store_true",
    )

    args = parser.parse_args(sys.argv[1:])

    # Get all league statistics
    from fplstats.analyzers import LeagueAnalyzer

    league_analyzer = LeagueAnalyzer(args.season, args.league, args.disable_prompt)
    league_analyzer.get_all_statistics()


if __name__ == "__main__":
    main()
