export type DeckName = "Luce-Ombra" | "TuonoSabbia";

export interface RoomPlayer {
  slot: number;
  name: string;
  connected: boolean;
  ready: boolean;
  deck: DeckName | null;
  rematch: boolean;
}

export interface RoomView {
  code: string;
  status: "waiting" | "active" | "finished";
  version: number;
  player_slot: number;
  players: Array<RoomPlayer | null>;
  agreed_deck: DeckName | null;
  game?: Record<string, unknown> | null;
}

export interface RoomAccess {
  code: string;
  token: string;
  room: RoomView;
}

const API_BASE = (process.env.NEXT_PUBLIC_BLESS_GAME_API ?? "").replace(/\/$/, "");

function roomStorageKey(code: string): string {
  return `bless-room-${code.toUpperCase()}`;
}

export function rememberRoomAccess(code: string, token: string): void {
  try {
    window.localStorage.setItem(roomStorageKey(code), token);
    return;
  } catch {
    // Con archivio pieno/bloccato, prova a conservare l'accesso nella scheda.
  }
  try {
    window.sessionStorage.setItem(roomStorageKey(code), token);
  } catch {
    throw new Error("Il browser non permette di conservare l'accesso alla stanza. Abilita la memoria del sito e riprova.");
  }
}

export function readRoomAccess(code: string): string | null {
  for (const storage of ["localStorage", "sessionStorage"] as const) {
    try {
      const token = window[storage].getItem(roomStorageKey(code));
      if (token) return token;
    } catch {
      // La lettura puo' essere vietata dalle impostazioni di privacy.
    }
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isRoomView(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return typeof value.code === "string"
    && Number.isInteger(value.version)
    && (value.player_slot === 0 || value.player_slot === 1)
    && ["waiting", "active", "finished"].includes(String(value.status))
    && Array.isArray(value.players)
    && value.players.length === 2
    && value.players.every((player) => player === null || (
      isRecord(player) && typeof player.name === "string" && typeof player.ready === "boolean"
    ));
}

async function request<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 35_000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init, headers, cache: "no-store", signal: controller.signal,
    });
    const payload: unknown = await response.json().catch(() => null);
    if (controller.signal.aborted) throw new Error("timeout");
    if (!response.ok) {
      throw new Error(isRecord(payload) && typeof payload.error === "string"
        ? payload.error : "Il tavolo online non è disponibile.");
    }
    if (!isRecord(payload)) throw new Error("Risposta della stanza non valida. Riprova tra poco.");
    const access = "room" in payload;
    if (!isRoomView(access ? payload.room : payload)
      || (access && (typeof payload.token !== "string" || !payload.token
        || payload.code !== (payload.room as Record<string, unknown>).code))) {
      throw new Error("Risposta della stanza non valida. Riprova tra poco.");
    }
    return payload as T;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error("La stanza non risponde. Controlla la connessione: il tavolo proverà a riconnettersi.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export function createRoom(name: string): Promise<RoomAccess> {
  return request<RoomAccess>("/api/game", {
    method: "POST",
    body: JSON.stringify({ operation: "create", name }),
  });
}

export function joinRoom(code: string, name: string): Promise<RoomAccess> {
  return request<RoomAccess>("/api/game", {
    method: "POST",
    body: JSON.stringify({ operation: "join", code, name }),
  });
}

export function getRoom(code: string, token: string): Promise<RoomView> {
  return request<RoomView>(`/api/game?code=${encodeURIComponent(code)}`, {}, token);
}

export function setRoomReady(code: string, token: string, deck: DeckName, ready: boolean): Promise<RoomView> {
  return request<RoomView>("/api/game", {
    method: "POST",
    body: JSON.stringify({ operation: "ready", code, deck, ready }),
  }, token);
}

export function sendRoomCommand(code: string, token: string, command: Record<string, unknown>): Promise<RoomView> {
  return request<RoomView>("/api/game", {
    method: "POST",
    body: JSON.stringify({ operation: "command", code, command }),
  }, token);
}

export function requestRoomRematch(code: string, token: string): Promise<RoomView> {
  return request<RoomView>("/api/game", {
    method: "POST",
    body: JSON.stringify({ operation: "rematch", code }),
  }, token);
}
