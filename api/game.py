from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import pickle
import re
import secrets
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = PROJECT_ROOT / "public" / "python"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.bless_server.multiplayer import MultiplayerGameSession  # noqa: E402


ROOM_TTL_SECONDS = 24 * 60 * 60
CONNECTED_WINDOW_SECONDS = 45
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_RE = re.compile(r"^[A-HJ-NP-Z2-9]{9}$")
DECKS = {"Luce-Ombra", "TuonoSabbia"}


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class RoomCollision(RuntimeError):
    pass


def now_seconds() -> int:
    return int(time.time())


def clean_name(value: Any, fallback: str) -> str:
    name = " ".join(str(value or "").strip().split())
    if not name:
        name = fallback
    if len(name) > 24 or any(ord(character) < 32 for character in name):
        raise ApiError(400, "Il nome può contenere al massimo 24 caratteri.")
    return name


def normalize_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    if not ROOM_CODE_RE.fullmatch(code):
        raise ApiError(404, "Questa stanza non esiste.")
    return code


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def state_secret() -> bytes:
    configured = os.getenv("BLESS_GAME_STATE_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    if os.getenv("VERCEL"):
        raise ApiError(503, "Il servizio di gioco deve ancora essere collegato in produzione.")
    return b"bless-local-development-state"


def encode_session(session: MultiplayerGameSession) -> str:
    payload = pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
    signature = hmac.new(state_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + payload).decode("ascii")


def decode_session(value: str) -> MultiplayerGameSession:
    try:
        encoded = base64.urlsafe_b64decode(value.encode("ascii"))
        signature, payload = encoded[:32], encoded[32:]
    except Exception as error:
        raise ApiError(500, "Lo stato della partita non è leggibile.") from error
    expected = hmac.new(state_secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ApiError(500, "Lo stato della partita non è valido.")
    session = pickle.loads(payload)
    if not isinstance(session, MultiplayerGameSession):
        raise ApiError(500, "La partita salvata non è valida.")
    return session


class RoomStore:
    def __init__(self) -> None:
        self.redis_url = (
            os.getenv("KV_REST_API_URL")
            or os.getenv("UPSTASH_REDIS_REST_URL")
            or ""
        ).rstrip("/")
        self.redis_token = (
            os.getenv("KV_REST_API_TOKEN")
            or os.getenv("UPSTASH_REDIS_REST_TOKEN")
            or ""
        )
        if bool(self.redis_url) != bool(self.redis_token):
            raise ApiError(503, "La memoria condivisa delle stanze non è configurata correttamente.")
        if os.getenv("VERCEL") and not self.redis_url:
            raise ApiError(503, "La memoria condivisa delle stanze deve ancora essere collegata.")
        self.sqlite_path = os.getenv(
            "BLESS_ROOM_DB",
            str(Path(tempfile.gettempdir()) / "bless-official-rooms.sqlite3"),
        )

    @staticmethod
    def key(code: str) -> str:
        return f"bless:room:{code}"

    def _redis_command(self, *parts: Any) -> Any:
        request = urllib.request.Request(
            self.redis_url,
            data=json.dumps([str(part) for part in parts], separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.redis_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise ApiError(503, "La stanza non è raggiungibile in questo momento.") from error
        if payload.get("error"):
            raise ApiError(503, "La memoria condivisa della stanza ha rifiutato la richiesta.")
        return payload.get("result")

    @contextlib.contextmanager
    def _redis_lock(self, code: str):
        lock_key = f"{self.key(code)}:lock"
        token = secrets.token_hex(16)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if self._redis_command("SET", lock_key, token, "NX", "PX", 15_000) == "OK":
                break
            time.sleep(0.06)
        else:
            raise ApiError(409, "La stanza è occupata: riprova tra un istante.")
        try:
            yield
        finally:
            script = "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
            try:
                self._redis_command("EVAL", script, 1, lock_key, token)
            except ApiError:
                pass

    def _sqlite(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path, timeout=8)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS rooms (code TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at INTEGER NOT NULL)"
        )
        return connection

    def mutate(
        self,
        code: str,
        callback: Callable[[dict[str, Any] | None], dict[str, Any]],
    ) -> dict[str, Any]:
        if self.redis_url:
            with self._redis_lock(code):
                raw = self._redis_command("GET", self.key(code))
                current = json.loads(raw) if raw else None
                updated = callback(current)
                self._redis_command(
                    "SET",
                    self.key(code),
                    json.dumps(updated, ensure_ascii=False, separators=(",", ":")),
                    "EX",
                    ROOM_TTL_SECONDS,
                )
                return updated

        connection = self._sqlite()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM rooms WHERE code = ?", (code,)).fetchone()
            current = json.loads(row[0]) if row else None
            updated = callback(current)
            connection.execute(
                "INSERT INTO rooms (code, payload, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(code) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at",
                (
                    code,
                    json.dumps(updated, ensure_ascii=False, separators=(",", ":")),
                    now_seconds() + ROOM_TTL_SECONDS,
                ),
            )
            connection.execute("DELETE FROM rooms WHERE expires_at < ?", (now_seconds(),))
            connection.commit()
            return updated
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def ensure_live_room(room: dict[str, Any] | None) -> dict[str, Any]:
    if room is None:
        raise ApiError(404, "Questa stanza non esiste più.")
    if int(room.get("expires_at", 0)) < now_seconds():
        raise ApiError(410, "Questa stanza è scaduta.")
    return room


def player_slot(room: dict[str, Any], token: str) -> int:
    if not token:
        raise ApiError(401, "Apri la stanza dal dispositivo con cui sei entrato.")
    digest = token_digest(token)
    for slot, player in enumerate(room["players"]):
        if player and hmac.compare_digest(str(player.get("token_hash", "")), digest):
            return slot
    raise ApiError(401, "Il tuo accesso a questa stanza non è valido.")


def agreed_deck(room: dict[str, Any]) -> str | None:
    players = room["players"]
    if not players[0] or not players[1]:
        return None
    decks = [players[0].get("deck"), players[1].get("deck")]
    return decks[0] if decks[0] in DECKS and decks[0] == decks[1] else None


def room_view(room: dict[str, Any], slot: int) -> dict[str, Any]:
    current = now_seconds()
    players = []
    for index, player in enumerate(room["players"]):
        if player is None:
            players.append(None)
            continue
        players.append(
            {
                "slot": index,
                "name": "Tu" if index == slot else player["name"],
                "connected": current - int(player.get("last_seen", 0)) <= CONNECTED_WINDOW_SECONDS,
                "ready": bool(player.get("ready")),
                "deck": player.get("deck"),
                "rematch": bool(player.get("rematch")),
            }
        )
    game_view = None
    if room.get("game"):
        game_view = decode_session(str(room["game"])).state_for(slot)
    return {
        "code": room["code"],
        "status": room["status"],
        "version": int(room["version"]),
        "player_slot": slot,
        "players": players,
        "agreed_deck": agreed_deck(room),
        "game": game_view,
    }


def create_room(store: RoomStore, name_value: Any) -> tuple[dict[str, Any], str]:
    name = clean_name(name_value, "Giocatore 1")
    token = new_token()
    for _ in range(12):
        code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(9))
        created = now_seconds()
        room = {
            "code": code,
            "status": "waiting",
            "version": 1,
            "created_at": created,
            "updated_at": created,
            "expires_at": created + ROOM_TTL_SECONDS,
            "players": [
                {
                    "name": name,
                    "token_hash": token_digest(token),
                    "last_seen": created,
                    "ready": False,
                    "deck": None,
                    "rematch": False,
                },
                None,
            ],
            "game": None,
        }

        def insert(current: dict[str, Any] | None) -> dict[str, Any]:
            if current is not None:
                raise RoomCollision()
            return room

        try:
            store.mutate(code, insert)
            return room, token
        except RoomCollision:
            continue
    raise ApiError(503, "Non è stato possibile assegnare un codice alla stanza.")


def join_room(store: RoomStore, code_value: Any, name_value: Any) -> tuple[dict[str, Any], str]:
    code = normalize_code(code_value)
    name = clean_name(name_value, "Giocatore 2")
    token = new_token()

    def join(current: dict[str, Any] | None) -> dict[str, Any]:
        room = ensure_live_room(current)
        if room["status"] != "waiting":
            raise ApiError(409, "La partita in questa stanza è già iniziata.")
        if room["players"][1] is not None:
            raise ApiError(409, "La stanza ha già due giocatori.")
        current_time = now_seconds()
        room["players"][1] = {
            "name": name,
            "token_hash": token_digest(token),
            "last_seen": current_time,
            "ready": False,
            "deck": None,
            "rematch": False,
        }
        room["version"] += 1
        room["updated_at"] = current_time
        room["expires_at"] = current_time + ROOM_TTL_SECONDS
        return room

    return store.mutate(code, join), token


def touch_room(store: RoomStore, code_value: Any, token: str) -> tuple[dict[str, Any], int]:
    code = normalize_code(code_value)
    found_slot = -1

    def touch(current: dict[str, Any] | None) -> dict[str, Any]:
        nonlocal found_slot
        room = ensure_live_room(current)
        found_slot = player_slot(room, token)
        room["players"][found_slot]["last_seen"] = now_seconds()
        return room

    room = store.mutate(code, touch)
    return room, found_slot


def ready_room(
    store: RoomStore,
    code_value: Any,
    token: str,
    deck_value: Any,
    ready_value: Any,
) -> tuple[dict[str, Any], int]:
    code = normalize_code(code_value)
    deck = str(deck_value or "")
    if deck not in DECKS:
        raise ApiError(400, "Scegli uno dei mazzi disponibili.")
    found_slot = -1

    def update(current: dict[str, Any] | None) -> dict[str, Any]:
        nonlocal found_slot
        room = ensure_live_room(current)
        found_slot = player_slot(room, token)
        if room["status"] != "waiting":
            raise ApiError(409, "La partita è già iniziata.")
        player = room["players"][found_slot]
        player["deck"] = deck
        player["ready"] = bool(ready_value)
        player["last_seen"] = now_seconds()
        room["version"] += 1
        room["updated_at"] = now_seconds()
        chosen = agreed_deck(room)
        if chosen and all(item and item.get("ready") for item in room["players"]):
            for item in room["players"]:
                item["rematch"] = False
            session = MultiplayerGameSession(
                {
                    "seed": secrets.randbelow(2_147_483_646) + 1,
                    "deck": chosen,
                    "player_names": [room["players"][0]["name"], room["players"][1]["name"]],
                    "first_player": secrets.randbelow(2),
                }
            )
            room["game"] = encode_session(session)
            room["status"] = "active"
            room["version"] += 1
        return room

    return store.mutate(code, update), found_slot


def command_room(
    store: RoomStore,
    code_value: Any,
    token: str,
    command: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    code = normalize_code(code_value)
    found_slot = -1

    def execute(current: dict[str, Any] | None) -> dict[str, Any]:
        nonlocal found_slot
        room = ensure_live_room(current)
        found_slot = player_slot(room, token)
        if room["status"] not in {"active", "finished"} or not room.get("game"):
            raise ApiError(409, "La partita non è ancora iniziata.")
        expected = command.get("expected_version")
        if expected is not None and int(expected) != int(room["version"]):
            raise ApiError(409, "Il tavolo è cambiato: aggiorno la partita.")
        session = decode_session(str(room["game"]))
        kind = str(command.get("type", ""))
        try:
            if kind == "action":
                session.perform_action(found_slot, str(command.get("action_id", "")))
            elif kind == "choice":
                session.submit_choice(found_slot, command.get("value"))
            elif kind == "end_turn":
                session.end_turn(found_slot)
            elif kind == "start_turn":
                session.start_turn(found_slot)
            elif kind == "abandon":
                session.forfeit(found_slot)
            else:
                raise ApiError(400, "Comando di gioco non valido.")
        except ApiError:
            raise
        except ValueError as error:
            raise ApiError(409, str(error)) from error
        room["game"] = encode_session(session)
        room["players"][found_slot]["last_seen"] = now_seconds()
        room["version"] += 1
        room["updated_at"] = now_seconds()
        if session.engine.game_over:
            room["status"] = "finished"
        return room

    return store.mutate(code, execute), found_slot


def rematch_room(
    store: RoomStore,
    code_value: Any,
    token: str,
) -> tuple[dict[str, Any], int]:
    code = normalize_code(code_value)
    found_slot = -1

    def request_rematch(current: dict[str, Any] | None) -> dict[str, Any]:
        nonlocal found_slot
        room = ensure_live_room(current)
        found_slot = player_slot(room, token)
        if room["status"] != "finished" or not room.get("game"):
            raise ApiError(409, "La partita non è ancora terminata.")

        current_time = now_seconds()
        player = room["players"][found_slot]
        player["rematch"] = True
        player["last_seen"] = current_time
        room["version"] += 1
        room["updated_at"] = current_time

        if all(item and item.get("rematch") for item in room["players"]):
            room["status"] = "waiting"
            room["game"] = None
            for item in room["players"]:
                item["ready"] = False
                item["rematch"] = False
            room["version"] += 1
        return room

    return store.mutate(code, request_rematch), found_slot


class handler(BaseHTTPRequestHandler):
    server_version = "BlessGame/1.0"

    def _origin(self) -> str | None:
        origin = self.headers.get("Origin")
        allowed = os.getenv("BLESS_ALLOWED_ORIGIN", "").rstrip("/")
        if origin and allowed and origin.rstrip("/") == allowed:
            return origin
        return None

    def _headers(self, status: int, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Vary", "Origin")
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, len(encoded))
        self.wfile.write(encoded)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(400, "Richiesta non valida.") from error
        if length < 1 or length > 65_536:
            raise ApiError(400, "Richiesta non valida.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ApiError(400, "Il contenuto della richiesta non è valido.") from error
        if not isinstance(payload, dict):
            raise ApiError(400, "Il contenuto della richiesta non è valido.")
        return payload

    def _token(self) -> str:
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ApiError(401, "Accesso alla stanza mancante.")
        token = authorization[7:].strip()
        if len(token) < 32 or len(token) > 128:
            raise ApiError(401, "Accesso alla stanza non valido.")
        return token

    def _handle(self, action: Callable[[], None]) -> None:
        try:
            action()
        except ApiError as error:
            self._json(error.status, {"error": str(error)})
        except Exception as error:
            print(f"Bless game API error: {type(error).__name__}: {error}", file=sys.stderr)
            self._json(500, {"error": "Il tavolo ha incontrato un problema inatteso."})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        def action() -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/game":
                raise ApiError(404, "Risorsa non trovata.")
            code = parse_qs(parsed.query).get("code", [""])[0]
            room, slot = touch_room(RoomStore(), code, self._token())
            self._json(200, room_view(room, slot))

        self._handle(action)

    def do_POST(self) -> None:
        def action() -> None:
            if urlparse(self.path).path != "/api/game":
                raise ApiError(404, "Risorsa non trovata.")
            payload = self._body()
            operation = str(payload.get("operation", ""))
            store = RoomStore()
            if operation == "create":
                room, token = create_room(store, payload.get("name"))
                self._json(201, {"code": room["code"], "token": token, "room": room_view(room, 0)})
                return
            if operation == "join":
                room, new_access = join_room(store, payload.get("code"), payload.get("name"))
                self._json(200, {"code": room["code"], "token": new_access, "room": room_view(room, 1)})
                return
            token = self._token()
            if operation == "ready":
                room, slot = ready_room(
                    store,
                    payload.get("code"),
                    token,
                    payload.get("deck"),
                    payload.get("ready"),
                )
                self._json(200, room_view(room, slot))
                return
            if operation == "command":
                command = payload.get("command")
                if not isinstance(command, dict):
                    raise ApiError(400, "Comando di gioco non valido.")
                room, slot = command_room(store, payload.get("code"), token, command)
                self._json(200, room_view(room, slot))
                return
            if operation == "rematch":
                room, slot = rematch_room(store, payload.get("code"), token)
                self._json(200, room_view(room, slot))
                return
            raise ApiError(400, "Operazione non valida.")

        self._handle(action)

    def log_message(self, message: str, *args: Any) -> None:
        if os.getenv("BLESS_API_LOG"):
            super().log_message(message, *args)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8788"))
    print(f"Bless game API on http://127.0.0.1:{port}/api/game")
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
