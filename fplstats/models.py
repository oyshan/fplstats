import datetime as dt
from pydantic import BaseModel
from typing import List, Dict

from fplstats.enums import Position, Chip


class PlayerHistory(BaseModel):
    round: int  # gameweek number
    element: str
    fixture: int
    opponent_team: int
    total_points: int
    was_home: bool
    kickoff_time: dt.datetime
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    own_goals: int
    penalties_saved: int
    penalties_missed: int
    yellow_cards: int
    red_cards: int
    saves: int
    bonus: int
    bps: int


class Player(BaseModel):
    id: str
    code: int
    element_type: Position  # TODO: rename?
    first_name: str
    second_name: str
    web_name: str
    points_per_game: float
    selected_by_percent: float
    special: bool  # ?
    status: str  # TODO: enum? a, u, i, d
    team: int
    team_code: int
    total_points: int
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    own_goals: int
    penalties_saved: int
    penalties_missed: int
    yellow_cards: int
    red_cards: int
    saves: int
    bonus: int
    bps: int
    history: List[PlayerHistory]
    fixtures: list


class Pick(BaseModel):
    element: str  # player id
    position: int
    multiplier: int
    is_captain: bool
    is_vice_captain: bool


class AutoSub(BaseModel):
    event: int  # gameweek
    entry: str  # user id
    element_in: str  # player id
    element_out: str  # player id


class ChipUsage(BaseModel):
    event: int  # gameweek number
    name: Chip
    time: dt.datetime


class Transfer(BaseModel):
    event: int  # gameweek number
    entry: str  # user id
    element_in: str  # player id
    element_in_cost: int
    element_out: str  # player id
    element_out_cost: int
    time: dt.datetime


class UserHistory(BaseModel):
    event: int  # gameweek number
    points: int
    total_points: int
    rank: int
    rank_sort: int
    overall_rank: int
    bank: int
    value: int
    event_transfers: int
    event_transfers_cost: int
    points_on_bench: int
    picks: List[Pick]
    auto_subs: List[AutoSub]
    chips: List[ChipUsage]
    transfers: List[Transfer]


class User(BaseModel):
    id: str
    name: str
    history: List[UserHistory]
    auto_subs: List[AutoSub]
    chips: List[ChipUsage]
    transfers: List[Transfer]


class UserListItem(BaseModel):
    id: str
    name: str


class Gameweek(BaseModel):
    id: int  # gameweek number
    name: str
    finished: bool


class LeagueStandingItem(BaseModel):
    entry: str  # user id
    entry_name: str  # user name
    player_name: str
    rank: int
    rank_sort: int
    event_total: int
    total: int


LeagueStandings = List[LeagueStandingItem]


class League(BaseModel):
    id: int
    name: str
    standings: LeagueStandings


# Types for stored files:
Gameweeks = List[Gameweek]
PlayerDict = Dict[str, Player]
UserDict = Dict[str, User]
UserList = List[UserListItem]
