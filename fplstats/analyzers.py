from typing import Dict, List, Optional, TypeVar

from prettytable import PrettyTable
from pydantic import BaseModel

from fplstats.constants import MIN_DEFS, MIN_FWDS, MIN_MIDS
from fplstats.enums import Chip, Position
from fplstats.models import (
    Gameweek,
    Gameweeks,
    League,
    Player,
    PlayerDict,
    PlayerHistory,
    User,
    UserDict,
    UserList,
    UserListItem,
)
from fplstats.utils import read_file, read_file_to_model


# TODO: move to typing.py (or similar)?
class ResultRow(BaseModel):  # total:
    id: str  # user id
    name: str  # user name


class HistoricStandingListItem(BaseModel):
    id: str  # user id
    name: str  # user name
    total_points: int


HistoricStandings = List[List[HistoricStandingListItem]]


class PlayerGameweekCombinedResult(BaseModel):
    total_points: int = 0
    minutes: int = 0
    goals_scored: int = 0
    assists: int = 0
    clean_sheets: int = 0
    goals_conceded: int = 0
    own_goals: int = 0
    penalties_saved: int = 0
    penalties_missed: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    saves: int = 0
    bonus: int = 0
    bps: int = 0


class GameweekPlayer(BaseModel):
    player: Player
    combined_result: PlayerGameweekCombinedResult
    results: List[PlayerHistory]


class BiggestLeaderResultRow(ResultRow):
    point_gap: int
    gameweek: int


class BiggestLoserResultRow(BiggestLeaderResultRow):
    pass


class LongestLeaderResultRow(ResultRow):
    first_place_count: int


class LongestLoserResultRow(ResultRow):
    last_place_count: int


class CaptainResultRow(ResultRow):
    total_captain_points: int
    total_vc_points: int
    total_gameweeks_with_vc: int
    total_gameweeks_without_captain: int


class PointsWithoutCaptainResultRow(ResultRow):
    points: int


class TopScorerResultRow(ResultRow):
    goals_scored: int


class AssistKingResultRow(ResultRow):
    assists: int


class GoalInvolvementsResultRow(ResultRow):
    goal_involvements: int


# Not sure why, but we need to type annotate
# self in LeagueAnalyzer methods to make mypy
# type check attributes on self.
# Annyoing, but it works..
T = TypeVar("T", bound="LeagueAnalyzer")


class LeagueAnalyzer(object):
    """
    Analyzer for FPL mini league statistics
    """

    league: League
    gameweeks: Gameweeks
    users: UserDict
    user_list: UserList
    players: PlayerDict

    _latest_gameweek: Optional[Gameweek] = None
    _historic_standings: Optional[HistoricStandings] = None

    def __init__(
        self: T, season: str, league_id: int, disable_prompt=False, live=False
    ):
        self.season = season
        self.league_id = league_id
        self.disable_prompt = disable_prompt
        self.live = live

        # Read league data for season
        # TODO: use file name constants
        base_data_path = f"data/{season}/{league_id}"
        try:
            self.league = read_file_to_model(f"{base_data_path}/league.json", League)

            raw_gameweeks = read_file(f"{base_data_path}/gameweeks.json")
            self.gameweeks: Gameweeks = [
                Gameweek.parse_obj(obj) for obj in raw_gameweeks
            ]

            raw_user_list = read_file(f"{base_data_path}/user_list.json")
            self.user_list: UserList = [
                UserListItem.parse_obj(obj) for obj in raw_user_list
            ]

            raw_users = read_file(f"{base_data_path}/users.json")
            self.users: UserDict = {}
            for user_id, user in raw_users.items():
                self.users[user_id] = User.parse_obj(user)

            raw_players = read_file(f"{base_data_path}/players.json")
            self.players: PlayerDict = {}
            for player_id, player in raw_players.items():
                self.players[player_id] = Player.parse_obj(player)
        except IOError:
            raise Exception(
                f"No data found for season {season} and league {league_id}. You need to fetch league data by running the `fetch_league` script"
            )

    def print_result(self: T, results: List[dict], attrs: Dict[str, str]):
        """
        Helper method for printing results
        `results` is a list of dictionaries
        `attrs` is a dictionary with labels as keys and
            field names as values
        """
        table = PrettyTable()
        table.field_names = attrs.keys()
        table.add_rows([[*[x[v] for v in attrs.values()]] for x in results])
        print(table)

    def get_latest_gameweek(self: T) -> Gameweek:
        """
        Get latest finished gameweek, or the current gameweek
        (if exists) if `self.live` is True
        """
        if self._latest_gameweek is not None:
            return self._latest_gameweek

        latest_finished_gameweek = next(
            (x for x in reversed(self.gameweeks) if x.finished)
        )
        self._latest_gameweek = latest_finished_gameweek

        if self.live:
            current_gameweek = next((x for x in self.gameweeks if x.is_current), None)
            if current_gameweek:
                self._latest_gameweek = current_gameweek

        return self._latest_gameweek

    def get_latest_gameweek_number(self: T) -> int:
        return self.get_latest_gameweek().id

    def get_historic_standings(self: T) -> HistoricStandings:
        if self._historic_standings:
            return self._historic_standings

        # Build historic standings for each finished gameweek
        historic_standings: HistoricStandings = []

        finished_gameweeks: Gameweeks = [x for x in self.gameweeks if x.finished]
        for i, gameweek in enumerate(finished_gameweeks):
            gameweek_standings = []

            # Get total points for each user for gameweek
            for user in self.users.values():
                user_gameweek = user.history[i]
                gameweek_standings.append(
                    HistoricStandingListItem(
                        id=user.id,
                        name=user.name,
                        total_points=user_gameweek.total_points,
                    )
                )

            # Sort gameweek standings and add to historic standings
            gameweek_standings = sorted(
                gameweek_standings, key=lambda x: x.total_points, reverse=True
            )
            historic_standings.append(gameweek_standings)

        # Set self._historic_standings and return
        self._historic_standings = historic_standings
        return self._historic_standings

    def get_player_gameweek_results(
        self: T, player_id: str, gameweek_number: int
    ) -> List[PlayerHistory]:
        """
        Returns list of gameweek results for player
        as there may be a blank/double gameweek
        """
        player = self.players[str(player_id)]
        player_history = player.history
        return [x for x in player_history if x.round == gameweek_number]

    def get_combined_gameweek_result_for_player(
        self: T, player_id: str, gameweek_number: int
    ) -> PlayerGameweekCombinedResult:
        # Get player's gameweek results
        # (Can be one, two (dgw), three (tgw) or none (bgw))
        player_gw_results = self.get_player_gameweek_results(player_id, gameweek_number)

        # Combine player's gameweek results
        combined_result = PlayerGameweekCombinedResult()
        for player_gw_result in player_gw_results:
            for key in combined_result.__fields__.keys():
                current_value = getattr(combined_result, key)
                new_value = getattr(player_gw_result, key)
                setattr(combined_result, key, current_value + new_value)
                # Use pick multiplier to give captain/triple captain points
                # if key == "total_points":
                #     new_value = pick.multiplier * getattr(player_gw_result, key)
                # else:
                #     new_value = getattr(player_gw_result, key)

                # current_value = getattr(combined_result, key)
                # setattr(combined_result, key, current_value + new_value)

        return combined_result

    def get_gameweek_players(
        self: T, user_id: str, gameweek_number: int
    ) -> List[GameweekPlayer]:
        """
        Gets list of players who played for the user in a given gameweek
        The list includes player info and combined gameweek results
        """
        user: User = self.users[str(user_id)]
        user_gameweek = user.history[gameweek_number - 1]
        gameweek_players: List[GameweekPlayer] = []
        for pick in user_gameweek.picks:
            # Player played for user if multiplier >= 1
            if pick.multiplier >= 1:
                player_id = pick.element
                player = self.players[player_id]
                player_gw_results = self.get_player_gameweek_results(
                    player_id, gameweek_number
                )

                # Combine player's gameweek results
                combined_result = PlayerGameweekCombinedResult()
                for player_gw_result in player_gw_results:
                    for key in combined_result.__fields__.keys():
                        # Use pick multiplier to give captain/triple captain points
                        if key == "total_points":
                            new_value = pick.multiplier * getattr(player_gw_result, key)
                        else:
                            new_value = getattr(player_gw_result, key)

                        current_value = getattr(combined_result, key)
                        setattr(combined_result, key, current_value + new_value)

                gameweek_players.append(
                    GameweekPlayer(
                        player=player,
                        combined_result=combined_result,
                        results=player_gw_results,
                    )
                )

        return gameweek_players

    def get_player_totals(
        self: T,
        attributes: Dict[str, str],
        sort_by: str,
        descending=True,
        print_result=True,
    ) -> List[dict]:
        """
        Helper method for getting and displaying total player statistic
        * `attributes`: dict with keys/labels, e.g. {"goals_scored", "Total goals scored"}
        * `sort_by`: the attribute the result should be sorted by
        * `descending`: if the result should be sorted in descending or ascending order
        * `print_result`: if the result should be printed
        Return list with total player statistics, including user ids and names
        """
        results: List[dict] = []

        # Aggregate player stats for each user
        for user in self.users.values():
            totals = {}
            for key in attributes.keys():
                totals[key] = 0

            for gameweek in user.history:
                gw_number = gameweek.event
                gw_players = self.get_gameweek_players(user.id, gw_number)
                for gw_player in gw_players:
                    for key in totals.keys():
                        totals[key] += getattr(gw_player.combined_result, key)

            results.append({"id": user.id, "name": user.name, **totals})

        # Sort
        results = sorted(results, key=lambda x: x[sort_by], reverse=descending)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", *attributes.values()]
            table.add_rows(
                [[x["name"], *[x[key] for key in attributes.keys()]] for x in results]
            )
            print(table)

        return results

    def get_player_gameweek_ownership_share(
        self: T, player_id: str, gameweek_number: int
    ) -> float:
        """
        Calculate the player's ownership share in the
        league for a given gameweek
        """
        users_count = len(self.user_list)
        owned_by_count = 0
        for user in self.users.values():
            user_gw = user.history[gameweek_number - 1]
            user_gw_picks = user_gw.picks
            player_ids = [x.element for x in user_gw_picks]
            if player_id in player_ids:
                owned_by_count += 1

        return owned_by_count / users_count

    def get_all_statistics(self: T):
        """
        Get (and print out) all statistics for loaded league
        up to latest finished/ongoing gameweek
        """
        latest_gw = self.get_latest_gameweek()
        if latest_gw.finished:
            latest_gw_status_str = "finished"
        elif latest_gw.is_current:
            latest_gw_status_str = "ongoing"
        else:
            raise ValueError("Invalid latest gameweek")

        print(
            "%s-statistikk for %s til og med gameweek %s (%s)\n"
            % (
                self.season,
                self.league.name,
                self.get_latest_gameweek_number(),
                latest_gw_status_str,
            )
        )

        print("\n\nÅRETS VISJONÆRE")
        print("What if-tabell for GW1-picks")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_gw1_picks_standings()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("ÅRETS CAPTAIN FORESIGHT")
        print("Spillerne med flest kapteinspoeng")
        print(
            'Her teller kun "ekstra" poeng spilleren gir for å være kaptein, ie. 1 x for normal kaptein og 2 x for triple'
        )
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_captain_foresight()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS CAPTAIN HINDSIGHT")
        print("Spillerne med flest poeng UTEN kapteinspoeng")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_captain_hindsight()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS LENGSTE LEDER")
        print("Spillerne som har ledet ligaen flest gameweeks")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_longest_leader()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS LENGSTE BALLETAK")
        print("Spillerne som har vært på sisteplass i ligaen flest gameweeks")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_longest_loser()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS STØRSTE LEDER")
        print("Lagene som har ledet med flest poeng ligaen")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_biggest_leader()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS STØRSTE BALLETAK")
        print("Lagene som har ligget bakerst med flest poeng ligaen")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_biggest_loser()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS GULLSTØVEL")
        print("Spillerne som har scoret flest mål")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_top_scorers()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS ASSISTKONGE")
        print("Spillerne som har flest assists")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_assist_kings()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS MÅLRETTEDE")
        print("Spillerne som har flest mål+assists")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_goal_involvements()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS FORSVARSLØSE")
        print("Spillerne som har flest mål imot fra spillende keepere og forsvarere")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_goals_conceded()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS SKUDDSIKRE")
        print(
            "Spillerne som har flest clean sheets fra spillende keepere og forsvarere"
        )
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_clean_sheets()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS KEEPER")
        print("Spillerne som har flest strafferedninger")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_penalties_saved()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS FORMSPILLER")
        print("Spillerne med høyest total ila. fem etterfølgende runder")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_best_streaks()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS UTE-AV-FORMSPILLER")
        print("Spillerne med lavest total ila. fem etterfølgende runder")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_worst_streaks()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS ANKER")
        print("Minst differanse mellom beste og verste GW")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_stable_user()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS BENKESLITER")
        print("Spillerne med mest poeng på benken (eksklusiv autoinnbyttere)")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_bench_points()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS SUPERINNBYTTER")
        print("Spillerne med mest autoinnbytterpoeng")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_auto_sub_points()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS STYGGE SPILLER")
        print(
            "Spillerne med flest minuspoeng for rødt+gult kort (fra spillende spillere)"
        )
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_cards()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS SELVEIDE")
        print("Spillerne med flest selvmål")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_own_goals()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS BOMSPILLER")
        print("Spillerne med flest straffebom")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_penalties_missed()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS BONUSSPILLER")
        print("Spillerne med flest bonuspoeng")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_bonus_points()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS MVP")
        print(
            "Spillerne som har gitt mest poeng til et lag ila. sesongen, inklusive kapteinspoeng"
        )
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_points_by_player()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS BESTE DIFF")
        print(
            "Spillerne som har gitt mest poeng (totalt, i snitt og på én runde) for et lag"
        )
        print("max_ownership_share for en differential er satt til 0.3")
        print(
            "Utregning av diff points for hver runde: gw_points/owned_by_count --> poeng den spilleren kun gir det laget"
        )
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_best_differential()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS HØYESTE RANK")
        print("Spillerne med høyest gw+overall rank")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_highest_rank()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS LAVESTE RANK")
        print("Spillerne med lavest gw+overall rank")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_lowest_rank()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS TEMPLATE")
        print(
            "Managerne med likest lag som de andre (i snitt per spiller per gameweek)"
        )
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_template_percentage()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS VINGLEPETTER")
        print("Managerne som har vært innom flest plasser på tabellen")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_league_positions()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS CHIPP-KONGE")
        print("Mest poeng på chips")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_chip_points()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS PIMP")
        print("Mest hits, best hits (samme gameweek)")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_hits()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS HIGHSCORE")
        print("Mest poeng på én gameweek")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_gw_points()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS LOWSCORE")
        print("Lavest poeng på én gameweek")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_least_gw_points()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS RUNDBRENNER")
        print("Managerne som har vært innom flest unike spillere")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_most_distinct_players()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS SPÅMANN")
        print("Mest poeng fra spillere byttet inn samme runde")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_best_transfers()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS KARMA")
        print("Mest poeng fra spillere byttet UT samme runde")
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_worst_transfers()

        if not self.disable_prompt:
            input("\n\nTrykk Enter for neste statistikk\n\n")

        print("\n\nÅRETS VANILLA (ICE)")
        print(
            "Mest vaniljepoeng, ie. poengtotal ekskludert ekstra kapteinspoeng (inkl. TC), auto-subs og benkespillere fra bench boost"
        )
        if not self.disable_prompt:
            input("Trykk Enter for å se resultatet")
        self.get_vanilla_standings()

        print("\n\nFERDIG!")

    def get_gw1_picks_standings(self: T, print_result=True):
        """
        Calculate total for gw1 picks for each user,
        including vice captain and auto-subs points
        NOTE: I know this is a terrible implementation. Deal with it.
        """
        gw_numbers = [x.id for x in self.gameweeks if x.finished]

        results: List[dict] = []
        for user in self.users.values():
            # Skip if user started after gameweek 1
            if user.history[0].picks == []:
                results.append(
                    {
                        "user_id": user.id,
                        "user_name": user.name,
                        "total_points": 0,
                        "gw1_player_names": "",
                        "captain_name": "",
                        "total_captain_points": 0,
                        "vice_captain_name": "",
                        "captain_vc_names": "",
                        "total_vice_captain_points": 0,
                        "total_auto_sub_points": 0,
                    }
                )
                continue

            gw1_all_picks = user.history[0].picks
            gw1_starting_picks = gw1_all_picks[:11]
            assert len(gw1_starting_picks) == 11
            gw1_bench_picks = gw1_all_picks[11:]
            assert len(gw1_bench_picks) == 4

            # Keep track of overall, captain/vc and
            # auto-sub totals
            captain_pick = next((x for x in gw1_starting_picks if x.is_captain))
            total_captain_points = 0
            vc_pick = next((x for x in gw1_all_picks if x.is_vice_captain))
            total_vice_captain_points = 0
            total_points = 0
            total_auto_sub_points = 0

            # Keep of track of points for each player
            points_per_player = {}
            for gw1_pick in gw1_all_picks:
                points_per_player[gw1_pick.element] = 0

            # For each gameweek, get gw points, points per player,
            # captain/vc points and auto-sub points
            for gw_number in gw_numbers:
                total_gw_points = 0
                captain_mins, captain_points = 0, 0
                vc_mins, vc_points = 0, 0
                gk = None
                defs: List[Player] = []
                mids: List[Player] = []
                fwds: List[Player] = []

                # For each starting/first pick, add to total, captain/vc
                # and player points and to "gw squad"
                for i, starting_pick in enumerate(gw1_starting_picks):
                    starting_player = self.players[starting_pick.element]
                    starting_player_pos = starting_player.element_type
                    starting_player_gw = self.get_combined_gameweek_result_for_player(
                        starting_player.id, gw_number
                    )
                    if starting_pick.is_captain:
                        captain_mins = starting_player_gw.minutes
                        captain_points = starting_player_gw.total_points
                    elif starting_pick.is_vice_captain:
                        vc_mins = starting_player_gw.minutes
                        vc_points = starting_player_gw.total_points

                    # If player played, add to gw squad in the right position
                    if starting_player_gw.minutes:
                        if starting_player_pos == Position.GOALKEEPER:
                            gk = starting_player
                        elif starting_player_pos == Position.DEFENDER:
                            defs.append(starting_player)
                        elif starting_player_pos == Position.MIDFIELDER:
                            mids.append(starting_player)
                        else:
                            fwds.append(starting_player)

                        # Add player's gw points to total gw points
                        # players.append(player)
                        points_per_player[
                            starting_player.id
                        ] += starting_player_gw.total_points
                        total_gw_points += starting_player_gw.total_points

                # Add captain/VC points
                if captain_mins:
                    total_gw_points += captain_points
                    total_captain_points += captain_points
                elif vc_mins:
                    total_gw_points += vc_points
                    total_vice_captain_points += vc_points

                # Auto-sub keeper if applicable
                gw_bench_picks = [*gw1_bench_picks]
                gk_bench_pick = gw_bench_picks[0]
                if not gk:
                    gk_player_id = gk_bench_pick.element
                    gk_bench_player_gw = self.get_combined_gameweek_result_for_player(
                        gk_player_id, gw_number
                    )
                    if gk_bench_player_gw.minutes:
                        gk = self.players[gk_player_id]
                        total_auto_sub_points += gk_bench_player_gw.total_points
                        points_per_player[
                            gk_player_id
                        ] += gk_bench_player_gw.total_points
                del gw_bench_picks[0]

                # Auto-sub outfield players if applicable
                assert len(gw_bench_picks) == 3
                while gw_bench_picks:
                    for (i, bench_pick) in enumerate(gw_bench_picks):
                        should_be_force_subbed_in = False
                        should_be_subbed_in = False
                        should_be_removed = False

                        # Check "outfield player status"
                        outfield_players = defs + mids + fwds
                        if len(outfield_players) == 10:
                            # If "outfield players" is full (ie. 10) we
                            # can't sub in any more. Clear bench and break
                            gw_bench_picks = []
                            break
                        elif len(outfield_players) + len(gw_bench_picks) <= 10:
                            # If there are open spots for for ALL the remaining
                            # bench players, they can all be subbed in (I think..)
                            should_be_force_subbed_in = True

                        # Get outfield bench player
                        bench_player = self.players[bench_pick.element]
                        bench_player_gw = self.get_combined_gameweek_result_for_player(
                            bench_player.id, gw_number
                        )
                        bench_player_pos = bench_player.element_type

                        if not bench_player_gw.minutes:
                            # Outfield bench player didn't play
                            # -> remove
                            should_be_removed = True
                        else:
                            # Outfield bench player played!
                            # -> Check if we can sub in
                            if bench_player_pos == Position.DEFENDER:
                                if (
                                    len(defs) < MIN_DEFS
                                    or (len(mids) >= MIN_MIDS and len(fwds) >= MIN_FWDS)
                                    or should_be_force_subbed_in
                                ):
                                    should_be_subbed_in = True
                                    defs.append(bench_player)
                            elif bench_player_pos == Position.MIDFIELDER:
                                if (
                                    len(mids) < MIN_MIDS
                                    or (len(defs) >= MIN_DEFS and len(fwds) >= MIN_FWDS)
                                    or should_be_force_subbed_in
                                ):
                                    should_be_subbed_in = True
                                    mids.append(bench_player)
                            elif bench_player_pos == Position.MIDFIELDER:
                                if (
                                    len(fwds) < MIN_FWDS
                                    or (len(defs) >= MIN_DEFS and len(mids) >= MIN_MIDS)
                                    or should_be_force_subbed_in
                                ):
                                    should_be_subbed_in = True
                                    fwds.append(bench_player)

                        # If last bench pick and we still can't add -> remove
                        is_last_pick = i == (len(gw_bench_picks) - 1)
                        if is_last_pick and not should_be_subbed_in:
                            should_be_removed = True

                        # Remove or sub in outfield bench player, else
                        # continue to next bench player
                        if should_be_removed:
                            del gw_bench_picks[i]
                            break
                        elif should_be_subbed_in:
                            # Sub in and add to totals!
                            total_gw_points += bench_player_gw.total_points
                            total_auto_sub_points += bench_player_gw.total_points
                            points_per_player[
                                bench_pick.element
                            ] += bench_player_gw.total_points
                            del gw_bench_picks[i]
                            break

                # Finally, add total_gw_points to total points
                total_points += total_gw_points

            # Format picks
            players_repr = ""
            current_pos = Position.GOALKEEPER
            for (i, p) in enumerate(gw1_all_picks):
                player = self.players[p.element]

                is_bench_pick = i >= 11
                if i == 11:
                    # Separate bench from other players
                    players_repr += "\n-\n"

                player_pos = player.element_type
                if player_pos != current_pos and not is_bench_pick:
                    players_repr += "\n"
                current_pos = player_pos

                cap_label = ""
                if p.is_captain:
                    cap_label = "(C)"
                elif p.is_vice_captain:
                    cap_label = "(VC)"

                player_label = (
                    f"{player.web_name}{cap_label} ({points_per_player[p.element]})"
                )
                players_repr += player_label + " "
            players_repr += "\n"

            # Add to results
            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "total_points": total_points,
                    "gw1_player_names": players_repr,
                    "captain_name": self.players[captain_pick.element].web_name,
                    "total_captain_points": total_captain_points,
                    "vice_captain_name": self.players[vc_pick.element].web_name,
                    "captain_vc_names": f"{self.players[captain_pick.element].web_name} ({self.players[vc_pick.element].web_name})",
                    "total_vice_captain_points": total_vice_captain_points,
                    "total_auto_sub_points": total_auto_sub_points,
                }
            )

        # Sort results
        results = sorted(results, key=lambda x: x["total_points"], reverse=True)

        if print_result:
            self.print_result(
                results,
                {
                    "Team": "user_name",
                    "Total points": "total_points",
                    "C points": "total_captain_points",
                    "VC points": "total_vice_captain_points",
                    "Auto-sub points": "total_auto_sub_points",
                    "GW1 picks": "gw1_player_names",
                },
            )

        return results

    def get_longest_leader(self: T, print_result=True) -> List[LongestLeaderResultRow]:
        """
        The user who has been in 1st place for the most gameweeks
        Return list of all users from high to low
        """
        # Get historic standings and create list of leaders
        # per gameweek
        historic_standings = self.get_historic_standings()
        first_place_user_ids = [x[0].id for x in historic_standings]

        # Count first places for each user
        results = []
        for user in self.users.values():
            results.append(
                LongestLeaderResultRow(
                    id=user.id,
                    name=user.name,
                    first_place_count=first_place_user_ids.count(user.id),
                )
            )

        # Sort list, high to low
        results = sorted(results, key=lambda x: x.first_place_count, reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Total number of gameweeks in first place"]
            table.add_rows([[x.name, x.first_place_count] for x in results])
            print(table)

        return results

    def get_longest_loser(self: T, print_result=True) -> List[LongestLoserResultRow]:
        """
        The user who has been in last place for the most gameweeks
        Return list of all users from high to low
        """
        # Get historic standings and create list of leaders
        # per gameweek
        historic_standings = self.get_historic_standings()
        last_place_user_ids = [x[-1].id for x in historic_standings]

        # Count first places for each user
        results = []
        for user in self.users.values():
            results.append(
                LongestLoserResultRow(
                    id=user.id,
                    name=user.name,
                    last_place_count=last_place_user_ids.count(user.id),
                )
            )

        # Sort list, high to low
        results = sorted(results, key=lambda x: x.last_place_count, reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Total number of gameweeks in last place"]
            table.add_rows([[x.name, x.last_place_count] for x in results])
            print(table)

        return results

    def get_biggest_leader(self: T, print_result=True) -> List[BiggestLeaderResultRow]:
        """
        The user(s) who has led by the most points in a gameweek
        Return list of users
        """
        # Get historic standings and create list of leaders
        # per gameweek
        historic_standings = self.get_historic_standings()

        biggest_leaders: List[BiggestLeaderResultRow] = []
        for i, standing in enumerate(historic_standings):
            first_place = standing[0]
            second_place = standing[1]
            point_gap = first_place.total_points - second_place.total_points

            biggest_leaders.append(
                BiggestLeaderResultRow(
                    id=first_place.id,
                    name=first_place.name,
                    point_gap=point_gap,
                    gameweek=i + 1,
                )
            )

        # Sort by biggest point gap
        biggest_leaders = sorted(
            biggest_leaders, key=lambda x: x.point_gap, reverse=True
        )

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Biggest point gap", "Gameweek"]
            table.add_rows(
                [[x.name, x.point_gap, x.gameweek] for x in biggest_leaders[:10]]
            )
            print(table)

        return biggest_leaders

    def get_biggest_loser(self: T, print_result=True) -> List[BiggestLoserResultRow]:
        """
        The user(s) who has been behind by the most points in a gameweek
        Return list of users
        """
        # Get historic standings and create list of losers
        # per gameweek
        historic_standings = self.get_historic_standings()
        user_count = len(historic_standings[0])

        biggest_losers: List[BiggestLoserResultRow] = []
        for i, standing in enumerate(historic_standings):
            last_place = standing[user_count - 1]
            second_last_place = standing[user_count - 2]
            point_gap = last_place.total_points - second_last_place.total_points

            biggest_losers.append(
                BiggestLoserResultRow(
                    id=last_place.id,
                    name=last_place.name,
                    point_gap=point_gap,
                    gameweek=i + 1,
                )
            )

        # Sort by biggest (negative) point gap
        biggest_losers = sorted(biggest_losers, key=lambda x: x.point_gap)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Biggest point gap", "Gameweek"]
            table.add_rows(
                [[x.name, x.point_gap, x.gameweek] for x in biggest_losers[:10]]
            )
            print(table)

        return biggest_losers

    def get_captain_foresight(self: T, print_result=True) -> List[CaptainResultRow]:
        """
        Most captain points (inlcuding vice captain and TC). Only counts
        the "extra captain points", ie. 1 * total gw points for a normal
        captain, and 2 * total gw points for a triple captain.
        Return list of all users from high to low
        """
        results = []

        # For each user, calculate total captain points
        for user in self.users.values():
            total_captain_points = 0
            total_vc_points = 0
            total_gameweeks_with_vc = 0
            total_gameweeks_without_captain = 0

            for user_gw in user.history:
                # Skip gameweek if "empty" (ie. the user started after this gameweek)
                if not user_gw.picks:
                    continue

                # Get player gw results and captain + vc picks
                gw_players = self.get_gameweek_players(user.id, user_gw.event)
                captain_pick = next((p for p in user_gw.picks if p.is_captain))
                vc_pick = next((p for p in user_gw.picks if p.is_vice_captain))

                # Increase total captain/vc picks by using the
                # pick multiplier (2 for normal captain, 3 for TC, 0 if not played)
                if captain_pick.multiplier:
                    captain_gw = next(
                        (x for x in gw_players if x.player.id == captain_pick.element)
                    )
                    total_captain_points += (
                        captain_pick.multiplier - 1
                    ) * captain_gw.combined_result.total_points
                elif vc_pick.multiplier:
                    vc_gw = next(
                        (x for x in gw_players if x.player.id == vc_pick.element)
                    )
                    vc_gw_points = (
                        vc_pick.multiplier - 1
                    ) * vc_gw.combined_result.total_points
                    total_captain_points += vc_gw_points
                    total_vc_points += vc_gw_points
                    total_gameweeks_with_vc += 1
                else:
                    total_gameweeks_without_captain += 1

            results.append(
                CaptainResultRow(
                    id=user.id,
                    name=user.name,
                    total_captain_points=total_captain_points,
                    total_vc_points=total_vc_points,
                    total_gameweeks_with_vc=total_gameweeks_with_vc,
                    total_gameweeks_without_captain=total_gameweeks_without_captain,
                )
            )

        # Sort by total captain points, descending
        results = sorted(results, key=lambda x: x.total_captain_points, reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total captain points",
                "Total captain points when VC stepped in",
                "Total gameweeks where VC stepped in",
                "Gameweeks without captain/VC",
            ]
            table.add_rows(
                [
                    [
                        x.name,
                        x.total_captain_points,
                        x.total_vc_points,
                        x.total_gameweeks_with_vc,
                        x.total_gameweeks_without_captain,
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_captain_hindsight(
        self: T, print_result=True
    ) -> List[PointsWithoutCaptainResultRow]:
        """
        Most points without captain points
        Return overall standings without captain points
        """
        captain_foresight_results = self.get_captain_foresight(print_result=False)

        results = []

        for row in captain_foresight_results:
            user_id = row.id
            user = self.users[user_id]
            total_points = user.history[-1].total_points
            total_points_minus_captain_points = total_points - row.total_captain_points

            results.append(
                PointsWithoutCaptainResultRow(
                    id=row.id,
                    name=row.name,
                    points=total_points_minus_captain_points,
                )
            )

        results = sorted(results, key=lambda x: x.points, reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Total points excluding captain points"]
            table.add_rows([[x.name, x.points] for x in results])
            print(table)

        return results

    def get_top_scorers(self: T, print_result=True) -> List[TopScorerResultRow]:
        """
        Most goals scored (auto-subs included)
        Return list of users, high to low
        """
        results = []

        # Count goals scored by each user
        for user in self.users.values():
            goals_scored = 0
            for gameweek in user.history:
                gameweek_number = gameweek.event

                # Summarize goals scored by each playing player for the user
                gw_players = self.get_gameweek_players(user.id, gameweek_number)
                for gw_player in gw_players:
                    goals_scored += gw_player.combined_result.goals_scored

            results.append(
                TopScorerResultRow(
                    id=user.id, name=user.name, goals_scored=goals_scored
                )
            )

        # Sort by goals scored
        results = sorted(results, key=lambda x: x.goals_scored, reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Goals scored"]
            table.add_rows([[x.name, x.goals_scored] for x in results])
            print(table)

        return results

    def get_assist_kings(self: T, print_result=True) -> List[AssistKingResultRow]:
        """
        Most assists (auto-subs included)
        Return list of users, high to low
        """
        results = []

        # Count assists by each user
        for user in self.users.values():
            assists = 0
            for gameweek in user.history:
                gameweek_number = gameweek.event

                # Summarize assists by each playing player for the user
                gw_players = self.get_gameweek_players(user.id, gameweek_number)
                for gw_player in gw_players:
                    assists += gw_player.combined_result.assists

            results.append(
                AssistKingResultRow(id=user.id, name=user.name, assists=assists)
            )
        # Sort by assists
        results = sorted(results, key=lambda x: x.assists, reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Assists"]
            table.add_rows([[x.name, x.assists] for x in results])
            print(table)

        return results

    def get_most_goal_involvements(
        self: T, print_result=True
    ) -> List[GoalInvolvementsResultRow]:
        """
        Most goal involvements (auto-subs included)
        Return list of users, high to low
        """
        # Reuse self.get_top_scorers and self.get_assist_kings
        top_scorers = self.get_top_scorers(print_result=False)
        assist_kings = self.get_assist_kings(print_result=False)

        # Summarize goals + assist for each user
        results = []
        for user in self.users.values():
            goals = next(x.goals_scored for x in top_scorers if x.id == user.id)
            assists = next(x.assists for x in assist_kings if x.id == user.id)
            results.append(
                GoalInvolvementsResultRow(
                    id=user.id, name=user.name, goal_involvements=goals + assists
                )
            )

        # Sort by goal involvements
        results = sorted(results, key=lambda x: x.goal_involvements, reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Goal involvements"]
            table.add_rows([[x.name, x.goal_involvements] for x in results])
            print(table)

        return results

    def get_best_streaks(self: T, print_result=True):
        """
        The most points during a 5-gameweek stretch, ie.
        the most inform-user
        """
        results: List[dict] = []
        for user in self.users.values():
            highest_five_gw_total = 0
            highest_from_gameweek = 0
            for i in range(0, self.get_latest_gameweek_number()):
                # Skip first 4 gameweeks
                if i < 4:
                    continue

                # Aggregate total for last 5 gameweeks
                last_five_gw_total = 0
                from_gameweek_index = i - 4
                to_gameweek_index = i + 1
                for j in range(from_gameweek_index, to_gameweek_index):
                    gameweek = user.history[j]
                    last_five_gw_total += gameweek.points

                if last_five_gw_total > highest_five_gw_total:
                    highest_five_gw_total = last_five_gw_total
                    highest_from_gameweek = from_gameweek_index + 1

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total": highest_five_gw_total,
                    "avg": highest_five_gw_total / 5,
                    "from_gameweek": highest_from_gameweek,
                    "to_gameweek": highest_from_gameweek + 4,
                }
            )

        # Sort by total
        results = sorted(results, key=lambda x: x["total"], reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total points",
                "Average points",
                "From gameweek",
                "To gameweek",
            ]
            table.add_rows(
                [
                    [
                        x["name"],
                        x["total"],
                        x["avg"],
                        x["from_gameweek"],
                        x["to_gameweek"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_worst_streaks(self: T, print_result=True):
        """
        The least points during a 5-gameweek stretch, ie.
        the most out-of-shape user
        """
        results: List[dict] = []
        for user in self.users.values():
            lowest_five_gw_total = float("inf")
            lowest_from_gameweek = 0
            for i in range(0, self.get_latest_gameweek_number()):
                # Skip first 4 gameweeks
                if i < 4:
                    continue

                # Aggregate total for last 5 gameweeks
                last_five_gw_total = 0
                from_gameweek_index = i - 4
                to_gameweek_index = i + 1
                for j in range(from_gameweek_index, to_gameweek_index):
                    gameweek = user.history[j]
                    last_five_gw_total += gameweek.points

                if last_five_gw_total < lowest_five_gw_total:
                    lowest_five_gw_total = last_five_gw_total
                    lowest_from_gameweek = from_gameweek_index + 1

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total": lowest_five_gw_total,
                    "avg": lowest_five_gw_total / 5,
                    "from_gameweek": lowest_from_gameweek,
                    "to_gameweek": lowest_from_gameweek + 4,
                }
            )

        # Sort by total, lowest first
        results = sorted(results, key=lambda x: x["total"])

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total points",
                "Average points",
                "From gameweek",
                "To gameweek",
            ]
            table.add_rows(
                [
                    [
                        x["name"],
                        x["total"],
                        x["avg"],
                        x["from_gameweek"],
                        x["to_gameweek"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_stable_user(self: T, print_result=True):
        """
        Lowest difference between highest and lowest gameweek
        Add average and total as well?
        """
        # Minst differense mellom høyest GW-score og lavest GW-score
        # bruk get_most_gw_points og get_least_gw_points
        results: List[dict] = []
        for user in self.users.values():
            highest_gw_points = 0
            lowest_gw_points = 999999
            for user_gw in user.history:
                if user_gw.rank is None:
                    # non-finished gameweek
                    continue

                if user_gw.points > highest_gw_points:
                    highest_gw_points = user_gw.points

                if user_gw.points < lowest_gw_points:
                    lowest_gw_points = user_gw.points

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "highest_gw_points": highest_gw_points,
                    "lowest_gw_points": lowest_gw_points,
                    "gw_point_range": highest_gw_points - lowest_gw_points,
                    "total_points": user.history[-1].total_points,
                    "avg_gw_points": user.history[-1].total_points / len(user.history),
                }
            )

        results = sorted(results, key=lambda x: x["gw_point_range"])

        if print_result:
            self.print_result(
                results,
                {
                    "Team": "user_name",
                    "Lowest range": "gw_point_range",
                    "Highest GW points": "highest_gw_points",
                    "Lowest GW points": "lowest_gw_points",
                    "Total points": "total_points",
                    "Average gw points": "avg_gw_points",
                },
            )

        return results

    def get_most_auto_sub_points(self: T, print_result=True):
        """
        Most points from auto-subbed players
        """
        results: List[dict] = []
        for user in self.users.values():
            total_auto_sub_points = 0
            for auto_sub in user.auto_subs:
                player_id = auto_sub.element_in
                player_gameweek_results = self.get_player_gameweek_results(
                    player_id, auto_sub.event
                )
                for gw_result in player_gameweek_results:
                    total_auto_sub_points += gw_result.total_points

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total_auto_sub_points": total_auto_sub_points,
                }
            )

        # Sort by total_auto_sub_points
        results = sorted(
            results, key=lambda x: x["total_auto_sub_points"], reverse=True
        )

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total auto-sub points",
            ]
            table.add_rows(
                [
                    [
                        x["name"],
                        x["total_auto_sub_points"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_bench_points(self: T, print_result=True):
        """
        Most points on bench, excluding auto-subs
        """
        results: List[dict] = []
        for user in self.users.values():
            total_bench_points = 0
            for gameweek in user.history:
                total_bench_points += gameweek.points_on_bench

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total_bench_points": total_bench_points,
                }
            )

        # Sort by total_bench_points
        results = sorted(results, key=lambda x: x["total_bench_points"], reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total bench points",
            ]
            table.add_rows(
                [
                    [
                        x["name"],
                        x["total_bench_points"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_goals_conceded(self: T, print_result=True):
        """
        Get most points conceded by playing goalkeepers and
        defenders, including auto-subs. Goals conceded by
        midfielders and attackers are ignored
        """
        results: List[dict] = []
        for user in self.users.values():
            total_goals_conceded = 0
            for gameweek in user.history:
                gw_number = gameweek.event
                gw_players = self.get_gameweek_players(user.id, gw_number)

                for gw_player in gw_players:
                    player = gw_player.player

                    # TODO: utils.get_player_position(player) -> Position
                    if player.element_type not in (
                        Position.GOALKEEPER,
                        Position.DEFENDER,
                    ):
                        continue

                    total_goals_conceded += gw_player.combined_result.goals_conceded

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total_goals_conceded": total_goals_conceded,
                }
            )

        # Sort by total goals conceded
        results = sorted(results, key=lambda x: x["total_goals_conceded"], reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total goals conceded",
            ]
            table.add_rows(
                [
                    [
                        x["name"],
                        x["total_goals_conceded"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_clean_sheets(self: T, print_result=True):
        """
        Get most clean sheets by playing goalkeepers and
        defenders, including auto-subs. Clean sheets by
        midfielders and attackers are ignored
        """
        results: List[dict] = []
        for user in self.users.values():
            total_clean_sheets = 0
            total_clean_sheet_points = 0
            for gameweek in user.history:
                gw_number = gameweek.event
                gw_players = self.get_gameweek_players(user.id, gw_number)

                for gw_player in gw_players:
                    player = gw_player.player
                    player_pos = player.element_type
                    if player_pos not in (
                        Position.GOALKEEPER,
                        Position.DEFENDER,
                        Position.MIDFIELDER,
                    ):
                        continue

                    if gw_player.combined_result.clean_sheets:
                        if player_pos == Position.MIDFIELDER:
                            total_clean_sheet_points += 1
                        else:
                            total_clean_sheet_points += 4
                            total_clean_sheets += 1

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total_clean_sheets": total_clean_sheets,
                    "total_clean_sheet_points": total_clean_sheet_points,
                }
            )

        # Sort by total clean sheets
        results = sorted(results, key=lambda x: x["total_clean_sheets"], reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total clean sheets (gk + def)",
                "Total clean sheet points (gk, def + mid)",
            ]
            table.add_rows(
                [
                    [x["name"], x["total_clean_sheets"], x["total_clean_sheet_points"]]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_penalties_saved(self: T, print_result=True):
        """ """
        results: List[dict] = []
        for user in self.users.values():
            total_penalties_saved = 0
            total_penalties_saved_points = 0
            for gameweek in user.history:
                gw_number = gameweek.event
                gw_players = self.get_gameweek_players(user.id, gw_number)
                for gw_player in gw_players:
                    if gw_player.combined_result.penalties_saved:
                        total_penalties_saved += (
                            gw_player.combined_result.penalties_saved
                        )
                        total_penalties_saved_points += (
                            5 * gw_player.combined_result.penalties_saved
                        )

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total_penalties_saved": total_penalties_saved,
                    "total_penalties_saved_points": total_penalties_saved_points,
                }
            )

        # Sort by total clean sheets
        results = sorted(
            results, key=lambda x: x["total_penalties_saved"], reverse=True
        )

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total penalties saved",
                "Total penalties saved points",
            ]
            table.add_rows(
                [
                    [
                        x["name"],
                        x["total_penalties_saved"],
                        x["total_penalties_saved_points"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_penalties_missed(self: T, print_result=True):
        """
        Get most penalties missed
        """
        return self.get_player_totals(
            attributes={"penalties_missed": "Total penalties missed"},
            sort_by="penalties_missed",
            descending=True,
            print_result=print_result,
        )

    def get_most_own_goals(self: T, print_result=True):
        """
        Get most own goals
        """
        results: List[dict] = []
        for user in self.users.values():
            total_own_goals = 0
            for gameweek in user.history:
                gw_number = gameweek.event
                gw_players = self.get_gameweek_players(user.id, gw_number)
                for gw_player in gw_players:
                    total_own_goals += gw_player.combined_result.own_goals

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total_own_goals": total_own_goals,
                }
            )

        # Sort by total own goals
        results = sorted(results, key=lambda x: x["total_own_goals"], reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total own goals",
            ]
            table.add_rows([[x["name"], x["total_own_goals"]] for x in results])
            print(table)

        return results

    def get_most_cards(self: T, print_result=True):
        """
        Get most cards (red, yellow + total). Sort by total card points
        """
        results: List[dict] = []
        for user in self.users.values():
            total_red_cards = 0
            total_yellow_cards = 0
            for gameweek in user.history:
                gw_number = gameweek.event
                gw_players = self.get_gameweek_players(user.id, gw_number)
                for gw_player in gw_players:
                    total_red_cards += gw_player.combined_result.red_cards
                    total_yellow_cards += gw_player.combined_result.yellow_cards

            total_card_points = -3 * total_red_cards - 1 * total_yellow_cards

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "total_red_cards": total_red_cards,
                    "total_yellow_cards": total_yellow_cards,
                    "total_cards": total_red_cards + total_yellow_cards,
                    "total_card_points": total_card_points,
                }
            )

        # Sort by total card points
        results = sorted(results, key=lambda x: x["total_card_points"])

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total card points",
                "Total red cards",
                "Total yellow cards",
                "Total cards",
            ]
            table.add_rows(
                [
                    [
                        x["name"],
                        x["total_card_points"],
                        x["total_red_cards"],
                        x["total_yellow_cards"],
                        x["total_cards"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_bonus_points(self: T, print_result=True):
        """
        Get most bonus points (+ bps)
        """
        return self.get_player_totals(
            attributes={
                "bonus": "Total bonus points",
                "bps": "Total BPS",
            },
            sort_by="bonus",
            descending=True,
            print_result=print_result,
        )

    def get_highest_rank(self: T, print_result=True):
        results: list = []
        for user in self.users.values():
            highest_gw_rank = 99999999999999999
            highest_overall_rank = 99999999999999999
            for user_gw in user.history:
                if user_gw.rank and user_gw.rank < highest_gw_rank:
                    highest_gw_rank = user_gw.rank

                if user_gw.overall_rank and user_gw.overall_rank < highest_overall_rank:
                    highest_overall_rank = user_gw.overall_rank

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "highest_gw_rank": highest_gw_rank,
                    "highest_overall_rank": highest_overall_rank,
                }
            )

        # Sort
        results = sorted(results, key=lambda x: x["highest_overall_rank"])

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Highest GW rank", "Highest overall rank"]
            table.add_rows(
                [
                    [x["user_name"], x["highest_gw_rank"], x["highest_overall_rank"]]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_lowest_rank(self: T, print_result=True):
        results: list = []
        for user in self.users.values():
            lowest_gw_rank = -1
            lowest_overall_rank = -1
            for user_gw in user.history:
                if user_gw.rank and user_gw.rank > lowest_gw_rank:
                    lowest_gw_rank = user_gw.rank

                if user_gw.overall_rank and user_gw.overall_rank > lowest_overall_rank:
                    lowest_overall_rank = user_gw.overall_rank

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "lowest_gw_rank": lowest_gw_rank,
                    "lowest_overall_rank": lowest_overall_rank,
                }
            )

        # Sort
        results = sorted(results, key=lambda x: x["lowest_overall_rank"], reverse=True)

        # Print result
        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Lowest GW rank", "Lowest overall rank"]
            table.add_rows(
                [
                    [x["user_name"], x["lowest_gw_rank"], x["lowest_overall_rank"]]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_best_differential(self: T, max_ownership_share=0.3, print_result=True):
        """
        Finds best differential player picks
            * by total diff points
            * by average diff points
            * by single gameweek

        Where:
            * a differential is defined as a player with an ownership of no more
                than `max_ownership_share`
            * differential points is calculated as the sum of gw_points/gw_owned_by_count,
                ie. the points the player yields to each if his owners "alone"

        Returns tuple with results:
            (by_total_diff_points, by_avg_diff_points, by_single_gw_diff_points)
        """
        users_count = len(self.user_list)

        diffs_per_user: dict = {}  # TODO: give proper type
        for user in self.users.values():
            diffs_per_user[user.id] = {}
            user_diffs = diffs_per_user[user.id]
            for gameweek in user.history:
                gw_players = self.get_gameweek_players(user.id, gameweek.event)
                for gw_player in gw_players:
                    player_id = gw_player.player.id
                    player_gw_ownership_share = (
                        self.get_player_gameweek_ownership_share(
                            player_id, gameweek.event
                        )
                    )
                    # The player is only seen as a differential that gw
                    # if the player's ownership share is <= the max
                    # ownership share
                    if player_gw_ownership_share <= max_ownership_share:
                        # We define the "differential points" as the amount of points the
                        # player yields to each owner "alone", ie. (points) / (owned_by_count)
                        player_gw_points = (
                            gw_player.combined_result.total_points
                        )  # NOTE: this is multiplied with 2 or 3 if captain/TC! Should we ignore captains?
                        diff_points = player_gw_points / (
                            users_count * player_gw_ownership_share
                        )

                        # Add diff data for player
                        if user_diffs.get(player_id, None):
                            # Player has been a diff previously. Increase totals/counts
                            # and calculate avgs
                            user_diffs[player_id]["gameweek_count"] += 1
                            user_diffs[player_id]["total_points"] += player_gw_points
                            user_diffs[player_id]["total_diff_points"] += diff_points
                            user_diffs[player_id]["avg_diff_points"] = (
                                user_diffs[player_id]["total_diff_points"]
                                / user_diffs[player_id]["gameweek_count"]
                            )

                            # Check if this is the player's highest diff points
                            if diff_points > user_diffs[player_id]["max_diff_points"]:
                                user_diffs[player_id]["max_diff_points"] = diff_points
                                user_diffs[player_id][
                                    "max_diff_gameweek"
                                ] = gameweek.event
                                user_diffs[player_id][
                                    "max_diff_ownership_share"
                                ] = player_gw_ownership_share

                        else:
                            # Player is a new diff. Add
                            user_diffs[player_id] = {
                                "total_points": player_gw_points,
                                "total_diff_points": diff_points,
                                "avg_diff_points": diff_points,
                                "max_diff_points": diff_points,
                                "max_diff_gameweek": gameweek.event,
                                "max_diff_ownership_share": player_gw_ownership_share,
                                "gameweek_count": 1,
                                "gameweeks": [],
                            }

                        # Add "diff gameweek" for player
                        user_diffs[player_id]["gameweeks"].append(
                            {
                                "gameweek_number": gameweek.event,
                                "ownership_share": player_gw_ownership_share,
                                "points": player_gw_points,
                                "diff_points": diff_points,
                            }
                        )

                        # Calculate player's avg. ownership share
                        user_diffs[player_id]["avg_ownership_share"] = (
                            sum(
                                [
                                    x["ownership_share"]
                                    for x in user_diffs[player_id]["gameweeks"]
                                ]
                            )
                            / user_diffs[player_id]["gameweek_count"]
                        )

        # Flatten lists of differentials
        diffs = []
        for user_id, user_diffs in diffs_per_user.items():
            for player_id, player_diff_for_user in user_diffs.items():
                diffs.append(
                    {
                        "user_id": user_id,
                        "user_name": self.users[user_id].name,
                        "player_id": player_id,
                        "player_name": self.players[player_id].web_name,
                        **player_diff_for_user,
                    }
                )

        # Sort results by total, avg., and highest single gw points
        diffs_by_total = sorted(
            diffs, key=lambda x: x["total_diff_points"], reverse=True
        )
        diffs_by_avg = sorted(diffs, key=lambda x: x["avg_diff_points"], reverse=True)
        diffs_by_highest_single_gw = sorted(
            diffs, key=lambda x: x["max_diff_points"], reverse=True
        )

        # Print results
        if print_result:
            display_configs: list = [  # TODO: give proper type
                {
                    "label": "BY TOTAL DIFF POINTS",
                    "list_fields": [
                        "total_diff_points",
                        "total_points",
                        "gameweek_count",
                        "avg_ownership_share",
                    ],
                    "diffs": diffs_by_total,
                },
                {
                    "label": "BY AVERAGE DIFF POINTS",
                    "list_fields": [
                        "avg_diff_points",
                        "total_points",
                        "gameweek_count",
                        "avg_ownership_share",
                    ],
                    "diffs": diffs_by_avg,
                },
                {
                    "label": "BY HIGHEST SINGLE GAMEWEEK DIFF",
                    "list_fields": [
                        "max_diff_points",
                        "max_diff_gameweek",
                        "max_diff_ownership_share",
                    ],
                    "diffs": diffs_by_highest_single_gw,
                },
            ]

            for display_config in display_configs:
                print("\n%s" % display_config["label"])
                table = PrettyTable()
                table.field_names = [
                    "Team",
                    "Player",
                    *[f for f in display_config["list_fields"]],
                ]
                table.add_rows(
                    [
                        [
                            x["user_name"],
                            x["player_name"],
                            *[x[f] for f in display_config["list_fields"]],
                        ]
                        for x in display_config["diffs"][:10]
                    ]
                )
                print(table)

        return (diffs_by_total, diffs_by_avg, diffs_by_highest_single_gw)

    def get_most_points_by_player(self: T, print_result=True):
        # Most points a single player has "given" a user during the season
        # Include captain points
        results: list = []
        player_points_per_user: dict = {}
        for user in self.users.values():
            player_points_per_user[user.id] = {}
            player_points_for_current_user = player_points_per_user[user.id]
            for user_gw in user.history:
                user_gw_players = self.get_gameweek_players(user.id, user_gw.event)
                for gw_player in user_gw_players:
                    player_id = gw_player.player.id
                    if player_id not in player_points_for_current_user:
                        player_points_for_current_user[player_id] = 0
                    player_points_for_current_user[
                        player_id
                    ] += gw_player.combined_result.total_points

            # Add to results
            for (
                player_id,
                total_player_points,
            ) in player_points_for_current_user.items():
                results.append(
                    {
                        "user_id": user.id,
                        "user_name": user.name,
                        "player_id": player_id,
                        "player_name": self.players[player_id].web_name,
                        "total_player_points": total_player_points,
                    }
                )

        # Sort results by total points
        results = sorted(results, key=lambda x: x["total_player_points"], reverse=True)

        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Player",
                "Total player points",
            ]
            table.add_rows(
                [
                    [
                        x["user_name"],
                        x["player_name"],
                        x["total_player_points"],
                    ]
                    for x in results[:10]
                ]
            )
            print(table)

        return results

    def get_template_percentage(self: T, print_result=True):
        # Likest lag (startellever) som de andre i ligaen per gw i snitt
        results: list = []
        for user in self.users.values():
            gw_ownership_share_sum: float = 0
            for user_gw in user.history:
                if not user_gw.picks:
                    continue  # skip gw if user started in a later gw

                gw_number = user_gw.event
                player_gw_ownership_share_sum: float = 0
                for pick in user_gw.picks:
                    player_gw_ownership_share = (
                        self.get_player_gameweek_ownership_share(
                            pick.element, gw_number
                        )
                    )
                    player_gw_ownership_share_sum += player_gw_ownership_share

                avg_gw_ownership_share: float = player_gw_ownership_share_sum / len(
                    user_gw.picks
                )
                gw_ownership_share_sum += avg_gw_ownership_share

            avg_ownership_share = gw_ownership_share_sum / len(user.history)

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "avg_ownership_percentage": avg_ownership_share * 100,
                }
            )

        # Sort results by total points
        results = sorted(
            results, key=lambda x: x["avg_ownership_percentage"], reverse=True
        )

        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Average player ownership percentage",
            ]
            table.add_rows(
                [
                    [
                        x["user_name"],
                        x["avg_ownership_percentage"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_league_positions(self: T, print_result=True):
        # Vært innom flest plasser
        # -> Plassering hver runde -> return set(league positions)
        results_per_user: dict = {}

        for (i, gw_standings) in enumerate(self.get_historic_standings()):
            for (j, standing_item) in enumerate(gw_standings):
                position = j + 1
                user_id = standing_item.id

                if user_id not in results_per_user:
                    results_per_user[user_id] = set()

                results_per_user[user_id].add(position)

        results = []
        for user_id, position_set in results_per_user.items():
            results.append(
                {
                    "user_id": user_id,
                    "user_name": self.users[user_id].name,
                    "position_set": position_set,
                    "position_length": len(position_set),
                }
            )

        # Sort results by total points
        results = sorted(results, key=lambda x: x["position_length"], reverse=True)

        if print_result:
            table = PrettyTable()
            table.field_names = ["Team", "Antall unike plasser", "Plasser"]
            table.add_rows(
                [
                    [x["user_name"], x["position_length"], x["position_set"]]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_chip_points(self: T, print_result=True):
        """
        Total chip points. "One-week" chip and wildcard
        points kept separate
        """
        results: list = []

        for user in self.users.values():
            total_chip_points = 0
            total_chip_points_excl_wc = 0
            total_wc_points = 0
            for chip in user.chips:
                gw_number = chip.event
                user_gw = user.history[gw_number - 1]

                total_chip_points += user_gw.points

                if chip.name == Chip.WILDCARD:
                    total_wc_points += user_gw.points
                else:
                    total_chip_points_excl_wc += user_gw.points

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "total_chip_points_excl_wc": total_chip_points_excl_wc,
                    "total_chip_points": total_chip_points,
                    "total_wc_points": total_wc_points,
                }
            )

        # Sort results by total points
        results = sorted(
            results, key=lambda x: x["total_chip_points_excl_wc"], reverse=True
        )

        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total chip points excluding wildcard",
                "Total chip points",
                "Total wildcard points",
            ]
            table.add_rows(
                [
                    [
                        x["user_name"],
                        x["total_chip_points_excl_wc"],
                        x["total_chip_points"],
                        x["total_wc_points"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_hits(self: T, print_result=True):
        """
        Total transfer cost ("hits"), and total transfers
        Also get avg.
        """
        results: list = []
        for user in self.users.values():
            total_transfers = 0
            total_transfers_with_hits = 0
            total_transfer_cost = 0
            total_points_for_players_transferred_in_with_hits = 0
            total_points_for_players_transferred_out_with_hits = 0
            total_points_earned_on_hits = 0
            for user_gw in user.history:
                total_transfers += user_gw.event_transfers

                gw_transfer_cost = user_gw.event_transfers_cost
                total_transfer_cost += gw_transfer_cost

                # If user took a hit, get the points the players transferred
                # in got that gameweek
                if gw_transfer_cost > 0:
                    gw_transfers = user_gw.transfers

                    # Calculate how many of the transfers that were free
                    # -> these should be ignored
                    free_transfers = int(
                        ((len(gw_transfers) * 4) - gw_transfer_cost) / 4
                    )

                    # Get list of transfers that was taken with a hit
                    hit_transfers = gw_transfers[: len(gw_transfers) - free_transfers]

                    # Get gameweek points for players that was transferred in
                    # with hits
                    for transfer in hit_transfers:
                        total_transfers_with_hits += 1

                        # Get points for player transferred IN
                        player_in_gw = self.get_combined_gameweek_result_for_player(
                            transfer.element_in, user_gw.event
                        )
                        total_points_for_players_transferred_in_with_hits += (
                            player_in_gw.total_points
                        )
                        # Get points for player transferred OUT
                        player_out_gw = self.get_combined_gameweek_result_for_player(
                            transfer.element_out, user_gw.event
                        )
                        total_points_for_players_transferred_out_with_hits += (
                            player_out_gw.total_points
                        )

                        # Aggregate total points earned on hits
                        # Subtract by 4 as that's the transfer cost for each hit
                        total_points_earned_on_hits += (
                            player_in_gw.total_points - player_out_gw.total_points - 4
                        )

            # Calculate avg. points on transfers in/out for transfers with hits
            if total_transfers_with_hits:
                avg_points_for_players_transferred_in_with_hits = (
                    total_points_for_players_transferred_in_with_hits
                    / total_transfers_with_hits
                )
                avg_points_for_players_transferred_out_with_hits = (
                    total_points_for_players_transferred_out_with_hits
                    / total_transfers_with_hits
                )
            else:
                avg_points_for_players_transferred_in_with_hits = "-"  # type: ignore
                avg_points_for_players_transferred_out_with_hits = "-"  # type: ignore

            # Calculate avg. points earned on transfers with hits
            if total_transfers_with_hits:
                avg_points_earned_per_hit = (
                    total_points_earned_on_hits / total_transfers_with_hits
                )
            else:
                avg_points_earned_per_hit = 0

            results.append(
                {
                    "user": user,
                    "total_points_earned_on_hits": total_points_earned_on_hits,
                    "avg_points_earned_per_hit": avg_points_earned_per_hit,
                    "total_points_for_players_transferred_in_with_hits": total_points_for_players_transferred_in_with_hits,
                    "avg_points_for_players_transferred_in_with_hits": avg_points_for_players_transferred_in_with_hits,
                    "total_points_for_players_transferred_out_with_hits": total_points_for_players_transferred_out_with_hits,
                    "avg_points_for_players_transferred_out_with_hits": avg_points_for_players_transferred_out_with_hits,
                    "total_transfers": total_transfers,
                    "total_transfer_cost": total_transfer_cost,
                    "total_transfers_with_hits": total_transfers_with_hits,
                    "avg_cost_per_transfer": total_transfer_cost / total_transfers,
                }
            )

        # Sort by total points earned on hits, ie. the best "hitter"
        results = sorted(
            results, key=lambda x: x["total_points_earned_on_hits"], reverse=True
        )

        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Total pts earned on hits",
                "Avg. pts earned per hit",
                "Avg. pts for players IN with hits",
                "Avg. pts for players OUT with hits",
                "Total transfers",
                "Total transfer hits",
                "Total transfer cost",
                "Avg. cost per transfer",
            ]
            table.add_rows(
                [
                    [
                        x["user"].name,
                        x["total_points_earned_on_hits"],
                        x["avg_points_earned_per_hit"],
                        x["avg_points_for_players_transferred_in_with_hits"],
                        x["avg_points_for_players_transferred_out_with_hits"],
                        x["total_transfers"],
                        x["total_transfers_with_hits"],
                        x["total_transfer_cost"],
                        x["avg_cost_per_transfer"],
                    ]
                    for x in results
                ]
            )
            print(table)

        return results

    def get_most_gw_points(self: T, print_result=True):
        results: List[dict] = []
        for user in self.users.values():
            for user_gw in user.history:
                results.append(
                    {
                        "user_id": user.id,
                        "user_name": user.name,
                        "gameweek_points": user_gw.points,
                        "gameweek_rank": user_gw.rank,
                        "gameweek_number": user_gw.event,
                    }
                )

        results = sorted(results, key=lambda x: x["gameweek_points"], reverse=True)

        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Gameweek points",
                "Gameweek rank",
                "Gameweek number",
            ]
            table.add_rows(
                [
                    [
                        x["user_name"],
                        x["gameweek_points"],
                        x["gameweek_rank"],
                        x["gameweek_number"],
                    ]
                    for x in results[:10]
                ]
            )
            print(table)

        return results

    def get_least_gw_points(self: T, print_result=True):
        results: List[dict] = []
        for user in self.users.values():
            for user_gw in user.history:
                if user_gw.rank is None:
                    # non-finished gameweek - skip
                    continue

                results.append(
                    {
                        "user_id": user.id,
                        "user_name": user.name,
                        "gameweek_points": user_gw.points,
                        "gameweek_rank": user_gw.rank,
                        "gameweek_number": user_gw.event,
                    }
                )

        results = sorted(results, key=lambda x: x["gameweek_points"], reverse=False)

        if print_result:
            table = PrettyTable()
            table.field_names = [
                "Team",
                "Gameweek points",
                "Gameweek rank",
                "Gameweek number",
            ]
            table.add_rows(
                [
                    [
                        x["user_name"],
                        x["gameweek_points"],
                        x["gameweek_rank"],
                        x["gameweek_number"],
                    ]
                    for x in results[:10]
                ]
            )
            print(table)

        return results

    def get_most_distinct_players(self: T, print_result=True):
        results: List[dict] = []

        for user in self.users.values():
            distinct_players = set()
            for user_gw in user.history:
                for pick in user_gw.picks:
                    distinct_players.add(pick.element)

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "distinct_players": distinct_players,
                    "total_players": len(distinct_players),
                }
            )

        results = sorted(results, key=lambda x: x["total_players"], reverse=True)

        if print_result:
            self.print_result(
                results=results[:10],
                attrs={
                    "Team": "user_name",
                    "Number of distinct players": "total_players",
                },
            )

        return results

    def get_best_transfers(self: T, print_result=True):
        # TODO: this probably doesn't work 100% with regard to wildcard and FH transfers

        results: List[dict] = []
        for user in self.users.values():
            total_points_from_players_transferred_in = 0
            total_transfers_in = 0
            for transfer in user.transfers:
                try:
                    gw_number = transfer.event
                    player_gw = self.get_combined_gameweek_result_for_player(
                        transfer.element_in, gw_number
                    )

                    # Only include points for players who was actually transferred in
                    # -> Ignores players transferred in and out same gw (WC/FH)
                    user_gw_picks = user.history[gw_number - 1].picks
                    pick = next(
                        (x for x in user_gw_picks if x.element == transfer.element_in),
                        None,  # probably a wildcard where player was transferred in, then out
                    )
                    if pick:
                        total_points_from_players_transferred_in += (
                            player_gw.total_points
                        )
                        total_transfers_in += 1

                except KeyError:
                    # Propbably a wildcard transfer, ie. player was transferred in, then out,
                    # thus the player has not been fetched
                    continue
            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "total_points_from_players_transferred_in": total_points_from_players_transferred_in,
                    "avg_points_from_players_transferred_in": total_points_from_players_transferred_in
                    / total_transfers_in
                    if user.transfers
                    else 0,
                }
            )

        results = sorted(
            results,
            key=lambda x: x["total_points_from_players_transferred_in"],
            reverse=True,
        )

        if print_result:
            self.print_result(
                results,
                attrs={
                    "Team": "user_name",
                    "Total points from players transferred in (the same gw)": "total_points_from_players_transferred_in",
                    "Average points from players transferred in (the same gw)": "avg_points_from_players_transferred_in",
                },
            )

        return results

    def get_worst_transfers(self: T, print_result=True):
        # TODO: this probably doesn't work 100% with regard to wildcard and FH transfers

        results: List[dict] = []
        for user in self.users.values():
            total_points_from_players_transferred_out = 0
            total_transfers_out = 0
            for transfer in user.transfers:
                try:
                    gw_number = transfer.event
                    player_gw = self.get_combined_gameweek_result_for_player(
                        transfer.element_out, gw_number
                    )

                    # Only include points for transferred out players who was not picked
                    # -> This handles players transferred in and out same gw (WC/FH)
                    user_gw_picks = user.history[gw_number - 1].picks
                    pick = next(
                        (x for x in user_gw_picks if x.element == transfer.element_out),
                        None,
                    )
                    if pick is None:
                        # Player was transferred out!
                        total_points_from_players_transferred_out += (
                            player_gw.total_points
                        )
                        total_transfers_out += 1

                except KeyError:
                    # Propbably a wildcard transfer, ie. player was transferred in, then out,
                    # thus the player has not been fetched
                    continue

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "total_points_from_players_transferred_out": total_points_from_players_transferred_out,
                    "avg_points_from_players_transferred_out": (
                        total_points_from_players_transferred_out / total_transfers_out
                    )
                    if total_transfers_out
                    else 0,
                }
            )

        results = sorted(
            results,
            key=lambda x: x["total_points_from_players_transferred_out"],
            reverse=True,
        )

        if print_result:
            self.print_result(
                results,
                attrs={
                    "Team": "user_name",
                    "Total points from players transferred out (the same gw)": "total_points_from_players_transferred_out",
                    "Average points from players transferred out (the same gw)": "avg_points_from_players_transferred_out",
                },
            )

        return results

    def get_vanilla_standings(self: T, print_result=True):
        """
        Arguably the most prestigious achievement, after the actual standings
        Total points excluding captain points (incl. TC), auto sub points
        and bench boost points, aka "vanilla" points.
        Return "vanilla" standings
        """
        results: List[dict] = []

        captain_standings = self.get_captain_foresight(print_result=False)
        auto_sub_standings = self.get_most_auto_sub_points(print_result=False)

        for user in self.users.values():
            # Get "extra" captain points, ie. extra points (e.g. 2x, 3x)
            # given by the captain, in addition to the "base" points (1x)
            captain_result = next((x for x in captain_standings if x.id == user.id))
            extra_captain_points = captain_result.total_captain_points

            # Get auto sub points
            auto_sub_result = next(
                (x for x in auto_sub_standings if x["id"] == user.id)
            )
            total_auto_sub_points = auto_sub_result["total_auto_sub_points"]

            # Get bench boost points
            total_bbost_bench_points = 0
            bbost_chip = next(
                (x for x in user.chips if x.name == Chip.BENCH_BOOST), None
            )
            if bbost_chip:
                bbost_gw_number = bbost_chip.event
                bbost_gw = user.history[bbost_gw_number - 1]
                bench_picks = bbost_gw.picks[11:]
                for pick in bench_picks:
                    player_gw = self.get_combined_gameweek_result_for_player(
                        pick.element, bbost_gw_number
                    )
                    total_bbost_bench_points += player_gw.total_points

            # Calculate vanilla points and add to results
            total_points = user.history[-1].total_points
            total_vanilla_points = (
                total_points
                - extra_captain_points
                - total_auto_sub_points
                - total_bbost_bench_points
            )

            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "total_vanilla_points": total_vanilla_points,
                    "total_points": total_points,
                    "extra_captain_points": extra_captain_points,
                    "total_auto_sub_points": total_auto_sub_points,
                    "total_bbost_bench_points": total_bbost_bench_points,
                }
            )

        # Sort by vanilla points
        results = sorted(results, key=lambda x: x["total_vanilla_points"], reverse=True)

        if print_result:
            self.print_result(
                results,
                {
                    "Team": "user_name",
                    "Total vanilla points": "total_vanilla_points",
                    "Total points": "total_points",
                    "Extra captain points": "extra_captain_points",
                    "Total auto sub points": "total_auto_sub_points",
                    "Total bench boost bench points": "total_bbost_bench_points",
                },
            )

        return results
