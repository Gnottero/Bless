"use client";

import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import {
  REPLAYS_KEY,
  botUrl,
  createRoom,
  downloadReplayArchive,
  joinRoom,
  readSavedReplays,
  rememberRoomAccess,
  roomUrl,
  type DeckId,
  type SavedReplay,
} from "@/lib/simulator";
import styles from "./PlayLauncher.module.css";

const DECKS: { id: DeckId; title: string; subtitle: string; text: string }[] = [
  {
    id: "Luce-Ombra",
    title: "Luce · Ombra",
    subtitle: "Il mazzo originale",
    text: "Strategia essenziale: Rivalità, Fato, Impatto, Barriera e le Preghiere.",
  },
  {
    id: "TuonoSabbia",
    title: "Tuono · Sabbia",
    subtitle: "La nuova sfida",
    text: "Cariche, Marchi, Sigilli, Glifi ed Esordio.",
  },
];


const dateFormat = new Intl.DateTimeFormat("it-IT", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : dateFormat.format(date);
}

/* Stroke icons, 24x24 grid. */
const ICONS = {
  bot: (
    <>
      <path d="M12 8V4H8" />
      <rect width="16" height="12" x="4" y="8" rx="2" />
      <path d="M2 14h2M20 14h2M15 13v2M9 13v2" />
    </>
  ),
  users: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75M22 21v-2a4 4 0 0 0-3-3.87" />
    </>
  ),
  link: <path d="M9 17H7A5 5 0 0 1 7 7h2M15 7h2a5 5 0 1 1 0 10h-2M8 12h8" />,
  download: <path d="M12 15V3M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5" />,
  check: <path d="M20 6 9 17l-5-5" />,
} satisfies Record<string, ReactNode>;

function Icon({ name, size = 20 }: { name: keyof typeof ICONS; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  );
}

function StepHeading({ n, kicker, title, id }: { n: string; kicker: string; title: string; id: string }) {
  return (
    <div className={styles.step}>
      <span className={styles.stepNumber} aria-hidden="true">
        {n}
      </span>
      <div>
        <p className={styles.kicker}>{kicker}</p>
        <h2 id={id} className={styles.h2}>
          {title}
        </h2>
      </div>
    </div>
  );
}

/**
 * Deck picker, bot / private room launch and the local match archive.
 * The match itself runs in the simulator: see `lib/simulator.ts`.
 */
export default function PlayLauncher() {
  const [deck, setDeck] = useState<DeckId>("Luce-Ombra");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  /** The room request on its way, if any: opening one or joining one. */
  const [busy, setBusy] = useState<"create" | "join" | null>(null);
  const [error, setError] = useState<{ form: "create" | "join"; text: string } | null>(null);
  // null until read on the client, so the server HTML doesn't claim "0".
  const [replays, setReplays] = useState<SavedReplay[] | null>(null);
  const [exportStatus, setExportStatus] = useState("");
  const nameId = useId();
  const codeId = useId();

  const selected = DECKS.find((d) => d.id === deck) ?? DECKS[0];

  useEffect(() => {
    const refresh = () => setReplays(readSavedReplays());
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key === REPLAYS_KEY) refresh();
    };
    // Coming back from the simulator via the back button restores this page
    // from the bfcache: re-read the archive and unlock the room buttons.
    const onPageShow = (e: PageTransitionEvent) => {
      if (!e.persisted) return;
      refresh();
      setBusy(null);
    };
    refresh();
    window.addEventListener("storage", onStorage);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, []);

  /** Opens a room, or joins a friend's by its code, then goes to its page. */
  async function enterRoom(form: "create" | "join", e: FormEvent) {
    e.preventDefault();
    // The name field serves both forms, so neither can mark it `required`.
    if (!name.trim()) {
      setError({ form, text: "Scegli un nome prima di entrare." });
      document.getElementById(nameId)?.focus();
      return;
    }
    setBusy(form);
    setError(null);
    try {
      const room = form === "create" ? await createRoom(name.trim()) : await joinRoom(code, name.trim());
      rememberRoomAccess(room.code, room.token);
      // The room page belongs to the simulator, not to this app: full load.
      window.location.assign(roomUrl(room.code));
    } catch (err) {
      const fallback =
        form === "create"
          ? "Non è stato possibile creare la stanza."
          : "Non è stato possibile entrare nella stanza.";
      setError({ form, text: err instanceof Error ? err.message : fallback });
      setBusy(null);
    }
  }

  const errorOf = (form: "create" | "join") =>
    error?.form === form && (
      <p className={styles.error} role="alert">
        {error.text}
      </p>
    );

  function onDownload() {
    if (!replays) return;
    const n = downloadReplayArchive(replays);
    setExportStatus(
      n > 0
        ? `File pronto: contiene ${n} ${n === 1 ? "partita" : "partite"}.`
        : "Non ci sono ancora partite da esportare.",
    );
  }

  const count = replays?.length ?? 0;

  return (
    <div className={styles.launcher} data-deck={deck}>
      {/* ------------------------------ 01 deck ------------------------------ */}
      <section className={styles.block} aria-labelledby="mazzi">
        <StepHeading n="01" kicker="Un solo mazzo per entrambi" title="Scegli il mazzo" id="mazzi" />
        <div className={styles.decks} role="radiogroup" aria-labelledby="mazzi">
          {DECKS.map((d) => (
            <label key={d.id} className={styles.deck} data-deck={d.id}>
              <input
                type="radio"
                name="deck"
                value={d.id}
                checked={deck === d.id}
                onChange={() => setDeck(d.id)}
                className={styles.deckInput}
              />
              <span className={styles.deckEmblem} aria-hidden="true" />
              <span className={styles.deckCheck} aria-hidden="true">
                <Icon name="check" size={16} />
              </span>
              <span className={styles.deckSubtitle}>{d.subtitle}</span>
              <span className={styles.deckTitle}>{d.title}</span>
              <span className={styles.deckText}>{d.text}</span>
            </label>
          ))}
        </div>
      </section>

      {/* ------------------------------ 02 mode ------------------------------ */}
      <section className={styles.block} aria-labelledby="modi">
        <StepHeading n="02" kicker="Mettiti alla prova" title="Scegli come giocare" id="modi" />
        <div className={styles.modes}>
          <article className={`panel ${styles.mode}`}>
            <span className={styles.modeIcon}>
              <Icon name="bot" size={28} />
            </span>
            <p className={styles.tag}>Disponibile subito</p>
            <h3 className={styles.modeTitle}>Gioca contro il Bot</h3>
            <p className={styles.modeText}>
              Una partita completa sul tuo dispositivo. Il Bot non vede la tua mano, le tue
              Cariche o l&apos;ordine del mazzo.
            </p>
            <p className={styles.chosen}>
              <span>Mazzo scelto</span>
              <strong>{selected.title}</strong>
            </p>
            {/* Plain <a>: the bot table is the simulator's page, not a route of this app. */}
            <a href={botUrl(deck)} className={`btn ${styles.action}`}>
              Inizia la partita <span aria-hidden="true">→</span>
            </a>
          </article>

          <article className={`panel ${styles.mode}`}>
            <span className={styles.modeIcon}>
              <Icon name="users" size={28} />
            </span>
            <p className={styles.tag}>Partita privata 1 contro 1</p>
            <h3 className={styles.modeTitle}>Invita un giocatore</h3>
            <p className={styles.modeText}>
              Crea una stanza e manda il codice al tuo avversario, oppure entra con il codice
              che ti hanno mandato. Chi crea la stanza sceglie la modalità.
            </p>
            <div className={styles.invite}>
              <label htmlFor={nameId} className={styles.fieldLabel}>
                Il tuo nome al tavolo
              </label>
              <input
                id={nameId}
                className={styles.field}
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={24}
                autoComplete="nickname"
                aria-required="true"
              />
              <form className={styles.invite} onSubmit={(e) => enterRoom("create", e)}>
                <button
                  type="submit"
                  className={`btn btn--ghost ${styles.action}`}
                  disabled={busy !== null}
                  aria-busy={busy === "create"}
                >
                  {busy === "create" ? (
                    <>
                      <span className={styles.spinner} aria-hidden="true" /> Creo la stanza…
                    </>
                  ) : (
                    <>
                      <Icon name="link" size={18} /> Crea link d&apos;invito
                    </>
                  )}
                </button>
                {errorOf("create")}
              </form>
              <form className={styles.join} onSubmit={(e) => enterRoom("join", e)}>
                <label htmlFor={codeId} className={styles.fieldLabel}>
                  Hai un codice? Entra nella stanza
                </label>
                <div className={styles.joinRow}>
                  <input
                    id={codeId}
                    className={`${styles.field} ${styles.codeField}`}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    required
                    maxLength={5}
                    autoComplete="off"
                    autoCapitalize="characters"
                    spellCheck={false}
                    placeholder="ABCDE"
                  />
                  <button
                    type="submit"
                    className={`btn btn--ghost ${styles.joinButton}`}
                    disabled={busy !== null || !code.trim()}
                    aria-busy={busy === "join"}
                  >
                    {busy === "join" && <span className={styles.spinner} aria-hidden="true" />}
                    Entra
                  </button>
                </div>
                {errorOf("join")}
              </form>
            </div>
          </article>
        </div>
      </section>

      {/* ----------------------------- 03 archive ----------------------------- */}
      <section className={styles.block} aria-labelledby="partite">
        <StepHeading n="03" kicker="Dati portatili" title="Porta le partite nel simulatore" id="partite" />
        <div className={`panel ${styles.archive}`}>
          <div className={styles.archiveCopy}>
            <p className={styles.tag}>Archivio su questo dispositivo</p>
            <h3 className={styles.modeTitle}>
              {replays === null
                ? "Partite salvate"
                : `${count} ${count === 1 ? "partita salvata" : "partite salvate"}`}
            </h3>
            <p className={styles.modeText}>
              Ogni partita completata viene conservata automaticamente qui. Scarica un unico file
              JSON da caricare nella chat «Sim. Bless» per analisi, replay e futuro allenamento
              del Bot.
            </p>
            {count > 0 && (
              <ol className={styles.replays}>
                {replays!.map((r) => (
                  <li key={r.id}>
                    <span>{r.title}</span>
                    <time dateTime={r.saved_at}>{formatDate(r.saved_at)}</time>
                  </li>
                ))}
              </ol>
            )}
            {/* Always rendered: a live region added together with its text isn't announced. */}
            <p className={styles.status} role="status">
              {exportStatus}
            </p>
          </div>
          <button
            type="button"
            className={`btn btn--ghost ${styles.action}`}
            disabled={count === 0}
            onClick={onDownload}
          >
            <Icon name="download" size={18} /> Scarica dati per Sim. Bless
          </button>
        </div>
      </section>
    </div>
  );
}
