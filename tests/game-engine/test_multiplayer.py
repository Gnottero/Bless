from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = PROJECT_ROOT / "public" / "python"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PYTHON_ROOT))

from api.bless_server.multiplayer import MultiplayerGameSession  # noqa: E402
from api.game import (  # noqa: E402
    RoomStore,
    command_room,
    create_room,
    join_room,
    ready_room,
    rematch_room,
    room_view,
)


def _started_session() -> MultiplayerGameSession:
    session = MultiplayerGameSession(
        {
            "seed": 81_308,
            "deck": "Luce-Ombra",
            "player_names": ["Alice", "Bruno"],
            "first_player": 0,
        }
    )
    session.submit_choice(0, [])
    session.submit_choice(1, [])
    return session


def test_server_engine_mirror_matches_the_browser_source() -> None:
    source_root = PROJECT_ROOT / "public" / "python"
    mirror_root = PROJECT_ROOT / "api" / "_engine"
    source_files = [
        *sorted((source_root / "bless_sim").glob("*.py")),
        source_root / "data" / "luce_ombra.json",
        source_root / "data" / "tuono_sabbia.json",
    ]
    for source in source_files:
        mirror = mirror_root / source.relative_to(source_root)
        assert mirror.read_bytes() == source.read_bytes(), f"Specchio non sincronizzato: {source.name}"


def test_multiplayer_setup_requires_each_players_own_choice() -> None:
    session = MultiplayerGameSession(
        {"seed": 3, "deck": "Luce-Ombra", "player_names": ["Alice", "Bruno"]}
    )
    assert session.pending_request["player"] == 0
    try:
        session.submit_choice(1, [])
    except ValueError as error:
        assert "altro giocatore" in str(error)
    else:
        raise AssertionError("Il secondo giocatore non deve rispondere alla scelta del primo.")


def test_player_waits_cleanly_while_opponent_completes_a_choice() -> None:
    session = MultiplayerGameSession(
        {"seed": 4, "deck": "Luce-Ombra", "player_names": ["Alice", "Bruno"]}
    )
    assert session.state_for(0)["mode"] == "choice"
    session.submit_choice(0, [])
    assert session.pending_request["player"] == 1
    assert session.state_for(0)["choice"] is None
    assert session.state_for(0)["mode"] == "waiting_choice"
    assert session.state_for(1)["mode"] == "choice"


def test_multiplayer_views_hide_opponent_hands_altars_and_charges() -> None:
    session = _started_session()
    charged_uid = session.engine.players[0].hand[0]
    session.engine.charge_card(charged_uid, 0, "test privacy")
    host = session.state_for(0)
    guest = session.state_for(1)

    assert host["players"][0]["hand"]
    assert not host["players"][0]["hand"][0].get("hidden", False)
    assert host["players"][1]["hand"][0]["hidden"] is True
    assert guest["players"][0]["hand"][0]["hidden"] is True
    assert host["players"][0]["charges"][0]["name"]
    assert guest["players"][0]["charges"][0]["hidden"] is True


def test_multiplayer_rejects_actions_from_the_inactive_player() -> None:
    session = _started_session()
    inactive = 1 - session.engine.active_player
    try:
        session.end_turn(inactive)
    except ValueError as error:
        assert "turno" in str(error)
    else:
        raise AssertionError("Il giocatore inattivo non deve poter terminare il turno.")


def test_room_starts_only_after_two_matching_ready_choices() -> None:
    database_path = Path(tempfile.gettempdir()) / f"bless-room-test-{os.getpid()}.sqlite3"
    previous = os.environ.get("BLESS_ROOM_DB")
    os.environ["BLESS_ROOM_DB"] = str(database_path)
    try:
        store = RoomStore()
        room, host_token = create_room(store, "Alice")
        room, guest_token = join_room(store, room["code"], "Bruno")
        room, _ = ready_room(store, room["code"], host_token, "Luce-Ombra", True)
        assert room["status"] == "waiting"
        room, _ = ready_room(store, room["code"], guest_token, "TuonoSabbia", True)
        assert room["status"] == "waiting"
        room, _ = ready_room(store, room["code"], guest_token, "Luce-Ombra", True)
        assert room["status"] == "active"
        assert room["game"]
    finally:
        if previous is None:
            os.environ.pop("BLESS_ROOM_DB", None)
        else:
            os.environ["BLESS_ROOM_DB"] = previous
        database_path.unlink(missing_ok=True)


def test_room_payload_never_exposes_access_tokens_or_opponent_private_cards() -> None:
    database_path = Path(tempfile.gettempdir()) / f"bless-room-view-test-{os.getpid()}.sqlite3"
    previous = os.environ.get("BLESS_ROOM_DB")
    os.environ["BLESS_ROOM_DB"] = str(database_path)
    try:
        store = RoomStore()
        room, host_token = create_room(store, "Alice")
        room, guest_token = join_room(store, room["code"], "Bruno")
        room, _ = ready_room(store, room["code"], host_token, "Luce-Ombra", True)
        room, _ = ready_room(store, room["code"], guest_token, "Luce-Ombra", True)
        host_view = room_view(room, 0)
        encoded = json.dumps(host_view)
        assert host_token not in encoded
        assert guest_token not in encoded
        assert "token_hash" not in encoded
        assert host_view["game"]["players"][1]["hand"][0]["hidden"] is True
    finally:
        if previous is None:
            os.environ.pop("BLESS_ROOM_DB", None)
        else:
            os.environ["BLESS_ROOM_DB"] = previous
        database_path.unlink(missing_ok=True)


def test_abandon_awards_the_win_to_the_other_player() -> None:
    database_path = Path(tempfile.gettempdir()) / f"bless-room-abandon-test-{os.getpid()}.sqlite3"
    previous = os.environ.get("BLESS_ROOM_DB")
    os.environ["BLESS_ROOM_DB"] = str(database_path)
    try:
        store = RoomStore()
        room, host_token = create_room(store, "Alice")
        room, guest_token = join_room(store, room["code"], "Bruno")
        room, _ = ready_room(store, room["code"], host_token, "Luce-Ombra", True)
        room, _ = ready_room(store, room["code"], guest_token, "Luce-Ombra", True)

        room, _ = command_room(
            store,
            room["code"],
            host_token,
            {"type": "abandon", "expected_version": room["version"]},
        )
        guest_view = room_view(room, 1)

        assert room["status"] == "finished"
        assert guest_view["game"]["winner"] == 1
        assert guest_view["game"]["game_over"] is True
        assert guest_view["game"]["replay"]
        assert "abbandonato" in guest_view["game"]["last_action"]
    finally:
        if previous is None:
            os.environ.pop("BLESS_ROOM_DB", None)
        else:
            os.environ["BLESS_ROOM_DB"] = previous
        database_path.unlink(missing_ok=True)


def test_both_players_can_request_a_rematch_in_the_same_room() -> None:
    database_path = Path(tempfile.gettempdir()) / f"bless-room-rematch-test-{os.getpid()}.sqlite3"
    previous = os.environ.get("BLESS_ROOM_DB")
    os.environ["BLESS_ROOM_DB"] = str(database_path)
    try:
        store = RoomStore()
        room, host_token = create_room(store, "Alice")
        room, guest_token = join_room(store, room["code"], "Bruno")
        room, _ = ready_room(store, room["code"], host_token, "TuonoSabbia", True)
        room, _ = ready_room(store, room["code"], guest_token, "TuonoSabbia", True)
        room, _ = command_room(
            store,
            room["code"],
            host_token,
            {"type": "abandon", "expected_version": room["version"]},
        )

        room, _ = rematch_room(store, room["code"], host_token)
        assert room["status"] == "finished"
        assert room_view(room, 0)["players"][0]["rematch"] is True
        assert room_view(room, 0)["players"][1]["rematch"] is False

        room, _ = rematch_room(store, room["code"], guest_token)
        assert room["status"] == "waiting"
        assert room["game"] is None
        assert [player["deck"] for player in room["players"]] == ["TuonoSabbia", "TuonoSabbia"]
        assert not any(player["ready"] or player["rematch"] for player in room["players"])
    finally:
        if previous is None:
            os.environ.pop("BLESS_ROOM_DB", None)
        else:
            os.environ["BLESS_ROOM_DB"] = previous
        database_path.unlink(missing_ok=True)
