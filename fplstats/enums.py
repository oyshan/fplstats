from enum import Enum


class Chip(Enum):
    TRIPLE_CAPTAIN = "3xc"
    BENCH_BOOST = "bboost"
    FREE_HIT = "freehit"
    WILDCARD = "wildcard"
    ASSMAN = "manager"


class Position(Enum):
    GOALKEEPER = 1
    DEFENDER = 2
    MIDFIELDER = 3
    ATTACKER = 4
    MANAGER = 5
