from test_tuono_sabbia_027 import ScriptedBot, _put_hand, _put_malediction, _put_prayer
from bless_sim.engine import GameEngine
from bless_sim.model import Zone


def table() -> GameEngine:
    engine = GameEngine(913, deck="TuonoSabbia", auto_setup=False)
    engine.turn_number = 3
    engine.active_player = 0
    engine.phase = "Fase principale"
    engine.players[0].actions = 1
    return engine


def test_suppression_removes_printed_and_granted_screening_and_restores_on_expiry() -> None:
    for target in (30, 34):
        engine = table()
        _put_malediction(engine, target, 1)
        _put_malediction(engine, 13, 1)
        _put_malediction(engine, 51, 0)
        if target == 34:
            engine.add_modifier("grant_screening", 1, source_uid=47, target_uid=target,
                                expires_after_turn=engine.turn_number + 2)
        assert engine.eclissi_targets(1) == [target]
        assert not any(a.kind == "attack" and a.target_uid == 13 for a in engine.legal_actions(0))

        # Vocio di Morte annulla davvero l'effetto, non solo una chiamata di test.
        engine.bots[0] = ScriptedBot(engine.bots[0], cards={"suppress": [target]})
        engine.resolve_prayer_effect(34, 0)
        assert engine.is_suppressed(target)
        assert not engine.has_ability(target, "schermatura")
        assert engine.eclissi_targets(1) == []
        assert any(a.kind == "attack" and a.target_uid == 13 for a in engine.legal_actions(0))

        engine.turn_number += 1
        assert not engine.is_suppressed(target)
        assert engine.has_ability(target, "schermatura")
        engine.cards[target].corrupted = True
        assert not engine.has_ability(target, "schermatura")


def test_deserto_ambra_changes_only_eye_and_tracks_sigil_state() -> None:
    engine = table()
    _put_malediction(engine, 34, 0)
    _put_malediction(engine, 13, 0)
    _put_malediction(engine, 39, 1)
    before = {uid: (engine.eye(uid), engine.karma(uid)) for uid in (34, 13, 39)}
    _put_prayer(engine, 36, 0)
    assert engine.eye(34) == before[34][0] + 1
    assert engine.karma(34) == before[34][1]
    for uid in (13, 39):
        assert (engine.eye(uid), engine.karma(uid)) == before[uid]
    engine.close_sigil(36, "test")
    assert (engine.eye(34), engine.karma(34)) == before[34]


def test_zap_zap_can_attack_after_calo_with_no_actions_left() -> None:
    engine = table()
    _put_malediction(engine, 13, 1)
    _put_malediction(engine, 34, 1)
    _put_hand(engine, 11, 0)
    play = next(a for a in engine.legal_actions(0) if a.kind == "play_malediction")
    engine.execute_action(play, 0)
    assert engine.players[0].actions == 0
    assert not engine.cards[11].stasis
    attacks = [a for a in engine.legal_actions(0) if a.kind == "attack"]
    assert attacks and all(a.card_uid == 11 and a.cost == 0 for a in attacks)
    engine.execute_action(attacks[0], 0)
    assert engine.telemetry.combats == 1
    assert engine.players[0].actions == 0
    assert not [a for a in engine.legal_actions(0) if a.kind == "attack"]


def test_zap_zap_checks_count_after_entering_and_counts_colosso_as_two() -> None:
    for defender, expected_stasis in ((13, True), (16, False)):
        engine = table()
        _put_malediction(engine, defender, 1)
        _put_hand(engine, 11, 0)
        play = next(a for a in engine.legal_actions(0) if a.kind == "play_malediction")
        engine.execute_action(play, 0)
        assert engine.cards[11].stasis is expected_stasis
        assert engine.attack_cost(11, defender) == (1 if expected_stasis else 0)


def test_zap_zap_generated_without_calo_does_not_gain_free_attack() -> None:
    engine = table()
    _put_malediction(engine, 16, 1)
    assert engine.play_generated_card(11, 0, forced_mode="Maledizione", calata=False)
    assert engine.cards[11].stasis
    assert engine.attack_cost(11, 16) == 1


def test_glyph_passive_survives_last_charge_and_recalculates_new_charges() -> None:
    for glyph in (8, 12, 19, 25, 32, 38, 45):
        engine = table()
        _put_malediction(engine, 34, 1)
        _put_prayer(engine, glyph, 0)
        base_eye = engine.eye(34)
        engine.charge_card(2, 0, "test")
        assert engine.mark_with_charge(34, 0, "test", marker_uid=2)
        assert not engine.players[0].charges
        assert engine.cards[glyph].zone == Zone.PRAYER
        assert engine.is_marked(34)
        assert engine.eye(34) == base_eye  # Il moltiplicatore e' zero, non il Marchio.
        assert not [a for a in engine.legal_actions(0) if a.kind == "use_glyph"]
        engine.charge_card(3, 0, "test")
        assert engine.eye(34) == base_eye - 1
        engine.spend_charges(0, 1, "test")
        assert engine.is_marked(34)
        assert engine.eye(34) == base_eye
        _put_prayer(engine, 35, 0)  # Deserto Perla: Carica virtuale anche con zero fisiche.
        assert engine.effective_charge_count(0) == 1
        assert engine.eye(34) == base_eye - 1
