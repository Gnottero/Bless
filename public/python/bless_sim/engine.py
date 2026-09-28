from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any, Iterable

from .cards import (
    ABILITY_LABELS,
    card_image_path,
    get_deck_definitions,
    get_deck_name,
    malediction_effect_value,
    normalize_deck_id,
    prayer_effect_value,
)
from .model import (
    Action,
    CardDefinition,
    CardInstance,
    Form,
    GameTelemetry,
    Modifier,
    PlayerState,
    PrayerType,
    ReplayStep,
    Zone,
)


@dataclass(slots=True)
class GameResult:
    seed: int
    deck: str
    bot_names: tuple[str, str]
    first_player: int
    winner: int | None
    scores: tuple[int, int]
    turns: int
    final_trigger_player: int | None
    final_trigger_cause: str | None
    final_trigger_won: bool | None
    stalemate: bool
    telemetry: GameTelemetry
    replay: list[ReplayStep]


class GameEngine:
    MAX_TURNS = 180
    MAX_ACTIONS_PER_TURN = 60

    def __init__(
        self,
        seed: int,
        bot_names: tuple[str, str] = ("Bot", "Bot"),
        first_player: int = 0,
        record_replay: bool = False,
        auto_setup: bool = True,
        bot_weights: dict[str, dict[str, float]] | None = None,
        deck: str = "Luce-Ombra",
    ) -> None:
        from .bots import make_bot

        self.seed = int(seed)
        self.deck_id = normalize_deck_id(deck)
        self.deck_name = get_deck_name(self.deck_id)
        self.definitions = get_deck_definitions(self.deck_id)
        self.rng = random.Random(self.seed)
        self.bot_names = bot_names
        learned = bot_weights or {}
        self.bots = [
            make_bot(bot_names[0], learned.get(bot_names[0])),
            make_bot(bot_names[1], learned.get(bot_names[1])),
        ]
        self.first_player = first_player
        self.record_replay = record_replay
        self.replay: list[ReplayStep] = []
        self.replay_action_counter = 0
        self.current_replay_action_index: int | None = None
        self.current_replay_action_label: str | None = None
        self.attack_event_counter = 0
        self.last_attack: dict[str, int | None] | None = None
        self.fate_event_counter = 0
        self.last_fate: dict[str, int | str | bool] | None = None
        self.impulse_event_counter = 0
        self.last_impulse: dict[str, int] | None = None
        self.telemetry = GameTelemetry()

        self.cards: dict[int, CardInstance] = {
            card_id: CardInstance(uid=card_id, definition_id=card_id)
            for card_id in self.definitions
        }
        self.players = [PlayerState(0), PlayerState(1)]
        self.deck = list(self.cards)
        self.void: list[int] = []
        self.esordio_uids: list[int] = []
        if self.is_thunder_sand:
            self.esordio_uids = [
                uid for uid in self.deck if "Esordio" in self.definition(uid).traits
            ]
            for uid in self.esordio_uids:
                self.deck.remove(uid)
        self.rng.shuffle(self.deck)
        self.modifiers: list[Modifier] = []
        self.sequence = 0
        self.turn_number = 0
        self.active_player = first_player
        self.phase = "Preparazione"
        self.force_end_turn = False
        self.final_turns_remaining: int | None = None
        self.final_trigger_player: int | None = None
        self.final_trigger_cause: str | None = None
        self.final_trigger_turn: int | None = None
        self.game_over = False
        self.winner: int | None = None
        self.stalemate = False
        self.completed_turns = 0
        self.effect_resolution_counts: dict[tuple[int, int], int] = {}
        self.stasis_removed_this_turn: list[set[int]] = [set(), set()]
        self.charge_spend_seen_turn: list[int] = [-1, -1]
        self._checking_seal_states = False
        if auto_setup:
            self.setup_game()

    # ------------------------------------------------------------------
    # Setup, state and logging
    # ------------------------------------------------------------------
    def setup_game(self) -> None:
        for player in (0, 1):
            self.draw(player, 4, "mano iniziale")
        for player in (0, 1):
            self.perform_mulligan(player, initial=True)
        if self.is_thunder_sand:
            self.resolve_esordio()
        self.turn_number = 1
        self.active_player = self.first_player
        self.phase = "Inizio turno"
        self.emit(
            f"Inizia la partita. Il Giocatore {self.active_player + 1} è il primo giocatore.",
            snapshot=True,
        )

    def resolve_esordio(self) -> None:
        if not self.is_thunder_sand or not self.esordio_uids:
            return
        available = list(self.esordio_uids)
        self.rng.shuffle(available)
        for player in (self.first_player, 1 - self.first_player):
            if not available:
                break
            uid = available.pop()
            self.reset_card_outside_field(uid, Zone.HAND, player)
            self.players[player].hand.append(uid)
            chooser = getattr(self.bots[player], "choose_esordio", None)
            if callable(chooser):
                mode = chooser(self, player, uid)
            else:
                mode = self.bots[player].choose_mode(
                    self,
                    player,
                    uid,
                    ["Maledizione", "Preghiera", "Mano"],
                )
            if mode in {"Maledizione", "Preghiera"}:
                played = self.play_card(uid, player, mode, calata=True)
                if played:
                    self.emit(
                        f"Il Giocatore {player + 1} gioca gratuitamente "
                        f"{self.definition(uid).name} con Esordio come {mode}."
                    )
                    continue
            self.emit(
                f"Il Giocatore {player + 1} tiene in mano "
                f"{self.definition(uid).name} con Esordio."
            )
        self.esordio_uids.clear()

    def clone_for_search(self, *, observer_player: int | None = None) -> GameEngine:
        # Copia mirata dello stato. Un deepcopy generico trascinava anche tutta
        # la telemetria e costava piu' della decisione stessa; questa versione
        # mantiene ogni elemento che puo' influire sulle regole ma parte con un
        # registro diagnostico vuoto.
        clone = object.__new__(GameEngine)
        clone.seed = self.seed
        clone.deck_id = self.deck_id
        clone.deck_name = self.deck_name
        clone.definitions = self.definitions
        clone.bot_names = self.bot_names
        # I rollout possono aggiornare intenzioni e contatori tattici: copie
        # superficiali impediscono che una previsione modifichi i bot reali.
        clone.bots = [copy.copy(bot) for bot in self.bots]
        clone.first_player = self.first_player
        clone.record_replay = False
        clone.replay = []
        clone.replay_action_counter = self.replay_action_counter
        clone.current_replay_action_index = None
        clone.current_replay_action_label = None
        clone.attack_event_counter = self.attack_event_counter
        clone.last_attack = copy.deepcopy(self.last_attack)
        clone.fate_event_counter = self.fate_event_counter
        clone.last_fate = copy.deepcopy(self.last_fate)
        clone.impulse_event_counter = self.impulse_event_counter
        clone.last_impulse = copy.deepcopy(self.last_impulse)
        clone.telemetry = GameTelemetry()
        clone.cards = {uid: copy.copy(card) for uid, card in self.cards.items()}
        clone.players = []
        for player in self.players:
            cloned_player = copy.copy(player)
            cloned_player.hand = list(player.hand)
            cloned_player.maledictions = list(player.maledictions)
            cloned_player.prayers = list(player.prayers)
            cloned_player.altar = list(player.altar)
            cloned_player.charges = list(player.charges)
            clone.players.append(cloned_player)
        clone.deck = list(self.deck)
        clone.void = list(self.void)
        clone.modifiers = [copy.copy(modifier) for modifier in self.modifiers]
        clone.sequence = self.sequence
        clone.turn_number = self.turn_number
        clone.active_player = self.active_player
        clone.phase = self.phase
        clone.force_end_turn = self.force_end_turn
        clone.final_turns_remaining = self.final_turns_remaining
        clone.final_trigger_player = self.final_trigger_player
        clone.final_trigger_cause = self.final_trigger_cause
        clone.final_trigger_turn = self.final_trigger_turn
        clone.game_over = self.game_over
        clone.winner = self.winner
        clone.stalemate = self.stalemate
        clone.completed_turns = self.completed_turns
        clone.effect_resolution_counts = dict(self.effect_resolution_counts)
        clone.stasis_removed_this_turn = [set(items) for items in self.stasis_removed_this_turn]
        clone.charge_spend_seen_turn = list(self.charge_spend_seen_turn)
        clone._checking_seal_states = False
        clone.esordio_uids = list(self.esordio_uids)
        # Il bot non conosce l'ordine del Mazzo. La ricerca usa quindi un
        # campione rimescolato invece di approfittare dello stato RNG reale.
        search_rng = random.Random(
            (self.seed * 1_000_003)
            ^ (self.turn_number * 9_176)
            ^ self.sequence
            ^ ((observer_player + 1) * 104_729 if observer_player is not None else 0)
        )
        if observer_player in {0, 1}:
            # La ricerca deve ragionare sull'informazione disponibile al bot,
            # non sulle vere carte private dell'avversario. Mano, Cariche e
            # Mazzo sconosciuti vengono quindi ricampionati conservando le
            # rispettive quantità. E' una determinizzazione leggera dello
            # stato informativo, adatta anche ai campioni da 10.000 partite.
            hidden_player = 1 - observer_player
            hidden_hand_count = len(clone.players[hidden_player].hand)
            hidden_charge_count = len(clone.players[hidden_player].charges)
            hidden_pool = [
                *clone.deck,
                *clone.players[hidden_player].hand,
                *clone.players[hidden_player].charges,
            ]
            search_rng.shuffle(hidden_pool)
            hidden_hand = hidden_pool[:hidden_hand_count]
            hidden_charges = hidden_pool[
                hidden_hand_count:hidden_hand_count + hidden_charge_count
            ]
            hidden_deck = hidden_pool[hidden_hand_count + hidden_charge_count:]
            clone.players[hidden_player].hand = hidden_hand
            clone.players[hidden_player].charges = hidden_charges
            clone.deck = hidden_deck
            for uid in hidden_hand:
                clone.reset_card_outside_field(uid, Zone.HAND, hidden_player)
            for uid in hidden_charges:
                clone.reset_card_outside_field(uid, Zone.CHARGE, hidden_player)
            for uid in hidden_deck:
                clone.reset_card_outside_field(uid, Zone.DECK, None)
        else:
            search_rng.shuffle(clone.deck)
        clone.rng = search_rng
        return clone

    def definition(self, uid: int) -> CardDefinition:
        return self.definitions[self.cards[uid].definition_id]

    @property
    def is_thunder_sand(self) -> bool:
        return self.deck_id == "tuono-sabbia"

    def malediction_effect_value(self, uid: int) -> float:
        return malediction_effect_value(self.deck_id, self.definition(uid).id)

    def prayer_effect_value(self, uid: int) -> float:
        return prayer_effect_value(self.deck_id, self.definition(uid).id)

    def image_path(self, uid: int) -> str:
        return card_image_path(self.deck_id, self.definition(uid).id)

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def emit(self, message: str, *, phase: str | None = None, snapshot: bool = True) -> None:
        if not self.record_replay or not snapshot:
            return
        self.replay.append(
            ReplayStep(
                index=len(self.replay),
                turn=self.turn_number,
                active_player=self.active_player,
                phase=phase or self.phase,
                message=message,
                snapshot=self.snapshot(),
                action_index=self.current_replay_action_index,
                action_label=self.current_replay_action_label,
            )
        )

    def card_summary(self, uid: int) -> dict[str, Any]:
        card = self.cards[uid]
        definition = self.definition(uid)
        summary: dict[str, Any] = {
            "uid": uid,
            "id": definition.id,
            "name": definition.name,
            "form": "/".join(sorted(self.forms(uid))),
            "zone": card.zone.value,
            "traits": list(definition.traits),
            "marked": self.is_marked(uid),
        }
        if card.zone == Zone.MALEDICTION:
            summary.update(
                {
                    "eye": self.eye(uid),
                    "karma": self.karma(uid),
                    "base_eye": definition.eye,
                    "base_karma": definition.karma,
                    "state": "Corrotta" if card.corrupted else "Pura",
                    "stasis": card.stasis,
                    "attached": self.attached_prayer(uid),
                    "field_weight": self.malediction_weight(uid),
                }
            )
        elif card.zone == Zone.PRAYER:
            summary.update(
                {
                    "type": definition.prayer_type.value,
                    "attached_to": card.attached_to,
                    "used": card.echo_used_turn == self.turn_number,
                    "open": card.seal_open if definition.prayer_type == PrayerType.SIGIL else None,
                    "glyph_used": card.glyph_used_turn == self.turn_number,
                }
            )
        return summary

    def snapshot(self) -> dict[str, Any]:
        return {
            "turn": self.turn_number,
            "active_player": self.active_player,
            "phase": self.phase,
            "deck": self.deck_name,
            "deck_id": self.deck_id,
            "deck_count": len(self.deck),
            "void": [self.definition(uid).name for uid in reversed(self.void)],
            "final_turns_remaining": self.final_turns_remaining,
            "final_trigger_player": self.final_trigger_player,
            "final_trigger_turn": self.final_trigger_turn,
            "last_attack": copy.deepcopy(self.last_attack),
            "last_fate": copy.deepcopy(self.last_fate),
            "last_impulse": copy.deepcopy(self.last_impulse),
            "players": [
                {
                    "id": player.id,
                    "score": player.score,
                    "actions": player.actions,
                    "hand": [self.card_summary(uid) for uid in player.hand],
                    "maledictions": [self.card_summary(uid) for uid in player.maledictions],
                    "prayers": [self.card_summary(uid) for uid in player.prayers],
                    "altar": [self.definition(uid).name for uid in player.altar],
                    "charges_count": len(player.charges),
                }
                for player in self.players
            ],
        }

    def state_signature(self) -> tuple[Any, ...]:
        return (
            self.active_player,
            self.players[self.active_player].actions,
            tuple(self.deck),
            tuple(self.void),
            tuple(
                (
                    tuple(player.hand),
                    tuple(player.maledictions),
                    tuple(player.prayers),
                    tuple(player.charges),
                    player.score,
                )
                for player in self.players
            ),
            tuple(
                (
                    uid,
                    card.zone,
                    card.controller,
                    card.corrupted,
                    card.stasis,
                    card.attached_to,
                    card.seal_open,
                    card.glyph_used_turn,
                    card.declared_form,
                    card.effect_target_uid,
                    card.effect_target_state,
                )
                for uid, card in sorted(self.cards.items())
            ),
            tuple(
                (
                    modifier.kind,
                    modifier.controller,
                    modifier.source_uid,
                    modifier.target_uid,
                    modifier.value,
                    modifier.reference_uid,
                    modifier.starts_turn,
                    modifier.expires_after_turn,
                )
                for modifier in self.active_modifiers()
            ),
        )

    # ------------------------------------------------------------------
    # Zones and deck
    # ------------------------------------------------------------------
    def all_maledictions(self) -> list[int]:
        return list(self.players[0].maledictions) + list(self.players[1].maledictions)

    def all_prayers(self) -> list[int]:
        return list(self.players[0].prayers) + list(self.players[1].prayers)

    def all_field_cards(self) -> list[int]:
        return self.all_maledictions() + self.all_prayers()

    def attached_prayer(self, host_uid: int) -> int | None:
        for uid in self.all_prayers():
            if self.cards[uid].attached_to == host_uid:
                return uid
        return None

    def mark_for(self, target_uid: int) -> int | None:
        return next(
            (
                uid
                for uid, card in self.cards.items()
                if card.zone == Zone.MARK and card.attached_to == target_uid
            ),
            None,
        )

    def is_marked(self, uid: int) -> bool:
        return self.mark_for(uid) is not None

    def _remove_from_zone_list(self, uid: int) -> None:
        card = self.cards[uid]
        if card.zone == Zone.HAND and card.controller is not None:
            bucket = self.players[card.controller].hand
        elif card.zone == Zone.MALEDICTION and card.controller is not None:
            bucket = self.players[card.controller].maledictions
        elif card.zone == Zone.PRAYER and card.controller is not None:
            bucket = self.players[card.controller].prayers
        elif card.zone == Zone.ALTAR and card.controller is not None:
            bucket = self.players[card.controller].altar
        elif card.zone == Zone.CHARGE and card.controller is not None:
            bucket = self.players[card.controller].charges
        elif card.zone == Zone.VOID:
            bucket = self.void
        elif card.zone == Zone.DECK:
            bucket = self.deck
        else:
            return
        if uid in bucket:
            bucket.remove(uid)

    def reset_card_outside_field(self, uid: int, zone: Zone, controller: int | None) -> None:
        card = self.cards[uid]
        card.zone = zone
        card.controller = controller
        card.corrupted = False
        card.stasis = False
        card.attached_to = None
        card.attacked_turn = -1
        card.echo_used_turn = -1
        card.corrupted_turn = -1
        card.blessed_turn = -1
        card.seal_open = True
        card.glyph_used_turn = -1
        card.declared_form = None
        card.effect_target_uid = None
        card.effect_target_state = None

    def ensure_deck(self, player: int, required: int, reason: str) -> None:
        if len(self.deck) >= required:
            return
        self.trigger_final_rounds(player, f"Mazzo insufficiente: {reason}")
        if self.void:
            moving = list(self.void)
            self.void.clear()
            for uid in moving:
                self.reset_card_outside_field(uid, Zone.DECK, None)
            self.deck.extend(moving)
            self.rng.shuffle(self.deck)
            self.emit(f"Il Vuoto viene rimescolato nel Mazzo ({len(moving)} carte).")

    def draw(self, player: int, count: int, reason: str) -> list[int]:
        drawn: list[int] = []
        for _ in range(count):
            self.ensure_deck(player, 1, reason)
            if not self.deck:
                break
            uid = self.deck.pop()
            self.reset_card_outside_field(uid, Zone.HAND, player)
            self.players[player].hand.append(uid)
            self.telemetry.record_draw(player, self.definition(uid).id)
            drawn.append(uid)
        if drawn:
            names = ", ".join(self.definition(uid).name for uid in drawn)
            self.emit(f"Il Giocatore {player + 1} prende {names} ({reason}).")
        return drawn

    def take_to_hand(self, uid: int, player: int, reason: str) -> None:
        card = self.cards[uid]
        if card.zone in {Zone.MALEDICTION, Zone.PRAYER}:
            self.leave_field(uid, destination=Zone.HAND, destination_controller=player, reason=reason)
            return
        self._remove_from_zone_list(uid)
        self.reset_card_outside_field(uid, Zone.HAND, player)
        self.players[player].hand.append(uid)
        self.telemetry.record_draw(player, self.definition(uid).id)
        self.emit(f"{self.definition(uid).name} va nella mano del Giocatore {player + 1} ({reason}).")

    def can_charge_during_mulligan(self, player: int, *, initial: bool) -> bool:
        return (
            self.is_thunder_sand
            and not initial
            and any(
                self.definition(uid).prayer_type == PrayerType.GLYPH
                for uid in self.players[player].prayers
            )
        )

    def perform_mulligan(self, player: int, *, initial: bool = False) -> None:
        selected = [
            uid
            for uid in self.bots[player].choose_mulligan(
                self,
                player,
                initial=initial,
            )
            if uid in self.players[player].hand
        ]
        charged: int | None = None
        if self.can_charge_during_mulligan(player, initial=initial) and selected:
            chooser = getattr(self.bots[player], "choose_mulligan_charge", None)
            if callable(chooser):
                charged = chooser(self, player, selected)
            elif selected:
                charged = self.bots[player].choose_card(
                    self,
                    player,
                    selected,
                    "charge",
                )
            if charged not in selected:
                charged = None
        for uid in selected:
            self.players[player].hand.remove(uid)
        missing = max(0, 4 - len(self.players[player].hand))
        if missing:
            self.draw(player, missing, "Mulligan iniziale" if initial else "Mulligan")
        returned: list[int] = []
        for uid in selected:
            if uid == charged:
                self.charge_card(uid, player, "Mulligan")
                continue
            self.reset_card_outside_field(uid, Zone.DECK, None)
            self.deck.append(uid)
            returned.append(uid)
        if returned:
            self.rng.shuffle(self.deck)
        if selected:
            self.telemetry.mulliganed += len(selected)
            self.emit(
                f"Il Giocatore {player + 1} rimette {len(returned)} carte nel Mazzo "
                f"e ne Carica {1 if charged is not None else 0} con il Mulligan."
            )

    def effective_charge_count(self, player: int) -> int:
        count = len(self.players[player].charges)
        if not self.is_thunder_sand:
            return count
        count += sum(
            1
            for uid in self.players[player].prayers
            if self.definition(uid).id == 35
            and self.definition(uid).prayer_type == PrayerType.SIGIL
            and self.cards[uid].seal_open
            and not self.is_suppressed(uid)
        )
        return count

    def charge_card(self, uid: int, player: int, reason: str) -> bool:
        if uid not in self.cards:
            return False
        self._remove_from_zone_list(uid)
        self.reset_card_outside_field(uid, Zone.CHARGE, player)
        self.players[player].charges.append(uid)
        self.telemetry.record_charge(player)
        self.emit(f"Il Giocatore {player + 1} Carica 1 carta ({reason}).")
        if self.is_thunder_sand:
            forms = self.forms(uid)
            for source_uid in self.all_maledictions():
                if self.is_suppressed(source_uid):
                    continue
                source_id = self.definition(source_uid).id
                required = "Tuono" if source_id == 22 else "Sabbia" if source_id == 42 else None
                if required is not None and required in forms:
                    self.players[player].score += 1
                    self.telemetry.record_ability(player, "Carica di forma")
                    self.emit(
                        f"Il Giocatore {player + 1} rivela una Carica {required}: "
                        f"{self.definition(source_uid).name} gli fa guadagnare 1 PV."
                    )
        self.check_seal_states()
        return True

    def charge_from_deck(self, player: int, count: int, reason: str) -> list[int]:
        charged: list[int] = []
        for _ in range(count):
            self.ensure_deck(player, 1, reason)
            if not self.deck:
                break
            uid = self.deck.pop()
            if self.charge_card(uid, player, reason):
                charged.append(uid)
        return charged

    def charge_from_hand(
        self,
        player: int,
        reason: str,
        *,
        source_uid: int | None = None,
    ) -> int | None:
        if not self.players[player].hand:
            return None
        uid = self._choose_target(
            player,
            self.players[player].hand,
            "charge",
            source_uid,
        )
        if uid is not None and self.charge_card(uid, player, reason):
            return uid
        return None

    def spend_charges(
        self,
        owner: int,
        count: int,
        reason: str,
        *,
        chooser: int | None = None,
    ) -> list[int]:
        if count <= 0 or len(self.players[owner].charges) < count:
            return []
        spent: list[int] = []
        for _ in range(count):
            if not self.players[owner].charges:
                break
            if chooser is None or chooser != owner:
                uid = self.rng.choice(self.players[owner].charges)
            else:
                uid = self._choose_target(owner, self.players[owner].charges, "spend_charge")
                if uid is None:
                    uid = self.players[owner].charges[0]
            self.players[owner].charges.remove(uid)
            spent.append(uid)

        self.emit(f"Il Giocatore {owner + 1} spende {len(spent)} Cariche ({reason}).")
        first_spend_this_turn = self.charge_spend_seen_turn[owner] != self.turn_number
        if spent and first_spend_this_turn:
            self.charge_spend_seen_turn[owner] = self.turn_number
        for index, uid in enumerate(spent):
            played = False
            if self.is_thunder_sand and index == 0 and first_spend_this_turn:
                notte_sources = [
                    source_uid
                    for source_uid in self.players[owner].maledictions
                    if self.definition(source_uid).id == 25
                    and not self.is_suppressed(source_uid)
                ]
                if notte_sources:
                    play_it = self._choose_option(
                        owner,
                        [True, False],
                        "play_spent_charge",
                        notte_sources[0],
                    )
                    if play_it is True:
                        played = self.play_generated_card(uid, owner, calata=False)
            definition_id = self.definition(uid).id
            if not played and self.is_thunder_sand and definition_id in {27, 38, 39}:
                self.reset_card_outside_field(uid, Zone.DECK, None)
                if self.play_generated_card(
                    uid,
                    owner,
                    forced_mode="Maledizione",
                    calata=False,
                ):
                    if definition_id == 38:
                        self.cards[uid].stasis = False
                    elif definition_id == 27:
                        self.add_modifier(
                            "target_eye_add",
                            owner,
                            source_uid=uid,
                            target_uid=uid,
                            value=1,
                        )
                        self.add_modifier(
                            "target_karma_add",
                            owner,
                            source_uid=uid,
                            target_uid=uid,
                            value=1,
                        )
                    self.emit(
                        f"{self.definition(uid).name} viene giocata perché è stata spesa come Carica."
                    )
                    continue
            if played:
                continue
            self.reset_card_outside_field(uid, Zone.DECK, None)
            self.deck.insert(0, uid)

        if spent and self.is_thunder_sand:
            for sigil in list(self.players[owner].prayers):
                if self.definition(sigil).id != 1 or not self.sigil_is_active(sigil):
                    continue
                candidates = [
                    target
                    for target in self.all_maledictions()
                    if self.cards[target].stasis and "Tuono" in self.forms(target)
                ]
                target = self._choose_target(
                    owner,
                    candidates,
                    "optional_remove_stasis",
                    sigil,
                )
                if target is not None:
                    self.cards[target].stasis = False
                    self.stasis_removed_this_turn[owner].add(target)
                    self.emit(
                        f"Cuore dei Cieli rimuove la Stasi da {self.definition(target).name}."
                    )
            for sigil in list(self.players[owner].prayers):
                if (
                    self.definition(sigil).id == 49
                    and self.sigil_is_active(sigil)
                ):
                    self.draw(owner, 1, "Carovana Notturna")
            self.check_seal_states()
        return spent

    def place_mark(
        self,
        target_uid: int,
        marker_uid: int,
        owner: int,
        reason: str,
    ) -> bool:
        if target_uid not in self.all_field_cards() or self.is_marked(target_uid):
            return False
        marker = self.cards[marker_uid]
        if marker.zone == Zone.CHARGE:
            if marker.controller != owner or marker_uid not in self.players[owner].charges:
                return False
            self.players[owner].charges.remove(marker_uid)
        elif marker.zone == Zone.HAND:
            if marker.controller != owner or marker_uid not in self.players[owner].hand:
                return False
            self.players[owner].hand.remove(marker_uid)
        elif marker.zone == Zone.DECK and marker_uid in self.deck:
            self.deck.remove(marker_uid)
        else:
            return False
        self.reset_card_outside_field(marker_uid, Zone.MARK, owner)
        marker.attached_to = target_uid
        self.emit(f"{self.definition(target_uid).name} viene Marchiata ({reason}).")
        self.check_seal_states()
        return True

    def mark_with_charge(
        self,
        target_uid: int,
        charge_owner: int,
        reason: str,
        *,
        chooser: int | None = None,
        marker_uid: int | None = None,
    ) -> bool:
        if self.is_marked(target_uid) or not self.players[charge_owner].charges:
            return False
        if marker_uid is not None:
            if marker_uid not in self.players[charge_owner].charges:
                return False
        elif chooser == charge_owner:
            marker_uid = self._choose_target(
                charge_owner,
                self.players[charge_owner].charges,
                "spend_charge",
            )
        else:
            marker_uid = self.rng.choice(self.players[charge_owner].charges)
        return marker_uid is not None and self.place_mark(
            target_uid,
            marker_uid,
            charge_owner,
            reason,
        )

    def choose_mark_charge(self, charge_owner: int, *, chooser: int | None = None) -> int | None:
        """Sceglie il costo del Marchio prima di chiedere il suo bersaglio."""
        charges = self.players[charge_owner].charges
        if not charges:
            return None
        if chooser == charge_owner:
            return self._choose_target(
                charge_owner,
                charges,
                "spend_charge",
            )
        return self.rng.choice(charges)

    def remove_mark(self, target_uid: int, reason: str) -> bool:
        marker_uid = self.mark_for(target_uid)
        if marker_uid is None:
            return False
        taken_by: int | None = None
        for player in (self.active_player,):
            boato = next(
                (
                    sigil
                    for sigil in self.players[player].prayers
                    if self.definition(sigil).id == 4 and self.sigil_is_active(sigil)
                ),
                None,
            )
            if boato is None:
                continue
            take_it = self._choose_option(
                player,
                [True, False],
                "take_removed_mark",
                boato,
            )
            if take_it is True:
                taken_by = player
                break
        if taken_by is not None:
            self.reset_card_outside_field(marker_uid, Zone.HAND, taken_by)
            self.players[taken_by].hand.append(marker_uid)
            self.telemetry.record_draw(taken_by, self.definition(marker_uid).id)
            self.emit(
                f"Il Giocatore {taken_by + 1} prende il Marchio con Boato del Marchio."
            )
        else:
            self.reset_card_outside_field(marker_uid, Zone.DECK, None)
            self.deck.insert(0, marker_uid)
        self.emit(f"Il Marchio su {self.definition(target_uid).name} viene rimosso ({reason}).")
        self.check_seal_states()
        return True

    def _expire_combat_marks(self, marks_at_start: dict[int, int | None]) -> None:
        """Rimuove soltanto i Marchi presenti quando lo scontro e' iniziato.

        Un Marchio ottenuto da un effetto successivo all'attacco, per esempio
        Voce Tonante, deve invece attendere lo scontro seguente.
        """
        for target_uid, marker_uid in marks_at_start.items():
            if marker_uid is not None and self.mark_for(target_uid) == marker_uid:
                self.remove_mark(target_uid, "fine dello scontro successivo")

    def trigger_final_rounds(self, player: int, cause: str) -> None:
        if self.final_turns_remaining is not None:
            return
        self.final_turns_remaining = 5
        self.final_trigger_player = player
        self.final_trigger_cause = cause
        self.final_trigger_turn = self.turn_number
        self.emit(f"Il Giocatore {player + 1} attiva i cinque Turni Finali: {cause}.")

    def sigil_is_active(self, uid: int) -> bool:
        return (
            self.cards[uid].zone == Zone.PRAYER
            and self.definition(uid).prayer_type == PrayerType.SIGIL
            and self.cards[uid].seal_open
            and not self.is_suppressed(uid)
        )

    def close_sigil(self, uid: int, reason: str) -> bool:
        if not self.sigil_is_active(uid):
            return False
        self.cards[uid].seal_open = False
        self.emit(f"Il Sigillo {self.definition(uid).name} si chiude ({reason}).")
        return True

    def open_sigil(self, uid: int, reason: str) -> bool:
        card = self.cards[uid]
        if (
            card.zone != Zone.PRAYER
            or self.definition(uid).prayer_type != PrayerType.SIGIL
            or card.seal_open
        ):
            return False
        card.seal_open = True
        self.emit(f"Il Sigillo {self.definition(uid).name} si apre ({reason}).")
        self.check_seal_states()
        return card.seal_open

    def check_seal_states(self) -> None:
        if not self.is_thunder_sand or self._checking_seal_states:
            return
        self._checking_seal_states = True
        try:
            for sigil in list(self.all_prayers()):
                if self.definition(sigil).id != 10 or not self.sigil_is_active(sigil):
                    continue
                controller = self.cards[sigil].controller
                if controller is None:
                    continue
                for target in list(self.players[controller].maledictions):
                    if self.has_ability(target, "emblema") and not self.cards[target].corrupted:
                        self.corrupt_card(target, controller, "Fulmine Fragile")

            for uid in list(self.all_prayers()):
                if not self.sigil_is_active(uid):
                    continue
                card = self.cards[uid]
                player = card.controller
                if player is None:
                    continue
                definition_id = self.definition(uid).id
                own_maledictions = self.players[player].maledictions
                enemy_maledictions = self.players[1 - player].maledictions
                own_sand = sum("Sabbia" in self.forms(target) for target in own_maledictions)
                enemy_sand = sum("Sabbia" in self.forms(target) for target in enemy_maledictions)
                close_reason: str | None = None
                if definition_id == 1 and not any(
                    "Tuono" in self.forms(target) for target in own_maledictions
                ):
                    close_reason = "non controlli Maledizioni Tuono"
                elif definition_id == 3 and self.used_malediction_slots(player) >= 4:
                    close_reason = "hai 4 Maledizioni"
                elif definition_id == 4 and not any(
                    self.is_marked(target) for target in self.all_field_cards()
                ):
                    close_reason = "non ci sono Marchi in campo"
                elif definition_id == 10 and not any(
                    self.has_ability(target, "emblema") for target in own_maledictions
                ):
                    close_reason = "non controlli Maledizioni con Emblema"
                elif definition_id in {14, 37} and len(self.players[player].charges) >= 3:
                    close_reason = "hai almeno 3 Cariche"
                elif definition_id == 28:
                    own = self.count_form_on_side(player, "Tuono")
                    enemy = self.count_form_on_side(1 - player, "Tuono")
                    if enemy > own:
                        close_reason = "l'avversario ha più Tuono"
                elif definition_id in {30, 56, 57} and own_sand == 0:
                    close_reason = "non controlli Maledizioni Sabbia"
                elif definition_id == 35 and len(self.players[1 - player].charges) < len(
                    self.players[player].charges
                ):
                    close_reason = "l'avversario ha meno Cariche di te"
                elif definition_id == 36 and enemy_sand > own_sand:
                    close_reason = "l'avversario ha più Sabbia di te"
                elif definition_id == 49 and len(self.players[player].charges) <= 2:
                    close_reason = "hai 2 Cariche o meno"
                if close_reason is not None:
                    self.close_sigil(uid, close_reason)
        finally:
            self._checking_seal_states = False

    # ------------------------------------------------------------------
    # Forms, values and continuous effects
    # ------------------------------------------------------------------
    def active_modifiers(self, kind: str | None = None) -> list[Modifier]:
        result = [modifier for modifier in self.modifiers if modifier.is_active(self.turn_number)]
        if kind is not None:
            result = [modifier for modifier in result if modifier.kind == kind]
        return result

    def is_suppressed(self, uid: int) -> bool:
        return any(
            modifier.kind == "suppress_effect" and modifier.target_uid == uid
            for modifier in self.active_modifiers()
        )

    def attached_effect_active(self, host_uid: int) -> int | None:
        if self.is_suppressed(host_uid):
            return None
        prayer_uid = self.attached_prayer(host_uid)
        if prayer_uid is None or self.is_suppressed(prayer_uid):
            return None
        return prayer_uid

    def forms(self, uid: int) -> set[str]:
        definition = self.definition(uid)
        dual_forms = {"Tuono", "Sabbia"} if self.is_thunder_sand else {"Luce", "Ombra"}
        forms = dual_forms if definition.form == Form.DUAL else {definition.form.value}
        overrides: list[tuple[int, str]] = []
        if self.cards[uid].zone in {Zone.MALEDICTION, Zone.PRAYER}:
            for modifier in self.active_modifiers("form_override"):
                if modifier.target_uid == uid and isinstance(modifier.value, str):
                    overrides.append((modifier.sequence, modifier.value))
        if self.cards[uid].zone == Zone.MALEDICTION and not self.is_thunder_sand:
            prayer_uid = self.attached_effect_active(uid)
            if prayer_uid is not None and self.definition(prayer_uid).id == 60 and definition.form != Form.DUAL:
                bond_sequence = self.cards[prayer_uid].entered_sequence
                earlier = [item for item in overrides if item[0] < bond_sequence]
                if earlier:
                    form_before_bond = max(earlier, key=lambda item: item[0])[1]
                else:
                    form_before_bond = definition.form.value
                opposite = "Ombra" if form_before_bond == "Luce" else "Luce"
                overrides.append((bond_sequence, opposite))
        if overrides:
            return {max(overrides, key=lambda item: item[0])[1]}
        return forms

    def count_form_on_side(self, player: int, form: str) -> int:
        cards = self.players[player].maledictions + self.players[player].prayers
        return sum(form in self.forms(uid) for uid in cards)

    def original_eye(self, uid: int) -> int:
        value = self.definition(uid).eye
        overrides = []
        if self.cards[uid].zone in {Zone.MALEDICTION, Zone.PRAYER}:
            overrides = [
                modifier
                for modifier in self.active_modifiers("set_original_eye")
                if modifier.target_uid == uid
            ]
        if overrides:
            value = int(max(overrides, key=lambda modifier: modifier.sequence).value or 0)
        return max(0, value)

    def karma(self, uid: int) -> int:
        if self.is_thunder_sand:
            return self._thunder_sand_karma(uid)
        definition = self.definition(uid)
        card = self.cards[uid]
        value = definition.karma
        if card.zone == Zone.MALEDICTION and not self.is_suppressed(uid):
            if definition.id == 25:
                value += sum("Luce" in self.forms(prayer) for prayer in self.all_prayers())
            attached = self.attached_effect_active(uid)
            if attached is not None:
                attached_id = self.definition(attached).id
                if attached_id in {2, 31}:
                    required = "Luce" if attached_id == 2 else "Ombra"
                    if required in self.forms(uid):
                        value += 2
                elif attached_id in {13, 48}:
                    value += 1
                elif attached_id == 36:
                    value -= 1
        for modifier in self.active_modifiers("target_karma_add"):
            if modifier.target_uid == uid:
                value += int(modifier.value or 0)
        return max(0, value)

    def _same_form_glyph_and_sigil(self, player: int) -> bool:
        glyphs = [
            uid
            for uid in self.players[player].prayers
            if self.definition(uid).prayer_type == PrayerType.GLYPH
            and not self.is_suppressed(uid)
        ]
        sigils = [
            uid
            for uid in self.players[player].prayers
            if self.definition(uid).prayer_type == PrayerType.SIGIL
            and self.sigil_is_active(uid)
        ]
        return any(not self.forms(glyph).isdisjoint(self.forms(sigil)) for glyph in glyphs for sigil in sigils)

    def _thunder_sand_karma(self, uid: int) -> int:
        definition = self.definition(uid)
        card = self.cards[uid]
        value = definition.karma
        if card.zone == Zone.MALEDICTION and not self.is_suppressed(uid):
            controller = card.controller
            definition_id = definition.id
            if controller is not None:
                if definition_id == 15:
                    value += 3 * (self.effective_charge_count(controller) // 3)
                elif definition_id == 21:
                    value += sum(
                        self.malediction_weight(other)
                        for other in self.players[controller].maledictions
                        if self.cards[other].attacked_turn == self.turn_number
                    )
                elif definition_id == 31:
                    value += sum(
                        self.is_marked(target)
                        for target in self.all_field_cards()
                    )
                elif definition_id == 60 and self._same_form_glyph_and_sigil(controller):
                    value += 2
                for source_uid in self.players[controller].maledictions:
                    if (
                        source_uid != uid
                        and self.definition(source_uid).id == 32
                        and not self.is_suppressed(source_uid)
                        and "Sabbia" in self.forms(uid)
                    ):
                        value += 1
                for sigil in self.players[controller].prayers:
                    if not self.sigil_is_active(sigil):
                        continue
                    sigil_id = self.definition(sigil).id
                    if sigil_id == 9 and "Tuono" in self.forms(uid):
                        value -= 1
        for modifier in self.active_modifiers("target_karma_add"):
            if modifier.target_uid == uid:
                value += int(modifier.value or 0)
        swaps = [
            modifier
            for modifier in self.active_modifiers("swap_eye_karma")
            if modifier.target_uid == uid and isinstance(modifier.value, str)
        ]
        if swaps:
            effective_eye, _effective_karma = str(
                max(swaps, key=lambda modifier: modifier.sequence).value
            ).split(":", 1)
            value = int(effective_eye)
        return max(0, value)

    def _always_original_effects(self, uid: int) -> list[tuple[int, int]]:
        card = self.cards[uid]
        if card.zone != Zone.MALEDICTION:
            return []
        effects: list[tuple[int, int]] = []
        for source_uid in self.all_maledictions():
            source = self.cards[source_uid]
            if self.definition(source_uid).id != 55 or self.is_suppressed(source_uid):
                continue
            if source_uid == uid or source.controller != card.controller:
                effects.append((source.entered_sequence, self.original_eye(uid)))
        return effects

    def eye(self, uid: int) -> int:
        if self.is_thunder_sand:
            return self._thunder_sand_eye(uid)
        card = self.cards[uid]
        definition = self.definition(uid)
        base = self.original_eye(uid)
        set_effects: list[tuple[int, int, bool]] = []
        sums = 0

        if card.zone == Zone.MALEDICTION and not self.is_suppressed(uid):
            controller = card.controller
            if definition.id in {3, 32} and controller is not None:
                required_form = "Ombra" if definition.id == 3 else "Luce"
                if sum(required_form in self.forms(other) for other in self.players[controller].maledictions) == 1:
                    sums += 2
            elif definition.id == 15 and controller is not None:
                other_lights = [
                    other for other in self.players[controller].maledictions
                    if other != uid and "Luce" in self.forms(other)
                ]
                if not other_lights:
                    sums += 3
            elif definition.id == 19 and card.corrupted:
                sums += 3
            elif definition.id in {27, 43} and controller is not None and self.active_player != controller:
                set_effects.append((card.entered_sequence, self.karma(uid), False))
            elif definition.id == 42:
                sums += sum(
                    other != uid and "Ombra" in self.forms(other)
                    for other in self.all_field_cards()
                )

            attached = self.attached_effect_active(uid)
            if attached is not None:
                attached_id = self.definition(attached).id
                seq = self.cards[attached].entered_sequence
                if attached_id == 7 and card.corrupted:
                    sums += 1
                elif attached_id == 13:
                    sums += 1
                elif attached_id == 19 and card.corrupted:
                    sums += 2
                elif attached_id == 21 and controller is not None:
                    sums += len(self.players[1 - controller].maledictions)
                elif attached_id == 25:
                    set_effects.append((seq, 5, True))
                elif attached_id == 26 and controller is not None:
                    opponents = self.players[1 - controller].maledictions
                    if opponents:
                        set_effects.append((seq, max(self.original_eye(other) for other in opponents), False))
                elif attached_id == 47:
                    sums += sum(
                        self.original_eye(other) > self.original_eye(uid)
                        for other in self.all_maledictions()
                    )
                elif attached_id == 48:
                    sums += 1
                elif attached_id == 49 and card.corrupted:
                    sums += 2
                elif attached_id == 50 and controller is not None:
                    shadow_maledictions = [
                        other for other in self.players[controller].maledictions
                        if "Ombra" in self.forms(other)
                    ]
                    if shadow_maledictions == [uid] or (len(shadow_maledictions) == 1 and uid in shadow_maledictions):
                        sums += 3

        if card.zone == Zone.MALEDICTION and card.controller is not None:
            controller = card.controller
            for source_uid in self.players[controller].maledictions:
                if self.is_suppressed(source_uid):
                    continue
                source_id = self.definition(source_uid).id
                if source_id == 22:
                    own = self.players[controller].maledictions
                    if own and all("Luce" in self.forms(other) for other in own):
                        sums += 2
                elif source_id == 39:
                    own = self.players[controller].maledictions
                    if own and all("Ombra" in self.forms(other) for other in own):
                        sums += 2

        for seq, value in self._always_original_effects(uid):
            set_effects.append((seq, value, True))

        for modifier in self.active_modifiers():
            if modifier.target_uid == uid:
                if modifier.kind == "target_eye_add":
                    sums += int(modifier.value or 0)
                elif modifier.kind == "target_eye_per_other_prayers":
                    source_is_prayer = (
                        modifier.source_uid is not None
                        and self.cards[modifier.source_uid].zone == Zone.PRAYER
                    )
                    prayer_count = len(self.all_prayers()) - int(source_is_prayer)
                    sums += int(modifier.value or 0) * max(0, prayer_count)
                elif modifier.kind == "target_eye_per_enemy_maledictions":
                    sums += int(modifier.value or 0) * len(self.players[1 - modifier.controller].maledictions)
                elif modifier.kind == "set_eye":
                    set_effects.append((modifier.sequence, int(modifier.value or 0), False))
                elif modifier.kind == "set_eye_reference" and modifier.reference_uid is not None:
                    set_effects.append((modifier.sequence, self.original_eye(modifier.reference_uid), False))
            if card.controller == modifier.controller:
                if modifier.kind == "own_corrupted_eye" and card.corrupted:
                    sums += int(modifier.value or 0)
                elif modifier.kind == "own_form_eye" and isinstance(modifier.value, str):
                    form, amount = modifier.value.split(":")
                    if form in self.forms(uid):
                        sums += int(amount)

        always = [item for item in set_effects if item[2]]
        if len(always) == 1:
            return max(0, always[0][1])
        if always:
            base = max(always, key=lambda item: item[0])[1]
        elif set_effects:
            base = max(set_effects, key=lambda item: item[0])[1]
        return max(0, base + sums)

    def _thunder_sand_eye(self, uid: int) -> int:
        card = self.cards[uid]
        definition = self.definition(uid)
        value = self.original_eye(uid)
        set_effects: list[tuple[int, int]] = []
        sums = 0
        if card.zone == Zone.MALEDICTION and not self.is_suppressed(uid):
            controller = card.controller
            definition_id = definition.id
            if controller is not None:
                if definition_id == 2:
                    sums += self.effective_charge_count(controller)
                elif definition_id in {41, 43} and card.corrupted:
                    sums += 2
                elif definition_id == 60 and self._same_form_glyph_and_sigil(controller):
                    sums += 2

                for sigil in self.all_prayers():
                    if not self.sigil_is_active(sigil):
                        continue
                    sigil_controller = self.cards[sigil].controller
                    if sigil_controller is None:
                        continue
                    sigil_id = self.definition(sigil).id
                    if sigil_id == 9 and sigil_controller == controller and "Tuono" in self.forms(uid):
                        sums += 2
                    elif (
                        sigil_id in {14, 37}
                        and sigil_controller == 1 - controller
                        and self.is_marked(uid)
                    ):
                        sums -= 2
                    elif sigil_id == 28 and sigil_controller == controller and "Tuono" in self.forms(uid):
                        sums += 1
                    elif sigil_id == 36 and sigil_controller == controller and "Sabbia" in self.forms(uid):
                        sums += 1
                    elif (
                        sigil_id == 57
                        and sigil_controller == controller
                        and definition.prayer_type == PrayerType.GLYPH
                    ):
                        sums += 2
                    elif (
                        sigil_id == 56
                        and sigil_controller == controller
                        and definition.prayer_type == PrayerType.SIGIL
                    ):
                        sums += 2

                for source_uid in self.players[controller].maledictions:
                    if (
                        self.definition(source_uid).id == 55
                        and not self.is_suppressed(source_uid)
                        and self.active_player != controller
                    ):
                        sums += 2 if self.cards[source_uid].corrupted else 1

                for glyph in self.all_prayers():
                    if (
                        self.definition(glyph).id in {8, 12, 19, 25, 32, 38, 45}
                        and self.definition(glyph).prayer_type == PrayerType.GLYPH
                        and not self.is_suppressed(glyph)
                        and self.cards[glyph].controller == 1 - controller
                        and self.is_marked(uid)
                    ):
                        sums -= self.effective_charge_count(1 - controller)

        for modifier in self.active_modifiers():
            if modifier.target_uid != uid:
                continue
            if modifier.kind == "target_eye_add":
                sums += int(modifier.value or 0)
            elif modifier.kind == "set_eye":
                set_effects.append((modifier.sequence, int(modifier.value or 0)))
            elif modifier.kind == "set_eye_reference" and modifier.reference_uid is not None:
                set_effects.append((modifier.sequence, self.original_eye(modifier.reference_uid)))
        if set_effects:
            value = max(set_effects, key=lambda item: item[0])[1]
        value = max(0, value + sums)
        if card.zone == Zone.MALEDICTION and card.corrupted and self.has_ability(uid, "emblema"):
            value *= 2
        if (
            card.zone == Zone.MALEDICTION
            and definition.id == 47
            and card.controller is not None
            and self.active_player != card.controller
            and not self.is_suppressed(uid)
        ):
            value *= 2
        swaps = [
            modifier
            for modifier in self.active_modifiers("swap_eye_karma")
            if modifier.target_uid == uid and isinstance(modifier.value, str)
        ]
        if swaps:
            _effective_eye, effective_karma = str(
                max(swaps, key=lambda modifier: modifier.sequence).value
            ).split(":", 1)
            value = int(effective_karma)
        return max(0, value)

    def has_ability(self, uid: int, ability: str) -> bool:
        card = self.cards[uid]
        if card.zone != Zone.MALEDICTION:
            return False
        suppressed = self.is_suppressed(uid)
        definition_id = self.definition(uid).id
        if self.is_thunder_sand:
            base_map = {
                "fato": {20},
                "schermatura": {30, 35, 36, 37, 40, 43, 47, 59},
                "emblema": {2, 5, 8, 12, 28, 59},
                "colosso": {16, 51},
                "cadenza": {7, 26, 46, 58},
            }
            # Annullare l'effetto rimuove anche Schermatura concessa da un'altra carta.
            # Il modificatore resta per ripristinarla quando l'annullamento scade.
            if ability == "schermatura" and (card.corrupted or suppressed):
                return False
            active = not suppressed and definition_id in base_map.get(ability, set())
            if ability == "schermatura":
                active = active or any(
                    modifier.kind == "grant_screening" and modifier.target_uid == uid
                    for modifier in self.active_modifiers()
                )
            if ability == "emblema":
                active = active or any(
                    modifier.kind == "grant_emblem" and modifier.target_uid == uid
                    for modifier in self.active_modifiers()
                )
            return active
        base_map = {
            "rivalita": {2, 8, 18, 31, 38, 47},
            "impatto": {14, 45, 49, 53, 60},
            "barriera": {9, 17, 20, 41, 60},
            "fato": {57},
        }
        active = not suppressed and definition_id in base_map.get(ability, set())
        attached = self.attached_effect_active(uid) if not suppressed else None
        if attached is not None:
            attached_id = self.definition(attached).id
            attached_map = {
                "rivalita": {3, 32},
                "impatto": {36},
                "barriera": {7},
            }
            active = active or attached_id in attached_map.get(ability, set())
        if ability == "barriera":
            # Una Barriera gia' concessa da Eco/Impulso e' un modificatore:
            # annullare il testo della carta bersaglio non la cancella.
            active = active or any(
                modifier.kind == "grant_barrier" and modifier.target_uid == uid
                for modifier in self.active_modifiers()
            )
        if ability == "rivalita" and self.forms(uid) == {"Luce", "Ombra"}:
            return False
        return active

    def combat_eye(self, uid: int, opponent_uid: int, *, projected_attack: bool = False) -> int:
        value = self.eye(uid)
        if self.has_ability(uid, "rivalita"):
            own_forms = self.forms(uid)
            opponent_forms = self.forms(opponent_uid)
            if opponent_forms != {"Luce", "Ombra"} and own_forms.isdisjoint(opponent_forms):
                value += 3
        if projected_attack:
            attacker_forms = self.forms(uid)
            for modifier in self.active_modifiers("watch_attacked"):
                if modifier.target_uid != opponent_uid:
                    continue
                watched_form, amount = str(modifier.value).split(":")
                if watched_form in attacker_forms:
                    value = value
                    # Il malus è applicato al bersaglio, gestito in predict_combat.
        return max(0, value)

    def combat_karma(self, uid: int, opponent_uid: int) -> int:
        value = self.karma(uid)
        if (
            self.is_thunder_sand
            and self.definition(uid).id == 9
            and not self.is_suppressed(uid)
            and self.is_marked(opponent_uid)
        ):
            value += 2
        return max(0, value)

    def projected_defender_eye(self, attacker_uid: int, defender_uid: int) -> int:
        value = self.combat_eye(defender_uid, attacker_uid)
        attacker_forms = self.forms(attacker_uid)
        for modifier in self.active_modifiers("watch_attacked"):
            if modifier.target_uid != defender_uid:
                continue
            watched_form, amount = str(modifier.value).split(":")
            if watched_form in attacker_forms:
                value += int(amount)
        return max(0, value)

    # ------------------------------------------------------------------
    # Heuristics and legal actions
    # ------------------------------------------------------------------
    def card_value(self, uid: int, perspective: int) -> float:
        definition = self.definition(uid)
        card = self.cards[uid]
        if card.zone == Zone.MALEDICTION:
            value = self.eye(uid) + 1.35 * self.karma(uid) + self.malediction_effect_value(uid)
            if card.corrupted:
                value -= 0.8
            if card.stasis:
                value -= 0.5
            return value
        if card.zone == Zone.PRAYER:
            persistent = definition.prayer_type in {PrayerType.ECHO, PrayerType.SIGIL, PrayerType.GLYPH}
            effect_value = self.prayer_effect_value(uid)
            if definition.prayer_type == PrayerType.SIGIL and not self.sigil_is_active(uid):
                # Un Sigillo chiuso conserva valore futuro, ma non vale come
                # se il suo effetto fosse gia' attivo. Questo evita che il Bot
                # spenda Azioni per Sigilli che si richiudono immediatamente.
                return 0.25 * effect_value + 0.35
            return effect_value + (1.0 if persistent else 0.3)
        return max(
            definition.eye + 1.2 * definition.karma + self.malediction_effect_value(uid),
            self.prayer_effect_value(uid) + (0.8 if definition.prayer_type in {PrayerType.ECHO, PrayerType.SIGIL, PrayerType.GLYPH} else 0.0),
        )

    def evaluate_position(self, player: int) -> float:
        opponent = 1 - player
        score = 3.5 * (self.players[player].score - self.players[opponent].score)
        score += sum(self.card_value(uid, player) for uid in self.players[player].maledictions)
        score -= sum(self.card_value(uid, player) for uid in self.players[opponent].maledictions)
        score += 0.8 * sum(self.card_value(uid, player) for uid in self.players[player].prayers)
        score -= 0.8 * sum(self.card_value(uid, player) for uid in self.players[opponent].prayers)
        score += 0.25 * (len(self.players[player].hand) - len(self.players[opponent].hand))
        score += 0.35 * (len(self.players[player].altar) - len(self.players[opponent].altar))
        return score

    def estimate_action(self, action: Action, player: int, profile: Any) -> float:
        if action.kind == "pass":
            return -0.4 if any(item.kind != "pass" for item in self.legal_actions(player)) else 0.0
        if action.card_uid is None:
            return 0.0
        definition = self.definition(action.card_uid)
        if action.kind == "play_malediction":
            return (
                definition.eye * profile.eye_weight
                + definition.karma * profile.karma_weight
                + self.malediction_effect_value(action.card_uid)
                + (0.8 if action.cost == 0 else 0.0)
            )
        if action.kind == "play_prayer":
            value = self.prayer_effect_value(action.card_uid) * profile.prayer_weight
            if definition.prayer_type == PrayerType.IMPULSE:
                value *= profile.control
            if definition.prayer_type == PrayerType.ECHO:
                value += 0.8 * len(self.players[player].prayers)
            if action.target_uid is not None:
                target_value = self.card_value(action.target_uid, player)
                if self.cards[action.target_uid].controller == player:
                    value += 0.18 * target_value * profile.board_weight
                else:
                    value -= 0.10 * target_value * profile.board_weight
            return value + (0.8 if action.cost == 0 else 0.0)
        if action.kind == "remove_stasis":
            return 1.2 + 0.35 * self.eye(action.card_uid) + profile.aggression
        if action.kind == "invoke":
            return self.prayer_effect_value(action.card_uid) * profile.prayer_weight
        if action.kind == "use_glyph":
            return self.prayer_effect_value(action.card_uid) * profile.prayer_weight + 0.45
        if action.kind == "attack_direct":
            return self.karma(action.card_uid) * profile.score_weight + 2.0 * profile.aggression
        if action.kind == "attack" and action.target_uid is not None:
            outcome = self.predict_combat(action.card_uid, action.target_uid)
            target_value = self.card_value(action.target_uid, player)
            own_value = self.card_value(action.card_uid, player)
            if outcome == "attacker_win":
                target = self.cards[action.target_uid]
                offer = target.corrupted
                return 2.5 + target_value * 0.5 + (self.karma(action.card_uid) * profile.score_weight if offer else 0)
            if outcome == "tie":
                return profile.risk * target_value - 0.25 * own_value
            return profile.risk * 0.5 * target_value - 0.7 * own_value
        return 0.0

    def malediction_weight(self, uid: int) -> int:
        return 2 if self.is_thunder_sand and self.definition(uid).id in {16, 51} else 1

    def used_malediction_slots(self, player: int) -> int:
        return sum(self.malediction_weight(uid) for uid in self.players[player].maledictions)

    def required_malediction_replacement_slots(self, player: int, uid: int) -> int:
        return max(0, self.used_malediction_slots(player) + self.malediction_weight(uid) - 4)

    def form_is_blocked(self, player: int, uid: int, *, calata: bool = True) -> bool:
        # Limitare del Mondo vieta di *calare* la Forma dichiarata. Come da
        # regolamento, una carta giocata dal Mazzo, dal Vuoto o da una Carica
        # non e' calata, salvo che un effetto dica esplicitamente "come se
        # fosse nella Mano" (quel chiamante passa calata=True).
        if not self.is_thunder_sand or not calata:
            return False
        for sigil in self.players[1 - player].prayers:
            if (
                self.definition(sigil).id == 60
                and self.sigil_is_active(sigil)
                and self.cards[sigil].declared_form in self.forms(uid)
            ):
                return True
        return False

    def can_play_malediction(self, player: int, uid: int | None = None) -> bool:
        current = self.players[player].maledictions
        incoming_weight = self.malediction_weight(uid) if uid is not None else 1
        if (
            self.is_thunder_sand
            and uid is not None
            and self.definition(uid).id in {7, 26, 46, 58}
            and (
                existing_cadenzas := [
                    other for other in current if self.has_ability(other, "cadenza")
                ]
            )
        ):
            # Una nuova Cadenza puo' sostituire quella gia' presente soltanto
            # quando il limite di Maledizioni viene effettivamente superato.
            # La vecchia deve essere Pura, perche' e' la carta che andra'
            # obbligatoriamente nel Vuoto per rientrare nel limite.
            replacement = self.required_malediction_replacement_slots(player, uid)
            if replacement <= 0 or any(self.cards[other].corrupted for other in existing_cadenzas):
                return False
        used = self.used_malediction_slots(player)
        removable = sum(
            self.malediction_weight(card_uid)
            for card_uid in current
            if not self.cards[card_uid].corrupted
        )
        return used - removable + incoming_weight <= 4

    def can_accept_prayer(self, player: int, definition: CardDefinition, target_uid: int | None = None) -> bool:
        if definition.prayer_type == PrayerType.ECHO:
            return True
        if definition.prayer_type == PrayerType.BOND:
            return target_uid is not None
        return True

    def glyph_cost(self, uid: int) -> int:
        if not self.is_thunder_sand or self.definition(uid).prayer_type != PrayerType.GLYPH:
            return 0
        return {
            6: 1,
            8: 1,
            12: 1,
            15: 2,
            18: 2,
            19: 1,
            21: 3,
            22: 2,
            25: 1,
            32: 1,
            38: 1,
            42: 2,
            44: 3,
            45: 1,
            47: 2,
            53: 3,
            61: 0,
            62: 0,
        }.get(self.definition(uid).id, 0)

    def glyph_can_resolve(self, uid: int, player: int) -> bool:
        """Evita di proporre un Glifo quando non esiste alcuna risoluzione valida."""
        if (
            not self.is_thunder_sand
            or uid not in self.players[player].prayers
            or self.definition(uid).prayer_type != PrayerType.GLYPH
            or self.is_suppressed(uid)
        ):
            return False
        definition_id = self.definition(uid).id
        if definition_id == 6:
            return any(not self.is_marked(target) for target in self.all_maledictions())
        if definition_id in {8, 12, 19, 25, 32, 38, 45}:
            return any(not self.is_marked(target) for target in self.all_field_cards())
        if definition_id == 15:
            return bool(self.void)
        if definition_id in {18, 47}:
            return bool(self.all_maledictions())
        if definition_id == 21:
            return bool(self.players[player].maledictions)
        if definition_id in {22, 42}:
            return any(self.cards[target].corrupted for target in self.all_maledictions())
        if definition_id == 44:
            return any(
                not (
                    self.cards[target].zone == Zone.MALEDICTION
                    and self.definition(target).id == 49
                    and not self.is_suppressed(target)
                )
                for target in self.all_field_cards()
            )
        if definition_id == 53:
            return any(len(state.maledictions) >= 2 for state in self.players)
        if definition_id in {61, 62}:
            return bool(self.players[player].hand) and any(
                not self.is_marked(target) for target in self.all_field_cards()
            )
        return False

    def extra_attacks_remaining(self, uid: int) -> int:
        return sum(
            int(modifier.value or 0)
            for modifier in self.active_modifiers("extra_attacks")
            if modifier.target_uid == uid
        )

    def attack_cost(self, attacker_uid: int, target_uid: int | None) -> int:
        if not self.is_thunder_sand:
            return 1
        if self.cards[attacker_uid].attacked_turn == self.turn_number and self.extra_attacks_remaining(attacker_uid) > 0:
            return 0
        if any(
            modifier.kind == "free_attack"
            and modifier.target_uid == attacker_uid
            for modifier in self.active_modifiers()
        ):
            return 0
        if (
            target_uid is not None
            and self.definition(attacker_uid).id in {5, 39}
            and not self.is_suppressed(attacker_uid)
            and self.is_marked(target_uid)
        ):
            return 0
        return 1

    def consume_extra_attack(self, uid: int) -> None:
        for modifier in self.active_modifiers("extra_attacks"):
            if modifier.target_uid == uid and int(modifier.value or 0) > 0:
                modifier.value = int(modifier.value or 0) - 1
                return

    def free_prayers_active(self, player: int) -> bool:
        return any(
            modifier.kind == "free_prayers" and modifier.controller == player
            for modifier in self.active_modifiers()
        )

    def active_library_source(self, player: int) -> int | None:
        return next(
            (
                source_uid
                for source_uid in self.players[player].maledictions
                if self.definition(source_uid).id == 48
                and not self.is_suppressed(source_uid)
                and not any(
                    modifier.kind == "library_play_used"
                    and modifier.controller == player
                    and modifier.source_uid == source_uid
                    for modifier in self.active_modifiers()
                )
            ),
            None,
        )

    def consume_free_prayer_type_play(self, player: int, prayer_type: PrayerType) -> None:
        for modifier in list(self.modifiers):
            if (
                modifier.kind == "free_prayer_type_play"
                and modifier.controller == player
                and modifier.value == prayer_type.value
                and modifier in self.active_modifiers()
            ):
                self.modifiers.remove(modifier)
                return

    def balena_block_target(self, sigil_uid: int) -> int | None:
        """Aggiorna il singolo bersaglio bloccato dal Sigillo di Balena."""
        sigil = self.cards[sigil_uid]
        if not self.sigil_is_active(sigil_uid) or self.definition(sigil_uid).id != 52:
            sigil.effect_target_uid = None
            sigil.effect_target_state = None
            return None
        maledictions = self.all_maledictions()
        if not maledictions:
            sigil.effect_target_uid = None
            sigil.effect_target_state = None
            return None
        maximum = max(self.eye(other) for other in maledictions)
        candidates = [other for other in maledictions if self.eye(other) == maximum]
        state_key = f"{maximum}:" + ",".join(str(other) for other in sorted(candidates))
        if len(candidates) == 1:
            sigil.effect_target_uid = candidates[0]
            sigil.effect_target_state = state_key
            return candidates[0]
        if sigil.effect_target_state != state_key or sigil.effect_target_uid not in candidates:
            controller = sigil.controller
            chosen = (
                self._choose_target(
                    controller,
                    candidates,
                    "highest_eye_block",
                    sigil_uid,
                )
                if controller is not None
                else None
            )
            sigil.effect_target_uid = chosen
            sigil.effect_target_state = state_key if chosen is not None else None
        return sigil.effect_target_uid

    def cannot_attack(self, uid: int) -> bool:
        blocked = any(
            modifier.kind == "cannot_attack" and modifier.target_uid == uid
            for modifier in self.active_modifiers()
        )
        if blocked or not self.is_thunder_sand:
            return blocked
        if self.cards[uid].zone != Zone.MALEDICTION:
            return True
        for sigil in self.all_prayers():
            if self.definition(sigil).id != 52 or not self.sigil_is_active(sigil):
                continue
            if self.balena_block_target(sigil) == uid:
                return True
        return False

    def cannot_be_attacked(self, uid: int, attacker_uid: int | None = None) -> bool:
        if any(
            modifier.kind == "cannot_be_attacked" and modifier.target_uid == uid
            for modifier in self.active_modifiers()
        ):
            return True
        if self.is_thunder_sand and not self.is_suppressed(uid):
            definition_id = self.definition(uid).id
            controller = self.cards[uid].controller
            if definition_id == 53 and controller is not None:
                others = [other for other in self.players[controller].maledictions if other != uid]
                if sum(self.malediction_weight(other) for other in others) >= 2:
                    return True
        if (
            not self.is_thunder_sand
            and attacker_uid is not None
            and not self.is_suppressed(uid)
        ):
            definition_id = self.definition(uid).id
            attacker_forms = self.forms(attacker_uid)
            if definition_id == 24 and "Ombra" in attacker_forms:
                return True
            if definition_id == 52 and "Luce" in attacker_forms:
                return True
        return False

    def eclissi_targets(self, defending_player: int) -> list[int]:
        if self.is_thunder_sand:
            return [
                uid
                for uid in self.players[defending_player].maledictions
                if self.has_ability(uid, "schermatura")
            ]
        return [
            uid
            for uid in self.players[defending_player].maledictions
            if self.definition(uid).id == 37 and not self.is_suppressed(uid)
        ]

    def legal_actions(self, player: int) -> list[Action]:
        if self.game_over or player != self.active_player:
            return [Action("pass", cost=0, label="Passa")]
        actions: list[Action] = []
        available = self.players[player].actions
        hand = list(self.players[player].hand)
        playable_from_void: set[int] = set()
        library_sources = [
            source_uid
            for source_uid in self.players[player].maledictions
            if self.definition(source_uid).id == 48
            and not self.is_suppressed(source_uid)
            and not any(
                modifier.kind == "library_play_used"
                and modifier.controller == player
                and modifier.source_uid == source_uid
                for modifier in self.active_modifiers()
            )
        ]
        if (
            self.is_thunder_sand
            and self.void
            and library_sources
        ):
            # Biblioteca Sepolta rende soltanto la carta in cima al Vuoto
            # giocabile come se fosse nella Mano. Rimane nel Vuoto fino alla
            # risoluzione dell'azione, quindi ogni controllo e ogni CALO usa
            # ancora la carta reale invece di crearne una copia temporanea.
            playable_from_void.add(self.void[-1])

        playable_cards = hand + [uid for uid in playable_from_void if uid not in hand]
        for uid in playable_cards:
            definition = self.definition(uid)
            origin_note = " dalla cima del Vuoto" if uid in playable_from_void else ""
            blocked = self.form_is_blocked(player, uid)
            free_form_play = any(
                modifier.kind == "free_form_play"
                and modifier.controller == player
                and isinstance(modifier.value, str)
                and modifier.value in self.forms(uid)
                for modifier in self.active_modifiers()
            )
            if self.is_thunder_sand:
                mal_cost = 2 if definition.id in {16, 51} else 1
                if free_form_play:
                    mal_cost = 0
            else:
                mal_cost = 0 if definition.id == 50 and len(hand) == 1 else 1
            if not blocked and mal_cost <= available and self.can_play_malediction(player, uid):
                replacement = self.required_malediction_replacement_slots(player, uid)
                replacement_note = " sostituendo una o più Maledizioni Pure" if replacement else ""
                actions.append(Action("play_malediction", uid, mode="Maledizione", cost=mal_cost, label=f"Cala {definition.name}{origin_note} come Maledizione{replacement_note}"))
            if (
                self.is_thunder_sand
                and definition.id == 58
                and self.players[player].charges
                and not blocked
                and self.can_play_malediction(player, uid)
            ):
                actions.append(
                    Action(
                        "play_malediction",
                        uid,
                        mode="MaledizioneCarica",
                        cost=0,
                        label=f"Spendi 1 Carica e cala {definition.name}{origin_note} come Maledizione",
                    )
                )
            free_type_play = any(
                modifier.kind == "free_prayer_type_play"
                and modifier.controller == player
                and modifier.value == definition.prayer_type.value
                for modifier in self.active_modifiers()
            )
            prayer_cost = 0 if self.free_prayers_active(player) or free_form_play or free_type_play else 1
            if prayer_cost > available or blocked:
                continue
            if definition.prayer_type == PrayerType.BOND:
                for target in self.all_maledictions():
                    if definition.id == 60 and self.forms(target) == {"Luce", "Ombra"}:
                        continue
                    actions.append(Action("play_prayer", uid, target_uid=target, mode="Preghiera", cost=prayer_cost, label=f"Lega {definition.name}{origin_note} a {self.definition(target).name}"))
            else:
                actions.append(Action("play_prayer", uid, mode="Preghiera", cost=prayer_cost, label=f"Cala {definition.name}{origin_note} come Preghiera"))

        if available > 0:
            for uid in self.players[player].maledictions:
                if self.cards[uid].stasis:
                    actions.append(Action("remove_stasis", uid, cost=1, label=f"Rimuovi Stasi da {self.definition(uid).name}"))

        opponent = 1 - player
        priority_targets = self.eclissi_targets(opponent)
        for attacker in self.players[player].maledictions:
            card = self.cards[attacker]
            already_attacked = card.attacked_turn == self.turn_number
            if (
                card.stasis
                or self.cannot_attack(attacker)
                or (already_attacked and self.extra_attacks_remaining(attacker) <= 0)
            ):
                continue
            for preview in self.attack_target_previews(player, attacker):
                if not preview["allowed"]:
                    continue
                target = int(preview["target_uid"])
                attack_cost = self.attack_cost(attacker, target)
                if attack_cost <= available:
                    actions.append(
                        Action(
                            "attack",
                            attacker,
                            target_uid=target,
                            cost=attack_cost,
                            label=f"{self.definition(attacker).name} attacca {self.definition(target).name}",
                        )
                    )
            direct_allowed = not self.players[opponent].maledictions
            if not self.is_thunder_sand and self.definition(attacker).id == 4 and not self.is_suppressed(attacker):
                direct_allowed = direct_allowed or (
                    self.count_form_on_side(player, "Luce")
                    > self.count_form_on_side(opponent, "Luce")
                )
            if self.is_thunder_sand and self.definition(attacker).id == 17 and not self.is_suppressed(attacker):
                direct_allowed = direct_allowed or (
                    self.count_form_on_side(player, "Tuono")
                    > self.count_form_on_side(opponent, "Tuono")
                )
            if self.is_thunder_sand and self.definition(attacker).id == 40 and not self.is_suppressed(attacker):
                direct_allowed = False
            direct_cost = self.attack_cost(attacker, None)
            if direct_allowed and not priority_targets and direct_cost <= available:
                actions.append(Action("attack_direct", attacker, cost=direct_cost, label=f"{self.definition(attacker).name} attacca direttamente"))

        for uid in self.players[player].prayers:
            definition = self.definition(uid)
            card = self.cards[uid]
            if available > 0 and definition.prayer_type == PrayerType.ECHO and card.echo_used_turn != self.turn_number:
                actions.append(Action("invoke", uid, cost=1, label=f"Invoca {definition.name}"))
            elif available > 0 and definition.prayer_type == PrayerType.SIGIL and not card.seal_open:
                actions.append(Action("invoke", uid, cost=1, label=f"Apri il Sigillo {definition.name}"))
            elif definition.prayer_type == PrayerType.GLYPH:
                glyph_cost = self.glyph_cost(uid)
                once_per_turn = definition.id in {61, 62}
                if (
                    len(self.players[player].charges) >= glyph_cost
                    and (not once_per_turn or card.glyph_used_turn != self.turn_number)
                    and self.glyph_can_resolve(uid, player)
                ):
                    actions.append(
                        Action(
                            "use_glyph",
                            uid,
                            cost=0,
                            label=f"Usa il Glifo {definition.name} ({glyph_cost} Cariche)",
                        )
                    )
        actions.append(Action("pass", cost=0, label="Termina il turno"))
        return actions

    # ------------------------------------------------------------------
    # Actions and movement
    # ------------------------------------------------------------------
    def execute_action(self, action: Action, player: int, *, from_search: bool = False) -> None:
        self.last_attack = None
        self.last_fate = None
        self.last_impulse = None
        track_action = self.record_replay and not from_search
        if track_action:
            self.replay_action_counter += 1
            self.current_replay_action_index = self.replay_action_counter
            self.current_replay_action_label = action.label or action.kind
        if action.kind == "pass":
            self.telemetry.unused_actions[player] += self.players[player].actions
            self.players[player].actions = 0
            self.force_end_turn = True
            self.emit(f"Il Giocatore {player + 1} termina la Fase Principale.")
            self.current_replay_action_index = None
            self.current_replay_action_label = None
            return
        if action.cost > self.players[player].actions:
            self.current_replay_action_index = None
            self.current_replay_action_label = None
            return
        self.players[player].actions -= action.cost
        self.telemetry.increment_action(action.kind)
        self.emit(f"Giocatore {player + 1}: {action.label}.")

        if action.kind == "play_malediction" and action.card_uid is not None:
            from_void = self.cards[action.card_uid].zone == Zone.VOID
            library_source = self.active_library_source(player) if from_void else None
            if action.mode == "MaledizioneCarica":
                if not self.spend_charges(
                    player,
                    1,
                    f"calare {self.definition(action.card_uid).name}",
                    chooser=player,
                ):
                    self.current_replay_action_index = None
                    self.current_replay_action_label = None
                    return
            played = self.play_card(action.card_uid, player, "Maledizione", calata=True)
            if played and library_source is not None:
                self.add_modifier(
                    "library_play_used",
                    player,
                    source_uid=library_source,
                )
        elif action.kind == "play_prayer" and action.card_uid is not None:
            from_void = self.cards[action.card_uid].zone == Zone.VOID
            library_source = self.active_library_source(player) if from_void else None
            definition = self.definition(action.card_uid)
            other_free = self.free_prayers_active(player) or any(
                modifier.kind == "free_form_play"
                and modifier.controller == player
                and isinstance(modifier.value, str)
                and modifier.value in self.forms(action.card_uid)
                for modifier in self.active_modifiers()
            )
            use_free_type = (
                action.cost == 0
                and not other_free
                and any(
                    modifier.kind == "free_prayer_type_play"
                    and modifier.controller == player
                    and modifier.value == definition.prayer_type.value
                    for modifier in self.active_modifiers()
                )
            )
            played = self.play_card(
                action.card_uid,
                player,
                "Preghiera",
                target_uid=action.target_uid,
                calata=True,
            )
            if played and use_free_type:
                self.consume_free_prayer_type_play(player, definition.prayer_type)
            if played and library_source is not None:
                self.add_modifier(
                    "library_play_used",
                    player,
                    source_uid=library_source,
                )
        elif action.kind == "remove_stasis" and action.card_uid is not None:
            self.cards[action.card_uid].stasis = False
            self.telemetry.stasis_removed += 1
            self.stasis_removed_this_turn[player].add(action.card_uid)
            self.emit(f"La Stasi viene rimossa da {self.definition(action.card_uid).name}.")
        elif action.kind == "attack" and action.card_uid is not None and action.target_uid is not None:
            if (
                self.is_thunder_sand
                and self.definition(action.target_uid).id in {26, 46}
                and not self.is_suppressed(action.target_uid)
                and not self.spend_charges(
                    player,
                    1,
                    f"attaccare {self.definition(action.target_uid).name}",
                    chooser=player,
                )
            ):
                self.current_replay_action_index = None
                self.current_replay_action_label = None
                return
            already_attacked = self.cards[action.card_uid].attacked_turn == self.turn_number
            self.attack_event_counter += 1
            self.last_attack = {
                "event_id": self.attack_event_counter,
                "attacker_uid": action.card_uid,
                "target_uid": action.target_uid,
                "target_player": 1 - player,
            }
            self.stasis_removed_this_turn[player].discard(action.card_uid)
            self.resolve_combat(action.card_uid, action.target_uid)
            if already_attacked:
                self.consume_extra_attack(action.card_uid)
            self.modifiers = [
                modifier
                for modifier in self.modifiers
                if not (modifier.kind == "free_attack" and modifier.target_uid == action.card_uid)
            ]
        elif action.kind == "attack_direct" and action.card_uid is not None:
            already_attacked = self.cards[action.card_uid].attacked_turn == self.turn_number
            mark_at_start = self.mark_for(action.card_uid)
            self.attack_event_counter += 1
            self.last_attack = {
                "event_id": self.attack_event_counter,
                "attacker_uid": action.card_uid,
                "target_uid": None,
                "target_player": 1 - player,
            }
            self.stasis_removed_this_turn[player].discard(action.card_uid)
            self.cards[action.card_uid].attacked_turn = self.turn_number
            self.telemetry.direct_attacks += 1
            self.bless_card(action.card_uid, player)
            if self.is_thunder_sand:
                self.resolve_after_attack(
                    action.card_uid,
                    None,
                    player,
                    self.eye(action.card_uid),
                    0,
                    self.definition(action.card_uid).id,
                )
                self._expire_combat_marks({action.card_uid: mark_at_start})
            if already_attacked:
                self.consume_extra_attack(action.card_uid)
            self.modifiers = [
                modifier
                for modifier in self.modifiers
                if not (modifier.kind == "free_attack" and modifier.target_uid == action.card_uid)
            ]
            self.emit(f"{self.definition(action.card_uid).name} completa un Attacco Diretto.")
        elif action.kind == "invoke" and action.card_uid is not None:
            if self.definition(action.card_uid).prayer_type == PrayerType.SIGIL:
                self.telemetry.record_invocation(player)
                self.open_sigil(action.card_uid, "Invocazione")
                if self.cards[action.card_uid].seal_open and self.definition(action.card_uid).id == 60:
                    self.declare_sigil_form(action.card_uid, player)
            else:
                self.use_echo(action.card_uid, player)
        elif action.kind == "use_glyph" and action.card_uid is not None:
            self.use_glyph(action.card_uid, player)
        if self.force_end_turn:
            self.players[player].actions = 0
        self.current_replay_action_index = None
        self.current_replay_action_label = None

    def _choose_limit_malediction(self, player: int) -> int | None:
        candidates = [uid for uid in self.players[player].maledictions if not self.cards[uid].corrupted]
        return self.bots[player].choose_card(self, player, candidates, "limit_remove")

    def _choose_limit_echo(self, player: int) -> int | None:
        candidates = [
            uid for uid in self.players[player].prayers
            if self.definition(uid).prayer_type == PrayerType.ECHO
        ]
        return self.bots[player].choose_card(self, player, candidates, "limit_remove")

    def _choose_limit_prayer(self, player: int, prayer_type: PrayerType) -> int | None:
        candidates = [
            uid
            for uid in self.players[player].prayers
            if self.definition(uid).prayer_type == prayer_type
        ]
        return self.bots[player].choose_card(self, player, candidates, "limit_remove")

    def legal_modes_for_generated_play(
        self,
        uid: int,
        player: int,
        *,
        calata: bool = False,
    ) -> list[str]:
        modes: list[str] = []
        blocked = self.form_is_blocked(player, uid, calata=calata)
        if not blocked and self.can_play_malediction(player, uid):
            modes.append("Maledizione")
        definition = self.definition(uid)
        if blocked:
            return modes
        if definition.prayer_type == PrayerType.BOND:
            targets = [target for target in self.all_maledictions() if not (definition.id == 60 and self.forms(target) == {"Luce", "Ombra"})]
            if targets:
                modes.append("Preghiera")
        else:
            modes.append("Preghiera")
        return modes

    def play_card(
        self,
        uid: int,
        player: int,
        mode: str,
        *,
        target_uid: int | None = None,
        calata: bool = False,
    ) -> bool:
        card = self.cards[uid]
        definition = self.definition(uid)
        if mode == "Maledizione" and not self.can_play_malediction(player, uid):
            return False
        if self.form_is_blocked(player, uid, calata=calata):
            return False
        if mode == "Preghiera" and definition.prayer_type == PrayerType.BOND:
            if target_uid is None or target_uid not in self.all_maledictions():
                candidates = [
                    target for target in self.all_maledictions()
                    if not (definition.id == 60 and self.forms(target) == {"Luce", "Ombra"})
                ]
                target_uid = self.bots[player].choose_card(
                    self,
                    player,
                    candidates,
                    "attach_benefit",
                    source_uid=uid,
                )
            if target_uid is None:
                return False
            if definition.id == 60 and self.forms(target_uid) == {"Luce", "Ombra"}:
                return False

        bond_eye_before = (
            self.eye(target_uid)
            if (
                mode == "Preghiera"
                and definition.prayer_type == PrayerType.BOND
                and target_uid is not None
                and self.cards[target_uid].zone == Zone.MALEDICTION
            )
            else None
        )

        if mode == "Maledizione":
            if self.is_thunder_sand and definition.id in {7, 26, 46, 58}:
                existing_cadenzas = [
                    other
                    for other in list(self.players[player].maledictions)
                    if self.has_ability(other, "cadenza")
                ]
                for existing in existing_cadenzas:
                    self.move_to_void_without_break(
                        existing,
                        "Sostituzione della Cadenza",
                    )
            while self.used_malediction_slots(player) + self.malediction_weight(uid) > 4:
                removal = self._choose_limit_malediction(player)
                if removal is None:
                    return False
                self.move_to_void_without_break(removal, "Limite Maledizioni")
        elif mode == "Preghiera" and definition.prayer_type == PrayerType.ECHO:
            echoes = [
                prayer for prayer in self.players[player].prayers
                if self.definition(prayer).prayer_type == PrayerType.ECHO
            ]
            if len(echoes) >= 2:
                removal = self._choose_limit_echo(player)
                if removal is None:
                    return False
                self.move_to_void_without_break(removal, "Limite Eco")
        elif mode == "Preghiera" and definition.prayer_type in {PrayerType.SIGIL, PrayerType.GLYPH}:
            existing = [
                prayer
                for prayer in self.players[player].prayers
                if self.definition(prayer).prayer_type == definition.prayer_type
            ]
            if existing:
                removal = self._choose_limit_prayer(player, definition.prayer_type)
                if removal is None:
                    return False
                self.move_to_void_without_break(
                    removal,
                    f"Limite {definition.prayer_type.value}",
                )
        elif mode == "Preghiera" and definition.prayer_type == PrayerType.BOND and target_uid is not None:
            existing = self.attached_prayer(target_uid)
            if existing is not None:
                self.move_to_void_without_break(existing, "Limite Legame")

        self._remove_from_zone_list(uid)
        card.controller = player
        card.entered_sequence = self.next_sequence()
        card.attached_to = None
        card.attacked_turn = -1
        card.echo_used_turn = -1
        card.glyph_used_turn = -1
        card.declared_form = None
        card.effect_target_uid = None
        card.effect_target_state = None

        if mode == "Maledizione":
            card.zone = Zone.MALEDICTION
            card.corrupted = False
            card.stasis = True
            self.players[player].maledictions.append(uid)
        else:
            card.zone = Zone.PRAYER
            card.corrupted = False
            card.stasis = False
            card.attached_to = target_uid if definition.prayer_type == PrayerType.BOND else None
            card.seal_open = True
            self.players[player].prayers.append(uid)

        self.telemetry.record_play(player, definition.id, mode)
        location = f" collegata a {self.definition(target_uid).name}" if target_uid is not None and mode == "Preghiera" else ""
        self.emit(f"{definition.name} entra come {mode}{location}.")

        if mode == "Maledizione":
            if calata:
                self.resolve_calo(uid, player)
        else:
            if definition.prayer_type == PrayerType.IMPULSE:
                self.impulse_event_counter += 1
                self.last_impulse = {
                    "event_id": self.impulse_event_counter,
                    "card_uid": uid,
                    "controller": player,
                }
                self.resolve_prayer_effect(uid, player)
                if (
                    self.is_thunder_sand
                    and definition.id in {7, 34}
                    and self.cards[uid].zone == Zone.PRAYER
                ):
                    opponent = 1 - player
                    can_pay = bool(self.players[opponent].hand) if definition.id == 7 else bool(self.players[opponent].charges)
                    if can_pay:
                        recover = self._choose_option(
                            opponent,
                            [True, False],
                            "recover_impulse",
                            uid,
                        )
                        paid = False
                        if recover is True and definition.id == 7:
                            discard = self._choose_target(
                                opponent,
                                self.players[opponent].hand,
                                "discard_own",
                                uid,
                            )
                            if discard is not None:
                                self.discard_from_hand(discard, opponent, "recuperare Pulsar")
                                paid = True
                        elif recover is True:
                            paid = bool(
                                self.spend_charges(
                                    opponent,
                                    1,
                                    "recuperare Vocio dalle Dune",
                                    chooser=opponent,
                                )
                            )
                        if paid and self.cards[uid].zone == Zone.PRAYER:
                            self.take_to_hand(uid, opponent, f"recupero di {definition.name}")
                if self.cards[uid].zone == Zone.PRAYER:
                    self.break_card(uid, reason="Risoluzione Impulso")
            elif definition.prayer_type == PrayerType.ECHO:
                self.use_echo(uid, player)
            elif definition.prayer_type == PrayerType.BOND:
                self.trigger_legame_played(player)
                if bond_eye_before is not None and target_uid is not None:
                    self._record_eye_support(
                        player,
                        target_uid,
                        self.eye(target_uid) - bond_eye_before,
                    )
            elif definition.prayer_type == PrayerType.SIGIL:
                if definition.id == 60:
                    self.declare_sigil_form(uid, player)
            elif definition.prayer_type == PrayerType.GLYPH:
                pass
        if self.is_thunder_sand and calata:
            self.trigger_thunder_sand_card_played(uid, player, mode)
        self.check_seal_states()
        return True

    def move_to_void_without_break(self, uid: int, reason: str) -> None:
        card = self.cards[uid]
        self.remove_mark(uid, "la carta Marchiata lascia il campo")
        if card.zone == Zone.MALEDICTION:
            attached = self.attached_prayer(uid)
            if attached is not None:
                self.break_card(attached, reason=f"La Maledizione ospite lascia il campo: {reason}")
        self._remove_from_zone_list(uid)
        self.reset_card_outside_field(uid, Zone.VOID, None)
        self.void.append(uid)
        self.emit(f"{self.definition(uid).name} va nel Vuoto senza essere Spezzata ({reason}).")
        self.check_seal_states()

    def leave_field(
        self,
        uid: int,
        *,
        destination: Zone,
        destination_controller: int | None,
        reason: str,
    ) -> None:
        card = self.cards[uid]
        self.remove_mark(uid, "la carta Marchiata cambia zona")
        if card.zone == Zone.MALEDICTION:
            attached = self.attached_prayer(uid)
            if attached is not None:
                self.break_card(attached, reason=f"La Maledizione ospite cambia zona: {reason}")
        self._remove_from_zone_list(uid)
        self.reset_card_outside_field(uid, destination, destination_controller)
        if destination == Zone.HAND and destination_controller is not None:
            self.players[destination_controller].hand.append(uid)
        elif destination == Zone.DECK:
            self.deck.append(uid)
            self.rng.shuffle(self.deck)
        elif destination == Zone.VOID:
            self.void.append(uid)
        self.emit(f"{self.definition(uid).name} lascia il campo ({reason}).")
        self.check_seal_states()

    def return_to_deck(self, uid: int, reason: str) -> None:
        card = self.cards[uid]
        self.remove_mark(uid, "la carta Marchiata torna nel Mazzo")
        if card.zone == Zone.MALEDICTION:
            attached = self.attached_prayer(uid)
            if attached is not None:
                self.break_card(attached, reason=f"La Maledizione ospite torna nel Mazzo: {reason}")
        self._remove_from_zone_list(uid)
        self.reset_card_outside_field(uid, Zone.DECK, None)
        self.deck.append(uid)
        self.rng.shuffle(self.deck)
        self.emit(f"{self.definition(uid).name} torna in un punto casuale del Mazzo ({reason}).")
        self.check_seal_states()

    def add_modifier(
        self,
        kind: str,
        controller: int,
        *,
        source_uid: int | None = None,
        target_uid: int | None = None,
        value: int | str | None = None,
        reference_uid: int | None = None,
        starts_turn: int | None = None,
        expires_after_turn: int | None = None,
    ) -> None:
        self.modifiers.append(
            Modifier(
                sequence=self.next_sequence(),
                kind=kind,
                controller=controller,
                source_uid=source_uid,
                target_uid=target_uid,
                value=value,
                reference_uid=reference_uid,
                starts_turn=self.turn_number if starts_turn is None else starts_turn,
                expires_after_turn=self.turn_number if expires_after_turn is None else expires_after_turn,
            )
        )

    def _record_eye_support(self, player: int, target_uid: int, gain: int) -> None:
        """Registra solo veri potenziamenti su una propria Maledizione."""
        card = self.cards[target_uid]
        if gain <= 0 or card.zone != Zone.MALEDICTION or card.controller != player:
            return
        self.telemetry.own_eye_buffs[player] += 1
        if self.karma(target_uid) >= 3 and self.eye(target_uid) <= 4:
            self.telemetry.high_karma_eye_buffs[player] += 1

    def _record_eye_debuff(self, player: int, target_uid: int) -> None:
        card = self.cards[target_uid]
        if card.zone == Zone.MALEDICTION and card.controller == 1 - player:
            self.telemetry.enemy_eye_debuffs[player] += 1

    # ------------------------------------------------------------------
    # Corruption, breaking, Bless and combat
    # ------------------------------------------------------------------
    def corrupt_card(self, uid: int, source_player: int | None = None, reason: str = "effetto") -> bool:
        card = self.cards[uid]
        if card.zone != Zone.MALEDICTION or card.corrupted:
            return False
        card.corrupted = True
        card.corrupted_turn = self.turn_number
        self.emit(f"{self.definition(uid).name} si Corrompe ({reason}).")
        controller = card.controller
        if source_player is not None:
            self.telemetry.record_corruption(source_player, controller)
        if controller is not None and self.has_ability(uid, "barriera"):
            self.add_modifier("cannot_be_attacked", controller, source_uid=uid, target_uid=uid)
            self.telemetry.record_ability(controller, "Barriera")
            self.emit(f"Barriera protegge {self.definition(uid).name} fino alla fine del turno.")
        if (
            not self.is_thunder_sand
            and controller is not None
            and self.definition(uid).id == 62
            and not self.is_suppressed(uid)
            and self.void
        ):
            chosen = self.bots[controller].choose_card(self, controller, self.void, "take")
            if chosen is not None:
                self.take_to_hand(chosen, controller, "Pozza di Luce Oscura")
        if self.is_thunder_sand and controller is not None and not self.is_suppressed(uid):
            definition_id = self.definition(uid).id
            if definition_id == 12:
                candidates = [card_uid for card_uid in self.void if "Tuono" in self.forms(card_uid)]
                chosen = self._choose_target(controller, candidates, "take", uid)
                if chosen is not None:
                    self.take_to_hand(chosen, controller, "Nido Dei Draghi")
            elif definition_id == 30:
                candidates = [card_uid for card_uid in self.void if "Sabbia" in self.forms(card_uid)]
                chosen = self._choose_target(controller, candidates, "play", uid)
                if chosen is not None:
                    self.play_generated_card(chosen, controller, calata=False)
            elif definition_id == 35:
                candidates = [
                    target
                    for target in self.all_maledictions()
                    if target != uid and self.cards[target].corrupted
                ]
                chosen = self._choose_target(controller, candidates, "purify_any", uid)
                if chosen is not None:
                    self.purify_card(chosen, "Deserto Perla")
            elif definition_id == 36:
                candidates = [
                    card_uid
                    for card_uid in self.players[controller].hand
                    if self.can_play_malediction(controller, card_uid)
                    and not self.form_is_blocked(controller, card_uid, calata=True)
                ]
                chosen = self._choose_target(controller, candidates, "play", uid)
                if chosen is not None:
                    self.play_generated_card(
                        chosen,
                        controller,
                        forced_mode="Maledizione",
                        calata=True,
                    )
            elif definition_id == 37:
                self.charge_from_deck(controller, 2, "Deserto Zaffiro")
            elif definition_id in {61, 62}:
                candidates = [
                    card_uid
                    for card_uid in self.deck
                    if self.definition(card_uid).prayer_type == PrayerType.GLYPH
                ]
                chosen = self._choose_target(controller, candidates, "take", uid)
                if chosen is not None:
                    self.deck.remove(chosen)
                    self.reset_card_outside_field(chosen, Zone.HAND, controller)
                    self.players[controller].hand.append(chosen)
                    self.rng.shuffle(self.deck)
                    self.emit(
                        f"Il Giocatore {controller + 1} prende un Glifo dal Mazzo e rimescola."
                    )

            if "Sabbia" in self.forms(uid):
                for sigil in list(self.players[controller].prayers):
                    if self.definition(sigil).id != 30 or not self.sigil_is_active(sigil):
                        continue
                    candidates = [
                        card_uid for card_uid in self.void if "Sabbia" in self.forms(card_uid)
                    ]
                    chosen = self._choose_target(controller, candidates, "take", sigil)
                    if chosen is not None:
                        self.take_to_hand(chosen, controller, "Fonte della Sabbia")
        self.check_seal_states()
        return True

    def purify_card(self, uid: int, reason: str) -> bool:
        card = self.cards[uid]
        if card.zone != Zone.MALEDICTION or not card.corrupted:
            return False
        card.corrupted = False
        card.corrupted_turn = -1
        self.emit(f"{self.definition(uid).name} viene purificata ({reason}).")
        self.check_seal_states()
        return True

    def _on_spezzata(
        self,
        uid: int,
        controller: int,
        attached_before_leaving: int | None = None,
    ) -> set[int]:
        """Risoluzione prima del movimento. Restituisce Legami salvate/ricollegate."""
        saved_prayers: set[int] = set()
        card = self.cards[uid]
        definition_id = self.definition(uid).id
        if self.is_thunder_sand:
            if card.zone == Zone.MALEDICTION and not self.is_suppressed(uid):
                if definition_id == 1:
                    candidates = [
                        card_uid
                        for card_uid in self.players[controller].hand
                        if "Tuono" in self.forms(card_uid)
                    ]
                    chosen = self._choose_target(controller, candidates, "play", uid)
                    if chosen is not None:
                        self.play_generated_card(
                            chosen,
                            controller,
                            forced_mode="Maledizione",
                            calata=True,
                        )
                elif definition_id == 28:
                    candidates = [card_uid for card_uid in self.void if "Tuono" in self.forms(card_uid)]
                    chosen = self._choose_target(controller, candidates, "play", uid)
                    if chosen is not None:
                        self.play_generated_card(
                            chosen,
                            controller,
                            forced_mode="Maledizione",
                            calata=False,
                        )
                elif definition_id == 33:
                    candidates = [
                        card_uid
                        for card_uid in self.deck
                        if self.original_eye(card_uid) <= 5
                    ]
                    chosen = self._choose_target(controller, candidates, "play", uid)
                    if chosen is not None:
                        self.deck.remove(chosen)
                        self.play_generated_card(
                            chosen,
                            controller,
                            forced_mode="Maledizione",
                            calata=False,
                        )
                        self.rng.shuffle(self.deck)
            return saved_prayers
        if card.zone == Zone.MALEDICTION and not self.is_suppressed(uid):
            if definition_id in {29, 58}:
                candidates = list(self.players[controller].hand)
                chosen = self.bots[controller].choose_card(self, controller, candidates, "play")
                if chosen is not None:
                    self.play_card(chosen, controller, "Maledizione", calata=True)
            elif definition_id == 35:
                candidates = [target for target in self.all_maledictions() if not self.cards[target].corrupted]
                chosen = self.bots[controller].choose_card(self, controller, candidates, "debuff")
                if chosen is not None:
                    self.corrupt_card(chosen, controller, "Sussurro Fatale SPEZZATA")
            elif definition_id == 54:
                candidates = list(reversed(self.void[-3:]))
                chosen = self.bots[controller].choose_card(self, controller, candidates, "play")
                if chosen is not None:
                    self.play_generated_card(chosen, controller)

            # Il Legame viene memorizzato prima che l'ospite lasci la lista del
            # Campo. Questo rende stabile SPEZZATA anche durante catene di
            # movimento, controllo o scelte interattive rigiocate dal client.
            attached = attached_before_leaving
            if attached is None:
                attached = self.attached_effect_active(uid)
            if attached is not None and self.definition(attached).id in {13, 48}:
                prayer_controller = self.cards[attached].controller
                effect_player = controller if prayer_controller is None else prayer_controller
                candidates = [
                    target for target in self.players[effect_player].maledictions
                    if target != uid and self.original_eye(target) < self.original_eye(uid)
                ]
                target = self.bots[effect_player].choose_card(
                    self,
                    effect_player,
                    candidates,
                    "attach_benefit",
                    source_uid=attached,
                )
                if target is not None:
                    existing = self.attached_prayer(target)
                    if existing is not None and existing != attached:
                        self.move_to_void_without_break(existing, "Limite Legame durante ricollegamento")
                    self.cards[attached].attached_to = target
                    saved_prayers.add(attached)
                    self.emit(f"{self.definition(attached).name} si ricollega a {self.definition(target).name}.")
        return saved_prayers

    def break_card(
        self,
        uid: int,
        *,
        reason: str,
        offer_to: int | None = None,
        charge_to: int | None = None,
    ) -> bool:
        card = self.cards[uid]
        if card.zone not in {Zone.MALEDICTION, Zone.PRAYER}:
            return False
        controller = card.controller
        if controller is None:
            return False
        if (
            self.is_thunder_sand
            and card.zone == Zone.PRAYER
            and self.definition(uid).prayer_type == PrayerType.GLYPH
            and self.players[controller].charges
        ):
            chooser = getattr(self.bots[controller], "should_prevent_glyph_break", None)
            should_prevent = bool(chooser(self, controller, uid, reason)) if callable(chooser) else True
            if should_prevent and self.spend_charges(
                controller,
                1,
                f"protezione di {self.definition(uid).name}",
                chooser=controller,
            ):
                self.telemetry.record_ability(controller, "Protezione Glifo")
                self.emit(
                    f"{self.definition(uid).name} evita di Spezzarsi spendendo 1 Carica."
                )
                return False
        self.emit(f"{self.definition(uid).name} si Spezza ({reason}).")

        attached_before_leaving = (
            self.attached_effect_active(uid)
            if card.zone == Zone.MALEDICTION
            else None
        )

        # La carta ha gia' lasciato il Campo quando risolve SPEZZATA, ma non e'
        # ancora nel Vuoto. In questo modo non occupa un posto nei Limiti e non
        # viene vista da effetti che contano le carte sul Campo.
        self.remove_mark(uid, "la carta Marchiata lascia il campo")
        self._remove_from_zone_list(uid)
        saved = self._on_spezzata(uid, controller, attached_before_leaving)
        if card.zone == Zone.MALEDICTION:
            attached = self.attached_prayer(uid)
            if attached is not None and attached not in saved:
                self.break_card(attached, reason=f"La Maledizione ospite {self.definition(uid).name} lascia il campo")
        if self.is_thunder_sand and offer_to is not None:
            if self.definition(uid).id == 54 and not self.is_suppressed(uid):
                self.emit("Sabbie Senza Tempo non può essere Offerta.")
                offer_to = None
            elif self.definition(uid).id == 41 and offer_to != controller and not self.is_suppressed(uid):
                if not self.spend_charges(
                    offer_to,
                    1,
                    "offrire Dedalo Emerso",
                    chooser=offer_to,
                ):
                    self.emit("Dedalo Emerso non viene Offerta: manca la Carica richiesta.")
                    offer_to = None
        if charge_to is not None:
            self.charge_card(uid, charge_to, reason)
        elif offer_to is not None:
            self.reset_card_outside_field(uid, Zone.ALTAR, offer_to)
            self.players[offer_to].altar.append(uid)
            self.telemetry.record_offer(offer_to)
            self.emit(f"{self.definition(uid).name} viene Offerta all'Altare del Giocatore {offer_to + 1}.")
            if len(self.players[offer_to].altar) >= 5:
                self.trigger_final_rounds(offer_to, "quinta carta nell'Altare")
        else:
            self.reset_card_outside_field(uid, Zone.VOID, None)
            self.void.append(uid)
            self.emit(f"{self.definition(uid).name} raggiunge il Vuoto.")
        self.check_seal_states()
        return True

    def bless_card(
        self,
        uid: int,
        controller: int,
        *,
        karma_override: int | None = None,
        definition_id_override: int | None = None,
        offered_was_marked: bool = False,
    ) -> None:
        definition_id = definition_id_override or self.definition(uid).id
        points = self.karma(uid) if karma_override is None and self.cards[uid].zone == Zone.MALEDICTION else max(0, karma_override or 0)
        self.players[controller].score += points
        self.telemetry.record_bless(controller, definition_id, points)
        if uid in self.cards:
            self.cards[uid].blessed_turn = self.turn_number
        self.emit(f"{self.definitions[definition_id].name} Blessa: Giocatore {controller + 1} guadagna {points} PV.")

        if self.is_thunder_sand:
            if (
                definition_id == 3
                and offered_was_marked
                and controller == self.active_player
                and uid in self.cards
                and self.cards[uid].zone == Zone.MALEDICTION
                and not self.is_suppressed(uid)
            ):
                self.players[controller].actions += 1
                self.emit("Drass fa guadagnare 1 Azione al giocatore attivo.")
            for sigil in list(self.players[controller].prayers):
                if self.definition(sigil).id == 52 and self.sigil_is_active(sigil):
                    self.close_sigil(sigil, "hai Blessato")
            return

        if definition_id == 34 and controller == self.active_player and self.cards[uid].zone == Zone.MALEDICTION and not self.is_suppressed(uid):
            self.players[controller].actions += 1
            self.emit("Lenora fa guadagnare 1 Azione al giocatore attivo.")
        if definition_id == 48 and self.cards[uid].zone != Zone.ALTAR:
            # L'effetto viene letto dall'ultima informazione valida della carta.
            self.return_to_deck(uid, "Costellazione Errante ha Blessato")
            return
        if self.cards[uid].zone == Zone.MALEDICTION and not self.is_suppressed(uid):
            attached = self.attached_effect_active(uid)
            if attached is not None and self.definition(attached).id in {2, 31}:
                self.break_card(attached, reason="La Maledizione collegata ha Blessato")

    def _win_condition(
        self,
        uid: int,
        opponent_uid: int,
        *,
        own_combat_eye: int,
        opponent_combat_eye: int,
    ) -> tuple[bool, bool]:
        if self.is_suppressed(uid):
            return False, False
        definition_id = self.definition(uid).id
        opponent = self.cards[opponent_uid]
        if self.is_thunder_sand:
            opponent_id = self.definition(opponent_uid).id
            if definition_id in {24, 50} and not opponent.corrupted:
                return True, False
            if (
                definition_id == 29
                and self.cards[uid].controller == self.active_player
                and opponent.corrupted
                and opponent.corrupted_turn >= 0
                and opponent.corrupted_turn < self.turn_number
            ):
                return True, False
            if definition_id == 45:
                if own_combat_eye < opponent_combat_eye:
                    return True, False
            if opponent_id == 10 and own_combat_eye <= 3:
                return True, False
            if opponent_id == 45 and own_combat_eye < opponent_combat_eye:
                return True, False
            if any(
                modifier.kind == "wins_marked"
                and modifier.target_uid == uid
                and self.is_marked(opponent_uid)
                for modifier in self.active_modifiers()
            ):
                return True, False
            return False, False
        if definition_id == 1 and "Luce" in self.forms(opponent_uid):
            return True, True
        if definition_id == 30 and "Ombra" in self.forms(opponent_uid):
            return True, True
        if definition_id in {7, 36} and opponent_combat_eye >= 6:
            return True, False
        if definition_id == 10 and self.karma(opponent_uid) <= 2:
            return True, False
        if definition_id == 33 and "Ombra" in self.forms(opponent_uid) and opponent.corrupted:
            return True, False
        if definition_id == 40 and opponent_combat_eye != self.original_eye(opponent_uid):
            return True, False
        return False, False

    def predict_combat(self, attacker_uid: int, defender_uid: int) -> str:
        if self.has_ability(attacker_uid, "fato") or self.has_ability(defender_uid, "fato"):
            return "fato"
        attacker_eye = self.combat_eye(attacker_uid, defender_uid)
        defender_eye = self.projected_defender_eye(attacker_uid, defender_uid)
        attacker_win, attacker_always = self._win_condition(
            attacker_uid,
            defender_uid,
            own_combat_eye=attacker_eye,
            opponent_combat_eye=defender_eye,
        )
        defender_win, defender_always = self._win_condition(
            defender_uid,
            attacker_uid,
            own_combat_eye=defender_eye,
            opponent_combat_eye=attacker_eye,
        )
        if attacker_always or defender_always:
            if attacker_always and defender_always:
                return "tie"
            return "attacker_win" if attacker_always else "defender_win"
        if attacker_win or defender_win:
            if attacker_win and defender_win:
                return "tie"
            return "attacker_win" if attacker_win else "defender_win"
        if attacker_eye == defender_eye:
            attacker_ties_win = (
                not self.is_thunder_sand
                and self.definition(attacker_uid).id == 16
                and not self.is_suppressed(attacker_uid)
            )
            defender_ties_win = (
                not self.is_thunder_sand
                and self.definition(defender_uid).id == 16
                and not self.is_suppressed(defender_uid)
            )
            if attacker_ties_win != defender_ties_win:
                return "attacker_win" if attacker_ties_win else "defender_win"
            return "tie"
        return "attacker_win" if attacker_eye > defender_eye else "defender_win"

    def simulate_combat_silently(self, attacker_uid: int, defender_uid: int) -> dict[str, Any]:
        """Prevede lo scontro senza modificare il tavolo o produrre eventi.

        La previsione usa i valori continuamente aggiornati del motore, incluse
        forme modificate, Legami, Rivalita', effetti "vince" e modificatori che
        reagiscono alla dichiarazione di un attacco.
        """
        # Vetro Smerigliato Carica appena viene attaccato. La Carica puo'
        # cambiare Occhio e altri effetti continui (per esempio il malus di
        # un Marchio sotto un Glifo), quindi la legalita' dell'attacco va
        # calcolata sullo stato immediatamente successivo alla dichiarazione.
        # La copia evita che la sola anteprima tocchi mazzo, Cariche o replay.
        preview_engine = self
        defender = self.cards[defender_uid]
        if (
            self.is_thunder_sand
            and self.definition(defender_uid).id == 57
            and not self.is_suppressed(defender_uid)
            and defender.controller is not None
        ):
            preview_engine = copy.deepcopy(self)
            preview_engine.record_replay = False
            preview_engine.charge_from_deck(defender.controller, 1, "Vetro Smerigliato")

        attacker_eye = preview_engine.combat_eye(attacker_uid, defender_uid)
        defender_eye = preview_engine.projected_defender_eye(attacker_uid, defender_uid)
        attacker_forms = sorted(preview_engine.forms(attacker_uid))
        defender_forms = sorted(preview_engine.forms(defender_uid))
        attacker_has_rivalry = preview_engine.has_ability(attacker_uid, "rivalita")
        defender_has_rivalry = preview_engine.has_ability(defender_uid, "rivalita")
        return {
            "attacker_uid": attacker_uid,
            "target_uid": defender_uid,
            "attacker_eye": attacker_eye,
            "defender_eye": defender_eye,
            "attacker_forms": attacker_forms,
            "defender_forms": defender_forms,
            "attacker_rivalry": attacker_has_rivalry,
            "attacker_rivalry_applied": attacker_has_rivalry and attacker_eye > preview_engine.eye(attacker_uid),
            "defender_rivalry": defender_has_rivalry,
            "defender_rivalry_applied": defender_has_rivalry and defender_eye > preview_engine.eye(defender_uid),
            "outcome": preview_engine.predict_combat(attacker_uid, defender_uid),
        }

    def attack_target_previews(
        self,
        player: int,
        attacker_uid: int,
        *,
        ignore_action_cost: bool = False,
    ) -> list[dict[str, Any]]:
        """Restituisce tutti i bersagli controllati in silenzio, validi e non."""
        if player != self.active_player:
            return []
        if attacker_uid not in self.players[player].maledictions:
            return []
        attacker = self.cards[attacker_uid]
        if (
            attacker.stasis
            or self.cannot_attack(attacker_uid)
            or (
                attacker.attacked_turn == self.turn_number
                and self.extra_attacks_remaining(attacker_uid) <= 0
            )
        ):
            return []

        opponent = 1 - player
        eclissi = self.eclissi_targets(opponent)
        targets = eclissi if eclissi else list(self.players[opponent].maledictions)
        if self.is_thunder_sand:
            forced_targets = [
                int(modifier.value)
                for modifier in self.active_modifiers("must_attack_uid")
                if modifier.target_uid == attacker_uid and modifier.value is not None
            ]
            forced_targets = [uid for uid in forced_targets if uid in targets]
            if forced_targets:
                targets = forced_targets
        previews: list[dict[str, Any]] = []
        for target_uid in targets:
            if self.cannot_be_attacked(target_uid, attacker_uid):
                continue
            preview = self.simulate_combat_silently(attacker_uid, target_uid)
            outcome = str(preview["outcome"])
            allowed = not attacker.corrupted or outcome in {"attacker_win", "fato"}
            reason = "Bersaglio valido dopo la previsione dello scontro."
            if (
                self.is_thunder_sand
                and self.definition(attacker_uid).id == 40
                and not self.is_suppressed(attacker_uid)
                and not self.cards[target_uid].corrupted
            ):
                allowed = False
                reason = "Quiete Ambita può attaccare soltanto Maledizioni Corrotte."
            elif (
                self.is_thunder_sand
                and self.definition(target_uid).id in {26, 46}
                and not self.is_suppressed(target_uid)
                and not self.players[player].charges
            ):
                allowed = False
                reason = f"Per attaccare {self.definition(target_uid).name} devi spendere 1 Carica."
            elif (
                not ignore_action_cost
                and self.attack_cost(attacker_uid, target_uid) > self.players[player].actions
            ):
                allowed = False
                reason = "Non hai abbastanza Azioni per dichiarare questo attacco."
            preview["allowed"] = allowed
            if allowed:
                preview["reason"] = reason
            elif reason != "Bersaglio valido dopo la previsione dello scontro.":
                preview["reason"] = reason
            elif outcome == "tie":
                reason = (
                    f"Previsione: {preview['attacker_eye']} contro {preview['defender_eye']}. "
                    "Una Maledizione Corrotta non puo' attaccare in un pareggio previsto."
                )
                if preview["attacker_rivalry"] and not preview["attacker_rivalry_applied"]:
                    attacker_form = "/".join(preview["attacker_forms"])
                    defender_form = "/".join(preview["defender_forms"])
                    reason += (
                        f" Rivalita' non si applica: le forme effettive sono "
                        f"{attacker_form} e {defender_form}."
                    )
                preview["reason"] = reason
            elif self.is_suppressed(attacker_uid):
                preview["reason"] = (
                    f"L'effetto di {self.definition(attacker_uid).name} è annullato: "
                    f"la previsione è {preview['attacker_eye']} contro {preview['defender_eye']} "
                    "e la Maledizione Corrotta perderebbe lo scontro."
                )
            else:
                preview["reason"] = (
                    f"Previsione: {preview['attacker_eye']} contro {preview['defender_eye']}. "
                    "La Maledizione Corrotta perderebbe lo scontro."
                )
            previews.append(preview)
        return previews

    def trigger_attacked_effects(self, attacker_uid: int, defender_uid: int) -> None:
        defender = self.cards[defender_uid]
        controller = defender.controller
        if controller is None:
            return
        definition_id = self.definition(defender_uid).id
        if self.is_thunder_sand and definition_id == 57 and not self.is_suppressed(defender_uid):
            self.charge_from_deck(controller, 1, "Vetro Smerigliato")
        if (
            not self.is_thunder_sand
            and definition_id == 5
            and not self.is_suppressed(defender_uid)
        ):
            attacker_controller = self.cards[attacker_uid].controller
            if attacker_controller is not None and self.players[attacker_controller].hand:
                chosen = self.bots[attacker_controller].choose_card(self, attacker_controller, self.players[attacker_controller].hand, "discard_own")
                if chosen is not None:
                    self.discard_from_hand(chosen, attacker_controller, "Battito d'Ali")
        attached = self.attached_effect_active(defender_uid)
        if (
            not self.is_thunder_sand
            and attached is not None
            and self.definition(attached).id == 53
            and self.all_prayers()
        ):
            chosen = self.bots[controller].choose_card(self, controller, self.all_prayers(), "break")
            if chosen is not None:
                self.break_card(chosen, reason="Vessillo del Presagio")

        attacker_forms = self.forms(attacker_uid)
        for modifier in list(self.active_modifiers("watch_attacked")):
            if modifier.target_uid != defender_uid:
                continue
            watched_form, amount = str(modifier.value).split(":")
            if watched_form in attacker_forms:
                self.add_modifier("target_eye_add", modifier.controller, source_uid=modifier.source_uid, target_uid=defender_uid, value=int(amount))
                self.emit(f"{self.definition(defender_uid).name} riceve {amount} Occhio perché è stata attaccata da una {watched_form}.")

    def resolve_combat(self, attacker_uid: int, defender_uid: int) -> None:
        attacker = self.cards[attacker_uid]
        defender = self.cards[defender_uid]
        attacker_controller = attacker.controller
        defender_controller = defender.controller
        if attacker_controller is None or defender_controller is None:
            return
        marks_at_start = {
            attacker_uid: self.mark_for(attacker_uid),
            defender_uid: self.mark_for(defender_uid),
        }
        attacker.attacked_turn = self.turn_number
        self.telemetry.combats += 1
        self.trigger_attacked_effects(attacker_uid, defender_uid)
        if attacker.zone != Zone.MALEDICTION or defender.zone != Zone.MALEDICTION:
            self.emit("Lo scontro termina perché una delle due Maledizioni ha lasciato il campo.")
            self._expire_combat_marks(marks_at_start)
            return

        attacker_eye = self.combat_eye(attacker_uid, defender_uid)
        defender_eye = self.projected_defender_eye(attacker_uid, defender_uid)
        combatants = (
            (attacker_uid, defender_uid, attacker_eye, defender_eye),
            (defender_uid, attacker_uid, defender_eye, attacker_eye),
        )
        for current, other, current_eye, other_eye in combatants:
            if self.has_ability(current, "rivalita"):
                own_forms = self.forms(current)
                other_forms = self.forms(other)
                if other_forms != {"Luce", "Ombra"} and own_forms.isdisjoint(other_forms):
                    controller = self.cards[current].controller
                    if controller is not None:
                        self.telemetry.record_ability(controller, "Rivalità")
            wins, always = self._win_condition(
                current,
                other,
                own_combat_eye=current_eye,
                opponent_combat_eye=other_eye,
            )
            if wins:
                controller = self.cards[current].controller
                if controller is not None:
                    self.telemetry.record_ability(controller, "Vince sempre" if always else "Vince")

        outcome = self.predict_combat(attacker_uid, defender_uid)
        if outcome == "fato":
            fate_uid = attacker_uid if self.has_ability(attacker_uid, "fato") else defender_uid
            fate_controller = self.cards[fate_uid].controller
            roll = self.rng.randint(1, 6)
            guessed_even = self.bots[fate_controller].choose_fate(
                self,
                fate_controller,
                fate_uid,
            ) if fate_controller is not None else self.rng.choice([True, False])
            fate_wins = (roll % 2 == 0) == guessed_even
            if fate_uid == attacker_uid:
                outcome = "attacker_win" if fate_wins else "defender_win"
            else:
                outcome = "defender_win" if fate_wins else "attacker_win"
            if fate_controller is not None:
                self.telemetry.record_ability(fate_controller, "Fato")
            choice = "Pari" if guessed_even else "Dispari"
            self.fate_event_counter += 1
            self.last_fate = {
                "event_id": self.fate_event_counter,
                "card_uid": fate_uid,
                "controller": fate_controller if fate_controller is not None else -1,
                "choice": choice,
                "roll": roll,
                "won": fate_wins,
            }
            self.emit(f"Fato sceglie {choice}; il dado mostra {roll}.")

        self.emit(f"Scontro: {self.definition(attacker_uid).name} ({attacker_eye}) contro {self.definition(defender_uid).name} ({defender_eye}); esito {outcome}.")

        attacker_loses = outcome in {"defender_win", "tie"}
        defender_loses = outcome in {"attacker_win", "tie"}
        defender_was_pure = not defender.corrupted
        attacker_was_pure = not attacker.corrupted
        attacker_karma = self.combat_karma(attacker_uid, defender_uid)
        attacker_definition_id = self.definition(attacker_uid).id
        defender_was_marked = self.is_marked(defender_uid)

        if defender_was_pure:
            self.corrupt_card(defender_uid, attacker_controller, "è stata attaccata")
            if self.has_ability(attacker_uid, "impatto"):
                self.telemetry.record_ability(attacker_controller, "Impatto")
                self.bless_card(attacker_uid, attacker_controller, karma_override=attacker_karma)
        if attacker_loses and attacker_was_pure:
            self.corrupt_card(attacker_uid, defender_controller, "ha perso lo scontro")

        broken: list[tuple[int, bool]] = []
        if attacker_loses and not attacker_was_pure:
            broken.append((attacker_uid, False))
        if defender_loses and not defender_was_pure:
            broken.append((defender_uid, True))
        broken.sort(key=lambda item: 0 if self.cards[item[0]].controller == self.active_player else 1)

        defender_offered = False
        for uid, is_defender in broken:
            if self.cards[uid].zone != Zone.MALEDICTION:
                continue
            offer_to = None
            if is_defender:
                should_offer = self.bots[attacker_controller].choose_offer(self, attacker_controller, uid)
                if should_offer:
                    offer_to = attacker_controller
            self.break_card(uid, reason="perdita dello scontro", offer_to=offer_to)
            if (
                is_defender
                and self.cards[uid].zone == Zone.ALTAR
                and self.cards[uid].controller == attacker_controller
            ):
                defender_offered = True

        if defender_offered:
            offer_karma = (
                self.combat_karma(attacker_uid, defender_uid)
                if self.cards[attacker_uid].zone == Zone.MALEDICTION
                else attacker_karma
            )
            self.bless_card(
                attacker_uid,
                attacker_controller,
                karma_override=offer_karma,
                definition_id_override=attacker_definition_id,
                offered_was_marked=defender_was_marked,
            )
        if self.is_thunder_sand:
            self.resolve_after_attack(
                attacker_uid,
                defender_uid,
                attacker_controller,
                attacker_eye,
                defender_eye,
                attacker_definition_id,
            )
            self._expire_combat_marks(marks_at_start)

    def resolve_after_attack(
        self,
        attacker_uid: int,
        defender_uid: int | None,
        player: int,
        attacker_eye: int,
        defender_eye: int,
        definition_id: int,
    ) -> None:
        if not self.is_thunder_sand:
            return
        if self.is_suppressed(attacker_uid):
            return
        if definition_id == 6:
            self.charge_from_deck(player, 1, "Occhi Folgoranti ha attaccato")
        elif (
            definition_id == 23
            and attacker_uid in self.cards
            and self.cards[attacker_uid].zone == Zone.MALEDICTION
            and not self.is_suppressed(attacker_uid)
        ):
            charge_owner = 1 - player
            candidates = [
                uid for uid in self.all_maledictions()
                if not self.is_marked(uid)
            ]
            target = self._choose_target(
                player,
                candidates if self.players[charge_owner].charges else [],
                "mark_any",
                attacker_uid,
            )
            if target is not None:
                self.mark_with_charge(
                    target,
                    charge_owner,
                    "Voce Tonante ha attaccato",
                )

        if definition_id in {16, 51} and defender_uid is not None:
            difference = abs(attacker_eye - defender_eye)
            candidates = [
                uid
                for uid in self.players[1 - player].maledictions
                if not self.cards[uid].corrupted and self.eye(uid) <= difference
            ]
            target = self._choose_target(
                player,
                candidates,
                "optional_corrupt",
                attacker_uid,
            )
            if target is not None:
                self.corrupt_card(target, player, "Colosso")

        if definition_id == 56:
            sigils = [
                uid
                for uid in self.players[player].prayers
                if self.definition(uid).prayer_type == PrayerType.SIGIL
                and not self.cards[uid].seal_open
            ]
            if sigils and self.players[player].charges:
                pay = self._choose_option(
                    player,
                    [True, False],
                    "open_sigil_after_attack",
                    attacker_uid,
                )
                if pay is True and self.spend_charges(
                    player,
                    1,
                    "aprire un tuo Sigillo dopo l'attacco di Cavalcare Sabbia",
                    chooser=player,
                ):
                    target = self._choose_target(
                        player,
                        [uid for uid in sigils if uid in self.players[player].prayers],
                        "open_own_sigil",
                        attacker_uid,
                    )
                    if target is not None:
                        self.open_sigil(target, "Cavalcare Sabbia dopo l'attacco")

    def discard_from_hand(self, uid: int, player: int, reason: str) -> None:
        if uid not in self.players[player].hand:
            return
        self.players[player].hand.remove(uid)
        self.reset_card_outside_field(uid, Zone.VOID, None)
        self.void.append(uid)
        self.emit(f"Il Giocatore {player + 1} scarta {self.definition(uid).name} ({reason}).")

    def change_control_malediction(self, uid: int, new_controller: int) -> bool:
        card = self.cards[uid]
        if card.zone != Zone.MALEDICTION or card.controller == new_controller:
            return False
        if (
            self.is_thunder_sand
            and self.has_ability(uid, "cadenza")
            and any(self.has_ability(other, "cadenza") for other in self.players[new_controller].maledictions)
        ):
            return False
        while self.used_malediction_slots(new_controller) + self.malediction_weight(uid) > 4:
            removal = self._choose_limit_malediction(new_controller)
            if removal is None:
                return False
            self.move_to_void_without_break(removal, "Limite prima del cambio di controllo")
        attached = self.attached_prayer(uid)
        if attached is not None:
            self.break_card(attached, reason="La Maledizione cambia lato del campo")
        old_controller = card.controller
        self.players[old_controller].maledictions.remove(uid)
        self.players[new_controller].maledictions.append(uid)
        card.controller = new_controller
        card.stasis = True
        self.emit(f"Il Giocatore {new_controller + 1} prende il controllo di {self.definition(uid).name}; viene applicata Stasi.")
        self.check_seal_states()
        return True

    def change_control_prayer(self, uid: int, new_controller: int) -> bool:
        card = self.cards[uid]
        if card.zone != Zone.PRAYER or card.controller == new_controller:
            return False
        definition = self.definition(uid)
        if definition.prayer_type == PrayerType.ECHO:
            echoes = [
                prayer for prayer in self.players[new_controller].prayers
                if self.definition(prayer).prayer_type == PrayerType.ECHO
            ]
            if len(echoes) >= 2:
                removal = self._choose_limit_echo(new_controller)
                if removal is None:
                    return False
                self.move_to_void_without_break(removal, "Limite Eco prima del cambio di controllo")
        elif definition.prayer_type in {PrayerType.SIGIL, PrayerType.GLYPH}:
            existing = [
                prayer
                for prayer in self.players[new_controller].prayers
                if self.definition(prayer).prayer_type == definition.prayer_type
            ]
            if existing:
                removal = self._choose_limit_prayer(new_controller, definition.prayer_type)
                if removal is None:
                    return False
                self.move_to_void_without_break(
                    removal,
                    f"Limite {definition.prayer_type.value} prima del cambio di controllo",
                )
        old_controller = card.controller
        self.players[old_controller].prayers.remove(uid)
        self.players[new_controller].prayers.append(uid)
        card.controller = new_controller
        self.emit(f"Il Giocatore {new_controller + 1} prende il controllo della Preghiera {definition.name}.")
        self.check_seal_states()
        return True

    # ------------------------------------------------------------------
    # Card effects
    # ------------------------------------------------------------------
    def declare_sigil_form(self, uid: int, player: int) -> None:
        if not self.is_thunder_sand or self.definition(uid).id != 60:
            return
        chooser = getattr(self.bots[player], "choose_declared_form", None)
        if callable(chooser):
            chosen = chooser(self, player, uid, ["Tuono", "Sabbia"])
        else:
            chosen = "Tuono" if self.count_form_on_side(1 - player, "Tuono") >= self.count_form_on_side(1 - player, "Sabbia") else "Sabbia"
        if chosen not in {"Tuono", "Sabbia"}:
            chosen = "Tuono"
        self.cards[uid].declared_form = chosen
        self.emit(
            f"{self.definition(uid).name} dichiara la Forma {chosen}: "
            f"l'avversario non può Calare carte di quella Forma."
        )

    def trigger_thunder_sand_card_played(self, uid: int, player: int, mode: str) -> None:
        if (
            not self.is_thunder_sand
            or mode != "Maledizione"
            or "Tuono" not in self.forms(uid)
        ):
            return
        sigils = [
            prayer
            for prayer in self.players[player].prayers
            if self.definition(prayer).id == 3 and self.sigil_is_active(prayer)
        ]
        for sigil in sigils:
            candidates = [target for target in self.all_field_cards() if not self.is_marked(target)]
            target = self._choose_target(player, candidates, "mark", sigil)
            if target is None:
                continue
            self.ensure_deck(player, 1, "Drass, Prima Saetta")
            if not self.deck:
                continue
            marker = self.deck[-1]
            self.place_mark(target, marker, player, "Drass, Prima Saetta")

    def use_glyph(self, uid: int, player: int) -> None:
        card = self.cards[uid]
        if (
            not self.is_thunder_sand
            or card.zone != Zone.PRAYER
            or card.controller != player
            or self.definition(uid).prayer_type != PrayerType.GLYPH
            or self.is_suppressed(uid)
        ):
            return
        definition_id = self.definition(uid).id
        if definition_id in {61, 62} and card.glyph_used_turn == self.turn_number:
            return
        if not self.glyph_can_resolve(uid, player):
            return
        cost = self.glyph_cost(uid)
        if len(self.players[player].charges) < cost:
            return
        marking_glyph = definition_id in {6, 8, 12, 19, 25, 32, 38, 45}
        if (
            cost
            and not marking_glyph
            and not self.spend_charges(
                player,
                cost,
                f"usare il Glifo {self.definition(uid).name}",
                chooser=player,
            )
        ):
            return
        card.glyph_used_turn = self.turn_number
        self.telemetry.record_glyph_use(player)
        self.telemetry.record_ability(player, "Glifo")
        self.emit(f"Il Giocatore {player + 1} usa il Glifo {self.definition(uid).name}.")
        self.resolve_thunder_sand_glyph(uid, player)

    def resolve_thunder_sand_glyph(self, source_uid: int, player: int) -> None:
        definition_id = self.definition(source_uid).id
        opponent = 1 - player
        if definition_id in {8, 12, 19, 25, 32, 38, 45}:
            candidates = [target for target in self.all_field_cards() if not self.is_marked(target)]
            marker = self.choose_mark_charge(player, chooser=player) if candidates else None
            target = self._choose_target(player, candidates, "mark", source_uid) if marker is not None else None
            if target is not None and marker is not None:
                self.mark_with_charge(
                    target,
                    player,
                    self.definition(source_uid).name,
                    chooser=player,
                    marker_uid=marker,
                )
        elif definition_id == 6:
            candidates = [
                target
                for target in self.all_maledictions()
                if not self.is_marked(target)
            ]
            marker = self.choose_mark_charge(player, chooser=player) if candidates else None
            target = self._choose_target(player, candidates, "mark", source_uid) if marker is not None else None
            if target is not None and marker is not None and self.mark_with_charge(
                target,
                player,
                self.definition(source_uid).name,
                chooser=player,
                marker_uid=marker,
            ):
                if self.eye(target) < self.effective_charge_count(player):
                    self.corrupt_card(target, player, self.definition(source_uid).name)
        elif definition_id == 15 and self.void:
            self.play_generated_card(self.void[-1], player)
        elif definition_id == 18:
            target = self._choose_target(
                player,
                self.all_maledictions(),
                "grant_emblem_any",
                source_uid,
            )
            if target is not None:
                self.add_modifier(
                    "grant_emblem",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                )
        elif definition_id in {22, 42}:
            target = self._choose_target(
                player,
                [target for target in self.all_maledictions() if self.cards[target].corrupted],
                "purify_any",
                source_uid,
            )
            if target is not None:
                self.purify_card(target, self.definition(source_uid).name)
        elif definition_id == 21:
            target = self._choose_target(
                player,
                self.players[player].maledictions,
                "extra_attacks",
                source_uid,
            )
            if target is not None:
                for other in list(self.players[player].maledictions):
                    if other != target and not self.cards[other].corrupted:
                        self.break_card(other, reason="Ruota di Folgori")
                self.add_modifier(
                    "extra_attacks",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                    value=2,
                )
                self.add_modifier(
                    "free_attack",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                )
        elif definition_id == 44:
            target = self._choose_target(player, self.all_field_cards(), "suppress", source_uid)
            if target is not None:
                self.add_modifier(
                    "suppress_effect",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                )
        elif definition_id == 47:
            target = self._choose_target(player, self.all_maledictions(), "protect_any", source_uid)
            if target is not None:
                self.add_modifier(
                    "grant_screening",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                    starts_turn=self.turn_number + 1,
                    expires_after_turn=self.turn_number + 1,
                )
        elif definition_id == 53:
            first_candidates = [
                target
                for state in self.players
                if len(state.maledictions) >= 2
                for target in state.maledictions
            ]
            first = self._choose_target(player, first_candidates, "eye_reference_any", source_uid)
            if first is not None and self.cards[first].controller is not None:
                self.cards[source_uid].effect_target_uid = first
                same_side = [
                    target
                    for target in self.players[self.cards[first].controller].maledictions
                    if target != first
                ]
                second = self._choose_target(
                    player,
                    same_side,
                    "eye_reference_partner",
                    source_uid,
                )
                self.cards[source_uid].effect_target_uid = None
                if second is not None:
                    first_original = self.original_eye(first)
                    second_original = self.original_eye(second)
                    self.add_modifier(
                        "set_original_eye",
                        player,
                        source_uid=source_uid,
                        target_uid=first,
                        value=second_original,
                        expires_after_turn=self.turn_number + 1,
                    )
                    self.add_modifier(
                        "set_original_eye",
                        player,
                        source_uid=source_uid,
                        target_uid=second,
                        value=first_original,
                        expires_after_turn=self.turn_number + 1,
                    )
        elif definition_id in {61, 62}:
            candidates = [target for target in self.all_field_cards() if not self.is_marked(target)]
            marker = (
                self._choose_target(player, self.players[player].hand, "mark_from_hand", source_uid)
                if candidates and self.players[player].hand
                else None
            )
            target = self._choose_target(player, candidates, "mark", source_uid) if marker is not None else None
            if target is not None and marker is not None:
                self.place_mark(target, marker, player, self.definition(source_uid).name)

    def play_generated_card(
        self,
        uid: int,
        player: int,
        *,
        forced_mode: str | None = None,
        calata: bool = False,
    ) -> bool:
        modes = self.legal_modes_for_generated_play(uid, player, calata=calata)
        if forced_mode is not None:
            modes = [mode for mode in modes if mode == forced_mode]
        if not modes:
            return False
        mode = forced_mode or self.bots[player].choose_mode(self, player, uid, modes)
        target = None
        if mode == "Preghiera" and self.definition(uid).prayer_type == PrayerType.BOND:
            candidates = [
                candidate for candidate in self.all_maledictions()
                if not (self.definition(uid).id == 60 and self.forms(candidate) == {"Luce", "Ombra"})
            ]
            purpose = "attach_benefit"
            target = self.bots[player].choose_card(
                self,
                player,
                candidates,
                purpose,
                source_uid=uid,
            )
            if target is None:
                return False
        return self.play_card(uid, player, mode, target_uid=target, calata=calata)

    def resolve_calo(self, uid: int, player: int) -> None:
        if self.is_suppressed(uid):
            return
        definition_id = self.definition(uid).id
        opponent = 1 - player
        if self.is_thunder_sand:
            if definition_id == 1:
                candidates = [
                    card_uid
                    for card_uid in self.players[player].hand
                    if "Tuono" in self.forms(card_uid)
                ]
                chosen = self._choose_target(player, candidates, "play", uid)
                if chosen is not None:
                    self.play_generated_card(
                        chosen,
                        player,
                        forced_mode="Maledizione",
                        calata=True,
                    )
            elif definition_id == 4:
                candidates = [target for target in self.all_field_cards() if self.is_marked(target)]
                target = self._choose_target(player, candidates, "break", uid)
                if target is not None:
                    self.break_card(target, reason=self.definition(uid).name)
            elif definition_id == 11:
                if self.used_malediction_slots(opponent) > self.used_malediction_slots(player):
                    # "Subito" permette di attaccare nel turno del CALO;
                    # il solo costo zero lascerebbe la carta bloccata in Stasi.
                    self.cards[uid].stasis = False
                    self.add_modifier(
                        "free_attack",
                        player,
                        source_uid=uid,
                        target_uid=uid,
                    )
            elif definition_id == 18:
                target = self._choose_target(player, self.all_maledictions(), "buff_eye", uid)
                if target is not None:
                    self._record_eye_support(player, target, 1)
                    self.add_modifier("target_eye_add", player, source_uid=uid, target_uid=target, value=1)
                    self.add_modifier("target_karma_add", player, source_uid=uid, target_uid=target, value=1)
            elif definition_id == 19:
                target = self._choose_target(
                    player,
                    self.all_maledictions(),
                    "debuff_eye_any",
                    uid,
                )
                if target is not None:
                    self._record_eye_debuff(player, target)
                    self.add_modifier("target_eye_add", player, source_uid=uid, target_uid=target, value=-3)
            elif definition_id == 44:
                target = self._choose_target(
                    player,
                    self.players[player].maledictions,
                    "swap_stats",
                    uid,
                )
                if target is not None:
                    effective_eye = self.eye(target)
                    effective_karma = self.karma(target)
                    self.add_modifier(
                        "swap_eye_karma",
                        player,
                        source_uid=uid,
                        target_uid=target,
                        value=f"{effective_eye}:{effective_karma}",
                    )
            elif definition_id == 52:
                target = self._choose_target(
                    player,
                    self.all_maledictions(),
                    "must_attack_any",
                    uid,
                )
                if target is not None:
                    self.add_modifier(
                        "must_attack_uid",
                        player,
                        source_uid=uid,
                        target_uid=target,
                        value=uid,
                        starts_turn=self.turn_number + 1,
                        expires_after_turn=self.turn_number + 1,
                    )
            elif definition_id == 56:
                sigils = [
                    prayer
                    for prayer in self.all_prayers()
                    if self.definition(prayer).prayer_type == PrayerType.SIGIL
                ]
                target = self._choose_target(player, sigils, "sigil_state_required", uid)
                if target is not None:
                    if self.cards[target].seal_open:
                        self.close_sigil(target, "CALO di Cavalcare Sabbia")
                    else:
                        self.open_sigil(target, "CALO di Cavalcare Sabbia")
            self.check_seal_states()
            return
        if definition_id == 6:
            while len(self.players[opponent].maledictions) > len(self.players[player].maledictions):
                chosen = self.bots[opponent].choose_card(
                    self, opponent, self.players[opponent].maledictions, "sacrifice"
                )
                if chosen is None:
                    break
                self.break_card(chosen, reason="Tormenta degli Angeli")
        elif definition_id == 12 and self.players[opponent].hand:
            chosen = self.rng.choice(self.players[opponent].hand)
            self.discard_from_hand(chosen, opponent, "Pendolo Veggente")
        elif definition_id in {21, 59}:
            candidates = [
                target for target in self.players[player].maledictions
                if self.cards[target].corrupted
            ]
            if (
                self.players[player].hand
                and candidates
                and self.bots[player].should_pay_purification(
                    self,
                    player,
                    uid,
                    candidates,
                )
            ):
                discarded = self.bots[player].choose_card(
                    self,
                    player,
                    self.players[player].hand,
                    "discard_own",
                    source_uid=uid,
                )
                if discarded is not None:
                    self.discard_from_hand(discarded, player, "costo di purificazione")
                    target = self.bots[player].choose_card(
                        self,
                        player,
                        candidates,
                        "purify",
                        source_uid=uid,
                    )
                    if target is not None:
                        self.purify_card(target, self.definition(uid).name)
        elif definition_id == 23:
            self.players[player].score += 1
            self.telemetry.record_ability(player, "PV diretto")
            self.emit("Orizzonte fa guadagnare 1 PV senza Blessare.")
        elif definition_id == 26:
            candidates = [
                card_uid for card_uid in self.players[player].hand
                if "Luce" in ({"Luce", "Ombra"} if self.definition(card_uid).form == Form.DUAL else {self.definition(card_uid).form.value})
            ]
            chosen = self.bots[player].choose_card(self, player, candidates, "play")
            if chosen is not None:
                self.play_generated_card(chosen, player, forced_mode="Preghiera", calata=True)
        elif definition_id == 46:
            echoes = [
                prayer for prayer in self.players[player].prayers
                if self.definition(prayer).prayer_type == PrayerType.ECHO
                and self.cards[prayer].echo_used_turn != self.turn_number
            ]
            chosen = self.bots[player].choose_card(self, player, echoes, "effect_source")
            if chosen is not None:
                self.use_echo(chosen, player)
        elif definition_id == 56:
            candidates = [card_uid for card_uid in self.void if self.original_eye(card_uid) >= 4]
            chosen = self.bots[player].choose_card(self, player, candidates, "take")
            if chosen is not None:
                self.take_to_hand(chosen, player, "Prima Notte")

    def trigger_legame_played(self, player: int) -> None:
        sources = [
            uid for uid in self.players[player].maledictions
            if self.definition(uid).id == 13 and not self.is_suppressed(uid)
        ]
        for source in sources:
            echoes = [
                prayer for prayer in self.players[player].prayers
                if self.definition(prayer).prayer_type == PrayerType.ECHO
                and self.cards[prayer].echo_used_turn != self.turn_number
            ]
            chosen = self.bots[player].choose_card(self, player, echoes, "effect_source")
            if chosen is not None:
                self.emit(f"Corona di Stirpe fa Invocare {self.definition(chosen).name}.")
                self.use_echo(chosen, player)

    def use_echo(self, uid: int, player: int) -> None:
        card = self.cards[uid]
        if card.controller != player or card.echo_used_turn == self.turn_number:
            return
        if self.definition(uid).prayer_type != PrayerType.ECHO:
            return
        card.echo_used_turn = self.turn_number
        self.telemetry.record_invocation(player)
        self.telemetry.record_ability(player, "Eco")
        self.emit(f"Il Giocatore {player + 1} usa l'effetto Eco di {self.definition(uid).name}.")
        if not self.is_suppressed(uid):
            self.resolve_prayer_effect(uid, player)

        while True:
            other_echoes = [
                prayer for prayer in self.players[player].prayers
                if prayer != uid
                and self.definition(prayer).prayer_type == PrayerType.ECHO
                and self.cards[prayer].echo_used_turn != self.turn_number
            ]
            if not other_echoes:
                break
            chosen = self.bots[player].choose_card(self, player, other_echoes, "effect_source")
            if chosen is None:
                break
            self.use_echo(chosen, player)

    def copy_prayer_effect_from_malediction(self, player: int) -> None:
        candidates = [
            uid for uid in self.players[player].maledictions
            if self.definition(uid).prayer_type in {PrayerType.ECHO, PrayerType.IMPULSE}
            and not self.is_suppressed(uid)
            and not (
                self.definition(uid).prayer_type == PrayerType.ECHO
                and self.cards[uid].echo_used_turn == self.turn_number
            )
        ]
        chosen = self.bots[player].choose_card(self, player, candidates, "effect_source")
        if chosen is None:
            return
        if self.definition(chosen).prayer_type == PrayerType.ECHO:
            self.use_echo(chosen, player)
        else:
            self.emit(f"Viene usato l'effetto Impulso stampato su {self.definition(chosen).name}.")
            self.resolve_prayer_effect(chosen, player, copied=True)

    def _choose_target(
        self,
        player: int,
        candidates: Iterable[int],
        purpose: str,
        source_uid: int | None = None,
    ) -> int | None:
        filtered = [
            uid
            for uid in list(candidates)
            if not (
                self.is_thunder_sand
                and uid in self.cards
                and self.cards[uid].zone == Zone.MALEDICTION
                and self.definition(uid).id == 49
                and not self.is_suppressed(uid)
                and purpose not in {"limit_remove", "sacrifice", "return_own", "charge", "spend_charge"}
            )
        ]
        return self.bots[player].choose_card(
            self,
            player,
            filtered,
            purpose,
            source_uid=source_uid,
        )

    def _choose_option(
        self,
        player: int,
        options: list[str | bool],
        purpose: str,
        source_uid: int | None = None,
    ) -> str | bool | None:
        if not options:
            return None
        chooser = getattr(self.bots[player], "choose_option", None)
        if callable(chooser):
            answer = chooser(self, player, options, purpose, source_uid=source_uid)
            return answer if answer in options else options[0]
        return options[0]

    def _take_choice_from_deck(self, player: int, reason: str) -> int | None:
        self.ensure_deck(player, 1, reason)
        if not self.deck:
            return None
        chosen = self._choose_target(player, self.deck, "take")
        if chosen is None:
            return None
        self.deck.remove(chosen)
        self.reset_card_outside_field(chosen, Zone.HAND, player)
        self.players[player].hand.append(chosen)
        self.telemetry.record_draw(player, self.definition(chosen).id)
        self.rng.shuffle(self.deck)
        self.emit(f"Il Giocatore {player + 1} consulta il Mazzo, prende {self.definition(chosen).name} e rimescola.")
        return chosen

    def _look_top_three(self, player: int, reason: str) -> int | None:
        self.ensure_deck(player, 3, reason)
        candidates = list(self.deck[-min(3, len(self.deck)):])
        chosen = self._choose_target(player, candidates, "take")
        if chosen is None:
            return None
        self.deck.remove(chosen)
        self.reset_card_outside_field(chosen, Zone.HAND, player)
        self.players[player].hand.append(chosen)
        self.telemetry.record_draw(player, self.definition(chosen).id)
        self.rng.shuffle(self.deck)
        self.emit(f"Il Giocatore {player + 1} guarda tre carte, prende {self.definition(chosen).name} e rimescola.")
        return chosen

    def _play_first_from_void(self, player: int, form: str, reason: str) -> None:
        chosen = next((uid for uid in reversed(self.void) if form in ({"Luce", "Ombra"} if self.definition(uid).form == Form.DUAL else {self.definition(uid).form.value})), None)
        if chosen is not None and self.play_generated_card(chosen, player):
            self.emit(f"{reason} gioca la prima {form} dalla cima del Vuoto.")

    def _play_top_deck(self, player: int, reason: str) -> None:
        self.ensure_deck(player, 1, reason)
        if not self.deck:
            return
        uid = self.deck[-1]
        if self.play_generated_card(uid, player):
            self.emit(f"{reason} gioca {self.definition(uid).name}, prima carta del Mazzo.")

    def _break_all_form(self, form: str, source_uid: int) -> None:
        initial = [uid for uid in self.all_field_cards() if form in self.forms(uid)]
        for controller in (self.active_player, 1 - self.active_player):
            remaining = [
                uid
                for uid in initial
                if self.cards[uid].controller == controller
                and self.cards[uid].zone in {Zone.MALEDICTION, Zone.PRAYER}
            ]
            while remaining:
                # Obelisco del Sole/Buio non chiede un bersaglio: ogni carta
                # della forma indicata si Spezza automaticamente. L'ordine
                # stabile del campo serve solo a risolvere eventuali SPEZZATA.
                self.break_card(
                    remaining[0],
                    reason=f"effetto di {self.definition(source_uid).name}",
                )
                remaining = [uid for uid in remaining if self.cards[uid].zone in {Zone.MALEDICTION, Zone.PRAYER}]

    def convert_prayer_to_malediction(
        self,
        uid: int,
        player: int,
        *,
        stasis: bool = False,
    ) -> bool:
        card = self.cards[uid]
        if card.zone != Zone.PRAYER or card.controller != player or not self.can_play_malediction(player, uid):
            return False
        while self.used_malediction_slots(player) + self.malediction_weight(uid) > 4:
            removal = self._choose_limit_malediction(player)
            if removal is None:
                return False
            self.move_to_void_without_break(removal, "Limite durante conversione")
        # La sostituzione del Limite puo' aver Spezzato proprio questa Legame
        # se era collegata alla Maledizione rimossa. In quel caso l'effetto si
        # risolve solo per la parte ancora possibile.
        if card.zone != Zone.PRAYER or card.controller != player or uid not in self.players[player].prayers:
            return False
        self.players[player].prayers.remove(uid)
        card.zone = Zone.MALEDICTION
        card.attached_to = None
        card.corrupted = False
        card.stasis = stasis
        card.entered_sequence = self.next_sequence()
        self.players[player].maledictions.append(uid)
        stasis_text = " in Stasi" if stasis else " non in Stasi"
        self.emit(
            f"{self.definition(uid).name} viene convertita in Maledizione Pura{stasis_text}."
        )
        self.check_seal_states()
        return True

    def resolve_prayer_effect(self, source_uid: int, player: int, *, copied: bool = False) -> None:
        key = (source_uid, self.definition(source_uid).id)
        count = self.effect_resolution_counts.get(key, 0)
        if count >= 2:
            self.emit(
                f"Il ciclo dell'effetto di {self.definition(source_uid).name} e' gia' avvenuto due volte: si passa oltre."
            )
            return
        self.effect_resolution_counts[key] = count + 1
        try:
            self._resolve_prayer_effect_impl(source_uid, player, copied=copied)
        finally:
            if count:
                self.effect_resolution_counts[key] = count
            else:
                self.effect_resolution_counts.pop(key, None)

    def _resolve_thunder_sand_impulse(self, source_uid: int, player: int) -> None:
        definition_id = self.definition(source_uid).id
        opponent = 1 - player
        own_maledictions = self.players[player].maledictions
        enemy_maledictions = self.players[opponent].maledictions

        if definition_id == 2:
            candidates = [
                target
                for target in self.all_field_cards()
                if self.eye(target) <= self.effective_charge_count(player)
            ]
            target = self._choose_target(player, candidates, "break", source_uid)
            if target is not None:
                self.break_card(target, reason=self.definition(source_uid).name)
        elif definition_id in {5, 24}:
            option = self._choose_option(
                player,
                ["+2 Occhio", "+1 Karma"],
                "stat_bonus",
                source_uid,
            )
            purpose = "buff_karma_any" if option == "+1 Karma" else "buff_eye_any"
            target = self._choose_target(player, self.all_maledictions(), purpose, source_uid)
            if target is not None:
                if option == "+1 Karma":
                    self.add_modifier("target_karma_add", player, source_uid=source_uid, target_uid=target, value=1)
                else:
                    self._record_eye_support(player, target, 2)
                    self.add_modifier("target_eye_add", player, source_uid=source_uid, target_uid=target, value=2)
        elif definition_id == 7:
            if self.all_maledictions() and len(self.players[player].charges) >= 2:
                pay = self._choose_option(player, [True, False], "spend_charges", source_uid)
                if pay is True and self.spend_charges(
                    player,
                    2,
                    self.definition(source_uid).name,
                    chooser=player,
                ):
                    target = self._choose_target(
                        player,
                        self.all_maledictions(),
                        "buff_karma_any",
                        source_uid,
                    )
                    if target is not None:
                        self.add_modifier("target_karma_add", player, source_uid=source_uid, target_uid=target, value=2)
        elif definition_id == 11:
            target = self._choose_target(
                player,
                self.all_maledictions(),
                "attack_setup_any",
                source_uid,
            )
            if target is not None:
                self.add_modifier("wins_marked", player, source_uid=source_uid, target_uid=target)
        elif definition_id == 13:
            if self.all_maledictions():
                maximum = max(self.eye(uid) for uid in self.all_maledictions())
                target = self._choose_target(
                    player,
                    [uid for uid in self.all_maledictions() if self.eye(uid) == maximum],
                    "break",
                    source_uid,
                )
                if target is not None:
                    self.break_card(target, reason=self.definition(source_uid).name)
        elif definition_id in {16, 51}:
            target = self._choose_target(player, own_maledictions, "toggle_corruption", source_uid)
            if target is not None:
                options = ["Purifica"] if self.cards[target].corrupted else ["Corrompi"]
                option = self._choose_option(player, options, "toggle_corruption", source_uid)
                if option == "Purifica":
                    self.purify_card(target, self.definition(source_uid).name)
                else:
                    self.corrupt_card(target, player, self.definition(source_uid).name)
        elif definition_id == 17:
            for prayer_type in (
                PrayerType.GLYPH,
                PrayerType.SIGIL,
                PrayerType.IMPULSE,
            ):
                self.add_modifier(
                    "free_prayer_type_play",
                    player,
                    source_uid=source_uid,
                    value=prayer_type.value,
                )
        elif definition_id == 20:
            self.charge_card(source_uid, player, "Dadi del Tuono")
            roll = self.rng.randint(1, 6)
            self.fate_event_counter += 1
            self.last_fate = {
                "event_id": self.fate_event_counter,
                "card_uid": source_uid,
                "controller": player,
                "choice": "Lancio",
                "roll": roll,
                "won": roll % 2 == 0,
            }
            self.emit(f"Dadi del Tuono lancia il dado: esce {roll}.")
            if roll % 2 == 0:
                self.charge_from_deck(player, 1, "Dadi del Tuono: risultato pari")
        elif definition_id == 23:
            attackers = [
                uid
                for uid in own_maledictions
                if not self.cards[uid].stasis and not self.cannot_attack(uid)
                and (
                    self.cards[uid].attacked_turn != self.turn_number
                    or self.extra_attacks_remaining(uid) > 0
                )
            ]
            attacker = self._choose_target(player, attackers, "attack_source", source_uid)
            if attacker is not None:
                previews = self.attack_target_previews(
                    player,
                    attacker,
                    ignore_action_cost=True,
                )
                targets = [
                    int(preview["target_uid"])
                    for preview in previews
                    if preview["allowed"] and self.is_marked(int(preview["target_uid"]))
                ]
                target = self._choose_target(player, targets, "attack_target", source_uid)
                if target is not None:
                    if (
                        self.definition(target).id in {26, 46}
                        and not self.is_suppressed(target)
                        and not self.spend_charges(
                            player,
                            1,
                            f"attaccare {self.definition(target).name}",
                            chooser=player,
                        )
                    ):
                        return
                    already_attacked = self.cards[attacker].attacked_turn == self.turn_number
                    self.attack_event_counter += 1
                    self.last_attack = {
                        "event_id": self.attack_event_counter,
                        "attacker_uid": attacker,
                        "target_uid": target,
                        "target_player": opponent,
                    }
                    self.resolve_combat(attacker, target)
                    if already_attacked:
                        self.consume_extra_attack(attacker)
        elif definition_id == 26:
            initial = [uid for uid in self.all_maledictions() if not self.cards[uid].corrupted]
            for controller in (self.active_player, 1 - self.active_player):
                for target in [uid for uid in initial if self.cards[uid].controller == controller]:
                    if self.cards[target].zone == Zone.MALEDICTION:
                        self.break_card(target, reason=self.definition(source_uid).name)
            self.force_end_turn = True
        elif definition_id == 27:
            target = self._choose_target(
                player,
                self.all_maledictions(),
                "grant_emblem_any",
                source_uid,
            )
            if target is not None:
                self.add_modifier(
                    "grant_emblem",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                    expires_after_turn=self.turn_number + 1,
                )
                self.add_modifier(
                    "target_karma_add",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                    value=-1,
                    expires_after_turn=self.turn_number + 1,
                )
        elif definition_id == 29:
            candidates = [
                target
                for target in self.all_maledictions()
                if any(
                    other != target
                    and self.cards[other].blessed_turn == self.turn_number
                    and self.karma(other) > self.karma(target)
                    for other in self.all_maledictions()
                )
            ]
            target = self._choose_target(player, candidates, "bless_any", source_uid)
            if target is not None:
                target_controller = self.cards[target].controller
                if target_controller is not None:
                    self.bless_card(target, target_controller)
        elif definition_id == 31:
            costs = [uid for uid in own_maledictions if not self.cards[uid].corrupted]
            cost = self._choose_target(player, costs, "cost", source_uid)
            if cost is not None and self.break_card(cost, reason="costo di Sil, il Sacerdote"):
                candidates = list(self.players[player].hand) + list(self.void[-3:])
                chosen = self._choose_target(player, candidates, "play", source_uid)
                if chosen is not None:
                    from_hand = chosen in self.players[player].hand
                    self.play_generated_card(
                        chosen,
                        player,
                        forced_mode="Maledizione",
                        calata=from_hand,
                    )
        elif definition_id == 33:
            for uid in list(self.players[player].hand):
                self.discard_from_hand(uid, player, self.definition(source_uid).name)
            target = self._choose_target(player, self.void, "play", source_uid)
            if target is not None:
                self.play_generated_card(target, player, calata=False)
        elif definition_id == 34:
            target = self._choose_target(
                player,
                self.all_field_cards(),
                "suppress",
                source_uid,
            )
            if target is not None:
                self.add_modifier("suppress_effect", player, source_uid=source_uid, target_uid=target)
        elif definition_id == 39:
            sigils = [
                uid
                for uid in self.players[opponent].prayers
                if self.definition(uid).prayer_type == PrayerType.SIGIL
            ]
            target = self._choose_target(player, sigils, "steal", source_uid)
            if target is not None and self.change_control_prayer(target, player):
                if not self.cards[target].seal_open:
                    self.open_sigil(target, self.definition(source_uid).name)
        elif definition_id == 40:
            candidates = [
                uid
                for uid in self.all_maledictions()
                if self.cards[uid].blessed_turn == self.turn_number - 1
                and not self.cards[uid].corrupted
            ]
            target = self._choose_target(player, candidates, "debuff", source_uid)
            if target is not None:
                self.corrupt_card(target, player, self.definition(source_uid).name)
        elif definition_id == 41:
            target = self._choose_target(player, self.all_prayers(), "break", source_uid)
            if target is not None:
                self.break_card(target, reason=self.definition(source_uid).name)
        elif definition_id == 43:
            own_sigils = [
                uid
                for uid in self.players[player].prayers
                if self.definition(uid).prayer_type == PrayerType.SIGIL
            ]
            enemy_sigils = [
                uid
                for uid in self.players[opponent].prayers
                if self.definition(uid).prayer_type == PrayerType.SIGIL
            ]
            options = []
            if own_sigils:
                options.append("Converti un tuo Sigillo")
            if enemy_sigils:
                options.append("Spezza un Sigillo avversario")
            option = self._choose_option(player, options, "pangolino_mode", source_uid)
            if option == "Converti un tuo Sigillo":
                target = self._choose_target(player, own_sigils, "convert", source_uid)
                if target is not None:
                    self.convert_prayer_to_malediction(target, player, stasis=True)
            elif option == "Spezza un Sigillo avversario":
                target = self._choose_target(player, enemy_sigils, "break", source_uid)
                if target is not None:
                    self.break_card(target, reason=self.definition(source_uid).name)
        elif definition_id == 46:
            for controller in (self.active_player, 1 - self.active_player):
                while self.used_malediction_slots(controller) > 1:
                    target = self._choose_target(
                        controller,
                        self.players[controller].maledictions,
                        "sacrifice",
                        source_uid,
                    )
                    if target is None:
                        break
                    charge_it = False
                    if controller == player:
                        charge_it = self._choose_option(
                            player,
                            [True, False],
                            "charge_broken",
                            source_uid,
                        )
                    self.break_card(
                        target,
                        reason=self.definition(source_uid).name,
                        charge_to=player if controller == player and charge_it is True else None,
                    )
            self.force_end_turn = True
            self.emit("Obelisco Nascosto termina il turno.")
        elif definition_id == 48:
            for uid in list(self.players[player].hand):
                self.discard_from_hand(uid, player, self.definition(source_uid).name)
            self._take_choice_from_deck(player, self.definition(source_uid).name)
        elif definition_id == 50:
            candidates = [
                charge
                for charge in self.players[player].charges
                if self.can_play_malediction(player, charge)
            ]
            target = self._choose_target(player, candidates, "convert_charge", source_uid)
            if target is not None and self.play_generated_card(
                target,
                player,
                forced_mode="Maledizione",
                calata=False,
            ):
                self.cards[target].stasis = False
        elif definition_id == 54:
            points = max(0, len(self.players[opponent].altar) - len(self.players[player].altar))
            self.players[player].score += points
            self.emit(f"Sabbie Senza Tempo fa guadagnare {points} PV al Giocatore {player + 1}.")
        elif definition_id == 55:
            candidates = [uid for uid in self.all_maledictions() if not self.has_ability(uid, "schermatura")]
            target = self._choose_target(player, candidates, "protect_any", source_uid)
            if target is not None:
                self.add_modifier(
                    "cannot_be_attacked",
                    player,
                    source_uid=source_uid,
                    target_uid=target,
                    starts_turn=self.turn_number + 1,
                    expires_after_turn=self.turn_number + 1,
                )
        elif definition_id == 58:
            self.players[player].actions += 1
            self.emit(
                f"{self.definition(source_uid).name} fa guadagnare 1 Azione "
                f"al Giocatore {player + 1}."
            )
            can_replay = self.effect_resolution_counts.get((source_uid, definition_id), 0) < 2
            if self.players[player].charges and can_replay:
                play_it = self._choose_option(
                    player,
                    [True, False],
                    "play_clessidra_as_prayer",
                    source_uid,
                )
                if play_it is True and self.spend_charges(
                    player,
                    1,
                    f"calare {self.definition(source_uid).name}",
                    chooser=player,
                ):
                    self.play_card(
                        source_uid,
                        player,
                        "Preghiera",
                        calata=True,
                    )
        elif definition_id == 59:
            initial = [uid for uid in self.all_maledictions() if self.eye(uid) >= 6]
            for controller in (self.active_player, 1 - self.active_player):
                for target in [uid for uid in initial if self.cards[uid].controller == controller]:
                    if self.cards[target].zone == Zone.MALEDICTION:
                        self.break_card(target, reason=self.definition(source_uid).name)

        self.check_seal_states()

    def _resolve_prayer_effect_impl(self, source_uid: int, player: int, *, copied: bool = False) -> None:
        definition_id = self.definition(source_uid).id
        if self.is_thunder_sand:
            self._resolve_thunder_sand_impulse(source_uid, player)
            return
        opponent = 1 - player
        field = self.all_field_cards()
        maledictions = self.all_maledictions()
        prayers = self.all_prayers()

        if definition_id in {1, 30}:
            form = "Luce" if definition_id == 1 else "Ombra"
            candidates = [
                uid for uid in self.players[player].maledictions
                if form in self.forms(uid)
            ]
            target = self._choose_target(player, candidates, "buff_eye", source_uid)
            if target is not None:
                self._record_eye_support(player, target, 2)
                self.add_modifier("target_eye_add", player, source_uid=source_uid, target_uid=target, value=2, expires_after_turn=self.turn_number + 1)
        elif definition_id in {2, 3, 7, 13, 19, 21, 25, 26, 31, 32, 36, 47, 48, 49, 50, 53, 60}:
            return
        elif definition_id == 4:
            target = self._choose_target(
                player,
                self.players[player].maledictions,
                "buff_eye",
                source_uid,
            )
            if target is not None:
                gain = sum(prayer != source_uid for prayer in prayers)
                self._record_eye_support(player, target, gain)
                self.add_modifier("target_eye_per_other_prayers", player, source_uid=source_uid, target_uid=target, value=1)
        elif definition_id in {5, 17, 33, 37}:
            target = self._choose_target(player, prayers, "break")
            if target is not None:
                self.break_card(target, reason=self.definition(source_uid).name)
        elif definition_id == 6:
            target = self._choose_target(player, self.players[opponent].prayers, "steal")
            if target is not None:
                self.change_control_prayer(target, player)
        elif definition_id == 8:
            target = self._choose_target(player, self.players[opponent].maledictions, "debuff")
            if target is not None:
                self.add_modifier("cannot_attack", player, source_uid=source_uid, target_uid=target, starts_turn=self.turn_number + 1, expires_after_turn=self.turn_number + 1)
        elif definition_id == 9:
            target = self._choose_target(player, self.players[player].maledictions, "protect_own")
            if target is not None:
                self.add_modifier("cannot_be_attacked", player, source_uid=source_uid, target_uid=target, starts_turn=self.turn_number + 1, expires_after_turn=self.turn_number + 1)
        elif definition_id == 10:
            target = self._choose_target(player, self.players[player].prayers, "convert")
            if target is not None:
                self.convert_prayer_to_malediction(target, player)
        elif definition_id in {11, 46}:
            self.copy_prayer_effect_from_malediction(player)
        elif definition_id == 12:
            self._take_choice_from_deck(player, "Pendolo Veggente")
            self.force_end_turn = True
        elif definition_id == 14:
            remaining = list(self.players[player].maledictions)
            for _ in range(min(2, len(remaining))):
                target = self._choose_target(player, remaining, "buff_eye", source_uid)
                if target is None:
                    break
                remaining.remove(target)
                self._record_eye_support(player, target, 1)
                self.add_modifier("target_eye_add", player, source_uid=source_uid, target_uid=target, value=1, expires_after_turn=self.turn_number + 1)
        elif definition_id == 15:
            for target in self.players[player].maledictions:
                if self.cards[target].corrupted:
                    self._record_eye_support(player, target, 2)
            self.add_modifier("own_corrupted_eye", player, source_uid=source_uid, value=2)
        elif definition_id == 16:
            target = self._choose_target(
                player,
                self.players[player].maledictions,
                "buff_eye",
                source_uid,
            )
            if target is not None:
                self._record_eye_support(player, target, 2)
                self.add_modifier("target_eye_add", player, source_uid=source_uid, target_uid=target, value=2)
        elif definition_id == 18:
            costs = [uid for uid in self.players[player].maledictions if not self.cards[uid].corrupted]
            cost = self._choose_target(player, costs, "cost")
            if cost is not None and self.corrupt_card(cost, player, "costo di Raggio Vanescente"):
                target = self._choose_target(player, self.all_field_cards(), "break")
                if target is not None:
                    self.break_card(target, reason="Raggio Vanescente")
        elif definition_id in {20, 41}:
            target = self._choose_target(
                player,
                self.players[opponent].maledictions + self.players[opponent].prayers,
                "suppress",
            )
            if target is not None:
                self.add_modifier("suppress_effect", player, source_uid=source_uid, target_uid=target)
        elif definition_id in {22, 39}:
            form = "Ombra" if definition_id == 22 else "Luce"
            self._break_all_form(form, source_uid)
            self.force_end_turn = True
        elif definition_id in {23, 38}:
            target = self._choose_target(
                player,
                self.players[opponent].maledictions,
                "debuff_eye",
                source_uid,
            )
            if target is not None:
                watched = "Luce" if definition_id == 23 else "Ombra"
                self._record_eye_debuff(player, target)
                self.add_modifier("watch_attacked", player, source_uid=source_uid, target_uid=target, value=f"{watched}:-2")
        elif definition_id in {24, 52}:
            form = "Luce" if definition_id == 24 else "Ombra"
            for target in self.players[player].maledictions:
                if form in self.forms(target):
                    self._record_eye_support(player, target, 1)
            self.add_modifier("own_form_eye", player, source_uid=source_uid, value=f"{form}:1", expires_after_turn=self.turn_number + 1)
        elif definition_id == 27:
            target = self._choose_target(
                player,
                [uid for uid in self.players[player].maledictions if "Luce" in self.forms(uid)],
                "buff_karma",
                source_uid,
            )
            if target is not None:
                self.add_modifier("target_karma_add", player, source_uid=source_uid, target_uid=target, value=1)
        elif definition_id in {28, 44}:
            self._look_top_three(player, self.definition(source_uid).name)
        elif definition_id == 29:
            self._play_first_from_void(player, "Luce", "Portale Solenne")
        elif definition_id == 34:
            if maledictions:
                maximum = max(self.eye(uid) for uid in maledictions)
                target = self._choose_target(player, [uid for uid in maledictions if self.eye(uid) == maximum], "break")
                if target is not None:
                    self.break_card(target, reason="Lenora, Spada Oscura")
        elif definition_id == 35:
            cost_candidates = []
            for uid in self.all_maledictions():
                controller = self.cards[uid].controller
                if controller is None or self.cards[uid].corrupted:
                    continue
                if any(
                    not self.cards[target].corrupted
                    for target in self.players[1 - controller].maledictions
                ):
                    cost_candidates.append(uid)
            cost = self._choose_target(player, cost_candidates, "cost", source_uid)
            if cost is not None and self.corrupt_card(
                cost,
                player,
                "costo di Sussurro Fatale",
            ):
                cost_controller = self.cards[cost].controller
                targets = [
                    uid
                    for uid in self.players[1 - cost_controller].maledictions
                    if not self.cards[uid].corrupted
                ] if cost_controller is not None else []
                target = self._choose_target(player, targets, "break", source_uid)
                if (
                    target is not None
                    and self.cards[target].zone == Zone.MALEDICTION
                    and not self.cards[target].corrupted
                ):
                    self.break_card(target, reason="Sussurro Fatale")
        elif definition_id == 40:
            target = self._choose_target(
                player,
                self.players[opponent].maledictions,
                "debuff_eye",
                source_uid,
            )
            if target is not None:
                if self.original_eye(target) > 3:
                    self._record_eye_debuff(player, target)
                self.add_modifier("set_original_eye", player, source_uid=source_uid, target_uid=target, value=3, starts_turn=self.turn_number + 1, expires_after_turn=self.turn_number + 1)
        elif definition_id == 42:
            references = [
                uid
                for uid in self.players[player].maledictions + self.players[player].prayers
                if uid != source_uid and "Ombra" in self.forms(uid)
            ]
            target = self._choose_target(
                player,
                self.all_maledictions() if references else [],
                "darkness_target",
                source_uid,
            )
            reference_purpose = (
                "darkness_reference_enemy"
                if target is not None and self.cards[target].controller != player
                else "darkness_reference_own"
            )
            reference = self._choose_target(player, references, reference_purpose, source_uid)
            if target is not None and reference is not None:
                self._record_eye_support(
                    player,
                    target,
                    self.original_eye(reference) - self.eye(target),
                )
                self.add_modifier("set_eye_reference", player, source_uid=source_uid, target_uid=target, reference_uid=reference)
        elif definition_id == 43:
            target = self._choose_target(
                player,
                [uid for uid in self.players[player].maledictions if "Ombra" in self.forms(uid)],
                "buff_karma",
                source_uid,
            )
            if target is not None:
                self.add_modifier("target_karma_add", player, source_uid=source_uid, target_uid=target, value=1)
        elif definition_id == 45:
            target = self._choose_target(
                player,
                self.players[player].maledictions,
                "buff_eye",
                source_uid,
            )
            if target is not None:
                self._record_eye_support(player, target, len(self.players[opponent].maledictions))
                self.add_modifier("target_eye_per_enemy_maledictions", player, source_uid=source_uid, target_uid=target, value=1, expires_after_turn=self.turn_number + 1)
        elif definition_id == 51:
            self.add_modifier("free_prayers", player, source_uid=source_uid)
        elif definition_id == 54:
            if len(self.players[player].maledictions) < len(self.players[opponent].maledictions) and self.void:
                target = self._choose_target(player, self.void, "play")
                if target is not None:
                    self.play_generated_card(target, player)
        elif definition_id == 55:
            for current in (opponent, player):
                target = self._choose_target(current, self.players[current].maledictions, "return_own")
                if target is not None:
                    self.leave_field(target, destination=Zone.HAND, destination_controller=current, reason="Passi Persi")
                    self.telemetry.record_draw(current, self.definition(target).id)
        elif definition_id == 56:
            target = self._choose_target(
                player,
                [uid for uid in self.players[player].maledictions if self.cards[uid].stasis],
                "protect_own",
            )
            if target is not None:
                self.add_modifier("cannot_be_attacked", player, source_uid=source_uid, target_uid=target, starts_turn=self.turn_number + 1, expires_after_turn=self.turn_number + 1)
        elif definition_id == 57:
            self._play_top_deck(player, "Dado Nero")
        elif definition_id == 58:
            self._play_first_from_void(player, "Ombra", "Varco Sepolto")
        elif definition_id == 59:
            target = self._choose_target(player, maledictions, "form_setup", source_uid)
            if target is not None:
                chosen_form = self.bots[player].choose_form(self, player, target)
                self.add_modifier("form_override", player, source_uid=source_uid, target_uid=target, value=chosen_form, expires_after_turn=self.turn_number + 1)
        elif definition_id == 61:
            own_pure = [uid for uid in self.players[player].maledictions if not self.cards[uid].corrupted]
            enemy = list(self.players[opponent].maledictions)
            if len(enemy) >= 2 and own_pure:
                cost = self._choose_target(player, own_pure, "cost")
                if cost is not None and self.break_card(cost, reason="costo di Oblio e Prigione"):
                    targets = list(self.players[opponent].maledictions)
                    target = self._choose_target(player, targets, "steal")
                    if target is not None and self.cards[target].zone == Zone.MALEDICTION:
                        self.change_control_malediction(target, player)
        elif definition_id == 62:
            target = self._choose_target(
                player,
                self.players[player].maledictions,
                "protect_own",
            )
            if target is not None:
                self.add_modifier("grant_barrier", player, source_uid=source_uid, target_uid=target, expires_after_turn=self.turn_number + 1)

    # ------------------------------------------------------------------
    # Turn cycle and game result
    # ------------------------------------------------------------------
    def start_turn(self) -> None:
        if self.game_over:
            return
        self.phase = "Inizio turno"
        self.force_end_turn = False
        base_actions = 2 if self.turn_number == 1 and self.active_player == self.first_player else 3
        if self.is_thunder_sand:
            penalty = sum(
                int(modifier.value or 0)
                for modifier in self.active_modifiers("next_turn_action_penalty")
                if modifier.controller == self.active_player
            )
            base_actions = max(0, base_actions - penalty)
        self.players[self.active_player].actions = base_actions
        self.emit(
            f"Inizio del turno {self.turn_number}: il Giocatore {self.active_player + 1} "
            f"ha {base_actions} Azioni."
        )
        if self.is_thunder_sand:
            for sigil in list(self.players[self.active_player].prayers):
                if self.definition(sigil).id == 60 and self.sigil_is_active(sigil):
                    self.close_sigil(sigil, "inizio del tuo turno")
            for source in list(self.players[self.active_player].maledictions):
                if self.has_ability(source, "cadenza"):
                    self.players[self.active_player].score += 1
                    self.telemetry.record_ability(self.active_player, "Cadenza")
                    self.emit(
                        f"Cadenza di {self.definition(source).name} fa guadagnare 1 PV "
                        f"al Giocatore {self.active_player + 1}."
                    )
            self.check_seal_states()
        start_sources = [
            uid
            for uid in self.players[self.active_player].maledictions
            if not self.is_thunder_sand
            and self.definition(uid).id in {28, 44}
            and not self.is_suppressed(uid)
        ]
        while start_sources:
            source = self.bots[self.active_player].choose_card(
                self,
                self.active_player,
                start_sources,
                "effect_source",
            )
            if source is None:
                source = start_sources[0]
            start_sources.remove(source)
            self.draw(self.active_player, 1, self.definition(source).name)
        self.phase = "Fase principale"

    def _remove_all_stasis(self) -> int:
        removed = 0
        for uid in self.all_maledictions():
            if self.cards[uid].stasis:
                self.cards[uid].stasis = False
                removed += 1
        return removed

    def end_turn(self) -> None:
        if self.game_over:
            return
        self.last_attack = None
        self.last_fate = None
        self.last_impulse = None
        ending_player = self.active_player
        self.phase = "Fine turno"
        if self.is_thunder_sand:
            for sigil in list(self.players[ending_player].prayers):
                if self.definition(sigil).id == 9 and self.sigil_is_active(sigil):
                    self.close_sigil(sigil, "fine del turno")
        self.telemetry.stasis_wasted[ending_player] += len(
            self.stasis_removed_this_turn[ending_player]
        )
        self.stasis_removed_this_turn[ending_player].clear()
        removed = self._remove_all_stasis()
        if removed:
            self.emit(f"La Stasi viene rimossa automaticamente da {removed} Maledizioni.")
        is_trigger_turn = (
            self.final_turns_remaining is not None
            and self.final_trigger_turn == self.turn_number
        )
        is_last_final_turn = (
            self.final_turns_remaining == 1
            and not is_trigger_turn
        )
        if not is_last_final_turn:
            self.perform_mulligan(ending_player)
        self.players[ending_player].actions = 0
        self.completed_turns += 1

        if self.final_turns_remaining is not None and not is_trigger_turn:
            self.final_turns_remaining -= 1
            self.emit(f"Restano {self.final_turns_remaining} Turni Finali.")
            if self.final_turns_remaining <= 0:
                self.finish_game()
                return

        if self.completed_turns >= self.MAX_TURNS:
            self.stalemate = True
            self.finish_game(forced=True)
            return

        self.active_player = 1 - ending_player
        self.turn_number += 1
        self.phase = "Passaggio turno"

    def finish_game(self, *, forced: bool = False) -> None:
        if self.game_over:
            return
        score_0 = self.players[0].score
        score_1 = self.players[1].score
        if score_0 > score_1:
            self.winner = 0
        elif score_1 > score_0:
            self.winner = 1
        elif self.final_trigger_player is not None:
            self.winner = self.final_trigger_player
        else:
            self.winner = None
            self.stalemate = True
        self.game_over = True
        self.phase = "Partita terminata"
        if forced:
            self.emit(
                f"Limite di sicurezza raggiunto. Punteggio finale: {score_0}-{score_1}; "
                f"esito {'pareggio tecnico' if self.winner is None else f'Giocatore {self.winner + 1}'}."
            )
        else:
            self.emit(
                f"Fine della partita: {score_0}-{score_1}. "
                f"Vince il Giocatore {self.winner + 1}."
            )

    def play_game(self) -> GameResult:
        while not self.game_over:
            self.start_turn()
            seen: dict[tuple[Any, ...], int] = {}
            action_count = 0
            while not self.force_end_turn and not self.game_over:
                actions = self.legal_actions(self.active_player)
                meaningful = [action for action in actions if action.kind != "pass"]
                if not meaningful:
                    break
                chosen = self.bots[self.active_player].choose_action(
                    self,
                    self.active_player,
                    actions,
                )
                self.execute_action(chosen, self.active_player)
                action_count += 1

                signature = self.state_signature()
                seen[signature] = seen.get(signature, 0) + 1
                if seen[signature] >= 2:
                    self.emit("Ciclo di stato ripetuto due volte: il simulatore passa oltre.")
                    self.force_end_turn = True
                if action_count >= self.MAX_ACTIONS_PER_TURN:
                    self.emit("Limite di sicurezza delle azioni raggiunto: il turno termina.")
                    self.force_end_turn = True

            self.end_turn()

        trigger_won = (
            self.winner == self.final_trigger_player
            if self.winner is not None and self.final_trigger_player is not None
            else None
        )
        return GameResult(
            seed=self.seed,
            deck=self.deck_name,
            bot_names=self.bot_names,
            first_player=self.first_player,
            winner=self.winner,
            scores=(self.players[0].score, self.players[1].score),
            turns=self.completed_turns,
            final_trigger_player=self.final_trigger_player,
            final_trigger_cause=self.final_trigger_cause,
            final_trigger_won=trigger_won,
            stalemate=self.stalemate,
            telemetry=self.telemetry,
            replay=self.replay,
        )
