from __future__ import annotations

import copy
from typing import Any, Mapping

from api._engine.bless_sim.engine import GameEngine, GameResult
from api._engine.bless_sim.manual import ChoiceRequired, HumanDecisionBot
from api._engine.bless_sim.model import Action
from api._engine.bless_sim.replay import replay_payload


class PlayerDecisionBot(HumanDecisionBot):
    """Human controller that marks every pending choice with its owner."""

    def __init__(self, player: int):
        super().__init__()
        self.player = player
        self.name = f"Giocatore {player + 1}"

    def _answer(self, request: dict[str, Any]) -> Any:
        owned = dict(request)
        owned["player"] = self.player
        return super()._answer(owned)

    def __deepcopy__(self, memo: dict[int, Any]) -> PlayerDecisionBot:
        result = PlayerDecisionBot(self.player)
        memo[id(self)] = result
        result._choices = copy.deepcopy(self._choices, memo)
        result._cursor = self._cursor
        result._combined_mulligan = self._combined_mulligan
        result._combined_mulligan_charge = self._combined_mulligan_charge
        result._fallback = copy.deepcopy(self._fallback, memo)
        return result


class MultiplayerGameSession:
    """Two-human deterministic game session with player-filtered views.

    The complete engine stays on the server. Clients receive only their own
    private zones, legal actions, and pending choices.
    """

    def __init__(self, config: Mapping[str, Any]):
        self.config = dict(config)
        self.seed = int(self.config.get("seed", 20_260_813))
        self.deck_name = str(self.config.get("deck", "Luce-Ombra"))
        raw_names = self.config.get("player_names") or ["Giocatore 1", "Giocatore 2"]
        self.player_names = (
            str(raw_names[0])[:24] or "Giocatore 1",
            str(raw_names[1])[:24] or "Giocatore 2",
        )
        first_player = int(self.config.get("first_player", self.seed % 2))
        if first_player not in (0, 1):
            raise ValueError("Primo giocatore non valido.")

        self.engine = GameEngine(
            self.seed,
            ("Bot", "Bot"),
            first_player=first_player,
            record_replay=True,
            auto_setup=False,
            deck=self.deck_name,
        )
        self.engine.bot_names = self.player_names
        self.engine.bots[0] = PlayerDecisionBot(0)
        self.engine.bots[1] = PlayerDecisionBot(1)
        self.transaction: dict[str, Any] | None = None
        self.preview_engine: GameEngine | None = None
        self.pending_request: dict[str, Any] | None = None
        self.last_action = "Preparazione della partita"
        self.finished_replay_payload: dict[str, Any] | None = None

        for player in (0, 1):
            self.engine.draw(player, 4, "mano iniziale")
        self._begin_operation({"kind": "setup"})

    @staticmethod
    def _controller(engine: GameEngine, player: int) -> PlayerDecisionBot:
        controller = engine.bots[player]
        if not isinstance(controller, PlayerDecisionBot):
            raise RuntimeError("Controllore del giocatore non disponibile.")
        return controller

    def _begin_operation(self, operation: dict[str, Any]) -> None:
        if self.transaction is not None:
            raise RuntimeError("C'è già una scelta in corso.")
        self.transaction = {
            "base": copy.deepcopy(self.engine),
            "operation": operation,
            "choices": {0: [], 1: []},
        }
        self._attempt_operation()

    def _attempt_operation(self) -> None:
        if self.transaction is None:
            return
        working = copy.deepcopy(self.transaction["base"])
        for player in (0, 1):
            self._controller(working, player).reset_choices(
                list(self.transaction["choices"][player])
            )
        try:
            label = self._execute_operation(working, self.transaction["operation"])
        except ChoiceRequired as request:
            self.preview_engine = working
            self.pending_request = dict(request.request)
            return

        self.engine = working
        for player in (0, 1):
            self._controller(self.engine, player).reset_choices([])
        self.preview_engine = None
        self.pending_request = None
        self.transaction = None
        self.last_action = label

    def _execute_operation(self, engine: GameEngine, operation: Mapping[str, Any]) -> str:
        kind = str(operation["kind"])
        if kind == "setup":
            engine.perform_mulligan(0, initial=True)
            engine.perform_mulligan(1, initial=True)
            if engine.is_thunder_sand:
                engine.resolve_esordio()
            engine.turn_number = 1
            engine.active_player = engine.first_player
            engine.phase = "Inizio turno"
            engine.emit(
                f"Inizia la partita. Il Giocatore {engine.active_player + 1} è il primo giocatore."
            )
            engine.start_turn()
            return "Partita iniziata"
        if kind == "start_turn":
            engine.start_turn()
            return f"Inizio del turno {engine.turn_number}"
        if kind == "action":
            player = int(operation["player"])
            action = Action(**dict(operation["action"]))
            engine.execute_action(action, player)
            return action.label
        if kind in {"end_turn", "forced_end"}:
            player = int(operation["player"])
            if kind == "end_turn":
                engine.execute_action(Action("pass", cost=0, label="Termina il turno"), player)
            engine.end_turn()
            return f"Fine del turno di {self.player_names[player]}"
        raise ValueError("Operazione multiplayer sconosciuta.")

    @staticmethod
    def _action_id(action: Action) -> str:
        return ":".join(
            [
                action.kind,
                str(action.card_uid or ""),
                str(action.target_uid or ""),
                str(action.mode or ""),
                str(action.cost),
            ]
        )

    def submit_choice(self, player: int, value: Any) -> dict[str, Any]:
        if self.transaction is None or self.pending_request is None:
            raise ValueError("Non c'è una scelta in attesa.")
        owner = int(self.pending_request.get("player", -1))
        if owner != player:
            raise ValueError("Questa scelta appartiene all'altro giocatore.")
        operation = dict(self.transaction["operation"])
        self.transaction["choices"][player].append(value)
        self._attempt_operation()
        if (
            operation.get("kind") == "action"
            and self.transaction is None
            and self.engine.force_end_turn
            and not self.engine.game_over
        ):
            self._begin_operation({"kind": "forced_end", "player": int(operation.get("player", player))})
        return self.state_for(player)

    def _ensure_turn(self, player: int, *, main_phase: bool = True) -> None:
        if self.pending_request is not None:
            raise ValueError("Completa prima la scelta richiesta.")
        if self.engine.game_over or self.engine.active_player != player:
            raise ValueError("Non è il tuo turno.")
        if main_phase and self.engine.phase != "Fase principale":
            raise ValueError("Il turno non è ancora nella Fase principale.")

    def start_turn(self, player: int) -> dict[str, Any]:
        self._ensure_turn(player, main_phase=False)
        if self.engine.phase != "Fase principale":
            self._begin_operation({"kind": "start_turn", "player": player})
        return self.state_for(player)

    def perform_action(self, player: int, action_id: str) -> dict[str, Any]:
        self._ensure_turn(player)
        actions = {
            self._action_id(action): action
            for action in self.engine.legal_actions(player)
            if action.kind != "pass"
        }
        action = actions.get(action_id)
        if action is None:
            raise ValueError("Questa Azione non è più valida.")
        self._begin_operation(
            {
                "kind": "action",
                "player": player,
                "action": {
                    "kind": action.kind,
                    "card_uid": action.card_uid,
                    "target_uid": action.target_uid,
                    "mode": action.mode,
                    "cost": action.cost,
                    "label": action.label,
                },
            }
        )
        if self.transaction is None and self.engine.force_end_turn and not self.engine.game_over:
            self._begin_operation({"kind": "forced_end", "player": player})
        return self.state_for(player)

    def end_turn(self, player: int) -> dict[str, Any]:
        self._ensure_turn(player)
        self._begin_operation({"kind": "end_turn", "player": player})
        return self.state_for(player)

    def forfeit(self, player: int) -> dict[str, Any]:
        if player not in (0, 1):
            raise ValueError("Giocatore non valido.")
        if self.engine.game_over:
            raise ValueError("La partita è già terminata.")

        # Un abbandono chiude anche un'eventuale scelta ancora aperta. Lo stato
        # parziale della preview non viene mai promosso a stato autoritativo.
        self.transaction = None
        self.preview_engine = None
        self.pending_request = None
        self.engine.force_end_turn = False
        self.engine.winner = 1 - player
        self.engine.stalemate = False
        self.engine.game_over = True
        self.engine.phase = "Partita terminata"
        self.last_action = f"{self.player_names[player]} ha abbandonato la partita"
        self.engine.emit(self.last_action)
        return self.state_for(player)

    @staticmethod
    def _card_payload(engine: GameEngine, uid: int, *, hidden: bool = False) -> dict[str, Any]:
        if hidden:
            return {"uid": uid, "hidden": True, "zone": engine.cards[uid].zone.value}
        definition = engine.definition(uid)
        payload = engine.card_summary(uid)
        payload.update(
            {
                "controller": engine.cards[uid].controller,
                "base_eye": definition.eye,
                "base_karma": definition.karma,
                "prayer_type": definition.prayer_type.value,
                "malediction_text": definition.malediction_text,
                "prayer_text": definition.prayer_text,
                "image": engine.image_path(uid),
                "tactical_notes": [],
            }
        )
        return payload

    def _player_payload(self, engine: GameEngine, player: int, viewer: int) -> dict[str, Any]:
        state = engine.players[player]
        hidden = player != viewer
        return {
            "id": player,
            "name": "Tu" if player == viewer else self.player_names[player],
            "score": state.score,
            "actions": state.actions,
            "hand": [self._card_payload(engine, uid, hidden=hidden) for uid in state.hand],
            "maledictions": [self._card_payload(engine, uid) for uid in state.maledictions],
            "prayers": [self._card_payload(engine, uid) for uid in state.prayers],
            "altar": [self._card_payload(engine, uid, hidden=hidden) for uid in state.altar],
            "altar_count": len(state.altar),
            "charges": [self._card_payload(engine, uid, hidden=hidden) for uid in state.charges],
            "charges_count": len(state.charges),
        }

    def _legal_actions(self, engine: GameEngine, viewer: int) -> list[dict[str, Any]]:
        if (
            self.pending_request is not None
            or engine.game_over
            or engine.active_player != viewer
            or engine.phase != "Fase principale"
        ):
            return []
        payloads: list[dict[str, Any]] = []
        for action in engine.legal_actions(viewer):
            if action.kind == "pass":
                continue
            payload: dict[str, Any] = {
                "id": self._action_id(action),
                "kind": action.kind,
                "card_uid": action.card_uid,
                "target_uid": action.target_uid,
                "mode": action.mode,
                "cost": action.cost,
                "label": action.label,
            }
            if action.kind == "attack" and action.card_uid is not None and action.target_uid is not None:
                preview = engine.simulate_combat_silently(action.card_uid, action.target_uid)
                preview["allowed"] = True
                preview["reason"] = "Bersaglio valido dopo la previsione dello scontro."
                payload["combat_preview"] = preview
            payloads.append(payload)
        return payloads

    def _combat_previews(self, engine: GameEngine, viewer: int) -> list[dict[str, Any]]:
        if (
            self.pending_request is not None
            or engine.game_over
            or engine.active_player != viewer
            or engine.phase != "Fase principale"
        ):
            return []
        return [
            preview
            for attacker in engine.players[viewer].maledictions
            for preview in engine.attack_target_previews(viewer, attacker)
        ]

    @staticmethod
    def _history_message(engine: GameEngine, step: Any, viewer: int) -> str:
        opponent = 1 - viewer
        message = str(step.message)
        draw_prefix = f"Il Giocatore {opponent + 1} prende "
        if message.startswith(draw_prefix):
            current_hand = len(step.snapshot["players"][opponent]["hand"])
            previous_hand = 0
            if step.index > 0:
                previous_hand = len(engine.replay[step.index - 1].snapshot["players"][opponent]["hand"])
            drawn = max(1, current_hand - previous_hand)
            noun = "carta" if drawn == 1 else "carte"
            return f"{opponent + 1} pesca {drawn} {noun}."
        hidden_return = f" va nella mano del Giocatore {opponent + 1}"
        if hidden_return in message:
            _, suffix = message.split(hidden_return, 1)
            return f"Una carta va nella mano dell'avversario{suffix}"
        return message

    def _finished_replay(self, engine: GameEngine) -> dict[str, Any]:
        if self.finished_replay_payload is None:
            trigger_won = (
                engine.winner == engine.final_trigger_player
                if engine.winner is not None and engine.final_trigger_player is not None
                else None
            )
            result = GameResult(
                seed=engine.seed,
                deck=engine.deck_name,
                bot_names=engine.bot_names,
                first_player=engine.first_player,
                winner=engine.winner,
                scores=(engine.players[0].score, engine.players[1].score),
                turns=engine.completed_turns,
                final_trigger_player=engine.final_trigger_player,
                final_trigger_cause=engine.final_trigger_cause,
                final_trigger_won=trigger_won,
                stalemate=engine.stalemate,
                telemetry=engine.telemetry,
                replay=engine.replay,
            )
            self.finished_replay_payload = replay_payload(result)
        return self.finished_replay_payload

    def state_for(self, viewer: int) -> dict[str, Any]:
        if viewer not in (0, 1):
            raise ValueError("Giocatore non valido.")
        engine = self.preview_engine or self.engine
        owner = int(self.pending_request.get("player", -1)) if self.pending_request else -1
        request = dict(self.pending_request) if owner == viewer else None
        if request is not None:
            request.pop("player", None)
            request["candidates"] = [
                self._card_payload(engine, int(uid))
                for uid in request.get("candidate_uids", [])
                if int(uid) in engine.cards
            ]
            source_uid = request.get("source_uid")
            if source_uid is not None and int(source_uid) in engine.cards:
                request["source"] = self._card_payload(engine, int(source_uid))

        if engine.game_over:
            mode = "game_over"
        elif request is not None:
            mode = "choice"
        elif self.pending_request is not None:
            # La scelta appartiene all'altro giocatore. Anche quando il motore
            # conserva questo giocatore come attivo, il client non deve provare
            # ad avanzare automaticamente il turno finche' la scelta non arriva.
            mode = "waiting_choice"
        elif engine.active_player == viewer:
            mode = "human_turn" if engine.phase == "Fase principale" else "human_start"
        else:
            mode = "opponent_turn" if engine.phase == "Fase principale" else "opponent_start"

        history = [
            {
                "index": step.index,
                "turn": step.turn,
                "player": step.active_player,
                "phase": step.phase,
                "message": self._history_message(engine, step, viewer),
                "action_index": step.action_index,
                "action_label": step.action_label,
            }
            for step in engine.replay[-120:]
        ]
        last_impulse = copy.deepcopy(engine.last_impulse)
        if last_impulse is not None:
            last_impulse["card"] = self._card_payload(
                engine,
                int(last_impulse["card_uid"]),
            )
        result: dict[str, Any] = {
            "seed": self.seed,
            "deck": engine.deck_name,
            "deck_id": engine.deck_id,
            "mode": mode,
            "turn": engine.turn_number,
            "active_player": engine.active_player,
            "human_player": viewer,
            "bot_player": 1 - viewer,
            "phase": engine.phase,
            "force_end_turn": engine.force_end_turn,
            "final_turns_remaining": engine.final_turns_remaining,
            "final_trigger_player": engine.final_trigger_player,
            "final_trigger_turn": engine.final_trigger_turn,
            "last_attack": copy.deepcopy(engine.last_attack),
            "last_fate": copy.deepcopy(engine.last_fate),
            "last_impulse": last_impulse,
            "deck_count": len(engine.deck),
            "void": [self._card_payload(engine, uid) for uid in reversed(engine.void)],
            "players": [
                self._player_payload(engine, 0, viewer),
                self._player_payload(engine, 1, viewer),
            ],
            "legal_actions": self._legal_actions(engine, viewer),
            "combat_previews": self._combat_previews(engine, viewer),
            "choice": request,
            "history": history,
            "last_action": self.last_action,
            "can_undo": False,
            "undo_label": None,
            "winner": engine.winner,
            "game_over": engine.game_over,
        }
        if engine.game_over and self.preview_engine is None:
            result["replay"] = self._finished_replay(engine)
        return result
