#!/usr/bin/env python3
"""
Usage: python fpl-stats/scripts/fetch_league.py \
    --league=<fpl_league_id> \
    --email=<fpl_username> \
    [--password=<fpl_password>] \
    [--force-fetch-all] \
    [--fetch-live] \
    [> <output_file>]
"""
import sys
import json
import time
import traceback
import argparse
import aiohttp
import asyncio
import time
import pathlib
from getpass import getpass
from fpl import FPL


BASE_FILE_PATH = None

LEAGUE_FILE_NAME = "league"
GAMEWEEKS_FILE_NAME = "gameweeks"
USER_LIST_FILE_NAME = "user_list"
USERS_FILE_NAME = "users"
PLAYERS_FILE_NAME = "players"


def read_file(file_name: str):
    if not BASE_FILE_PATH:
        raise ValueError("BASE_FILE_PATH not set")

    full_file_path = f"{BASE_FILE_PATH}/{file_name}.json"
    try:
        return json.loads(open(full_file_path).read())
    except IOError:
        # No such file or directory
        return None


def write_file(obj, file_name: str):
    if not BASE_FILE_PATH:
        raise ValueError("BASE_FILE_PATH not set")

    full_file_path = f"{BASE_FILE_PATH}/{file_name}.json"
    print(f"Writing to {full_file_path}")
    with open(full_file_path, "w") as outfile:
        json.dump(obj, outfile, indent=2)


async def fetch_league_data(
    email: str, password: str, league_id: int, force_fetch_all=False, fetch_live=False
):
    """
    Fetches league data for a given league up to the
    latest gameweek, ie. user data and player data,
    including gameweek history, picks, auto-subs and
    chip usage.

    Dumps the following json files:
    * /data/<season>/<league_id>/league.json
    * /data/<season>/<league_id>/gameweeks.json
    * /data/<season>/<league_id>/user_list.json -- simple list of users in league, with id and name
    * /data/<season>/<league_id>/users.json -- complete set of user data, with gameweek history, picks, auto-subs and chip usage
    * /data/<season>/<league_id>/players.json
    """
    async with aiohttp.ClientSession() as session:
        encountered_error = False

        print(
            "Fetching data for league %s (force_fetch_all=%s, fetch_live=%s)\n"
            % (league_id, force_fetch_all, fetch_live)
        )

        # Init FPL
        fpl = FPL(session)

        # Login
        print("Logging in")
        await fpl.login(email, password)

        # Get league
        print("\nGetting league:", league_id)
        league_result = await fpl.get_classic_league(league_id, return_json=True)
        league_info = league_result["league"]
        print("League name:", league_info["name"])

        # Identify season ("<start_year>_<end_year>")
        league_created_year = int(league_info["created"][0:4])
        season = f"{league_created_year}_{league_created_year + 1}"
        print("Season: %s" % season)

        # Set base file path: "data/<season>/<league_id>"
        global BASE_FILE_PATH
        BASE_FILE_PATH = f"data/{season}/{league_id}"

        print("Making dirs: %s" % BASE_FILE_PATH)
        pathlib.Path(BASE_FILE_PATH).mkdir(parents=True, exist_ok=True)

        # Store league data: {**league_info, "standings": [...]}
        league_standings = league_result.pop("standings")["results"]
        league_data = {**league_info, "standings": league_standings}
        write_file(league_data, LEAGUE_FILE_NAME)

        # Get users from league
        print("\nExtracting list of users from league standings")
        user_list = []
        for standing in league_standings:
            user_list.append(
                {
                    "id": standing["entry"],
                    "name": standing["entry_name"],
                    "player_name": standing["player_name"],
                }
            )
        write_file(user_list, USER_LIST_FILE_NAME)

        # Find the latest fetched and finished gameweek
        latest_finished_gameweek_number_fetched = ''
        fetched_gameweeks = read_file(GAMEWEEKS_FILE_NAME) or []
        if fetched_gameweeks:
            latest_finished_gameweek_number_fetched = next(
                (g for g in reversed(fetched_gameweeks) if g["finished"])
            )["id"]
            print(
                "Latest fetched and finished gameweek",
                latest_finished_gameweek_number_fetched,
            )

        # Get gameweeks from FPL and write to file
        print("\nGetting gameweeks")
        gameweeks = await fpl.get_gameweeks(return_json=True)
        write_file(gameweeks, GAMEWEEKS_FILE_NAME)

        latest_finished_gameweek_number = next(
            (g for g in reversed(gameweeks) if g["finished"])
        )["id"]
        print("Latest finished gameweek: %s" % latest_finished_gameweek_number)

        # Check if we already have fetched for the latest, finished gameweek
        has_fetched_for_latest_gameweek = (
            latest_finished_gameweek_number_fetched == latest_finished_gameweek_number
        )
        if has_fetched_for_latest_gameweek:
            print("Has already fetched for the latest, finished gameweek!")

        if fetch_live:
            print("Should fetch 'live' data for current/ongoing gameweek")

        # Get user data if not already fetched
        users_already_fetched = False
        users = read_file(USERS_FILE_NAME) or {}
        if users:
            user = users[list(users)[0]]
            latest_fetched_user_gameweek = user["history"][-1]["event"]
            print("\nLatest fetched user gameweek:", latest_fetched_user_gameweek)
            if (
                latest_fetched_user_gameweek >= latest_finished_gameweek_number
                and has_fetched_for_latest_gameweek
            ):
                print("\nUsers already up to date")
                users_already_fetched = True
                if force_fetch_all:
                    print("..but should force fetch")
                elif fetch_live:
                    print("..but should fetch for current gameweek")

        # Store gameweek history including picks, auto subs and chips with each user
        # Always fetch if one of `force_fetch_all` and `fetch_live` is True
        if not users_already_fetched or force_fetch_all or fetch_live:
            print("\nGetting users")
            for user in user_list:
                print("\tSleeping 4 seconds to not get 429: Too Many Requests from the API")
                time.sleep(4)
                print("\tGetting for user:", user["name"])
                user_id = str(user["id"])

                users[user_id] = {**user}

                current_user = users[user_id]

                # Get user
                print("\t\tGetting user")
                fpl_user = await fpl.get_user(user_id)
                time.sleep(0.5)

                # Get gameweek history
                print("\t\tGetting user gameweek history")
                gameweek_history = await fpl_user.get_gameweek_history()
                time.sleep(0.5)

                # Set user.history
                current_user["history"] = gameweek_history
                current_history = current_user["history"]

                # Default to empty lists of auto_subs and chips for each gameweek
                for gameweek in gameweek_history:
                    gameweek["auto_subs"] = []
                    gameweek["chips"] = []
                    gameweek["transfers"] = []

                # Get picks - store with gameweeks
                print("\t\tGetting user picks")
                picks = await fpl_user.get_picks()
                time.sleep(0.5)
                for gameweek_number, gameweek_picks in picks.items():
                    current_history[gameweek_number - 1]["picks"] = gameweek_picks

                # Get auto-subs - store both at root and for the applicable gameweeks
                print("\t\tGetting user auto-subs")
                auto_subs = await fpl_user.get_automatic_substitutions()
                time.sleep(0.5)
                current_user["auto_subs"] = auto_subs
                for auto_sub in auto_subs:
                    gameweek_number = auto_sub["event"]
                    current_history[gameweek_number - 1]["auto_subs"].append(auto_sub)

                # Get chips history - store both at root and for the applicable gameweeks
                print("\t\tGetting user chips history")
                chips = await fpl_user.get_chips_history()
                time.sleep(0.5)
                current_user["chips"] = chips
                for chip in chips:
                    gameweek_number = chip["event"]
                    current_history[gameweek_number - 1]["chips"].append(chip)

                # Get transfers
                print("\t\tGetting transfers")
                transfers = await fpl_user.get_transfers()
                time.sleep(0.5)
                current_user["transfers"] = transfers
                for transfer in transfers:
                    gameweek_number = transfer["event"]
                    current_history[gameweek_number - 1]["transfers"].append(transfer)

            # Store users
            write_file(users, USERS_FILE_NAME)

        # Get players, with gameweek history
        players: dict = read_file(PLAYERS_FILE_NAME) or {}

        # Check if we already have fetched players, and if so,
        # for which gameweeks
        latest_fetched_player_gameweek = None
        players_already_fetched = False
        if players:
            first_player = players[list(players)[0]]
            latest_fetched_player_gameweek = first_player["history"][-1]["round"]
            print("\nLatest fetched player gameweek:", latest_fetched_player_gameweek)
            if (
                latest_fetched_player_gameweek >= latest_finished_gameweek_number
                and has_fetched_for_latest_gameweek
            ):
                players_already_fetched = True
                print("\nPlayers already up to date")
                if force_fetch_all:
                    print("..but should force fetch")
                elif fetch_live:
                    print("..but should fetch for current gameweek")

        # Fetch players if applicable
        # Always fetch if one of `force_fetch_all` and `fetch_live` is True
        if not players_already_fetched or force_fetch_all or fetch_live:
            try:
                print("\nGetting players")

                # Fetch updated player data for all existing players
                print("\tUpdating existing players")
                for player_id in players.keys():
                    print("\t\tUpdating player info for:", player_id)
                    players[player_id] = await fpl.get_player(
                        int(player_id),
                        include_summary=True,
                        return_json=True,
                    )
                    time.sleep(2)

                # Only search players for the gameweeks we don't have
                # unless `force_fetch_all` is True
                gameweek_start_number = latest_finished_gameweek_number_fetched or 1
                if force_fetch_all:
                    players = {}
                    gameweek_start_number = 1

                # Get player info for each relevant player, ie.
                # each player that has been picked by at least one of
                # the users in at least one gameweek
                for user in users.values():
                    print("\tGetting for user:", user["name"])
                    gameweek_start_index = gameweek_start_number - 1
                    gameweek_history = user["history"][gameweek_start_index:]
                    for gameweek in gameweek_history:
                        print("\t\tGetting for gameweek:", gameweek["event"])
                        for pick in gameweek["picks"]:
                            player_id = str(pick["element"])
                            if not players.get(player_id):
                                print("\t\t\tGetting player info for:", player_id)
                                players[player_id] = await fpl.get_player(
                                    int(player_id),
                                    include_summary=True,
                                    return_json=True,
                                )
                                time.sleep(2)
                            else:
                                print(
                                    "\t\t\tPlayer info already fetched for:", player_id
                                )
            except Exception:
                # Probably a 429 too many requests
                print("\n!!!ERROR OCCURED!!!")
                traceback.print_exception(*sys.exc_info())
                print("\n")
                encountered_error = True

            # Store players
            write_file(players, PLAYERS_FILE_NAME)

        if not encountered_error:
            print("\nFinished successfully!")
        else:
            print("\nFinished with errors")


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", "-l", help="FPL league id", type=int, required=True)
    parser.add_argument("--email", "-e", help="FPL email", type=str, required=True)
    parser.add_argument(
        "--password", "-p", help="FPL password", type=str, required=False
    )
    parser.add_argument(
        "--force-fetch-all", help="Include to force fetch all data", action="store_true"
    )
    parser.add_argument(
        "--fetch-live",
        help="Fetch 'live' data for current gameweek",
        action="store_true",
    )

    args = parser.parse_args(sys.argv[1:])

    # Get password if not provided as argument
    email = args.email
    password = args.password
    if not password:
        password = getpass("FPL password for %s: " % email)

    # Fetch league data
    asyncio.run(
        fetch_league_data(
            email, password, args.league, args.force_fetch_all, args.fetch_live
        )
    )
