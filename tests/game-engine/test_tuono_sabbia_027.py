from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "public" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from bless_sim.engine import GameEngine  # noqa: E402
from bless_sim.manual import ChoiceRequired, HumanDecisionBot  # noqa: E402
from bless_sim.model import Action, PrayerType, Zone  # noqa: E402


class ScriptedBot:
    """Sovrascrive solo le scelte utili al caso limite e delega tutto il resto."""

    def __init__(
        self,
        delegate: Any,
        *,
        cards: dict[str, list[int | None]] | None = None,
        options: dict[str, list[str | bool]] | None = None,
        modes: list[str] | None = None,
    ) -> None:
        self.delegate = delegate
        self.cards = {key: list(values) for key, values in (cards or {}).items()}
        self.options = {key: list(values) for key, values in (options or {}).items()}
        self.modes = list(modes or [])
        self.option_calls: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def choose_card(
        self,
        engine: GameEngine,
        player: int,
        candidates: Iterable[int],
        purpose: str,
        *,
        source_uid: int | None = None,
    ) -> int | None:
        choices = list(candidates)
        queue = self.cards.get(purpose)
        if queue:
            answer = queue.pop(0)
            assert answer is None or answer in choices, (purpose, answer, choices)
            return answer
        return self.delegate.choose_card(
            engine,
            player,
            choices,
            purpose,
            source_uid=source_uid,
        )

    def choose_option(
        self,
        engine: GameEngine,
        player: int,
        options: list[str | bool],
        purpose: str,
        *,
        source_uid: int | None = None,
    ) -> str | bool:
        self.option_calls[purpose] += 1
        queue = self.options.get(purpose)
        if queue:
            answer = queue.pop(0)
            assert answer in options, (purpose, answer, options)
            return answer
        return self.delegate.choose_option(
            engine,
            player,
            options,
            purpose,
            source_uid=source_uid,
        )

    def choose_mode(
        self,
        engine: GameEngine,
        player: int,
        uid: int,
        legal_modes: list[str],
    ) -> str:
        if self.modes:
            answer = self.modes.pop(0)
            assert answer in legal_modes, (answer, legal_modes)
            return answer
        return self.delegate.choose_mode(engine, player, uid, legal_modes)


class FixedRoll:
    def __init__(self, delegate: Any, roll: int) -> None:
        self.delegate = delegate
        self.roll = roll

    def randint(self, _start: int, _end: int) -> int:
        return self.roll

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def _remove_everywhere(engine: GameEngine, uid: int) -> None:
    engine._remove_from_zone_list(uid)


def _put_malediction(
    engine: GameEngine,
    uid: int,
    player: int,
    *,
    corrupted: bool = False,
    stasis: bool = False,
) -> None:
    _remove_everywhere(engine, uid)
    engine.reset_card_outside_field(uid, Zone.MALEDICTION, player)
    engine.cards[uid].corrupted = corrupted
    engine.cards[uid].stasis = stasis
    engine.cards[uid].entered_sequence = engine.next_sequence()
    engine.players[player].maledictions.append(uid)


def _put_prayer(engine: GameEngine, uid: int, player: int, *, open_: bool = True) -> None:
    _remove_everywhere(engine, uid)
    engine.reset_card_outside_field(uid, Zone.PRAYER, player)
    engine.cards[uid].seal_open = open_
    engine.cards[uid].entered_sequence = engine.next_sequence()
    engine.players[player].prayers.append(uid)


def _put_hand(engine: GameEngine, uid: int, player: int) -> None:
    _remove_everywhere(engine, uid)
    engine.reset_card_outside_field(uid, Zone.HAND, player)
    engine.players[player].hand.append(uid)


def _put_void(engine: GameEngine, uid: int) -> None:
    _remove_everywhere(engine, uid)
    engine.reset_card_outside_field(uid, Zone.VOID, None)
    engine.void.append(uid)


def test_new_card_data_updates_names_stats_and_effects() -> None:
    payload = json.loads((PYTHON_ROOT / "data" / "tuono_sabbia.json").read_text(encoding="utf-8"))
    cards = {card["id"]: card for card in payload["cards"]}

    assert payload["version"] == "0.2.7"
    assert cards[43]["name"] == "Pangolino di Seta e Sabbia"
    assert cards[56]["prayer_text"].startswith("Le tue Maledizioni che hanno l'effetto Preghiera Sigillo")
    assert cards[31]["eye"] == 6
    assert cards[31]["karma"] == 0
    assert cards[53]["name"] == "Torri di Sabbia"
    assert cards[55]["name"] == "Elmo Ritrovato"
    assert cards[58]["prayer_text"].startswith("Guadagni 1 Azione")
    assert cards[58]["name"] == "Clessidra di Zhares"
    assert cards[62]["name"] == "Riposo degli Esploratori"
    assert cards[3]["prayer_text"].startswith("Se cali 1 Maledizione Tuono")
    assert cards[46]["prayer_text"].endswith("poi termina il turno.")
    assert cards[1]["image"] == "ThunderSand_01.png"
    assert cards[43]["image"] == "ThunderSand_43.png"
    assert cards[58]["image"] == "ThunderSand_58.png"


def test_biblioteca_sepolta_plays_only_the_void_top_as_if_it_were_in_hand() -> None:
    engine = GameEngine(230, deck="TuonoSabbia", auto_setup=False)
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 3
    _put_malediction(engine, 48, 0)
    _put_void(engine, 5)
    _put_void(engine, 6)

    actions = engine.legal_actions(0)
    top_actions = [action for action in actions if action.card_uid == 6]

    assert top_actions
    assert not any(action.card_uid == 5 for action in actions)
    assert {action.kind for action in top_actions} == {"play_malediction", "play_prayer"}
    assert {action.cost for action in top_actions} == {1}
    assert all("dalla cima del Vuoto" in action.label for action in top_actions)

    malediction = next(action for action in top_actions if action.kind == "play_malediction")
    engine.execute_action(malediction, 0)

    assert engine.cards[6].zone == Zone.MALEDICTION
    assert engine.cards[6].controller == 0
    assert engine.cards[6].stasis
    assert 6 not in engine.void
    assert engine.void[-1] == 5
    assert not any(action.card_uid == 5 for action in engine.legal_actions(0))

    engine.turn_number += 1
    assert any(action.card_uid == 5 for action in engine.legal_actions(0))


def test_biblioteca_sepolta_void_play_counts_as_calo() -> None:
    engine = GameEngine(231, deck="TuonoSabbia", auto_setup=False)
    engine.active_player = 0
    engine.turn_number = 3
    engine.phase = "Fase principale"
    engine.players[0].actions = 3
    _put_malediction(engine, 48, 0)
    _put_malediction(engine, 2, 1)
    _put_malediction(engine, 3, 1)
    _put_malediction(engine, 4, 1)
    _put_void(engine, 11)

    action = next(
        action
        for action in engine.legal_actions(0)
        if action.card_uid == 11 and action.kind == "play_malediction"
    )
    engine.execute_action(action, 0)

    assert engine.cards[11].zone == Zone.MALEDICTION
    assert any(
        modifier.kind == "free_attack" and modifier.target_uid == 11
        for modifier in engine.active_modifiers()
    )


def test_biblioteca_sepolta_stops_exposing_the_void_when_suppressed_or_removed() -> None:
    engine = GameEngine(232, deck="TuonoSabbia", auto_setup=False)
    engine.active_player = 0
    engine.turn_number = 2
    engine.phase = "Fase principale"
    engine.players[0].actions = 3
    _put_malediction(engine, 48, 0)
    _put_void(engine, 6)

    engine.add_modifier("suppress_effect", 1, target_uid=48)
    assert not any(action.card_uid == 6 for action in engine.legal_actions(0))

    engine.modifiers.clear()
    assert any(action.card_uid == 6 for action in engine.legal_actions(0))

    engine.move_to_void_without_break(48, "test Biblioteca rimossa")
    assert not any(
        action.card_uid in {6, 48}
        and action.kind in {"play_malediction", "play_prayer"}
        for action in engine.legal_actions(0)
    )


def test_colosso_counts_as_two_but_is_one_card_when_broken() -> None:
    engine = GameEngine(201, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 3, 0)
    _put_malediction(engine, 16, 0)
    _put_malediction(engine, 5, 0)
    _put_malediction(engine, 6, 0)

    assert engine.used_malediction_slots(0) == 4
    engine.check_seal_states()
    assert not engine.cards[3].seal_open

    assert engine.break_card(16, reason="test Colosso")
    assert engine.cards[16].zone == Zone.VOID
    assert engine.players[0].maledictions == [5, 6]

    count_engine = GameEngine(224, deck="TuonoSabbia", auto_setup=False)
    count_engine.turn_number = 3
    _put_malediction(count_engine, 21, 0)
    _put_malediction(count_engine, 16, 0)
    count_engine.cards[16].attacked_turn = 3
    assert count_engine.karma(21) == count_engine.definition(21).karma + 2


def test_cuore_uses_an_already_spent_charge_and_can_remove_enemy_stasis() -> None:
    engine = GameEngine(202, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    _put_prayer(engine, 1, 0)
    _put_malediction(engine, 2, 0)
    _put_malediction(engine, 3, 1, stasis=True)
    engine.charge_card(5, 0, "test")

    engine.spend_charges(0, 1, "test Cuore", chooser=0)
    assert not engine.cards[3].stasis
    assert engine.cards[1].seal_open

    engine.break_card(2, reason="test chiusura immediata")
    assert not engine.cards[1].seal_open


def test_boato_can_take_any_removed_mark_and_then_closes_without_marks() -> None:
    engine = GameEngine(203, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 31, 1)
    engine.charge_card(38, 1, "test")
    assert engine.place_mark(31, 38, 1, "test")
    _put_prayer(engine, 4, 0)

    assert engine.remove_mark(31, "test Boato")
    assert 38 in engine.players[0].hand
    assert engine.cards[38].zone == Zone.HAND
    assert 38 not in engine.deck
    assert not engine.cards[4].seal_open


def test_fulmine_fragile_continuously_recorrupts_own_emblems() -> None:
    engine = GameEngine(204, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 10, 0)
    _put_malediction(engine, 2, 0)

    engine.check_seal_states()
    assert engine.cards[2].corrupted
    assert engine.cards[10].seal_open

    engine.bless_card(2, 0)
    assert engine.cards[10].seal_open

    engine.purify_card(2, "test purificazione")
    assert engine.cards[2].corrupted


def test_rito_uses_each_full_group_of_three_effective_charges() -> None:
    engine = GameEngine(205, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 15, 0)
    for uid in (1, 2, 3, 4, 7, 8):
        engine.charge_card(uid, 1, "test")
    _put_prayer(engine, 35, 0)
    for uid in (9, 10):
        engine.charge_card(uid, 0, "test")

    assert engine.effective_charge_count(0) == 3
    assert engine.karma(15) == 4

    for uid in (11, 12, 13):
        engine.charge_card(uid, 0, "test")
    assert engine.effective_charge_count(0) == 6
    assert engine.karma(15) == 7


def test_notte_can_play_only_the_first_spent_charge_without_calo() -> None:
    engine = GameEngine(206, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 5
    engine.active_player = 0
    _put_malediction(engine, 25, 0)
    _put_hand(engine, 2, 0)
    engine.charge_card(1, 0, "test")
    scripted = ScriptedBot(
        engine.bots[0],
        options={"play_spent_charge": [True]},
        modes=["Maledizione"],
    )
    engine.bots[0] = scripted

    engine.spend_charges(0, 1, "test Notte", chooser=0)
    assert engine.cards[1].zone == Zone.MALEDICTION
    assert engine.cards[1].stasis
    assert 2 in engine.players[0].hand
    assert scripted.option_calls["play_spent_charge"] == 1

    engine.charge_card(3, 0, "test seconda spesa")
    engine.spend_charges(0, 1, "test seconda spesa", chooser=0)
    assert engine.cards[3].zone == Zone.DECK
    assert scripted.option_calls["play_spent_charge"] == 1


def test_fonte_curse_and_fonte_sigil_are_separate_effects() -> None:
    curse_engine = GameEngine(207, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(curse_engine, 30, 0)
    _put_void(curse_engine, 31)
    _put_void(curse_engine, 36)
    curse_engine.bots[0] = ScriptedBot(
        curse_engine.bots[0],
        cards={"play": [31]},
        modes=["Maledizione"],
    )
    curse_engine.corrupt_card(30, 0, "test Fonte Maledizione")
    assert curse_engine.cards[31].zone == Zone.MALEDICTION
    assert curse_engine.players[0].hand == []
    assert curse_engine.cards[36].zone == Zone.VOID

    sigil_engine = GameEngine(208, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(sigil_engine, 30, 0)
    _put_malediction(sigil_engine, 31, 0)
    _put_void(sigil_engine, 36)
    sigil_engine.bots[0] = ScriptedBot(
        sigil_engine.bots[0],
        cards={"take": [36]},
    )
    sigil_engine.corrupt_card(31, 0, "test Fonte Sigillo")
    assert sigil_engine.cards[36].zone == Zone.HAND
    assert 36 in sigil_engine.players[0].hand


def test_fonte_della_sabbia_has_screening_only_while_pure() -> None:
    engine = GameEngine(226, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 30, 0)

    assert engine.has_ability(30, "schermatura")
    assert engine.eclissi_targets(0) == [30]

    engine.corrupt_card(30, 1, "test Schermatura")
    assert not engine.has_ability(30, "schermatura")
    assert engine.eclissi_targets(0) == []


def test_idolo_spezzata_plays_from_void_without_triggering_calo() -> None:
    engine = GameEngine(227, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 28, 0)
    _put_void(engine, 1)
    _put_hand(engine, 2, 0)
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"play": [1]},
        modes=["Maledizione"],
    )

    engine.break_card(28, reason="test Idolo")

    assert engine.cards[1].zone == Zone.MALEDICTION
    assert engine.cards[2].zone == Zone.HAND
    assert 2 in engine.players[0].hand


def test_limitare_blocks_only_calo_not_other_generated_play() -> None:
    engine = GameEngine(231, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 60, 1)
    engine.cards[60].declared_form = "Tuono"
    _put_hand(engine, 1, 0)
    _put_void(engine, 2)

    assert not engine.play_card(1, 0, "Maledizione", calata=True)
    assert engine.cards[1].zone == Zone.HAND

    assert engine.play_generated_card(
        2,
        0,
        forced_mode="Maledizione",
        calata=False,
    )
    assert engine.cards[2].zone == Zone.MALEDICTION


def test_tomo_bot_converts_the_most_useful_playable_charge() -> None:
    engine = GameEngine(232, deck="TuonoSabbia", auto_setup=False)
    engine.charge_card(1, 0, "test Tomo")
    engine.charge_card(51, 0, "test Tomo")

    chosen = engine.bots[0].choose_card(
        engine,
        0,
        engine.players[0].charges,
        "convert_charge",
        source_uid=50,
    )

    assert chosen == 51


def test_bot_does_not_invent_eye_bonus_for_fulmine_or_tomo() -> None:
    engine = GameEngine(233, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 31, 0, corrupted=True)
    bot = engine.bots[0]

    fulmine_plan = bot._eye_prayer_plan(
        engine,
        0,
        Action("play_prayer", 10, mode="Preghiera", cost=1),
    )
    tomo_plan = bot._eye_prayer_plan(
        engine,
        0,
        Action("play_prayer", 50, mode="Preghiera", cost=1),
    )

    assert fulmine_plan == (0.0, 0.0)
    assert tomo_plan == (0.0, 0.0)
    assert bot._estimated_eye_gain(engine, 0, 18, 31) == engine.eye(31)

    engine.cards[31].corrupted = False
    assert bot._estimated_eye_gain(engine, 0, 18, 31) == 0


def test_unqualified_targets_can_be_chosen_on_either_side() -> None:
    engine = GameEngine(234, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 1, 0)
    _put_malediction(engine, 31, 1)
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"buff_eye_any": [31]},
        options={"stat_bonus": ["+2 Occhio"]},
    )

    eye_before = engine.eye(31)
    engine._resolve_thunder_sand_impulse(5, 0)
    assert engine.eye(31) == eye_before + 2

    vocio = GameEngine(235, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(vocio, 1, 0)
    vocio.bots[0] = ScriptedBot(vocio.bots[0], cards={"suppress": [1]})
    vocio._resolve_thunder_sand_impulse(34, 0)
    assert vocio.is_suppressed(1)


def test_solerzia_can_bless_an_enemy_but_scores_for_its_controller() -> None:
    engine = GameEngine(236, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 4
    _put_malediction(engine, 54, 0)
    _put_malediction(engine, 31, 1)
    engine.cards[54].blessed_turn = engine.turn_number
    engine.bots[0] = ScriptedBot(engine.bots[0], cards={"bless_any": [31]})

    engine._resolve_thunder_sand_impulse(29, 0)

    assert engine.players[0].score == 0
    assert engine.players[1].score == engine.karma(31)


def test_miraggio_swaps_effective_not_printed_stats() -> None:
    engine = GameEngine(237, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 31, 0)
    engine.add_modifier("target_eye_add", 0, source_uid=5, target_uid=31, value=3)
    engine.add_modifier("target_karma_add", 0, source_uid=7, target_uid=31, value=2)
    effective_eye = engine.eye(31)
    effective_karma = engine.karma(31)
    engine.bots[0] = ScriptedBot(engine.bots[0], cards={"swap_stats": [31]})

    engine.resolve_calo(44, 0)

    assert engine.eye(31) == effective_karma
    assert engine.karma(31) == effective_eye


def test_balena_blocks_one_tied_maximum_and_tracks_a_new_unique_maximum() -> None:
    engine = GameEngine(238, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 52, 0)
    _put_malediction(engine, 1, 0)
    _put_malediction(engine, 31, 1)
    engine.add_modifier("set_eye", 0, source_uid=52, target_uid=1, value=6)
    engine.add_modifier("set_eye", 0, source_uid=52, target_uid=31, value=6)
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"highest_eye_block": [31]},
    )

    assert not engine.cannot_attack(1)
    assert engine.cannot_attack(31)

    engine.add_modifier("set_eye", 0, source_uid=5, target_uid=1, value=7)
    assert engine.cannot_attack(1)
    assert not engine.cannot_attack(31)


def test_balena_tie_is_exposed_as_a_real_human_choice() -> None:
    engine = GameEngine(245, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 52, 0)
    _put_malediction(engine, 1, 0)
    _put_malediction(engine, 31, 1)
    engine.add_modifier("set_eye", 0, source_uid=52, target_uid=1, value=6)
    engine.add_modifier("set_eye", 0, source_uid=52, target_uid=31, value=6)
    human = HumanDecisionBot()
    engine.bots[0] = human

    human.reset_choices([])
    try:
        engine.cannot_attack(1)
    except ChoiceRequired as required:
        assert required.request["purpose"] == "highest_eye_block"
        assert set(required.request["candidate_uids"]) == {1, 31}
    else:
        raise AssertionError("Il pareggio di Balena deve chiedere quale carta bloccare.")

    human.reset_choices([31])
    assert not engine.cannot_attack(1)
    assert engine.cannot_attack(31)


def test_balena_calo_lock_survives_balena_leaving_the_field() -> None:
    engine = GameEngine(239, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    _put_malediction(engine, 52, 0)
    _put_malediction(engine, 31, 1)
    engine.bots[0] = ScriptedBot(engine.bots[0], cards={"must_attack_any": [31]})

    engine.resolve_calo(52, 0)
    engine.move_to_void_without_break(52, "test Balena lascia il campo")

    locks = [
        modifier
        for modifier in engine.modifiers
        if modifier.kind == "must_attack_uid" and modifier.target_uid == 31
    ]
    assert len(locks) == 1
    assert locks[0].value == 52
    assert locks[0].starts_turn == 4


def test_torri_can_swap_two_enemy_maledictions() -> None:
    engine = GameEngine(240, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 53, 0)
    _put_malediction(engine, 31, 1)
    _put_malediction(engine, 32, 1)
    first_eye = engine.original_eye(31)
    second_eye = engine.original_eye(32)
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"eye_reference_any": [31], "eye_reference_partner": [32]},
    )

    engine.resolve_thunder_sand_glyph(53, 0)

    assert engine.original_eye(31) == second_eye
    assert engine.original_eye(32) == first_eye


def test_new_cadenza_can_replace_the_old_pure_cadenza_at_the_limit() -> None:
    engine = GameEngine(241, deck="TuonoSabbia", auto_setup=False)
    for uid in (7, 1, 2, 3):
        _put_malediction(engine, uid, 0)
    _put_hand(engine, 26, 0)

    assert engine.can_play_malediction(0, 26)
    assert engine.play_card(26, 0, "Maledizione", calata=True)
    assert 7 in engine.void
    assert 26 in engine.players[0].maledictions
    assert engine.used_malediction_slots(0) == 4


def test_bot_chooses_karma_when_the_bonus_can_be_converted_into_a_bless() -> None:
    engine = GameEngine(242, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    engine.phase = "main"
    engine.players[0].actions = 1
    _put_malediction(engine, 51, 0)
    _put_malediction(engine, 31, 1, corrupted=True)

    karma_before = engine.karma(51)
    engine._resolve_thunder_sand_impulse(5, 0)

    assert engine.karma(51) == karma_before + 1


def test_pangolino_bot_breaks_enemy_sigil_when_own_conversion_is_illegal() -> None:
    engine = GameEngine(243, deck="TuonoSabbia", auto_setup=False)
    for uid in (1, 2, 3, 4):
        _put_malediction(engine, uid, 0, corrupted=True)
    _put_prayer(engine, 10, 0)
    _put_prayer(engine, 52, 1)

    engine._resolve_thunder_sand_impulse(43, 0)

    assert engine.cards[10].zone == Zone.PRAYER
    assert engine.cards[52].zone == Zone.VOID


def test_bot_values_a_closed_sigil_as_future_setup_not_active_effect() -> None:
    engine = GameEngine(244, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 10, 0, open_=True)
    open_value = engine.card_value(10, 0)

    engine.cards[10].seal_open = False
    closed_value = engine.card_value(10, 0)

    assert closed_value < open_value
    assert closed_value > 0


def test_voce_tonante_respects_attack_limit_and_consumes_extra_attacks() -> None:
    engine = GameEngine(228, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    _put_prayer(engine, 23, 0)
    _put_malediction(engine, 6, 0)
    _put_malediction(engine, 31, 1)
    engine.charge_card(4, 0, "test Marchio")
    assert engine.mark_with_charge(31, 0, "test Marchio", marker_uid=4)
    engine.cards[6].attacked_turn = engine.turn_number

    engine.resolve_prayer_effect(23, 0)
    assert engine.last_attack is None
    assert not engine.cards[31].corrupted

    engine.add_modifier(
        "extra_attacks",
        0,
        source_uid=23,
        target_uid=6,
        value=1,
        expires_after_turn=engine.turn_number,
    )
    engine.resolve_prayer_effect(23, 0)

    assert engine.last_attack is not None
    assert engine.last_attack["attacker_uid"] == 6
    assert engine.last_attack["target_uid"] == 31
    assert engine.cards[31].corrupted
    assert engine.extra_attacks_remaining(6) == 0


def test_quiete_ambita_cannot_attack_directly_while_its_effect_is_active() -> None:
    engine = GameEngine(229, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.phase = "main"
    engine.players[0].actions = 1
    _put_malediction(engine, 40, 0)

    actions = engine.legal_actions(0)
    assert not any(action.kind == "attack_direct" for action in actions)

    engine.add_modifier(
        "suppress_effect",
        1,
        source_uid=31,
        target_uid=40,
        expires_after_turn=engine.turn_number,
    )
    actions = engine.legal_actions(0)
    assert any(action.kind == "attack_direct" for action in actions)


def test_vetro_preview_applies_its_charge_before_checking_attack_legality() -> None:
    engine = GameEngine(230, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    engine.phase = "main"
    engine.players[0].actions = 1
    _put_malediction(engine, 10, 0, corrupted=True)
    _put_malediction(engine, 57, 1)
    _put_prayer(engine, 8, 1)
    engine.charge_card(2, 1, "test Marchio")
    assert engine.mark_with_charge(10, 1, "test Marchio", marker_uid=2)
    charges_before_preview = list(engine.players[1].charges)

    preview = next(
        item
        for item in engine.attack_target_previews(0, 10)
        if item["target_uid"] == 57
    )

    assert preview["attacker_eye"] == 8
    assert preview["defender_eye"] == 8
    assert preview["outcome"] == "tie"
    assert not preview["allowed"]
    assert engine.players[1].charges == charges_before_preview


def test_sil_and_pagina_pay_their_costs_before_the_play_choice() -> None:
    sil = GameEngine(209, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(sil, 5, 0)
    sil.bots[0] = ScriptedBot(
        sil.bots[0],
        cards={"cost": [5], "play": [5]},
    )
    sil._resolve_thunder_sand_impulse(31, 0)
    assert sil.cards[5].zone == Zone.MALEDICTION
    assert sil.cards[5].stasis

    pagina = GameEngine(210, deck="TuonoSabbia", auto_setup=False)
    _put_hand(pagina, 1, 0)
    _put_hand(pagina, 2, 0)
    pagina.bots[0] = ScriptedBot(
        pagina.bots[0],
        cards={"play": [1]},
        modes=["Preghiera"],
    )
    pagina._resolve_thunder_sand_impulse(33, 0)
    assert pagina.cards[1].zone == Zone.PRAYER
    assert pagina.cards[2].zone == Zone.VOID

    spezzata = GameEngine(225, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(spezzata, 33, 0)
    _put_malediction(spezzata, 41, 1)
    spezzata.charge_card(2, 0, "test")
    spezzata.place_mark(41, 2, 0, "test")
    spezzata.bots[0] = ScriptedBot(spezzata.bots[0], cards={"play": [4]})
    spezzata.break_card(33, reason="test Pagina SPEZZATA")
    assert spezzata.cards[4].zone == Zone.MALEDICTION
    assert spezzata.is_marked(41), "Giocare dal Mazzo non deve attivare CALO"


def test_pangolino_conversion_has_stasis_but_tomo_conversion_does_not() -> None:
    pangolino = GameEngine(211, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(pangolino, 3, 0)
    pangolino.bots[0] = ScriptedBot(
        pangolino.bots[0],
        cards={"convert": [3]},
        options={"pangolino_mode": ["Converti un tuo Sigillo"]},
    )
    pangolino._resolve_thunder_sand_impulse(43, 0)
    assert pangolino.cards[3].zone == Zone.MALEDICTION
    assert pangolino.cards[3].stasis
    assert not pangolino.cards[3].corrupted

    tomo = GameEngine(212, deck="TuonoSabbia", auto_setup=False)
    engine_bot = ScriptedBot(tomo.bots[0], cards={"convert_charge": [1]})
    tomo.bots[0] = engine_bot
    _put_hand(tomo, 2, 0)
    tomo.charge_card(1, 0, "test")
    tomo._resolve_thunder_sand_impulse(50, 0)
    assert tomo.cards[1].zone == Zone.MALEDICTION
    assert not tomo.cards[1].stasis
    assert 2 in tomo.players[0].hand


def test_mark_penalties_apply_only_to_opponents_and_cavalcare_buffs_sigil_cards() -> None:
    marks = GameEngine(213, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(marks, 14, 0)
    _put_malediction(marks, 43, 0)
    _put_malediction(marks, 41, 1)
    marks.charge_card(1, 0, "test")
    marks.place_mark(43, 1, 0, "test proprio")
    marks.charge_card(2, 0, "test")
    marks.place_mark(41, 2, 0, "test avversario")
    assert marks.eye(43) == marks.original_eye(43)
    assert marks.eye(41) == max(0, marks.original_eye(41) - 2)

    cavalry = GameEngine(214, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(cavalry, 56, 0)
    _put_malediction(cavalry, 1, 0)
    _put_malediction(cavalry, 2, 0)
    _put_malediction(cavalry, 31, 0)
    assert cavalry.definition(1).prayer_type == PrayerType.SIGIL
    assert cavalry.definition(2).prayer_type == PrayerType.IMPULSE
    assert cavalry.eye(1) == cavalry.original_eye(1) + 2
    assert cavalry.eye(2) == cavalry.original_eye(2)


def test_cavalcare_toggles_on_calo_but_pays_before_post_attack_opening() -> None:
    calo = GameEngine(215, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(calo, 56, 0)
    _put_prayer(calo, 3, 1, open_=False)
    calo.bots[0] = ScriptedBot(calo.bots[0], cards={"sigil_state_required": [3]})
    calo.resolve_calo(56, 0)
    assert calo.cards[3].seal_open

    attack = GameEngine(216, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(attack, 56, 0)
    _put_malediction(attack, 2, 0)
    _put_prayer(attack, 1, 0, open_=False)
    attack.charge_card(5, 0, "test")
    attack.bots[0] = ScriptedBot(
        attack.bots[0],
        cards={"open_own_sigil": [1]},
        options={"open_sigil_after_attack": [True]},
    )
    attack.resolve_after_attack(56, None, 0, attack.eye(56), 0, 56)
    assert attack.players[0].charges == []
    assert attack.cards[1].seal_open


def test_dadi_always_charges_itself_and_only_even_adds_the_deck_top() -> None:
    even = GameEngine(217, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(even, 20, 0)
    _remove_everywhere(even, 1)
    even.reset_card_outside_field(1, Zone.DECK, None)
    even.deck.append(1)
    even.rng = FixedRoll(even.rng, 2)
    even._resolve_thunder_sand_impulse(20, 0)
    assert even.players[0].charges == [20, 1]

    odd = GameEngine(218, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(odd, 20, 0)
    _remove_everywhere(odd, 1)
    odd.reset_card_outside_field(1, Zone.DECK, None)
    odd.deck.append(1)
    odd.rng = FixedRoll(odd.rng, 3)
    odd._resolve_thunder_sand_impulse(20, 0)
    assert odd.players[0].charges == [20]
    assert odd.deck[-1] == 1


def test_elmo_bonus_changes_while_corrupted_and_dedalo_stays_corrupted() -> None:
    engine = GameEngine(219, deck="TuonoSabbia", auto_setup=False)
    engine.active_player = 1
    engine.turn_number = 2
    _put_malediction(engine, 55, 0)
    _put_malediction(engine, 31, 0)
    assert engine.eye(55) == engine.original_eye(55) + 1
    assert engine.eye(31) == engine.original_eye(31) + 1

    engine.corrupt_card(55, 0, "test")
    assert engine.eye(55) == engine.original_eye(55) + 2
    assert engine.eye(31) == engine.original_eye(31) + 2

    dedalo = GameEngine(220, deck="TuonoSabbia", auto_setup=False)
    dedalo.active_player = 0
    dedalo.turn_number = 2
    _put_malediction(dedalo, 41, 0, corrupted=True)
    dedalo.end_turn()
    assert dedalo.cards[41].corrupted


def test_obelisco_uses_colosso_count_and_only_charges_its_controllers_cards() -> None:
    engine = GameEngine(221, deck="TuonoSabbia", auto_setup=False)
    engine.active_player = 0
    _put_malediction(engine, 1, 0)
    _put_malediction(engine, 2, 0)
    _put_malediction(engine, 16, 1)
    _put_malediction(engine, 3, 1)
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"sacrifice": [1]},
        options={"charge_broken": [True]},
    )
    engine.bots[1] = ScriptedBot(
        engine.bots[1],
        cards={"sacrifice": [16]},
    )

    engine._resolve_thunder_sand_impulse(46, 0)
    assert engine.players[0].maledictions == [2]
    assert engine.players[0].charges == [1]
    assert engine.players[1].maledictions == [3]
    assert engine.players[1].charges == []
    assert engine.cards[16].zone == Zone.VOID
    assert engine.force_end_turn


def test_clessidra_gains_one_action_without_a_later_penalty() -> None:
    engine = GameEngine(222, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 1
    engine.active_player = 0
    engine.players[0].actions = 1

    engine._resolve_thunder_sand_impulse(58, 0)
    engine._resolve_thunder_sand_impulse(58, 0)
    assert engine.players[0].actions == 3

    engine.turn_number = 3
    engine.active_player = 0
    engine.start_turn()
    assert engine.players[0].actions == 3


def test_exar_breaks_using_effective_eye_and_charge_count() -> None:
    engine = GameEngine(223, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 53, 1)
    _put_malediction(engine, 41, 1)
    engine.charge_card(1, 0, "test")
    engine.charge_card(3, 0, "test")

    engine._resolve_thunder_sand_impulse(2, 0)
    assert engine.cards[53].zone == Zone.VOID
    assert engine.cards[41].zone == Zone.MALEDICTION


def test_sil_gains_karma_not_eye_for_each_mark() -> None:
    engine = GameEngine(240, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 31, 0)
    _put_malediction(engine, 32, 1)
    engine.charge_card(4, 0, "test")
    engine.charge_card(5, 0, "test")
    assert engine.place_mark(31, 4, 0, "test")
    assert engine.place_mark(32, 5, 0, "test")

    assert engine.eye(31) == 6
    assert engine.karma(31) == 2


def test_deserto_zaffiro_charges_two_cards_when_corrupted() -> None:
    engine = GameEngine(241, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 37, 0)
    deck_before = len(engine.deck)

    assert engine.corrupt_card(37, 1, "test")
    assert len(engine.players[0].charges) == 2
    assert len(engine.deck) == deck_before - 2


def test_sciame_and_scarabei_attack_marked_cards_for_free() -> None:
    for attacker_uid in (5, 39):
        engine = GameEngine(242 + attacker_uid, deck="TuonoSabbia", auto_setup=False)
        engine.turn_number = 3
        _put_malediction(engine, attacker_uid, 0)
        _put_malediction(engine, 31, 1)
        _put_malediction(engine, 32, 1)
        engine.charge_card(4, 0, "test")
        assert engine.place_mark(31, 4, 0, "test")

        assert engine.attack_cost(attacker_uid, 31) == 0
        assert engine.attack_cost(attacker_uid, 32) == 1


def test_scarabei_are_played_when_spent_as_a_charge() -> None:
    engine = GameEngine(243, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    engine.charge_card(39, 0, "test")

    assert engine.spend_charges(0, 1, "test", chooser=0) == [39]
    assert engine.cards[39].zone == Zone.MALEDICTION
    assert engine.cards[39].controller == 0


def test_volo_grants_one_free_play_for_each_prayer_type() -> None:
    engine = GameEngine(244, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 3
    for uid in (8, 1, 2):
        _put_hand(engine, uid, 0)

    engine._resolve_thunder_sand_impulse(17, 0)
    actions = engine.legal_actions(0)
    assert next(action for action in actions if action.card_uid == 8 and action.kind == "play_prayer").cost == 0
    assert next(action for action in actions if action.card_uid == 1 and action.kind == "play_prayer").cost == 0
    assert next(action for action in actions if action.card_uid == 2 and action.kind == "play_prayer").cost == 0

    glyph_action = next(
        action for action in actions
        if action.card_uid == 8 and action.kind == "play_prayer"
    )
    engine.execute_action(glyph_action, 0)
    _put_hand(engine, 12, 0)
    second_glyph = next(
        action for action in engine.legal_actions(0)
        if action.card_uid == 12 and action.kind == "play_prayer"
    )
    assert second_glyph.cost == 1


def test_ruota_makes_the_selected_card_free_for_all_three_attacks() -> None:
    engine = GameEngine(245, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    _put_prayer(engine, 21, 0)
    _put_malediction(engine, 5, 0)
    _put_malediction(engine, 6, 0)
    _put_malediction(engine, 31, 1)
    for charge_uid in (1, 2, 3):
        engine.charge_card(charge_uid, 0, "test")
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"spend_charge": [1, 2, 3], "extra_attacks": [5]},
    )

    engine.use_glyph(21, 0)
    assert engine.cards[6].zone == Zone.VOID
    assert engine.extra_attacks_remaining(5) == 2
    assert engine.attack_cost(5, 31) == 0


def test_voce_uses_an_opponent_charge_to_mark_the_chosen_malediction() -> None:
    engine = GameEngine(246, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    _put_malediction(engine, 23, 0)
    _put_malediction(engine, 31, 1)
    engine.charge_card(5, 1, "test")
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"mark_any": [31]},
    )

    engine.resolve_after_attack(23, 31, 0, 7, 6, 23)
    assert engine.mark_for(31) == 5
    assert engine.cards[5].controller == 1


def test_clessidra_prayer_effect_replays_it_as_a_prayer() -> None:
    engine = GameEngine(247, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_prayer(engine, 58, 0)
    engine.charge_card(4, 0, "test")
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"spend_charge": [4]},
        options={"play_clessidra_as_prayer": [True]},
    )

    engine._resolve_thunder_sand_impulse(58, 0)
    assert engine.players[0].actions == 3
    assert engine.cards[58].zone == Zone.VOID
    assert engine.players[0].charges == []


def test_drass_marks_only_after_a_thunder_malediction_is_played() -> None:
    engine = GameEngine(249, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    _put_prayer(engine, 3, 0)
    _put_malediction(engine, 31, 1)
    _put_hand(engine, 2, 0)
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"mark": [31]},
    )

    assert engine.play_card(2, 0, "Preghiera", calata=True)
    assert engine.mark_for(31) is None

    _put_hand(engine, 2, 0)
    assert engine.play_card(2, 0, "Maledizione", calata=True)
    assert engine.mark_for(31) is not None


def test_pulsar_is_taken_directly_without_entering_the_void() -> None:
    engine = GameEngine(248, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    _put_hand(engine, 7, 0)
    _put_hand(engine, 5, 1)
    engine.bots[1] = ScriptedBot(
        engine.bots[1],
        cards={"discard_own": [5]},
        options={"recover_impulse": [True]},
    )

    assert engine.play_card(7, 0, "Preghiera", calata=True)
    assert engine.cards[7].zone == Zone.HAND
    assert engine.cards[7].controller == 1
    assert 7 in engine.players[1].hand
    assert 7 not in engine.void
    assert engine.cards[5].zone == Zone.VOID


def test_vocio_is_taken_directly_without_entering_the_void() -> None:
    engine = GameEngine(249, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    _put_hand(engine, 34, 0)
    _put_malediction(engine, 31, 1)
    engine.charge_card(5, 1, "test")
    engine.bots[0] = ScriptedBot(
        engine.bots[0],
        cards={"suppress": [31]},
    )
    engine.bots[1] = ScriptedBot(
        engine.bots[1],
        cards={"spend_charge": [5]},
        options={"recover_impulse": [True]},
    )

    assert engine.play_card(34, 0, "Preghiera", calata=True)
    assert engine.cards[34].zone == Zone.HAND
    assert engine.cards[34].controller == 1
    assert 34 in engine.players[1].hand
    assert 34 not in engine.void
