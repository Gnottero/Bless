from __future__ import annotations

import json
import sys
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[2] / "public" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from browser_bridge import aggregate_chunks, run_chunk  # noqa: E402


def test_browser_bridge_returns_report_replay_and_bundle() -> None:
    config = json.dumps(
        {
            "games": 2,
            "deck": "Luce-Ombra",
            "mode": "Sfida diretta",
            "bot_1": "Bot",
            "bot_2": "Bot",
            "seed": 24680,
            "workers": 2,
            "learning_enabled": True,
            "learning_generation": 3,
            "learning_total_games": 250,
            "learning_weights": {},
        }
    )
    chunks = [run_chunk(config, 0, 1, 0), run_chunk(config, 1, 2, 1)]
    payload = json.loads(aggregate_chunks(config, json.dumps(chunks)))

    assert payload["report"]["summary"]["games"] == 2
    assert len(payload["report"]["card_stats"]) == 62
    replay_actions = payload["report"]["replay"]["actions"]
    assert replay_actions
    assert all(action["events"] for action in replay_actions)
    assert all("snapshot" in action for action in replay_actions)
    assert any(len(action["events"]) > 1 for action in replay_actions)
    first_malediction = next(
        card
        for action in replay_actions
        for player in action["snapshot"]["players"]
        for card in player["maledictions"]
    )
    assert "base_eye" in first_malediction
    assert "base_karma" in first_malediction
    assert payload["report"]["learning"]["generation_after"] == 4
    assert payload["report"]["learning"]["total_games_after"] == 252
    assert set(payload["report"]["learning"]["next_state"]["weights"]) == {"Bot"}
    bot = payload["report"]["learning"]["diagnostics"]["Bot"]
    assert "own_eye_buffs_per_game" in bot
    assert "high_karma_eye_buffs_per_game" in bot
    assert "enemy_eye_debuffs_per_game" in bot
    assert "eye_karma_setup" in payload["report"]["learning"]["next_state"]["weights"]["Bot"]
    assert "next_turn_plan" in payload["report"]["learning"]["next_state"]["weights"]["Bot"]
    assert payload["bundle_name"].endswith(".zip")
    assert len(payload["bundle_base64"]) > 100


if __name__ == "__main__":
    test_browser_bridge_returns_report_replay_and_bundle()
    print("browser bridge: ok")
