"""Motore di simulazione per Bless."""

from .cards import CARD_DEFINITIONS, get_card_definition
from .engine import GameEngine, GameResult

__all__ = ["CARD_DEFINITIONS", "GameEngine", "GameResult", "get_card_definition"]
