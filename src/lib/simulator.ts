/**
 * Client side of the online simulator.
 *
 * The table, private rooms and match API are served by this same application.
 * Paths, storage keys and payloads below are their shared contract.
 *
 * Browser only: every function touches `window`.
 */

export type DeckId = "Luce-Ombra" | "TuonoSabbia";

const API = "/api/game";
const ROOM_KEY_PREFIX = "bless-room-";
/** Also the key to listen for in `storage` events. */
export const REPLAYS_KEY = "bless-saved-replays-v1";
const MAX_REPLAYS = 8;
const TIMEOUT_MS = 35_000;

export function botUrl(deck: DeckId): string {
  return `/gioco/bot?mazzo=${encodeURIComponent(deck)}`;
}

export function roomUrl(code: string): string {
  return `/gioco/stanza/${encodeURIComponent(code)}`;
}

/* ------------------------------ rooms ------------------------------ */

type CreatedRoom = { code: string; token: string };

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Opens a private room and returns its code plus the host's access token. */
export async function createRoom(name: string): Promise<CreatedRoom> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation: "create", name }),
      cache: "no-store",
      signal: controller.signal,
    });
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(
        isObject(body) && typeof body.error === "string"
          ? body.error
          : "Il tavolo online non è disponibile.",
      );
    }
    if (
      !isObject(body) ||
      typeof body.code !== "string" ||
      typeof body.token !== "string" ||
      !body.token
    ) {
      throw new Error("Risposta della stanza non valida. Riprova tra poco.");
    }
    return { code: body.code, token: body.token };
  } catch (err) {
    if (controller.signal.aborted) {
      throw new Error("La stanza non risponde. Controlla la connessione e riprova.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Stores the token the room page reads to let the host back in. */
export function rememberRoomAccess(code: string, token: string): void {
  const key = ROOM_KEY_PREFIX + code.toUpperCase();
  for (const store of ["localStorage", "sessionStorage"] as const) {
    try {
      window[store].setItem(key, token);
      return;
    } catch {
      // Storage blocked: try the next one.
    }
  }
  throw new Error(
    "Il browser non permette di conservare l'accesso alla stanza. Abilita la memoria del sito e riprova.",
  );
}

/* ----------------------------- replays ----------------------------- */

/** A finished match, as the simulator saves it. `replay` is opaque here. */
export type SavedReplay = {
  id: string;
  saved_at: string;
  title: string;
  replay: unknown;
};

export function readSavedReplays(): SavedReplay[] {
  try {
    const raw = window.localStorage.getItem(REPLAYS_KEY);
    if (!raw) return [];
    const list: unknown = JSON.parse(raw);
    if (!Array.isArray(list)) return [];
    return list
      .filter(
        (r): r is SavedReplay =>
          isObject(r) &&
          typeof r.id === "string" &&
          typeof r.saved_at === "string" &&
          typeof r.title === "string" &&
          Boolean(r.replay),
      )
      .slice(0, MAX_REPLAYS);
  } catch {
    return [];
  }
}

/**
 * Downloads every saved match as one JSON file, in the archive format the
 * "Sim. Bless" chat reads. Returns how many matches went in (0 on failure).
 */
export function downloadReplayArchive(replays: SavedReplay[]): number {
  if (!replays.length) return 0;
  try {
    const archive = {
      format: "bless.replay.archive",
      version: 1,
      source: "blesscardgame.com",
      exported_at: new Date().toISOString(),
      records: replays.slice(0, MAX_REPLAYS),
    };
    const blob = new Blob([JSON.stringify(archive, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `bless-partite-${archive.exported_at.slice(0, 10)}.json`;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
    return archive.records.length;
  } catch {
    return 0;
  }
}
