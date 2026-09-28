from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[2] / "public" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from bless_sim.bots import BOT_NAMES  # noqa: E402
from bless_sim.engine import GameEngine  # noqa: E402
from bless_sim.model import Zone  # noqa: E402


def _put_malediction(engine: GameEngine, uid: int, player: int, *, stasis: bool = False) -> None:
    if uid in engine.deck:
        engine.deck.remove(uid)
    card = engine.cards[uid]
    card.zone = Zone.MALEDICTION
    card.controller = player
    card.stasis = stasis
    engine.players[player].maledictions.append(uid)


def _put_hand(engine: GameEngine, uid: int, player: int) -> None:
    if uid in engine.deck:
        engine.deck.remove(uid)
    card = engine.cards[uid]
    card.zone = Zone.HAND
    card.controller = player
    engine.players[player].hand.append(uid)


def _put_prayer(engine: GameEngine, uid: int, player: int) -> None:
    if uid in engine.deck:
        engine.deck.remove(uid)
    card = engine.cards[uid]
    card.zone = Zone.PRAYER
    card.controller = player
    card.echo_used_turn = -1
    engine.players[player].prayers.append(uid)


class _NoTargetChoiceBot:
    def choose_card(self, *_args, **_kwargs):
        raise AssertionError("L'Obelisco non deve chiedere di scegliere una carta.")


class _RecordedChoiceBot:
    def __init__(self, answers: dict[str, int]) -> None:
        self.answers = answers
        self.candidates: dict[str, list[int]] = {}

    def choose_card(
        self,
        _engine: GameEngine,
        _player: int,
        candidates,
        purpose: str,
        **_kwargs,
    ) -> int | None:
        choices = list(candidates)
        self.candidates[purpose] = choices
        answer = self.answers.get(purpose)
        assert answer is None or answer in choices, (purpose, answer, choices)
        return answer


def test_only_requested_bot_families_exist() -> None:
    assert BOT_NAMES == ["Bot"]


def test_obelisco_del_sole_breaks_every_shadow_without_target_choice() -> None:
    engine = GameEngine(22039, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    _put_malediction(engine, 31, 0)
    _put_prayer(engine, 32, 1)
    engine.bots = [_NoTargetChoiceBot(), _NoTargetChoiceBot()]

    engine.resolve_prayer_effect(22, 0)

    assert engine.cards[31].zone == Zone.VOID
    assert engine.cards[32].zone == Zone.VOID
    assert engine.force_end_turn is True


def test_oscurita_can_set_the_eye_of_an_opposing_malediction() -> None:
    engine = GameEngine(4201, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 3
    _put_prayer(engine, 42, 0)  # Oscurità che sta risolvendo il proprio Impulso.
    _put_malediction(engine, 31, 0)  # Altra Ombra propria, Occhio originale 4.
    _put_malediction(engine, 1, 1)  # Bersaglio avversario.
    chooser = _RecordedChoiceBot(
        {"darkness_target": 1, "darkness_reference_enemy": 31}
    )
    engine.bots = [chooser, chooser]

    engine.resolve_prayer_effect(42, 0)

    assert 1 in chooser.candidates["darkness_target"]
    assert engine.eye(1) == engine.original_eye(31)


def test_oscurita_cannot_use_itself_as_the_eye_reference() -> None:
    engine = GameEngine(4202, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 3
    _put_prayer(engine, 42, 0)
    _put_malediction(engine, 31, 0)
    _put_malediction(engine, 1, 1)
    chooser = _RecordedChoiceBot(
        {"darkness_target": 1, "darkness_reference_enemy": 31}
    )
    engine.bots = [chooser, chooser]

    engine.resolve_prayer_effect(42, 0)

    references = chooser.candidates["darkness_reference_enemy"]
    assert 31 in references
    assert 42 not in references


def test_attack_event_identifies_both_cards_for_the_table_animation() -> None:
    engine = GameEngine(113, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 8, 0)
    _put_malediction(engine, 31, 1)
    action = next(item for item in engine.legal_actions(0) if item.kind == "attack")

    engine.execute_action(action, 0)

    assert engine.last_attack is not None
    assert engine.last_attack["attacker_uid"] == 8
    assert engine.last_attack["target_uid"] == 31
    assert engine.last_attack["target_player"] == 1


def test_silent_combat_preview_applies_rivalry_before_unlocking_attack() -> None:
    engine = GameEngine(18154, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 18, 0)  # Raggio Vanescente: Rivalita', 3 Occhio.
    _put_malediction(engine, 54, 1)  # Oltretomba: 3 Occhio.
    engine.cards[18].corrupted = True
    engine.cards[54].corrupted = True

    preview = engine.simulate_combat_silently(18, 54)
    legal_attacks = [
        action
        for action in engine.legal_actions(0)
        if action.kind == "attack" and action.card_uid == 18 and action.target_uid == 54
    ]

    assert preview["attacker_eye"] == 6
    assert preview["defender_eye"] == 3
    assert preview["attacker_rivalry_applied"] is True
    assert preview["outcome"] == "attacker_win"
    assert len(legal_attacks) == 1


def test_cancelli_bond_changes_effective_form_before_rivalry_preview() -> None:
    engine = GameEngine(6018154, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 18, 0)  # Raggio Vanescente, Luce.
    _put_malediction(engine, 54, 1)  # Oltretomba nasce Ombra.
    _put_prayer(engine, 60, 1)  # Cancelli di Mezzo inverte la forma legata.
    engine.cards[60].attached_to = 54
    engine.cards[18].corrupted = True
    engine.cards[54].corrupted = True

    preview = next(
        item for item in engine.attack_target_previews(0, 18)
        if item["target_uid"] == 54
    )
    legal_attacks = [
        action
        for action in engine.legal_actions(0)
        if action.kind == "attack" and action.card_uid == 18 and action.target_uid == 54
    ]

    assert preview["attacker_forms"] == ["Luce"]
    assert preview["defender_forms"] == ["Luce"]
    assert preview["attacker_eye"] == 3
    assert preview["outcome"] == "tie"
    assert preview["attacker_rivalry_applied"] is False
    assert preview["allowed"] is False
    assert "Rivalita' non si applica" in preview["reason"]
    assert legal_attacks == []


def test_bot_does_not_remove_stasis_without_an_action_to_attack() -> None:
    for name in BOT_NAMES:
        engine = GameEngine(91, (name, name), auto_setup=False)
        engine.turn_number = 2
        engine.active_player = 0
        engine.players[0].actions = 1
        _put_malediction(engine, 1, 0, stasis=True)

        chosen = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))

        assert chosen.kind == "pass"


def test_bot_attacks_a_pure_card_to_prepare_corruption() -> None:
    for name in BOT_NAMES:
        engine = GameEngine(113, (name, name), auto_setup=False)
        engine.turn_number = 2
        engine.active_player = 0
        engine.players[0].actions = 1
        _put_malediction(engine, 8, 0)
        _put_malediction(engine, 31, 1)

        chosen = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))

        assert chosen.kind == "attack"
        assert chosen.target_uid == 31


def test_bot_prefers_ali_di_som_to_an_inactive_obelisk() -> None:
    engine = GameEngine(68878711, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 1
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 23, 0, stasis=True)  # Orizzonte e' Luce.
    _put_hand(engine, 39, 0)  # Obelisco del Buio: effetto inattivo.
    _put_hand(engine, 36, 0)  # Ali di Som.

    chosen = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))

    assert chosen.kind == "play_malediction"
    assert chosen.card_uid == 36


def test_win_conditions_use_eye_after_rivalry_and_other_combat_effects() -> None:
    engine = GameEngine(68878712, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    _put_malediction(engine, 23, 0)  # Orizzonte, 5 Occhio.
    _put_malediction(engine, 36, 1)  # Ali di Som.
    _put_prayer(engine, 3, 0)  # Rivalità collegata a Orizzonte.
    engine.cards[3].attached_to = 23

    assert engine.eye(23) == 5
    assert engine.combat_eye(23, 36) == 8
    assert engine.predict_combat(23, 36) == "defender_win"
    assert engine.predict_combat(36, 23) == "attacker_win"

    _put_malediction(engine, 40, 1)  # Nube Mentale vede l'Occhio modificato.
    assert engine.predict_combat(40, 23) == "attacker_win"

    engine.cards[23].corrupted = True
    engine.cards[36].corrupted = True
    engine.resolve_combat(23, 36)

    assert engine.cards[23].zone == Zone.VOID
    assert engine.cards[36].zone == Zone.MALEDICTION


def test_seed_68878711_does_not_build_an_obelisk_setup_that_turns_itself_off() -> None:
    engine = GameEngine(68878711, ("Bot", "Bot"), record_replay=True)
    engine.start_turn()

    first_action = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))
    assert first_action.kind == "play_malediction"
    assert first_action.card_uid != 39
    engine.execute_action(first_action, 0)

    second_action = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))
    assert second_action.kind == "play_malediction"
    assert second_action.card_uid != 39


def test_crepuscolo_does_not_discard_without_a_corrupted_target() -> None:
    engine = GameEngine(68878711, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_hand(engine, 59, 0)  # Crepuscolo.
    _put_hand(engine, 42, 0)  # Carta che non deve essere scartata a vuoto.

    action = next(
        candidate
        for candidate in engine.legal_actions(0)
        if candidate.kind == "play_malediction" and candidate.card_uid == 59
    )
    engine.execute_action(action, 0)

    assert 42 in engine.players[0].hand
    assert 42 not in engine.void


def test_bot_invokes_echo_to_prepare_a_bless_attack() -> None:
    engine = GameEngine(317, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.players[0].actions = 2
    _put_malediction(engine, 14, 0)  # Elica Empirea, Luce con 4 Occhio.
    _put_malediction(engine, 34, 1)  # Lenora, 6 Occhio.
    engine.cards[34].corrupted = True
    _put_prayer(engine, 23, 0)  # Orizzonte: -2 se attaccata da una Luce.

    first_action = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))
    assert first_action.kind == "invoke"
    assert first_action.card_uid == 23

    engine.execute_action(first_action, 0)
    second_action = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))
    assert second_action.kind == "attack"
    assert second_action.card_uid == 14
    assert second_action.target_uid == 34

    engine.execute_action(second_action, 0)
    assert engine.players[0].score == 1
    assert 34 in engine.players[0].altar


def test_eye_buff_never_targets_an_enemy_card() -> None:
    engine = GameEngine(433, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 41, 1)  # Unico possibile bersaglio in campo: avversario.
    _put_hand(engine, 16, 0)  # Fiamma Perpetua: +2 Occhio al bersaglio.

    action = next(
        candidate
        for candidate in engine.legal_actions(0)
        if candidate.kind == "play_prayer" and candidate.card_uid == 16
    )
    engine.execute_action(action, 0)

    assert not [modifier for modifier in engine.modifiers if modifier.kind == "target_eye_add"]
    assert engine.telemetry.own_eye_buffs[0] == 0


def test_bot_buffs_oltretomba_to_bless_for_more_points() -> None:
    engine = GameEngine(901, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    engine.players[0].actions = 2
    _put_malediction(engine, 54, 0)  # Oltretomba: 3 Occhio, 3 Karma.
    _put_malediction(engine, 45, 0)  # Volo Notturno: 7 Occhio, ma solo 1 Karma.
    _put_malediction(engine, 41, 1)  # Vetta Solitaria: 5 Occhio.
    engine.cards[41].corrupted = True
    _put_hand(engine, 16, 0)  # Fiamma Perpetua Eco: +2 Occhio.

    first_action = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))
    assert first_action.kind == "play_prayer"
    assert first_action.card_uid == 16
    engine.execute_action(first_action, 0)

    eye_modifier = next(
        modifier for modifier in engine.modifiers if modifier.kind == "target_eye_add"
    )
    assert eye_modifier.target_uid == 54
    second_action = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))
    assert second_action.kind == "attack"
    assert second_action.card_uid == 54
    engine.execute_action(second_action, 0)

    assert engine.players[0].score == 3
    assert 41 in engine.players[0].altar
    assert engine.telemetry.high_karma_eye_buffs[0] == 1


def test_bot_invests_in_an_echo_for_the_next_turn() -> None:
    engine = GameEngine(902, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 54, 0, stasis=True)
    _put_malediction(engine, 41, 1)
    engine.cards[41].corrupted = True
    _put_hand(engine, 16, 0)

    chosen = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))

    # Non puo' attaccare in questo turno: l'Eco viene tenuta in campo per
    # poter essere invocata di nuovo dopo la risposta dell'avversario.
    assert chosen.kind == "play_prayer"
    assert chosen.card_uid == 16


def test_unified_bot_uses_both_maledictions_and_prayers() -> None:
    action_totals = Counter()
    for index in range(12):
        result = GameEngine(
            7000 + index * 97,
            ("Bot", "Bot"),
            first_player=index % 2,
        ).play_game()
        for player in (0, 1):
            action_totals.update(result.telemetry.chosen_action_kinds[player])

    assert action_totals["play_prayer"] > 0
    assert action_totals["play_malediction"] > 0


def test_ts_bot_plays_a_glyph_to_prepare_end_turn_charges() -> None:
    engine = GameEngine(83001, ("Bot", "Bot"), deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 1
    _put_malediction(engine, 1, 0)
    _put_malediction(engine, 31, 1)
    _put_hand(engine, 8, 0)  # ElettroNova puo' essere Maledizione o Glifo.

    chosen = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))

    assert chosen.kind == "play_prayer"
    assert chosen.card_uid == 8


def test_ts_bot_keeps_a_charge_candidate_in_its_end_turn_mulligan() -> None:
    engine = GameEngine(83002, ("Bot", "Bot"), deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    for uid in (10, 16, 51, 57):
        _put_hand(engine, uid, 0)
    _put_prayer(engine, 8, 0)

    selected = engine.bots[0].choose_mulligan(engine, 0, initial=False)
    charged = engine.bots[0].choose_mulligan_charge(engine, 0, selected)

    assert selected
    assert charged in selected
    engine.perform_mulligan(0, initial=False)
    assert len(engine.players[0].charges) == 1
    assert engine.telemetry.charges_created[0] == 1


def test_corona_di_stirpe_reattaches_when_its_host_breaks() -> None:
    engine = GameEngine(13048, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 4
    engine.active_player = 0
    _put_malediction(engine, 48, 0)  # Costellazione Errante: Occhio originale 4.
    _put_malediction(engine, 1, 0)   # Re Luce: Occhio originale 3.
    _put_prayer(engine, 13, 0)       # Corona di Stirpe come Legame.
    engine.cards[13].attached_to = 48

    engine.break_card(48, reason="test ricollegamento")

    assert engine.cards[48].zone == Zone.VOID
    assert engine.cards[13].zone == Zone.PRAYER
    assert engine.cards[13].attached_to == 1
    assert 13 not in engine.void


def test_final_turns_follow_non_activator_5_3_1_and_activator_4_2() -> None:
    engine = GameEngine(50123, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 7
    engine.active_player = 0
    engine.trigger_final_rounds(0, "test")

    # Il turno che attiva il conto non e' uno dei cinque Turni Finali.
    engine.end_turn()
    observed: list[tuple[int, int]] = []
    while not engine.game_over:
        assert engine.final_turns_remaining is not None
        observed.append((engine.active_player, engine.final_turns_remaining))
        engine.end_turn()

    assert observed == [(1, 5), (0, 4), (1, 3), (0, 2), (1, 1)]


def test_bot_still_offers_and_blesses_during_the_last_final_turn() -> None:
    engine = GameEngine(771, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 12
    engine.active_player = 0
    engine.final_turns_remaining = 1
    engine.final_trigger_player = 1
    _put_malediction(engine, 45, 0)  # Solo 1 Karma.
    _put_malediction(engine, 31, 1)
    engine.cards[45].attacked_turn = engine.turn_number

    assert engine.bots[0].choose_offer(engine, 0, 31) is True


def test_fato_exposes_a_structured_dice_result_for_the_ui() -> None:
    engine = GameEngine(57001, ("Bot", "Bot"), auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 57, 0)
    _put_malediction(engine, 31, 1)
    action = next(item for item in engine.legal_actions(0) if item.kind == "attack")

    engine.execute_action(action, 0)

    assert engine.last_fate is not None
    assert engine.last_fate["card_uid"] == 57
    assert engine.last_fate["choice"] in {"Pari", "Dispari"}
    assert 1 <= int(engine.last_fate["roll"]) <= 6
    assert isinstance(engine.last_fate["won"], bool)


if __name__ == "__main__":
    test_only_requested_bot_families_exist()
    test_obelisco_del_sole_breaks_every_shadow_without_target_choice()
    test_attack_event_identifies_both_cards_for_the_table_animation()
    test_silent_combat_preview_applies_rivalry_before_unlocking_attack()
    test_cancelli_bond_changes_effective_form_before_rivalry_preview()
    test_bot_does_not_remove_stasis_without_an_action_to_attack()
    test_bot_attacks_a_pure_card_to_prepare_corruption()
    test_bot_prefers_ali_di_som_to_an_inactive_obelisk()
    test_seed_68878711_does_not_build_an_obelisk_setup_that_turns_itself_off()
    test_crepuscolo_does_not_discard_without_a_corrupted_target()
    test_bot_invokes_echo_to_prepare_a_bless_attack()
    test_eye_buff_never_targets_an_enemy_card()
    test_bot_buffs_oltretomba_to_bless_for_more_points()
    test_bot_invests_in_an_echo_for_the_next_turn()
    test_unified_bot_uses_both_maledictions_and_prayers()
    test_ts_bot_plays_a_glyph_to_prepare_end_turn_charges()
    test_ts_bot_keeps_a_charge_candidate_in_its_end_turn_mulligan()
    test_corona_di_stirpe_reattaches_when_its_host_breaks()
    test_final_turns_follow_non_activator_5_3_1_and_activator_4_2()
    test_bot_still_offers_and_blesses_during_the_last_final_turn()
    test_fato_exposes_a_structured_dice_result_for_the_ui()
    print("bots: ok")
