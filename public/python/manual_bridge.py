from __future__ import annotations

import json
from typing import Any

from bless_sim.manual import ManualGameSession


SESSION: ManualGameSession | None = None


def _encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def start_manual_game(config_json: str) -> str:
    global SESSION
    SESSION = ManualGameSession(json.loads(config_json))
    return _encode(SESSION.state())


def manual_command(command_json: str) -> str:
    if SESSION is None:
        raise RuntimeError("Avvia prima una partita.")
    command = json.loads(command_json)
    kind = command.get("type")
    if kind == "state":
        state = SESSION.state()
    elif kind == "action":
        state = SESSION.perform_action(str(command["action_id"]))
    elif kind == "choice":
        state = SESSION.submit_choice(command.get("value"))
    elif kind == "end_turn":
        state = SESSION.end_human_turn()
    elif kind == "undo":
        state = SESSION.undo_last_move()
    elif kind == "opponent_step":
        state = SESSION.opponent_step()
    elif kind == "human_start":
        state = SESSION.start_human_turn()
    else:
        raise ValueError(f"Comando manuale non valido: {kind}")
    return _encode(state)
