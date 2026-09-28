from __future__ import annotations

from typing import Any

from .engine import GameResult
from .version import ENGINE_VERSION, REPLAY_SCHEMA_VERSION


def replay_payload(result: GameResult) -> dict[str, Any]:
    """Raggruppa gli eventi del motore per Azione per il replay grafico."""
    actions: list[dict[str, Any]] = []
    pending_events: list[dict[str, Any]] = []
    pending_last_step: Any | None = None
    current: dict[str, Any] | None = None

    def event_payload(step: Any, event_type: str) -> dict[str, Any]:
        return {
            "index": step.index,
            "turn": step.turn,
            "phase": step.phase,
            "message": step.message,
            "type": event_type,
        }

    for step in result.replay:
        if step.action_index is None:
            if current is None:
                pending_events.append(event_payload(step, "fase"))
                pending_last_step = step
            else:
                # Le risoluzioni automatiche tra due mosse sono conseguenze
                # dell'Azione appena eseguita e restano nello stesso passo.
                current["events"].append(event_payload(step, "fase"))
                current["snapshot"] = step.snapshot
            continue

        starts_action = current is None or current["action_number"] != step.action_index
        if starts_action:
            if current is not None:
                actions.append(current)
            current = {
                "index": len(actions),
                "action_number": step.action_index,
                "turn": step.turn,
                "active_player": step.active_player,
                "phase": step.phase,
                "label": step.action_label or step.message,
                "events": [*pending_events, event_payload(step, "azione")],
                "snapshot": step.snapshot,
            }
            pending_events = []
            pending_last_step = None
        else:
            current["events"].append(event_payload(step, "effetto"))
            current["snapshot"] = step.snapshot

    if current is not None:
        actions.append(current)
    elif pending_last_step is not None:
        actions.append(
            {
                "index": 0,
                "action_number": 0,
                "turn": pending_last_step.turn,
                "active_player": pending_last_step.active_player,
                "phase": pending_last_step.phase,
                "label": "Svolgimento della partita",
                "events": pending_events,
                "snapshot": pending_last_step.snapshot,
            }
        )

    return {
        "schema": "bless.replay",
        "schema_version": REPLAY_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "seed": result.seed,
        "deck": result.deck,
        "bots": list(result.bot_names),
        "first_player": result.first_player,
        "winner": result.winner,
        "scores": list(result.scores),
        "turns": result.turns,
        "final_trigger_player": result.final_trigger_player,
        "final_trigger_cause": result.final_trigger_cause,
        "player_activity": [
            {
                "invocations": result.telemetry.invocations[player],
                "glyph_uses": result.telemetry.glyph_uses[player],
                "charges_created": result.telemetry.charges_created[player],
            }
            for player in (0, 1)
        ],
        "actions": actions,
    }
