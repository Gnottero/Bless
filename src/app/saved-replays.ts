export const SAVED_REPLAYS_STORAGE_KEY = "bless-saved-replays-v1";
export const MAX_SAVED_REPLAYS = 8;
export const REPLAY_ARCHIVE_FORMAT = "bless.replay.archive";
export const REPLAY_ARCHIVE_VERSION = 1;

export interface SavedReplayReview {
  outcome: "vittoria" | "pareggio" | "sconfitta";
  human_score: number;
  bot_score: number;
  bot: string;
  turns: number;
  actions: number;
  altar_cards: number;
  prayer_share: number;
  own_eye_buffs: number;
  high_karma_eye_buffs: number;
  enemy_eye_debuffs: number;
  human_invocations?: number;
  bot_invocations?: number;
  human_glyph_uses?: number;
  bot_glyph_uses?: number;
  human_charges_created?: number;
  bot_charges_created?: number;
}

export interface SavedReplayRecord<ReplayValue = unknown> {
  id: string;
  saved_at: string;
  title: string;
  replay: ReplayValue;
  review?: SavedReplayReview;
}

export interface SavedReplayArchive<ReplayValue = unknown> {
  format: typeof REPLAY_ARCHIVE_FORMAT;
  version: typeof REPLAY_ARCHIVE_VERSION;
  source: "blesscardgame.com";
  exported_at: string;
  records: SavedReplayRecord<ReplayValue>[];
}

export function parseSavedReplays<ReplayValue>(raw: string | null): SavedReplayRecord<ReplayValue>[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is SavedReplayRecord<ReplayValue> => Boolean(
        item
        && typeof item === "object"
        && typeof (item as SavedReplayRecord<ReplayValue>).id === "string"
        && typeof (item as SavedReplayRecord<ReplayValue>).saved_at === "string"
        && typeof (item as SavedReplayRecord<ReplayValue>).title === "string"
        && (item as SavedReplayRecord<ReplayValue>).replay,
      ))
      .slice(0, MAX_SAVED_REPLAYS);
  } catch {
    return [];
  }
}

export function readSavedReplays<ReplayValue>(): SavedReplayRecord<ReplayValue>[] {
  try {
    return parseSavedReplays<ReplayValue>(window.localStorage.getItem(SAVED_REPLAYS_STORAGE_KEY));
  } catch {
    // Il browser puo' negare anche la lettura (privacy, storage disabilitato).
    // L'archivio non deve impedire l'accesso al gioco.
    return [];
  }
}

export function createSavedReplayArchive<ReplayValue>(
  records: SavedReplayRecord<ReplayValue>[],
  exportedAt = new Date().toISOString(),
): SavedReplayArchive<ReplayValue> {
  return {
    format: REPLAY_ARCHIVE_FORMAT,
    version: REPLAY_ARCHIVE_VERSION,
    source: "blesscardgame.com",
    exported_at: exportedAt,
    records: records.slice(0, MAX_SAVED_REPLAYS),
  };
}

export function downloadSavedReplayArchive<ReplayValue>(
  records: SavedReplayRecord<ReplayValue>[],
): number {
  if (!records.length || typeof document === "undefined" || typeof URL === "undefined") return 0;
  try {
    const archive = createSavedReplayArchive(records);
    const blob = new Blob([JSON.stringify(archive, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `bless-partite-${archive.exported_at.slice(0, 10)}.json`;
    link.style.display = "none";
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    return archive.records.length;
  } catch {
    return 0;
  }
}
