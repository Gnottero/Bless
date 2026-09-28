from __future__ import annotations

import sys
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[2] / "public" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from bless_sim.engine import GameEngine  # noqa: E402
from bless_sim.manual import ChoiceRequired, HumanDecisionBot, ManualGameSession  # noqa: E402
from bless_sim.model import Action, PrayerType, Zone  # noqa: E402
from bless_sim.simulation import SimulationConfig, run_simulation  # noqa: E402
from bless_sim.version import ENGINE_VERSION  # noqa: E402


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


def test_tuono_sabbia_deck_loads_all_cards_and_esordio() -> None:
    engine = GameEngine(1, deck="TuonoSabbia", auto_setup=False)
    assert engine.deck_name == "TuonoSabbia"
    assert len(engine.definitions) == 62
    assert engine.definition(1).form.value == "Tuono"
    assert engine.definition(30).form.value == "Sabbia"
    assert engine.definition(59).form.value == "Duale"
    assert engine.definition(61).traits == ("Esordio",)
    assert engine.definition(61).prayer_type == PrayerType.GLYPH
    assert 61 not in engine.deck and 62 not in engine.deck
    assert engine.image_path(1).endswith("/ThunderSand_01.png")


def test_esordio_assigns_one_card_to_each_player_outside_the_deck() -> None:
    engine = GameEngine(2, deck="TuonoSabbia")
    assert engine.cards[61].controller != engine.cards[62].controller
    assert {engine.cards[61].controller, engine.cards[62].controller} == {0, 1}
    assert engine.cards[61].zone != Zone.DECK
    assert engine.cards[62].zone != Zone.DECK


def test_charge_paid_to_mark_becomes_the_mark_then_goes_to_deck_bottom() -> None:
    engine = GameEngine(3, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 1
    engine.active_player = 0
    _put_prayer(engine, 8, 0)
    _put_malediction(engine, 31, 1)
    engine.charge_card(38, 0, "test")

    engine.use_glyph(8, 0)

    assert engine.players[0].charges == []
    assert engine.mark_for(31) == 38
    assert engine.cards[38].zone == Zone.MARK
    assert engine.cards[38].attached_to == 31
    assert 38 not in engine.deck
    assert 38 not in engine.players[0].maledictions

    engine.remove_mark(31, "test")
    assert engine.cards[38].zone == Zone.DECK
    assert engine.deck[0] == 38


def test_boato_does_not_charge_from_hand_when_a_card_becomes_corrupted() -> None:
    engine = GameEngine(49, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    _put_prayer(engine, 4, 0)
    _put_malediction(engine, 5, 0)
    _put_malediction(engine, 31, 1)
    charge_uid = 7
    _remove_everywhere(engine, charge_uid)
    engine.reset_card_outside_field(charge_uid, Zone.HAND, 0)
    engine.players[0].hand.append(charge_uid)
    assert engine.corrupt_card(31, source_player=0, reason="scontro con Sciame Irrequieto")
    assert charge_uid in engine.players[0].hand
    assert charge_uid not in engine.players[0].charges
    assert charge_uid not in engine.void
    assert engine.cards[charge_uid].zone == Zone.HAND


def test_valle_delle_mante_glyph_costs_one_charge_and_marks() -> None:
    engine = GameEngine(4, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 1
    engine.active_player = 0
    _put_prayer(engine, 38, 0)
    _put_malediction(engine, 31, 1)
    engine.charge_card(5, 0, "test")

    assert engine.glyph_cost(38) == 1
    assert engine.glyph_can_resolve(38, 0)
    engine.use_glyph(38, 0)
    assert engine.mark_for(31) == 5


def test_mark_expires_after_the_next_combat_but_a_new_post_attack_mark_remains() -> None:
    engine = GameEngine(41, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    _put_malediction(engine, 31, 0)
    _put_malediction(engine, 6, 1)
    engine.charge_card(4, 0, "test")
    assert engine.place_mark(31, 4, 0, "test")

    engine.resolve_combat(31, 6)

    assert not engine.is_marked(31)
    assert engine.cards[4].zone == Zone.DECK
    assert engine.deck[0] == 4

    _put_malediction(engine, 23, 0)
    _put_malediction(engine, 32, 1)
    engine.charge_card(5, 1, "test")
    engine.resolve_combat(23, 32)
    assert any(engine.mark_for(uid) == 5 for uid in engine.all_maledictions())
    assert engine.cards[5].controller == 1


def test_a_marked_card_loses_its_mark_after_a_direct_attack() -> None:
    engine = GameEngine(42, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 1
    _put_malediction(engine, 31, 0)
    engine.charge_card(4, 0, "test")
    assert engine.place_mark(31, 4, 0, "test")
    action = next(
        item
        for item in engine.legal_actions(0)
        if item.kind == "attack_direct" and item.card_uid == 31
    )
    engine.execute_action(action, 0)
    assert not engine.is_marked(31)
    assert engine.deck[0] == 4


def test_a_spent_special_charge_is_played_with_replacement_at_four_maledictions() -> None:
    engine = GameEngine(43, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    for uid in (1, 2, 3, 4):
        _put_malediction(engine, uid, 0)
    engine.charge_card(27, 0, "test")

    assert engine.spend_charges(0, 1, "test", chooser=0) == [27]
    assert 27 in engine.players[0].maledictions
    assert engine.eye(27) == engine.original_eye(27) + 1
    assert engine.karma(27) == engine.definition(27).karma + 1
    assert engine.used_malediction_slots(0) == 4
    assert sum(uid in engine.void for uid in (1, 2, 3, 4)) == 1


def test_clessidra_offers_paid_prayer_and_free_charge_modes() -> None:
    engine = GameEngine(44, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 1
    engine.take_to_hand(58, 0, "test")
    engine.charge_card(4, 0, "test")

    actions = [item for item in engine.legal_actions(0) if item.card_uid == 58]
    assert ("play_malediction", "Maledizione", 1) in {
        (item.kind, item.mode, item.cost) for item in actions
    }
    assert ("play_prayer", "Preghiera", 1) in {
        (item.kind, item.mode, item.cost) for item in actions
    }
    assert ("play_malediction", "MaledizioneCarica", 0) in {
        (item.kind, item.mode, item.cost) for item in actions
    }


def test_emblem_doubles_the_final_modified_eye() -> None:
    engine = GameEngine(5, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 1
    _put_malediction(engine, 2, 0, corrupted=True)
    engine.charge_card(3, 0, "test")
    engine.add_modifier("target_eye_add", 0, target_uid=2, value=1)
    assert engine.eye(2) == 4


def test_colossus_costs_two_actions_uses_two_slots_and_corrupts_after_attack() -> None:
    engine = GameEngine(6, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 2
    engine.take_to_hand(16, 0, "test")
    action = next(
        item
        for item in engine.legal_actions(0)
        if item.kind == "play_malediction" and item.card_uid == 16
    )
    assert action.cost == 2
    engine.execute_action(action, 0)
    assert engine.used_malediction_slots(0) == 2
    assert engine.players[0].actions == 0

    engine.cards[16].stasis = False
    _put_malediction(engine, 6, 1)
    _put_malediction(engine, 44, 1)
    engine.resolve_after_attack(16, 6, 0, 10, 7, 16)
    assert engine.cards[44].corrupted


def test_colossus_can_replace_one_pure_malediction_when_three_slots_are_used() -> None:
    engine = GameEngine(61, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 2
    _put_malediction(engine, 1, 0)
    _put_malediction(engine, 2, 0, corrupted=True)
    _put_malediction(engine, 3, 0, corrupted=True)
    engine.take_to_hand(16, 0, "test")

    action = next(
        item
        for item in engine.legal_actions(0)
        if item.kind == "play_malediction" and item.card_uid == 16
    )
    assert "sostituendo" in action.label
    engine.execute_action(action, 0)

    assert 16 in engine.players[0].maledictions
    assert 1 in engine.void
    assert engine.used_malediction_slots(0) == 4


def test_cadence_scores_and_blocks_a_second_cadence_malediction() -> None:
    for cadence_uid in (7, 26, 46, 58):
        for corrupted in (False, True):
            engine = GameEngine(7000 + cadence_uid, deck="TuonoSabbia", auto_setup=False)
            engine.turn_number = 2
            _put_malediction(engine, cadence_uid, 1, corrupted=corrupted)

            engine.active_player = 0
            engine.start_turn()
            assert engine.players[0].score == 0
            assert engine.players[1].score == 0

            engine.active_player = 1
            engine.turn_number += 1
            engine.start_turn()
            assert engine.players[0].score == 0
            assert engine.players[1].score == 1
            assert engine.telemetry.ability_by_player[1]["Cadenza"] == 1

    engine = GameEngine(7, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 7, 0)
    assert not engine.can_play_malediction(0, 26)


def test_corrupted_piramide_can_attack_every_higher_eye_enemy_and_bot_uses_best_target() -> None:
    engine = GameEngine(4516, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 3
    _put_malediction(engine, 45, 0, corrupted=True)
    _put_malediction(engine, 7, 1)   # 6 Occhio.
    _put_malediction(engine, 16, 1)  # 10 Occhio e Colosso.

    previews = engine.attack_target_previews(0, 45)
    legal_targets = {
        action.target_uid
        for action in engine.legal_actions(0)
        if action.kind == "attack" and action.card_uid == 45
    }

    assert {preview["target_uid"] for preview in previews} == {7, 16}
    assert all(preview["outcome"] == "attacker_win" for preview in previews)
    assert all(preview["allowed"] for preview in previews)
    assert legal_targets == {7, 16}

    chosen = engine.bots[0].choose_action(engine, 0, engine.legal_actions(0))
    assert chosen.kind == "attack"
    assert chosen.card_uid == 45
    assert chosen.target_uid == 16


def test_piramide_preview_explains_when_its_effect_is_suppressed() -> None:
    engine = GameEngine(4507, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.players[0].actions = 1
    _put_malediction(engine, 45, 0, corrupted=True)
    _put_malediction(engine, 7, 1)
    engine.add_modifier("suppress_effect", 1, source_uid=44, target_uid=45)

    preview = engine.attack_target_previews(0, 45)[0]

    assert preview["outcome"] == "defender_win"
    assert preview["allowed"] is False
    assert "effetto di Piramide nel Cielo è annullato" in preview["reason"]


def test_screening_limits_attack_targets() -> None:
    engine = GameEngine(8, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.players[0].actions = 3
    _put_malediction(engine, 6, 0)
    _put_malediction(engine, 35, 1)
    _put_malediction(engine, 31, 1)
    previews = engine.attack_target_previews(0, 6)
    assert {preview["target_uid"] for preview in previews} == {35}

    engine.cards[35].corrupted = True
    previews = engine.attack_target_previews(0, 6)
    assert {preview["target_uid"] for preview in previews} == {35, 31}


def test_sigil_reopens_then_immediately_closes_if_condition_is_still_true() -> None:
    engine = GameEngine(9, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 35, 0, open_=False)
    for uid in (2, 3, 4):
        engine.charge_card(uid, 0, "test")
    assert engine.open_sigil(35, "test") is False
    assert engine.cards[35].seal_open is False


def test_glyph_can_spend_a_charge_to_prevent_breaking() -> None:
    engine = GameEngine(10, deck="TuonoSabbia", auto_setup=False)
    _put_prayer(engine, 8, 0)
    engine.charge_card(5, 0, "test")
    engine.bots[0].should_prevent_glyph_break = lambda *_args: True
    assert engine.break_card(8, reason="test") is False
    assert engine.cards[8].zone == Zone.PRAYER
    assert not engine.players[0].charges


def test_bot_simulation_and_report_use_tuono_sabbia() -> None:
    report = run_simulation(
        SimulationConfig(games=2, deck="TuonoSabbia", workers=1, learning_enabled=False)
    )
    assert report.config["deck"] == "TuonoSabbia"
    assert report.replay["deck"] == "TuonoSabbia"
    assert report.replay["schema"] == "bless.replay"
    assert report.replay["schema_version"] == 1
    assert report.replay["engine_version"] == ENGINE_VERSION
    assert report.card_stats[0]["name"] == "Cuore dei Cieli"
    assert len(report.card_stats) == 62
    assert "invocations_total" in report.summary
    assert "glyph_uses_total" in report.summary
    assert "charges_created_total" in report.summary
    assert len(report.replay["player_activity"]) == 2


def test_ts_activity_counts_invocations_glyphs_and_charges() -> None:
    engine = GameEngine(47, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 1
    _put_prayer(engine, 35, 0, open_=False)
    invoke = next(
        action
        for action in engine.legal_actions(0)
        if action.kind == "invoke" and action.card_uid == 35
    )
    engine.execute_action(invoke, 0)

    _put_prayer(engine, 8, 0)
    _put_malediction(engine, 31, 1)
    engine.charge_card(4, 0, "test")
    engine.use_glyph(8, 0)

    assert engine.telemetry.invocations == [1, 0]
    assert engine.telemetry.glyph_uses == [1, 0]
    assert engine.telemetry.charges_created == [1, 0]


def test_information_set_search_does_not_use_true_opponent_hidden_cards() -> None:
    engine = GameEngine(48, deck="TuonoSabbia", auto_setup=False)
    engine.take_to_hand(1, 0, "test")
    engine.take_to_hand(2, 1, "test")
    engine.charge_card(3, 0, "test")
    engine.charge_card(4, 1, "test")
    observer_hand = list(engine.players[0].hand)
    observer_charges = list(engine.players[0].charges)
    hidden_pool = set(engine.deck + engine.players[1].hand + engine.players[1].charges)

    clone = engine.clone_for_search(observer_player=0)

    assert clone.players[0].hand == observer_hand
    assert clone.players[0].charges == observer_charges
    assert len(clone.players[1].hand) == len(engine.players[1].hand)
    assert len(clone.players[1].charges) == len(engine.players[1].charges)
    assert set(clone.deck + clone.players[1].hand + clone.players[1].charges) == hidden_pool


def test_manual_session_exposes_deck_and_human_private_charges() -> None:
    session = ManualGameSession(
        {"seed": 11, "deck": "TuonoSabbia", "bot": "Bot", "first_player": "human"}
    )
    state = session.state()
    assert state["deck"] == "TuonoSabbia"
    assert state["deck_id"] == "tuono-sabbia"
    assert state["choice"]["purpose"] == "mulligan"
    state = session.submit_choice([])
    while state.get("choice") and state["choice"]["purpose"] == "esordio":
        state = session.submit_choice("Mano")
    human = state["players"][1]
    bot = state["players"][0]
    assert "charges" in human and "charges_count" in human
    assert all(card.get("hidden") for card in bot["charges"])


def test_initial_mulligan_cannot_create_a_charge() -> None:
    session = ManualGameSession(
        {"seed": 45, "deck": "TuonoSabbia", "bot": "Bot", "first_player": "human"}
    )
    initial = session.state()
    assert initial["choice"]["allow_charge"] is False
    charge_uid = initial["choice"]["candidate_uids"][0]
    state = session.submit_choice(
        {"mulligan_uids": [charge_uid], "charge_uid": charge_uid}
    )
    assert not state.get("choice") or state["choice"]["purpose"] != "charge_mulligan"
    assert state["players"][1]["charges_count"] == 0


def test_end_turn_mulligan_can_charge_only_while_controlling_a_glyph() -> None:
    session = ManualGameSession(
        {"seed": 49, "deck": "TuonoSabbia", "bot": "Bot", "first_player": "human"}
    )
    state = session.submit_choice([])
    while state.get("choice") and state["choice"]["purpose"] == "esordio":
        state = session.submit_choice("Mano")
    assert state["mode"] == "human_turn"

    _put_prayer(session.engine, 8, 1)
    state = session.end_human_turn()
    assert state["choice"]["purpose"] == "mulligan"
    assert state["choice"]["allow_charge"] is True
    charge_uid = state["choice"]["candidate_uids"][0]
    state = session.submit_choice(
        {"mulligan_uids": [charge_uid], "charge_uid": charge_uid}
    )
    assert state["players"][1]["charges_count"] == 1
    assert state["players"][1]["charges"][0]["uid"] == charge_uid


def test_manual_card_payload_explains_dynamic_tactical_targets() -> None:
    session = ManualGameSession(
        {"seed": 46, "deck": "TuonoSabbia", "bot": "Bot", "first_player": "human"}
    )
    session.transaction = None
    session.preview_engine = None
    session.pending_request = None
    engine = session.engine
    engine.turn_number = 5
    engine.active_player = 1
    engine.phase = "Fase principale"

    _put_malediction(engine, 5, 1)
    _put_malediction(engine, 29, 1)
    _put_malediction(engine, 31, 0, corrupted=True)
    engine.cards[31].attacked_turn = 4
    engine.cards[31].corrupted_turn = 3
    _put_malediction(engine, 32, 0)
    engine.cards[32].attacked_turn = 5
    _put_prayer(engine, 60, 0)
    engine.cards[60].declared_form = "Tuono"
    engine._remove_from_zone_list(6)
    engine.reset_card_outside_field(6, Zone.HAND, 1)
    engine.players[1].hand.append(6)

    state = session.state()
    human_cards = {
        card["id"]: card
        for card in state["players"][1]["maledictions"]
    }
    limitare = next(
        card for card in state["players"][0]["prayers"] if card["id"] == 60
    )
    free_attack_text = " ".join(
        note["text"] for note in human_cards[5]["tactical_notes"]
    )
    solerzia_text = " ".join(
        note["text"] for note in human_cards[29]["tactical_notes"]
    )
    limitare_text = " ".join(note["text"] for note in limitare["tactical_notes"])

    assert "Sil, il Sacerdote" in free_attack_text
    assert "Tempesta" not in free_attack_text
    assert "Sil, il Sacerdote" in solerzia_text
    assert "Forma vietata: Tuono" in limitare_text
    assert engine.definition(6).name in limitare_text


def test_luce_ombra_pays_discard_before_asking_for_purification_target() -> None:
    engine = GameEngine(50, deck="Luce-Ombra", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    _put_malediction(engine, 21, 0)
    _put_malediction(engine, 22, 0, corrupted=True)
    cost_uid = 24
    _remove_everywhere(engine, cost_uid)
    engine.reset_card_outside_field(cost_uid, Zone.HAND, 0)
    engine.players[0].hand.append(cost_uid)
    human = HumanDecisionBot()
    engine.bots[0] = human

    human.reset_choices([True])
    try:
        engine.resolve_calo(21, 0)
    except ChoiceRequired as required:
        assert required.request["purpose"] == "discard_own"
    else:
        raise AssertionError("Il costo di scarto deve essere scelto prima del bersaglio.")

    human.reset_choices([True, cost_uid])
    try:
        engine.resolve_calo(21, 0)
    except ChoiceRequired as required:
        assert required.request["purpose"] == "purify"
    else:
        raise AssertionError("Dopo il costo deve essere chiesto il bersaglio da Purificare.")

    assert cost_uid in engine.void
    assert cost_uid not in engine.players[0].hand
    assert engine.cards[22].corrupted is True


def test_perla_purifies_another_malediction_when_corrupted() -> None:
    engine = GameEngine(51, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    _put_malediction(engine, 35, 0)
    _put_malediction(engine, 31, 1, corrupted=True)

    assert engine.corrupt_card(35, 1, "test")
    assert engine.cards[31].corrupted is False


def test_ambra_plays_a_malediction_from_hand_when_corrupted() -> None:
    engine = GameEngine(53, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 2
    engine.active_player = 0
    _put_malediction(engine, 36, 0)
    _remove_everywhere(engine, 4)
    engine.reset_card_outside_field(4, Zone.HAND, 0)
    engine.players[0].hand.append(4)

    assert engine.corrupt_card(36, 1, "test")
    assert engine.cards[4].zone == Zone.MALEDICTION
    assert engine.cards[4].controller == 0


def test_card_ids_do_not_leak_luce_ombra_combat_effects_into_tuono_sabbia() -> None:
    engine = GameEngine(52, deck="TuonoSabbia", auto_setup=False)
    _put_malediction(engine, 31, 0)
    _put_malediction(engine, 5, 1)
    hand_uid = 7
    _remove_everywhere(engine, hand_uid)
    engine.reset_card_outside_field(hand_uid, Zone.HAND, 0)
    engine.players[0].hand.append(hand_uid)

    engine.trigger_attacked_effects(31, 5)

    assert engine.players[0].hand == [hand_uid]
    assert hand_uid not in engine.void

    _put_malediction(engine, 16, 0)
    _put_malediction(engine, 51, 1)
    assert engine.eye(16) == engine.eye(51)
    assert engine.predict_combat(16, 51) == "tie"


def test_battito_d_ali_still_discards_only_in_luce_ombra() -> None:
    engine = GameEngine(53, deck="Luce-Ombra", auto_setup=False)
    _put_malediction(engine, 31, 0)
    _put_malediction(engine, 5, 1)
    hand_uid = 7
    _remove_everywhere(engine, hand_uid)
    engine.reset_card_outside_field(hand_uid, Zone.HAND, 0)
    engine.players[0].hand.append(hand_uid)

    engine.trigger_attacked_effects(31, 5)

    assert hand_uid not in engine.players[0].hand
    assert hand_uid in engine.void


def test_tuono_sabbia_tactical_notes_are_not_shown_on_luce_ombra_cards() -> None:
    session = ManualGameSession(
        {"seed": 54, "deck": "Luce-Ombra", "bot": "Bot", "first_player": "human"}
    )
    session.transaction = None
    session.preview_engine = None
    session.pending_request = None
    _put_malediction(session.engine, 29, 1)
    _put_malediction(session.engine, 5, 1)
    _put_prayer(session.engine, 60, 1)

    state = session.state()["players"][1]
    portale = next(card for card in state["maledictions"] if card["id"] == 29)
    battito = next(card for card in state["maledictions"] if card["id"] == 5)
    cancelli = next(card for card in state["prayers"] if card["id"] == 60)
    assert all(note["title"] != "Vittoria di Solerzia" for note in portale["tactical_notes"])
    assert all(note["title"] != "Attacco gratuito" for note in battito["tactical_notes"])
    assert all(note["title"] != "Limitare del Mondo" for note in cancelli["tactical_notes"])


def test_impulse_event_keeps_the_played_card_public_until_visual_resolution() -> None:
    session = ManualGameSession(
        {"seed": 53, "deck": "Luce-Ombra", "bot": "Bot", "first_player": "human"}
    )
    session.transaction = None
    session.preview_engine = None
    session.pending_request = None
    engine = session.engine
    _remove_everywhere(engine, 22)
    engine.reset_card_outside_field(22, Zone.HAND, 1)
    engine.players[1].hand.append(22)

    assert engine.play_card(22, 1, "Preghiera", calata=True)
    state = session.state()

    assert engine.cards[22].zone == Zone.VOID
    assert state["last_impulse"]["card_uid"] == 22
    assert state["last_impulse"]["card"]["name"] == "Obelisco del Sole"
    assert state["last_impulse"]["card"]["prayer_type"] == "Impulso"
