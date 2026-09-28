from __future__ import annotations

import json
import sys
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[2] / "public" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from bless_sim.manual import BOT_PLAYER, HUMAN_PLAYER, ManualGameSession  # noqa: E402
from bless_sim.model import Zone  # noqa: E402


def _started_session(*, first_player: str = "human") -> ManualGameSession:
    session = ManualGameSession(
        {
            "seed": 20260810,
            "bot": "Bot",
            "first_player": first_player,
            "learning_weights": {},
        }
    )
    initial = session.state()
    assert initial["choice"]["purpose"] == "mulligan"
    session.submit_choice([])
    return session


def _resolve_choices(session: ManualGameSession, state: dict) -> dict:
    while state["choice"] is not None:
        choice = state["choice"]
        if choice["kind"] == "card":
            value = choice["candidate_uids"][0]
        elif choice["kind"] in {"option", "confirm"}:
            value = choice["options"][0]
        else:
            value = []
        state = session.submit_choice(value)
    return state


def _put_malediction(session: ManualGameSession, uid: int, player: int) -> None:
    engine = session.engine
    engine._remove_from_zone_list(uid)
    engine.reset_card_outside_field(uid, Zone.MALEDICTION, player)
    engine.cards[uid].entered_sequence = engine.next_sequence()
    engine.players[player].maledictions.append(uid)


def _put_prayer(session: ManualGameSession, uid: int, player: int) -> None:
    engine = session.engine
    engine._remove_from_zone_list(uid)
    engine.reset_card_outside_field(uid, Zone.PRAYER, player)
    engine.cards[uid].entered_sequence = engine.next_sequence()
    engine.players[player].prayers.append(uid)


def test_manual_game_starts_with_a_visible_human_mulligan() -> None:
    session = ManualGameSession(
        {
            "seed": 20260810,
            "bot": "Bot",
            "first_player": "human",
            "learning_weights": {},
        }
    )

    state = session.state()
    assert state["mode"] == "choice"
    assert state["turn"] == 0
    assert state["choice"]["kind"] == "multi_card"
    assert len(state["choice"]["candidates"]) == 4
    assert all(card.get("name") for card in state["choice"]["candidates"])
    assert all(card["hidden"] for card in state["players"][BOT_PLAYER]["hand"])


def test_public_history_hides_cards_drawn_into_the_bot_hand() -> None:
    session = _started_session()
    state = session.state()
    public_history = " ".join(step["message"] for step in state["history"])
    raw_bot_draws = [
        step.message
        for step in session.engine.replay
        if step.message.startswith(f"Il Giocatore {BOT_PLAYER + 1} prende ")
    ]
    hidden_names = {
        session.engine.definition(uid).name
        for uid in session.engine.cards
        if any(session.engine.definition(uid).name in message for message in raw_bot_draws)
    }

    assert raw_bot_draws
    assert hidden_names
    assert "Il bot pesca" in public_history
    assert f"Il Giocatore {BOT_PLAYER + 1} prende " not in public_history
    assert all(name not in public_history for name in hidden_names)


def test_manual_actions_spend_points_and_turn_only_ends_on_request() -> None:
    session = _started_session()
    state = session.state()
    assert state["mode"] == "human_turn"
    assert state["players"][HUMAN_PLAYER]["actions"] == 2

    action = next(item for item in state["legal_actions"] if item["cost"] == 1)
    state = _resolve_choices(session, session.perform_action(action["id"]))

    assert state["players"][HUMAN_PLAYER]["actions"] == 1
    assert state["mode"] == "human_turn"
    action_steps = [step for step in state["history"] if step["action_index"] is not None]
    assert action_steps
    assert all(step["action_label"] for step in action_steps)

    state = session.end_human_turn()
    assert state["choice"]["purpose"] == "mulligan"
    state = session.submit_choice([])
    assert state["active_player"] == BOT_PLAYER
    assert state["mode"] in {"opponent_start", "opponent_turn"}


def test_last_human_action_restores_the_exact_previous_table_state() -> None:
    session = _started_session()
    before = session.state()
    before_hand = [card["uid"] for card in before["players"][HUMAN_PLAYER]["hand"]]
    before_maledictions = [card["uid"] for card in before["players"][HUMAN_PLAYER]["maledictions"]]
    before_prayers = [card["uid"] for card in before["players"][HUMAN_PLAYER]["prayers"]]
    before_actions = before["players"][HUMAN_PLAYER]["actions"]

    action = next(item for item in before["legal_actions"] if item["kind"] == "play_malediction")
    played = _resolve_choices(session, session.perform_action(action["id"]))
    assert played["can_undo"] is True
    assert played["undo_label"] == action["label"]

    restored = session.undo_last_move()
    assert restored["players"][HUMAN_PLAYER]["actions"] == before_actions
    assert [card["uid"] for card in restored["players"][HUMAN_PLAYER]["hand"]] == before_hand
    assert [card["uid"] for card in restored["players"][HUMAN_PLAYER]["maledictions"]] == before_maledictions
    assert [card["uid"] for card in restored["players"][HUMAN_PLAYER]["prayers"]] == before_prayers
    assert restored["choice"] is None
    assert restored["can_undo"] is False
    assert restored["last_action"].startswith("Mossa annullata:")


def test_end_turn_can_be_undone_during_mulligan_choice() -> None:
    session = _started_session()
    before = session.state()
    before_hand = [card["uid"] for card in before["players"][HUMAN_PLAYER]["hand"]]

    pending = session.end_human_turn()
    assert pending["choice"]["purpose"] == "mulligan"
    assert pending["can_undo"] is True

    restored = session.undo_last_move()
    assert restored["mode"] == "human_turn"
    assert restored["active_player"] == HUMAN_PLAYER
    assert restored["choice"] is None
    assert restored["players"][HUMAN_PLAYER]["actions"] == before["players"][HUMAN_PLAYER]["actions"]
    assert [card["uid"] for card in restored["players"][HUMAN_PLAYER]["hand"]] == before_hand
    assert restored["can_undo"] is False


def test_undo_restores_charge_mark_and_continuous_glyph_interaction() -> None:
    session = ManualGameSession(
        {"seed": 20260830, "deck": "TuonoSabbia", "bot": "Bot", "first_player": "human"}
    )
    session.transaction = None
    session.preview_engine = None
    session.pending_request = None
    engine = session.engine
    engine.turn_number = 5
    engine.active_player = HUMAN_PLAYER
    engine.phase = "Fase principale"
    engine.players[HUMAN_PLAYER].actions = 1

    # Fulmine Fragile e' Marchiato dal bot. ElettroNova applica quindi il
    # malus continuo in base alle Cariche reali del bot.
    _put_malediction(session, 10, HUMAN_PLAYER)
    _put_malediction(session, 57, BOT_PLAYER)  # Vetro Smerigliato Carica se attaccato.
    _put_prayer(session, 8, BOT_PLAYER)  # ElettroNova.
    engine.charge_card(2, BOT_PLAYER, "preparazione test")
    assert engine.mark_with_charge(10, BOT_PLAYER, "preparazione test", marker_uid=2)
    engine.charge_card(3, BOT_PLAYER, "preparazione test")

    signature_before = engine.state_signature()
    assert engine.mark_for(10) == 2
    assert engine.players[BOT_PLAYER].charges == [3]
    assert engine.eye(10) == 8  # 9 stampato, -1 per la Carica del bot.

    attack = next(
        action
        for action in session.state()["legal_actions"]
        if action["kind"] == "attack"
        and action["card_uid"] == 10
        and action["target_uid"] == 57
    )
    session.perform_action(attack["id"])

    # La dichiarazione contro Vetro ha creato una seconda Carica e lo scontro
    # ha consumato il Marchio: sono proprio gli elementi che l'annullamento
    # deve ripristinare come stato di gioco, non solo come grafica.
    assert len(session.engine.players[BOT_PLAYER].charges) == 2
    assert not session.engine.is_marked(10)

    restored = session.undo_last_move()
    restored_engine = session.engine
    assert restored_engine.state_signature() == signature_before
    assert restored_engine.mark_for(10) == 2
    assert restored_engine.cards[2].zone == Zone.MARK
    assert restored_engine.cards[2].attached_to == 10
    assert restored_engine.players[BOT_PLAYER].charges == [3]
    assert restored_engine.cards[3].zone == Zone.CHARGE
    assert restored_engine.eye(10) == 8

    card = next(
        item
        for item in restored["players"][HUMAN_PLAYER]["maledictions"]
        if item["uid"] == 10
    )
    assert card["eye"] == 8

    # Anche una nuova previsione ricalcola il malus dopo la Carica che Vetro
    # genererebbe: 9 Occhio - 2 Cariche = 7.
    preview = restored_engine.simulate_combat_silently(10, 57)
    assert preview["attacker_eye"] == 7


def test_last_final_turn_ends_without_a_mulligan_choice() -> None:
    session = _started_session()
    session.engine.final_turns_remaining = 1
    session.engine.final_trigger_player = BOT_PLAYER
    session.engine.final_trigger_turn = session.engine.turn_number - 1

    final_state = session.end_human_turn()

    assert final_state["game_over"] is True
    assert final_state["final_turns_remaining"] == 0
    assert final_state["choice"] is None


def test_opponent_advances_one_action_per_step() -> None:
    session = _started_session(first_player="bot")
    state = session.state()
    assert state["active_player"] == BOT_PLAYER
    assert "combat_previews" in state

    history_before = len(state["history"])
    state = session.opponent_step()
    assert state["phase"] == "Fase principale"
    assert len(state["history"]) >= history_before

    if not state["choice"] and state["mode"] == "opponent_turn":
        actions_before = state["players"][BOT_PLAYER]["actions"]
        state = session.opponent_step()
        assert state["players"][BOT_PLAYER]["actions"] >= 0
        assert state["players"][BOT_PLAYER]["actions"] <= actions_before


def test_choice_payload_includes_cards_outside_the_field() -> None:
    session = _started_session()
    uid = session.engine.deck[0]
    session.pending_request = {
        "kind": "card",
        "purpose": "take",
        "prompt": "Scegli",
        "explanation": "Test",
        "candidate_uids": [uid],
    }

    choice = session.state()["choice"]
    assert choice["candidates"][0]["uid"] == uid
    assert choice["candidates"][0]["name"]
    assert choice["candidates"][0]["image"].endswith(".jpg")


def test_luce_ombra_tutorial_guides_the_complete_learning_sequence() -> None:
    session = ManualGameSession(
        {
            "seed": 20260928,
            "deck": "Luce-Ombra",
            "bot": "Bot",
            "first_player": "human",
            "tutorial": True,
        }
    )

    state = session.state()
    assert state["tutorial"]["step"] == "initial_mulligan"
    assert state["tutorial"]["mulligan_locked_uids"] == [23, 1]
    state = session.submit_choice({"mulligan_uids": [44], "charge_uid": None})

    def perform_expected(step: str) -> dict:
        current = session.state()
        assert current["tutorial"]["step"] == step
        assert len(current["legal_actions"]) == 1
        return session.perform_action(current["legal_actions"][0]["id"])

    state = perform_expected("play_horizon")
    assert session.engine.players[HUMAN_PLAYER].score == 1
    assert 23 in session.engine.players[HUMAN_PLAYER].maledictions

    state = perform_expected("play_echo")
    assert state["choice"]["candidate_uids"] == [23]
    state = session.submit_choice(23)
    assert 1 in session.engine.players[HUMAN_PLAYER].prayers
    assert session.engine.eye(23) == 7

    assert state["tutorial"]["allow_end_turn"] is True
    state = session.end_human_turn()
    assert state["tutorial"]["step"] == "end_turn_mulligan"
    assert state["tutorial"]["mulligan_locked_uids"] == []
    optional_uid = next(uid for uid in state["choice"]["candidate_uids"] if uid not in {19, 25, 37})
    state = session.submit_choice({"mulligan_uids": [optional_uid], "charge_uid": None})

    while state["active_player"] == BOT_PLAYER:
        state = session.opponent_step()
    state = session.start_human_turn()
    assert 21 in session.engine.players[BOT_PLAYER].maledictions
    assert 7 in session.engine.players[BOT_PLAYER].maledictions
    assert 2 in session.engine.players[BOT_PLAYER].prayers
    assert session.engine.cards[2].attached_to == 7

    state = perform_expected("play_second_curse")
    assert session.engine.cards[19].stasis is True
    state = perform_expected("invoke_echo")
    assert state["choice"]["candidate_uids"] == [23]
    state = session.submit_choice(23)
    assert session.engine.eye(23) == 7
    state = perform_expected("first_combat")
    assert session.engine.cards[21].corrupted is True

    state = session.end_human_turn()
    assert set(state["tutorial"]["mulligan_locked_uids"]) == {25, 37}
    state = session.submit_choice({"mulligan_uids": [], "charge_uid": None})
    while state["active_player"] == BOT_PLAYER:
        state = session.opponent_step()
    state = session.start_human_turn()
    assert session.engine.cards[19].corrupted is True
    assert session.engine.eye(19) == 4

    state = perform_expected("bless_combat")
    assert state["choice"]["purpose"] == "offer"
    assert state["choice"]["options"] == [True]
    state = session.submit_choice(True)
    assert session.engine.players[HUMAN_PLAYER].score == 5
    assert 21 in session.engine.players[HUMAN_PLAYER].altar

    state = perform_expected("play_impulse")
    assert state["choice"]["candidate_uids"] == [2]
    state = session.submit_choice(2)
    assert session.engine.cards[37].zone == Zone.VOID
    assert 2 not in session.engine.players[BOT_PLAYER].prayers

    state = perform_expected("play_bond")
    assert state["tutorial"]["complete"] is True
    assert session.engine.cards[25].attached_to == 19
    assert state["legal_actions"] == []


def test_winning_human_examples_receive_more_learning_weight() -> None:
    winner = _started_session()
    winner.engine.game_over = True
    winner.engine.winner = HUMAN_PLAYER
    winning_update = winner.state()["learning"]

    loser = _started_session()
    loser.engine.game_over = True
    loser.engine.winner = BOT_PLAYER
    losing_update = loser.state()["learning"]

    assert winning_update["outcome"] == "vittoria"
    assert losing_update["outcome"] == "sconfitta"
    assert winning_update["outcome_weight"] > losing_update["outcome_weight"]


def test_manual_protocol_reaches_game_over_and_returns_learning() -> None:
    session = ManualGameSession(
        {
            "seed": 781223,
            "bot": "Bot",
            "first_player": "human",
            "learning_weights": {},
        }
    )

    for _ in range(800):
        state = session.state()
        if state["game_over"]:
            break
        choice = state["choice"]
        if choice is not None:
            if choice["kind"] == "multi_card":
                value = []
            elif choice["kind"] == "card":
                value = choice["candidate_uids"][0] if choice["candidate_uids"] else None
            else:
                value = choice["options"][0]
            session.submit_choice(value)
        elif state["mode"] == "human_turn":
            if state["legal_actions"]:
                session.perform_action(state["legal_actions"][0]["id"])
            else:
                session.end_human_turn()
        elif state["mode"] == "human_start":
            session.start_human_turn()
        else:
            session.opponent_step()
    else:
        raise AssertionError("La partita manuale non e' terminata entro il limite di sicurezza.")

    final_state = session.state()
    assert final_state["game_over"] is True
    assert final_state["learning"]["outcome"] in {"vittoria", "pareggio", "sconfitta"}
    assert set(final_state["learning"]["weight_deltas"]) == {"Bot"}
    assert final_state["replay"]["actions"]
    assert final_state["replay"]["bots"][HUMAN_PLAYER] == "Umano"
    encoded = json.dumps(final_state, ensure_ascii=False)
    assert '"game_over": true' in encoded
    assert '"replay"' in encoded
    assert len(encoded.encode("utf-8")) < 4_500_000


if __name__ == "__main__":
    test_manual_game_starts_with_a_visible_human_mulligan()
    test_public_history_hides_cards_drawn_into_the_bot_hand()
    test_manual_actions_spend_points_and_turn_only_ends_on_request()
    test_last_human_action_restores_the_exact_previous_table_state()
    test_end_turn_can_be_undone_during_mulligan_choice()
    test_undo_restores_charge_mark_and_continuous_glyph_interaction()
    test_last_final_turn_ends_without_a_mulligan_choice()
    test_opponent_advances_one_action_per_step()
    test_choice_payload_includes_cards_outside_the_field()
    test_winning_human_examples_receive_more_learning_weight()
    test_manual_protocol_reaches_game_over_and_returns_learning()
    print("manual play: ok")
