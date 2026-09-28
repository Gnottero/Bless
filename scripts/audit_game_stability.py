"""Partite riproducibili senza apprendimento o scritture sui dati di produzione."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "python"))

from bless_sim.engine import GameEngine
from bless_sim.model import Zone


class AuditedGame(GameEngine):
    def check_consistency(self):
        located = []
        collections = [(self.deck, Zone.DECK, None), (self.void, Zone.VOID, None)]
        for player in self.players:
            for name, zone in (("hand", Zone.HAND), ("maledictions", Zone.MALEDICTION),
                               ("prayers", Zone.PRAYER), ("altar", Zone.ALTAR), ("charges", Zone.CHARGE)):
                collections.append((getattr(player, name), zone, player.id))
            assert player.actions >= 0, (self.seed, "negative actions", player)
        for uids, zone, owner in collections:
            for uid in uids:
                card = self.cards[uid]
                assert card.zone == zone, (self.seed, uid, card.zone, zone)
                if owner is not None:
                    assert card.controller == owner, (self.seed, uid, "wrong controller")
                located.append(uid)
        for uid, card in self.cards.items():
            if card.zone == Zone.MARK:
                assert card.attached_to in self.cards, (self.seed, uid, "orphan mark")
                located.append(uid)
        assert Counter(located) == Counter(self.cards.keys()), (self.seed, "missing or duplicated cards")
        json.dumps(self.snapshot())

    def execute_action(self, action, player):
        result = super().execute_action(action, player)
        self.check_consistency()
        return result

    def end_turn(self):
        result = super().end_turn()
        self.check_consistency()
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-deck", type=int, default=6)
    parser.add_argument("--seed", type=int, default=915000)
    args = parser.parse_args()
    if not 1 <= args.games_per_deck <= 100:
        parser.error("games-per-deck deve essere fra 1 e 100")
    for deck in ("Luce-Ombra", "TuonoSabbia"):
        for index in range(args.games_per_deck):
            engine = AuditedGame(args.seed + index, deck=deck, first_player=index % 2,
                                 record_replay=False)
            engine.check_consistency()
            result = engine.play_game()
            assert engine.game_over
            print(f"PASS {deck} seed={engine.seed} turni={result.turns} punteggio={result.scores}", flush=True)
    print(f"Audit completato: {args.games_per_deck * 2} partite.", flush=True)


if __name__ == "__main__":
    main()
