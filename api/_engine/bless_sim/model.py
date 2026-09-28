from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Form(StrEnum):
    LIGHT = "Luce"
    SHADOW = "Ombra"
    THUNDER = "Tuono"
    SAND = "Sabbia"
    DUAL = "Duale"


class PrayerType(StrEnum):
    ECHO = "Eco"
    BOND = "Legame"
    IMPULSE = "Impulso"
    SIGIL = "Sigillo"
    GLYPH = "Glifo"


class Zone(StrEnum):
    DECK = "mazzo"
    HAND = "mano"
    MALEDICTION = "maledizione"
    PRAYER = "preghiera"
    VOID = "vuoto"
    ALTAR = "altare"
    CHARGE = "carica"
    MARK = "marchio"


@dataclass(frozen=True, slots=True)
class CardDefinition:
    id: int
    name: str
    form: Form
    eye: int
    karma: int
    malediction_text: str
    prayer_text: str
    prayer_type: PrayerType
    image: str | None = None
    traits: tuple[str, ...] = ()


@dataclass(slots=True)
class CardInstance:
    uid: int
    definition_id: int
    zone: Zone = Zone.DECK
    controller: int | None = None
    corrupted: bool = False
    stasis: bool = False
    attached_to: int | None = None
    entered_sequence: int = 0
    attacked_turn: int = -1
    echo_used_turn: int = -1
    corrupted_turn: int = -1
    blessed_turn: int = -1
    seal_open: bool = True
    glyph_used_turn: int = -1
    declared_form: str | None = None
    effect_target_uid: int | None = None
    effect_target_state: str | None = None


@dataclass(slots=True)
class PlayerState:
    id: int
    hand: list[int] = field(default_factory=list)
    maledictions: list[int] = field(default_factory=list)
    prayers: list[int] = field(default_factory=list)
    altar: list[int] = field(default_factory=list)
    charges: list[int] = field(default_factory=list)
    score: int = 0
    actions: int = 0


@dataclass(slots=True)
class Modifier:
    sequence: int
    kind: str
    controller: int
    source_uid: int | None = None
    target_uid: int | None = None
    value: int | str | None = None
    reference_uid: int | None = None
    starts_turn: int = 0
    expires_after_turn: int = 0

    def is_active(self, turn: int) -> bool:
        return self.starts_turn <= turn <= self.expires_after_turn


@dataclass(frozen=True, slots=True)
class Action:
    kind: str
    card_uid: int | None = None
    target_uid: int | None = None
    mode: str | None = None
    cost: int = 1
    label: str = ""


@dataclass(slots=True)
class ReplayStep:
    index: int
    turn: int
    active_player: int
    phase: str
    message: str
    snapshot: dict[str, Any]
    action_index: int | None = None
    action_label: str | None = None


@dataclass(slots=True)
class GameTelemetry:
    actions: dict[str, int] = field(default_factory=dict)
    card_draws: list[dict[int, int]] = field(default_factory=lambda: [{}, {}])
    card_modes: list[dict[int, dict[str, int]]] = field(default_factory=lambda: [{}, {}])
    card_bless_points: list[dict[int, int]] = field(default_factory=lambda: [{}, {}])
    card_bless_events: list[dict[int, int]] = field(default_factory=lambda: [{}, {}])
    ability_triggers: dict[str, int] = field(default_factory=dict)
    ability_by_player: list[dict[str, int]] = field(default_factory=lambda: [{}, {}])
    combats: int = 0
    direct_attacks: int = 0
    mulliganed: int = 0
    stasis_removed: int = 0
    altar_offers: list[int] = field(default_factory=lambda: [0, 0])
    corruptions_caused: list[int] = field(default_factory=lambda: [0, 0])
    enemy_corruptions_created: list[int] = field(default_factory=lambda: [0, 0])
    unused_actions: list[int] = field(default_factory=lambda: [0, 0])
    stasis_wasted: list[int] = field(default_factory=lambda: [0, 0])
    own_eye_buffs: list[int] = field(default_factory=lambda: [0, 0])
    high_karma_eye_buffs: list[int] = field(default_factory=lambda: [0, 0])
    enemy_eye_debuffs: list[int] = field(default_factory=lambda: [0, 0])
    invocations: list[int] = field(default_factory=lambda: [0, 0])
    glyph_uses: list[int] = field(default_factory=lambda: [0, 0])
    charges_created: list[int] = field(default_factory=lambda: [0, 0])
    learning_gradients: list[dict[str, float]] = field(default_factory=lambda: [{}, {}])
    learning_feature_totals: list[dict[str, float]] = field(default_factory=lambda: [{}, {}])
    learning_decisions: list[int] = field(default_factory=lambda: [0, 0])
    chosen_action_kinds: list[dict[str, int]] = field(default_factory=lambda: [{}, {}])

    def increment_action(self, kind: str) -> None:
        self.actions[kind] = self.actions.get(kind, 0) + 1

    def record_draw(self, player: int, card_id: int) -> None:
        bucket = self.card_draws[player]
        bucket[card_id] = bucket.get(card_id, 0) + 1

    def record_play(self, player: int, card_id: int, mode: str) -> None:
        card = self.card_modes[player].setdefault(card_id, {"Maledizione": 0, "Preghiera": 0})
        card[mode] += 1

    def record_bless(self, player: int, card_id: int, points: int) -> None:
        bucket = self.card_bless_points[player]
        bucket[card_id] = bucket.get(card_id, 0) + points
        events = self.card_bless_events[player]
        events[card_id] = events.get(card_id, 0) + 1

    def record_ability(self, player: int, ability: str) -> None:
        self.ability_triggers[ability] = self.ability_triggers.get(ability, 0) + 1
        bucket = self.ability_by_player[player]
        bucket[ability] = bucket.get(ability, 0) + 1

    def record_offer(self, player: int) -> None:
        self.altar_offers[player] += 1

    def record_corruption(self, source_player: int, target_player: int | None) -> None:
        self.corruptions_caused[source_player] += 1
        if target_player is not None and target_player != source_player:
            self.enemy_corruptions_created[source_player] += 1

    def record_invocation(self, player: int) -> None:
        self.invocations[player] += 1

    def record_glyph_use(self, player: int) -> None:
        self.glyph_uses[player] += 1

    def record_charge(self, player: int) -> None:
        self.charges_created[player] += 1

    def record_learning_decision(
        self,
        player: int,
        action_kind: str,
        chosen_features: dict[str, float],
        comparison_features: dict[str, float],
    ) -> None:
        """Accumula un segnale compatto per l'aggiornamento a fine campione.

        Il gradiente e' la differenza tra le caratteristiche della mossa scelta
        e la media delle alternative credibili. Conserviamo solo le somme, non
        l'intero albero decisionale, cosi' anche 10.000 partite restano leggere.
        """
        self.learning_decisions[player] += 1
        kinds = self.chosen_action_kinds[player]
        kinds[action_kind] = kinds.get(action_kind, 0) + 1
        gradient = self.learning_gradients[player]
        totals = self.learning_feature_totals[player]
        for feature, value in chosen_features.items():
            numeric = float(value)
            baseline = float(comparison_features.get(feature, 0.0))
            gradient[feature] = gradient.get(feature, 0.0) + numeric - baseline
            totals[feature] = totals.get(feature, 0.0) + numeric
