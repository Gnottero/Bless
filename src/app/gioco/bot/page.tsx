"use client";

import { CSSProperties, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { flushSync } from "react-dom";
import Link from "next/link";
import {
  downloadSavedReplayArchive,
  MAX_SAVED_REPLAYS,
  readSavedReplays,
  SAVED_REPLAYS_STORAGE_KEY,
} from "../../saved-replays";
import type { SavedReplayRecord, SavedReplayReview } from "../../saved-replays";
import { AbilityTerm } from "../ability-term";
import { CardDragAccessibility, useCardDrag, type CardDragButtonProps, type CardDropMode } from "../card-drag";
import { ImpulseStage, InspectCue, OrientationGate, PanelDragHandle, useDraggablePanel, type ImpulseStageEvent } from "../table-ui";
import "./play.css";

type BotName = "Bot";
type DeckName = "Luce-Ombra" | "TuonoSabbia";
type Screen = "setup" | "loading" | "game" | "error";
type ZoneModal = "void" | "altar" | "charges" | null;

interface GameCard {
  uid: number;
  id?: number;
  name?: string;
  form?: string;
  zone: string;
  controller?: number | null;
  hidden?: boolean;
  eye?: number;
  karma?: number;
  base_eye?: number;
  base_karma?: number;
  state?: string;
  stasis?: boolean;
  attached?: number | null;
  attached_to?: number | null;
  used?: boolean;
  prayer_type?: string;
  malediction_text?: string;
  prayer_text?: string;
  image?: string;
  traits?: string[];
  marked?: boolean;
  open?: boolean | null;
  glyph_used?: boolean;
  field_weight?: number;
  tactical_notes?: Array<{ title: string; text: string }>;
}

interface GamePlayer {
  id: number;
  name: string;
  score: number;
  actions: number;
  hand: GameCard[];
  maledictions: GameCard[];
  prayers: GameCard[];
  altar: GameCard[];
  altar_count: number;
  charges: GameCard[];
  charges_count: number;
}

interface LegalAction {
  id: string;
  kind: string;
  card_uid: number | null;
  target_uid: number | null;
  mode: string | null;
  cost: number;
  label: string;
  combat_preview?: CombatPreview;
}

interface CombatPreview {
  attacker_uid: number;
  target_uid: number;
  attacker_eye: number;
  defender_eye: number;
  attacker_forms: string[];
  defender_forms: string[];
  attacker_rivalry: boolean;
  attacker_rivalry_applied: boolean;
  defender_rivalry: boolean;
  defender_rivalry_applied: boolean;
  outcome: "attacker_win" | "defender_win" | "tie" | "fato" | string;
  allowed: boolean;
  reason: string;
}

interface ChoiceRequest {
  kind: "card" | "multi_card" | "option" | "confirm";
  purpose: string;
  prompt: string;
  explanation: string;
  candidate_uids?: number[];
  candidates?: GameCard[];
  options?: Array<string | boolean>;
  allow_skip?: boolean;
  minimum?: number;
  maximum?: number;
  allow_charge?: boolean;
  source?: GameCard;
  context?: string | null;
}

interface MulliganSelection {
  mulligan_uids: number[];
  charge_uid: number | null;
}

interface HistoryEntry {
  index: number;
  turn: number;
  player: number;
  phase: string;
  message: string;
  action_index?: number | null;
  action_label?: string | null;
}

interface TurnActionLog {
  key: string;
  actionNumber: number | null;
  label: string;
  phase: string;
  messages: string[];
}

interface TurnLog {
  turn: number;
  player: number;
  playerName: string;
  current: boolean;
  actions: TurnActionLog[];
}

interface AttackEvent {
  event_id: number;
  attacker_uid: number;
  target_uid: number | null;
  target_player: number;
}

interface FateEvent {
  event_id: number;
  card_uid: number;
  controller: number;
  choice: "Pari" | "Dispari";
  roll: number;
  won: boolean;
}

interface AttackTraceState {
  eventId: number;
  x: number;
  y: number;
  length: number;
  angle: number;
  humanAttack: boolean;
  direct: boolean;
}

interface BondTraceState {
  prayerUid: number;
  hostUid: number;
  x: number;
  y: number;
  length: number;
  angle: number;
}

interface ManualReplay {
  seed: number;
  deck?: string;
  bots: [string, string];
  first_player: number;
  winner: number | null;
  scores: [number, number];
  turns: number;
  final_trigger_player: number | null;
  final_trigger_cause: string | null;
  player_activity?: Array<{
    invocations: number;
    glyph_uses: number;
    charges_created: number;
  }>;
  actions: Array<Record<string, unknown>>;
}

interface HumanLearning {
  outcome: "vittoria" | "pareggio" | "sconfitta";
  outcome_weight: number;
  weight_deltas: Record<BotName, Record<string, number>>;
  top_signals: Array<{ feature: string; label: string; delta: number }>;
  summary: {
    actions: Record<string, number>;
    choices: Record<string, number>;
    prayer_share: number;
    own_eye_buffs: number;
    high_karma_eye_buffs: number;
    enemy_eye_debuffs: number;
    invocations: number;
    opponent_invocations: number;
    glyph_uses: number;
    opponent_glyph_uses: number;
    charges_created: number;
    opponent_charges_created: number;
    score: number;
    opponent_score: number;
  };
}

interface TutorialGuide {
  active: boolean;
  step: string;
  progress: number;
  total: number;
  title: string;
  body: string;
  instruction: string;
  focus: string;
  focus_uids: number[];
  choice_uids: number[] | null;
  choice_options: Array<string | boolean> | null;
  mulligan_uids: number[] | null;
  mulligan_locked_uids: number[] | null;
  allow_end_turn: boolean;
  complete: boolean;
}

interface ManualState {
  seed: number;
  deck: string;
  deck_id: string;
  mode: "choice" | "human_turn" | "human_start" | "opponent_turn" | "opponent_start" | "game_over";
  turn: number;
  active_player: number;
  human_player: number;
  bot_player: number;
  phase: string;
  force_end_turn: boolean;
  final_turns_remaining: number | null;
  final_trigger_player: number | null;
  final_trigger_turn: number | null;
  last_attack: AttackEvent | null;
  last_fate: FateEvent | null;
  last_impulse: ImpulseStageEvent<GameCard> | null;
  deck_count: number;
  void: GameCard[];
  players: [GamePlayer, GamePlayer];
  legal_actions: LegalAction[];
  combat_previews: CombatPreview[];
  choice: ChoiceRequest | null;
  history: HistoryEntry[];
  last_action: string;
  can_undo: boolean;
  undo_label: string | null;
  winner: number | null;
  game_over: boolean;
  learning?: HumanLearning;
  replay?: ManualReplay;
  tutorial?: TutorialGuide;
}

interface TargetPlan {
  title: string;
  actions: LegalAction[];
}

const BOT_DELAY = 1550;

const ABILITY_HELP = [
  {
    name: "Rivalità",
    pattern: /rivalit/i,
    description: "Durante uno scontro contro una Maledizione della forma opposta, ottiene +3 Occhio. Non si applica alle Duali.",
  },
  {
    name: "Impatto",
    pattern: /impatto/i,
    description: "Quando attacca e fa Corrompere una Maledizione Pura, questa Maledizione Blessa immediatamente. Non si attiva in difesa.",
  },
  {
    name: "Barriera",
    pattern: /barriera/i,
    description: "Quando questa Maledizione si Corrompe, non può essere attaccata fino alla fine del turno.",
  },
  {
    name: "Fato",
    pattern: /fato/i,
    description: "Dichiara Pari o Dispari e tira un dado a 6 facce: se indovini vince lo scontro, altrimenti lo perde.",
  },
  {
    name: "Schermatura",
    pattern: /schermatura/i,
    description: "Funziona solo mentre la Maledizione è Pura. Finché ne controlli almeno una Pura, l'avversario può attaccare soltanto Maledizioni con Schermatura.",
  },
  {
    name: "Emblema",
    pattern: /emblema/i,
    description: "Quando la Maledizione è Corrotta, il suo Occhio finale raddoppia.",
  },
  {
    name: "Colosso",
    pattern: /colosso/i,
    description: "Costa 2 Azioni, occupa due posti Maledizione e, dopo l'attacco, può Corrompere una Maledizione avversaria entro la differenza d'Occhio.",
  },
  {
    name: "Cadenza",
    pattern: /cadenza/i,
    description: "All'inizio del tuo turno guadagni 1 PV. Non puoi controllare un'altra Maledizione con Cadenza.",
  },
] as const;
const ABILITY_SPLIT_PATTERN = /(Rivalità|Impatto|Barriera|Fato|Schermatura|Emblema|Colosso|Cadenza)/gi;

function randomSeed(): number {
  return Math.floor(Math.random() * 2_147_483_646) + 1;
}

function normalizeLogText(value: string): string {
  return value.trim().replace(/[.…]+$/u, "").toLocaleLowerCase("it");
}

function isActionAnnouncement(message: string, label: string): boolean {
  const content = normalizeLogText(message);
  const separator = content.indexOf(":");
  if (separator < 0) return false;
  return content.slice(separator + 1).trim() === normalizeLogText(label);
}

function buildTurnLog(
  history: HistoryEntry[],
  currentTurn: number,
  activePlayer: number,
  players: [GamePlayer, GamePlayer],
  includeAll = false,
): TurnLog[] {
  const turns = includeAll
    ? Array.from(new Set([...history.map((event) => event.turn), currentTurn])).sort((a, b) => a - b)
    : [currentTurn, currentTurn - 1].filter((turn) => turn >= 0);
  return turns.flatMap((turn) => {
    const events = history.filter((event) => event.turn === turn);
    if (turn !== currentTurn && events.length === 0) return [];
    const player = events.at(-1)?.player ?? activePlayer;
    const actions: TurnActionLog[] = [];
    let numberedActions = 0;

    events.forEach((event) => {
      const previous = actions.at(-1);
      const belongsToPrevious = event.action_index != null
        ? previous?.key === `action-${event.action_index}`
        : previous?.actionNumber == null && previous?.phase === event.phase;

      if (belongsToPrevious && previous) {
        previous.messages.push(event.message);
        return;
      }

      if (event.action_index != null) numberedActions += 1;
      actions.push({
        key: event.action_index != null ? `action-${event.action_index}` : `event-${event.index}`,
        actionNumber: event.action_index != null ? numberedActions : null,
        label: event.action_label ?? event.phase ?? "Evento di turno",
        phase: event.phase,
        messages: [event.message],
      });
    });

    actions.forEach((action) => {
      if (action.actionNumber != null && action.messages.length && isActionAnnouncement(action.messages[0], action.label)) {
        action.messages.shift();
      }
    });

    return [{
      turn,
      player,
      playerName: players.find((candidate) => candidate.id === player)?.name ?? `Giocatore ${player + 1}`,
      current: turn === currentTurn,
      actions,
    }];
  });
}

function persistManualReplay(game: ManualState): string | null {
  if (!game.replay) return null;
  const human = game.players[game.human_player];
  const opponent = game.players[game.bot_player];
  try {
    const existing = readSavedReplays<ManualReplay>();
    const id = `manual-${game.seed}-${Date.now().toString(36)}`;
    const learning = game.learning;
    const outcome: SavedReplayReview["outcome"] = learning?.outcome
      ?? (game.winner === game.human_player ? "vittoria" : game.winner == null ? "pareggio" : "sconfitta");
    const review: SavedReplayReview = {
      outcome,
      human_score: human.score,
      bot_score: opponent.score,
      bot: opponent.name,
      turns: game.replay.turns,
      actions: game.replay.actions.length,
      altar_cards: human.altar_count,
      prayer_share: learning?.summary.prayer_share ?? 0,
      own_eye_buffs: learning?.summary.own_eye_buffs ?? 0,
      high_karma_eye_buffs: learning?.summary.high_karma_eye_buffs ?? 0,
      enemy_eye_debuffs: learning?.summary.enemy_eye_debuffs ?? 0,
      human_invocations: learning?.summary.invocations,
      bot_invocations: learning?.summary.opponent_invocations,
      human_glyph_uses: learning?.summary.glyph_uses,
      bot_glyph_uses: learning?.summary.opponent_glyph_uses,
      human_charges_created: learning?.summary.charges_created,
      bot_charges_created: learning?.summary.opponent_charges_created,
    };
    const record: SavedReplayRecord<ManualReplay> = {
      id,
      saved_at: new Date().toISOString(),
      title: `${game.deck} · Tu ${human.score}–${opponent.score} ${opponent.name}`,
      replay: game.replay,
      review,
    };
    const records = [record, ...existing].slice(0, MAX_SAVED_REPLAYS);
    for (let count = records.length; count >= 1; count -= 1) {
      try {
        window.localStorage.setItem(SAVED_REPLAYS_STORAGE_KEY, JSON.stringify(records.slice(0, count)));
        return id;
      } catch {
        // Se lo spazio locale e' pieno, conserva la partita nuova e rimuove
        // progressivamente soltanto i replay meno recenti.
      }
    }
    return null;
  } catch {
    return null;
  }
}

function ActionPips({ value }: { value: number }) {
  const count = Math.max(3, value);
  return (
    <div className="action-pips" aria-label={`${value} Azioni disponibili`}>
      {Array.from({ length: count }, (_, index) => (
        <span className={index < value ? "pip-filled" : ""} key={index}>{index < value ? "✦" : ""}</span>
      ))}
    </div>
  );
}

function AltarVisual({ count }: { count: number }) {
  const visibleCards = Math.max(1, Math.min(10, count));
  return (
    <span className={`altar-visual ${count === 0 ? "is-empty" : ""}`} aria-hidden="true">
      {Array.from({ length: visibleCards }, (_, index) => (
        <img
          src="/cards/back.png"
          alt=""
          key={index}
          style={{
            "--altar-index": index,
            "--altar-tilt": `${((index % 3) - 1) * 1.4}deg`,
          } as CSSProperties}
        />
      ))}
    </span>
  );
}

function AltarDisplay({ count, onOpen }: { count: number; onOpen?: () => void }) {
  const content = (
    <>
      <span className="altar-display-title">Altare</span>
      <span className="altar-display-body">
        <AltarVisual count={count} />
        <b>{count}</b>
      </span>
    </>
  );
  if (onOpen) {
    return (
      <button type="button" className="altar-display" onClick={onOpen} aria-label={`Apri il tuo Altare: ${count} carte`}>
        {content}
        <InspectCue label="Guarda" />
      </button>
    );
  }
  return <div className="altar-display" aria-label={`Altare avversario: ${count} carte`}>{content}</div>;
}

function FieldChargePile({ count, onOpen }: { count: number; onOpen?: () => void }) {
  if (count <= 0) return null;
  const content = (
    <>
      <img src="/cards/back.png" alt="" />
      <span>{count}</span>
      <small>Cariche del Glifo</small>
    </>
  );
  if (onOpen) {
    return (
      <button
        type="button"
        className="field-charge-pile"
        onClick={onOpen}
        aria-label={`Apri le tue Cariche: ${count} carte`}
      >
        {content}
        <InspectCue label="Guarda" />
      </button>
    );
  }
  return <div className="field-charge-pile is-opponent" aria-label={`${count} Cariche avversarie`}>{content}</div>;
}

function ScoreDifferenceMeter({ humanScore, botScore }: { humanScore: number; botScore: number }) {
  const difference = humanScore - botScore;
  const marker = 50 + Math.tanh(difference / 8) * 43;
  const fillStart = Math.min(50, marker);
  const fillSize = Math.abs(marker - 50);
  const label = difference > 0
    ? `Sei avanti di ${difference} Punti Vittoria`
    : difference < 0
      ? `Sei indietro di ${Math.abs(difference)} Punti Vittoria`
      : "Punti Vittoria in parità";

  return (
    <section className={`score-meter ${difference > 0 ? "human-leading" : difference < 0 ? "bot-leading" : "is-even"}`} aria-label={label} title={label}>
      <span className="score-track" aria-hidden="true">
        <span className="score-fill" style={{ top: `${fillStart}%`, height: `${fillSize}%` }} />
        <span className="score-marker" style={{ top: `${marker}%` }}><b>{Math.abs(difference)}</b></span>
      </span>
    </section>
  );
}

function OpponentPanel({ player, finalsActivator }: { player: GamePlayer; finalsActivator: boolean }) {
  return (
    <section className={`opponent-panel rail-panel ${finalsActivator ? "is-final-activator" : ""}`}>
      <header>
        <div><span>Avversario</span><strong>{player.name}</strong></div>
        {finalsActivator && <em>Turni finali</em>}
      </header>
      <div className="opponent-hand-heading"><span>Mano</span><b>{player.hand.length}</b></div>
      <div className="opponent-hidden-hand" aria-label={`${player.hand.length} carte nella mano avversaria`}>
        {player.hand.map((card) => <img src="/cards/back.png" alt="Carta coperta" key={card.uid} />)}
        {!player.hand.length && <small>Mano vuota</small>}
      </div>
      <AltarDisplay count={player.altar_count} />
    </section>
  );
}

function VoidPreview({ card, count, onOpen, onInspect }: {
  card: GameCard | null;
  count: number;
  onOpen: () => void;
  onInspect: () => void;
}) {
  return (
    <button type="button" className="void-rail-panel rail-panel" onClick={onOpen} onMouseEnter={onInspect}>
      <span className="void-rail-heading"><b>Vuoto</b><em>{count}</em></span>
      <span className="void-rail-card">
        {card ? <img src={card.image} alt={`Carta in cima al Vuoto: ${card.name}`} /> : <i />}
      </span>
      {!card && <span className="void-rail-empty">Nessuna carta</span>}
      <InspectCue label="Guarda" />
    </button>
  );
}

function TurnLogEntries({ turns, containerRef }: { turns: TurnLog[]; containerRef?: RefObject<HTMLDivElement | null> }) {
  return (
    <div className="turn-log-list" ref={containerRef}>
      {turns.map((turn) => (
        <article className={`turn-log-group ${turn.current ? "is-current" : ""}`} key={turn.turn}>
          <h4><span>Turno {turn.turn}</span><strong>{turn.playerName}</strong></h4>
          <div className="turn-actions">
            {turn.actions.map((action) => (
              <div className="turn-action" key={action.key}>
                <div className="turn-action-heading">
                  <span>{action.actionNumber != null ? `Azione ${action.actionNumber}` : action.phase}</span>
                  {action.actionNumber != null && <b>{action.label}</b>}
                </div>
                {action.messages.length > 0 && <p>{action.messages.join(" → ")}</p>}
              </div>
            ))}
            {turn.actions.length === 0 && <p className="empty-turn-log">Nessuna azione ancora.</p>}
          </div>
        </article>
      ))}
    </div>
  );
}

function CompactActionLog({ turns, onExpand }: { turns: TurnLog[]; onExpand: () => void }) {
  const latestTurn = turns.find((turn) => turn.actions.length > 0) ?? turns[0];
  const latestAction = latestTurn?.actions.at(-1);
  const message = latestAction?.messages.at(-1) ?? "Nessuna azione ancora.";
  const action = latestAction?.actionNumber != null
    ? `Azione ${latestAction.actionNumber} · ${latestAction.label}`
    : latestAction?.phase ?? "In attesa";
  return (
    <button type="button" className="compact-action-log rail-panel" onClick={onExpand} aria-label={`Apri il registro. ${action}. ${message}`}>
      <span className="compact-log-heading"><b>Ultima azione</b><small aria-hidden="true">↗</small></span>
      <span className="compact-log-summary">
        <strong>{latestTurn ? `T${latestTurn.turn} · ${latestTurn.playerName}` : "Registro"}</strong>
        <span>{action} · {message}</span>
      </span>
    </button>
  );
}

function ExpandedLogDialog({ turns, onClose }: { turns: TurnLog[]; onClose: () => void }) {
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [turns]);
  return (
    <div className="modal-layer log-modal-layer">
      <button type="button" className="modal-backdrop" aria-label="Chiudi il Registro azioni" onClick={onClose} />
      <section className="expanded-log-dialog">
        <header><div><span>Partita completa</span><h2>Registro azioni</h2></div><button type="button" onClick={onClose}>Chiudi</button></header>
        <TurnLogEntries turns={turns} containerRef={logRef} />
      </section>
    </div>
  );
}

function TutorialCoach({ guide, minimized, onToggle }: { guide: TutorialGuide; minimized: boolean; onToggle: () => void }) {
  const drag = useDraggablePanel("tutorial-coach");
  const progress = Math.min(100, Math.max(0, (guide.progress / Math.max(1, guide.total)) * 100));
  if (minimized) {
    return (
      <button type="button" className="tutorial-coach-minimized" onClick={onToggle} aria-label="Riapri la guida del tutorial">
        <span>Guida · {guide.progress}/{guide.total}</span><b>＋</b>
      </button>
    );
  }
  return (
    <aside
      ref={drag.panelRef}
      style={drag.panelStyle}
      className={`tutorial-coach ${drag.panelClassName} ${guide.complete ? "is-complete" : ""}`}
      aria-live="polite"
    >
      <div className="tutorial-coach-heading">
        <span>{guide.complete ? "Tutorial completato" : `Passaggio ${guide.progress} di ${guide.total}`}</span>
        <div>
          <PanelDragHandle handleProps={drag.handleProps} />
          {!guide.complete && <b>{Math.round(progress)}%</b>}
          <button type="button" onClick={onToggle} aria-label="Riduci la guida">−</button>
        </div>
      </div>
      {!guide.complete && <div className="tutorial-progress" aria-hidden="true"><i style={{ width: `${progress}%` }} /></div>}
      <h2>{guide.title}</h2>
      <p>{guide.body}</p>
      {!guide.complete ? (
        <div className="tutorial-instruction"><span>Adesso fai così</span><strong>{guide.instruction}</strong></div>
      ) : (
        <div className="tutorial-finish-actions">
          <Link href="/gioco/bot?mazzo=Luce-Ombra">Gioca contro il Bot</Link>
          <Link href="/gioco">Torna alle modalità</Link>
        </div>
      )}
    </aside>
  );
}

const TUTORIAL_CARD_PARTS = [
  {
    key: "eye",
    eyebrow: "1 · Occhio",
    title: "La forza negli scontri",
    body: "L'Occhio è il valore in alto a sinistra. Di norma, durante un combattimento vince la Maledizione con più Occhio.",
    value: "5",
  },
  {
    key: "karma",
    eyebrow: "2 · Karma",
    title: "Quanti PV vale una Blessatura",
    body: "Il Karma è in alto a destra. Quando questa carta Blessa, il suo controllore guadagna normalmente un numero di Punti Vittoria pari al Karma.",
    value: "2",
  },
  {
    key: "effects",
    eyebrow: "3 · Effetti",
    title: "Due modi di giocare la stessa carta",
    body: "Il testo Maledizione vale nella zona Maledizioni; il testo Preghiera vale nella zona Preghiere. La zona scelta cambia completamente il ruolo della carta.",
    value: "M / P",
  },
  {
    key: "prayer",
    eyebrow: "4 · Tipo di Preghiera",
    title: "Eco, Impulso o Legame",
    body: "Orizzonte è un Eco. Gli Eco restano in campo e possono essere Invocati di nuovo nei turni successivi. Il tipo è indicato insieme all'effetto Preghiera.",
    value: "Eco",
  },
  {
    key: "form",
    eyebrow: "5 · Forma",
    title: "Luce, Ombra oppure Duale",
    body: "La Forma di Orizzonte è Luce. Forma ed effetti possono modificare bersagli, bonus e condizioni di vittoria negli scontri.",
    value: "Luce",
  },
] as const;

function TutorialIntro({ onStart }: { onStart: () => void }) {
  const [partIndex, setPartIndex] = useState(0);
  const part = TUTORIAL_CARD_PARTS[partIndex];
  const lastPart = partIndex === TUTORIAL_CARD_PARTS.length - 1;
  const moveLesson = (direction: -1 | 1) => {
    if (direction < 0) {
      setPartIndex((value) => Math.max(0, value - 1));
      return;
    }
    if (lastPart) onStart();
    else setPartIndex((value) => Math.min(TUTORIAL_CARD_PARTS.length - 1, value + 1));
  };
  return (
    <div className="tutorial-intro-layer" role="dialog" aria-modal="true" aria-labelledby="tutorial-intro-title">
      <section className="tutorial-intro-card">
        <div className="tutorial-intro-heading">
          <span className="choice-kicker">Prima di giocare · Com’è fatta una carta</span>
          <h1 id="tutorial-intro-title">Leggiamo Orizzonte.</h1>
          <p>Ti mostro una caratteristica alla volta. Durante la partita potrai passare il puntatore su qualunque carta per rileggerla nel pannello a destra.</p>
        </div>
        <div
          className={`tutorial-card-lesson lesson-${part.key}`}
          onClick={(event) => {
            if ((event.target as HTMLElement).closest("button")) return;
            const bounds = event.currentTarget.getBoundingClientRect();
            moveLesson(event.clientX < bounds.left + bounds.width / 2 ? -1 : 1);
          }}
          title="Clicca a sinistra per tornare indietro o a destra per avanzare"
        >
          <div className="tutorial-card-visual">
            <img src="/cards/23.jpg" alt="Carta Orizzonte" />
            <span className={`tutorial-card-pin pin-${part.key}`}>{part.value}</span>
          </div>
          <div className="tutorial-card-explanation" key={part.key}>
            <span>{part.eyebrow}</span>
            <h2>{part.title}</h2>
            <p>{part.body}</p>
            <div className="tutorial-part-dots" aria-label="Avanzamento nella spiegazione della carta">
              {TUTORIAL_CARD_PARTS.map((item, index) => (
                <button
                  type="button"
                  key={item.key}
                  aria-label={`Mostra ${item.eyebrow}`}
                  aria-current={index === partIndex ? "step" : undefined}
                  onClick={() => setPartIndex(index)}
                />
              ))}
            </div>
          </div>
        </div>
        <div className="tutorial-intro-actions">
          <small>Clicca la metà sinistra o destra della spiegazione per muoverti. Nel tutorial saranno disponibili soltanto le mosse spiegate.</small>
          {partIndex > 0 && <button type="button" className="tutorial-back" onClick={() => moveLesson(-1)}>Indietro</button>}
          <button type="button" onClick={() => moveLesson(1)}>
            {lastPart ? "Inizia il tutorial" : "Avanti"}
          </button>
        </div>
      </section>
    </div>
  );
}

function PlayerControls({ player, disabled, finalsActivator, onOpenAltar, onEndTurn }: {
  player: GamePlayer;
  disabled: boolean;
  finalsActivator: boolean;
  onOpenAltar: () => void;
  onEndTurn: () => void;
}) {
  return (
    <section className={`player-controls rail-panel ${finalsActivator ? "is-final-activator" : ""}`}>
      <AltarDisplay count={player.altar_count} onOpen={onOpenAltar} />
      <div className="turn-control-stack">
        <div className="player-action-control"><span>Le tue Azioni</span><ActionPips value={player.actions} /></div>
        {finalsActivator && <small className="human-final-label">Hai attivato i Turni Finali</small>}
        <button type="button" className="end-turn" disabled={disabled} onClick={onEndTurn}>Fine turno</button>
      </div>
    </section>
  );
}

function CardView({
  card,
  kind,
  selected = false,
  targetable = false,
  disabled = false,
  onClick,
  onInspect,
  dragProps,
  motion = true,
  tutorialFocused = false,
}: {
  card: GameCard;
  kind: "malediction" | "prayer" | "hand" | "mini";
  selected?: boolean;
  targetable?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  onInspect?: () => void;
  dragProps?: CardDragButtonProps;
  motion?: boolean;
  tutorialFocused?: boolean;
}) {
  const corrupted = card.state === "Corrotta";
  const closedSeal = kind === "prayer" && card.prayer_type === "Sigillo" && card.open === false;
  const eyeChanged = card.eye != null && card.base_eye != null && card.eye !== card.base_eye;
  const karmaChanged = card.karma != null && card.base_karma != null && card.karma !== card.base_karma;
  return (
    <button
      type="button"
      className={`play-card card-${kind} ${corrupted ? "is-corrupted" : ""} ${closedSeal ? "is-seal-closed" : ""} ${card.marked ? "is-marked" : ""} ${selected ? "is-selected" : ""} ${targetable ? "is-targetable" : ""} ${dragProps ? "is-card-draggable" : ""} ${tutorialFocused ? "is-tutorial-focus" : ""}`}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => {
        if (window.innerWidth > 760) onInspect?.();
      }}
      data-card-uid={card.uid}
      style={motion ? { viewTransitionName: `bless-card-${card.uid}` } as CSSProperties : undefined}
      aria-label={card.hidden ? "Carta coperta" : `${card.name}${targetable ? ", bersaglio valido" : ""}`}
      aria-pressed={kind === "hand" ? selected : undefined}
      {...dragProps}
    >
      {card.marked && <span className="card-mark-back"><img src="/cards/back.png" alt="Marchio sotto la carta" /></span>}
      <span className="play-card-shell">
        <img src={card.hidden ? "/cards/back.png" : card.image} alt={card.hidden ? "Retro della carta Bless" : card.name ?? "Carta Bless"} draggable={false} />
        {!card.hidden && kind === "malediction" && (
          <>
            <span className={`play-stat play-eye ${eyeChanged ? (Number(card.eye) > Number(card.base_eye) ? "stat-up" : "stat-down") : ""}`}>{card.eye}</span>
            <span className={`play-stat play-karma ${karmaChanged ? (Number(card.karma) > Number(card.base_karma) ? "stat-up" : "stat-down") : ""}`}>{card.karma}</span>
          </>
        )}
        {targetable && <span className="target-ring">Scegli</span>}
      </span>
      {!card.hidden && kind !== "mini" && (
        <span className="play-card-flags">
          {card.stasis && <i>Stasi</i>}
          {kind === "prayer" && card.used && <i>Usata</i>}
          {kind === "prayer" && card.glyph_used && <i>Usato</i>}
          {kind === "prayer" && card.attached_to != null && <i>Legame</i>}
          {kind === "prayer" && card.open != null && <i>{card.open === false ? "Chiuso" : "Aperto"}</i>}
          {card.marked && <i>Marchiata</i>}
        </span>
      )}
    </button>
  );
}

function PlayerField({
  player,
  isHuman,
  active,
  selectedUid,
  targetUids,
  onCard,
  onInspect,
  onOpenCharges,
  finalsActivator,
  tutorialFocusUids,
}: {
  player: GamePlayer;
  isHuman: boolean;
  active: boolean;
  selectedUid: number | null;
  targetUids: Set<number>;
  onCard: (card: GameCard) => void;
  onInspect: (card: GameCard) => void;
  onOpenCharges?: () => void;
  finalsActivator: boolean;
  tutorialFocusUids?: Set<number>;
}) {
  const prayerCounts = player.prayers.reduce<Record<string, number>>((counts, card) => {
    const type = card.prayer_type || "Altro";
    counts[type] = (counts[type] ?? 0) + 1;
    return counts;
  }, {});
  const prayerSummary = ["Eco", "Legame", "Impulso", "Sigillo", "Glifo"]
    .filter((type) => prayerCounts[type])
    .map((type) => `${type}: ${prayerCounts[type]}`)
    .join(" · ");
  const firstGlyphUid = player.prayers.find((card) => card.prayer_type === "Glifo")?.uid;
  return (
    <section
      className={`duelist-field ${isHuman ? "human-field" : "bot-field"} ${active ? "is-active" : ""} ${finalsActivator ? "is-final-activator" : ""}`}
      data-player-summary={player.id}
    >
      <span className="field-player-tag">{isHuman ? "Tu" : player.name}{active ? " · turno attivo" : ""}</span>
      <div className="field-zones">
        <div
          className="drop-zone malediction-zone"
          data-card-drop-mode={isHuman ? "Maledizione" : undefined}
        >
          <span className="zone-caption"><span>Maledizioni <b>{player.maledictions.reduce((sum, card) => sum + (card.field_weight ?? 1), 0)}/4</b></span></span>
          <div className="field-card-row">
            {player.maledictions.map((card) => (
              <CardView
                card={card}
                kind="malediction"
                key={card.uid}
                selected={selectedUid === card.uid}
                targetable={targetUids.has(card.uid)}
                tutorialFocused={tutorialFocusUids?.has(card.uid)}
                onClick={() => onCard(card)}
                onInspect={() => onInspect(card)}
              />
            ))}
            {!player.maledictions.length && <span className="empty-zone">Trascina qui una carta dalla mano</span>}
          </div>
        </div>
        <div
          className="drop-zone prayer-zone"
          data-card-drop-mode={isHuman ? "Preghiera" : undefined}
        >
          <span className="zone-caption">
            <span>Preghiere <b>{player.prayers.length}</b></span>
            <em>{prayerSummary || "Nessuna Preghiera"}</em>
          </span>
          <div className="field-card-row">
            {player.prayers.map((card) => [
              <CardView
                card={card}
                kind="prayer"
                key={card.uid}
                selected={selectedUid === card.uid}
                targetable={targetUids.has(card.uid)}
                tutorialFocused={tutorialFocusUids?.has(card.uid)}
                onClick={() => onCard(card)}
                onInspect={() => onInspect(card)}
              />,
              card.uid === firstGlyphUid
                ? <FieldChargePile key={`charges-${player.id}`} count={player.charges_count} onOpen={isHuman ? onOpenCharges : undefined} />
                : null,
            ])}
            {firstGlyphUid == null && <FieldChargePile count={player.charges_count} onOpen={isHuman ? onOpenCharges : undefined} />}
            {!player.prayers.length && !player.charges_count && <span className="empty-zone">Zona Preghiere</span>}
          </div>
        </div>
      </div>
    </section>
  );
}

function AttackTrace({ trace }: { trace: AttackTraceState }) {
  return (
    <div
      className={`attack-trace ${trace.humanAttack ? "human-attack" : "bot-attack"} ${trace.direct ? "direct-attack" : ""}`}
      style={{
        left: trace.x,
        top: trace.y,
        width: trace.length,
        transform: `rotate(${trace.angle}rad)`,
        "--attack-angle": `${trace.angle}rad`,
      } as CSSProperties}
      aria-hidden="true"
    >
      <span>{trace.direct ? "Attacco diretto" : "Attacco"}</span>
    </div>
  );
}

function BondTrace({ trace }: { trace: BondTraceState }) {
  return (
    <div
      className="bond-trace"
      style={{
        left: trace.x,
        top: trace.y,
        width: trace.length,
        transform: `rotate(${trace.angle}rad)`,
        "--bond-angle": `${trace.angle}rad`,
      } as CSSProperties}
      aria-hidden="true"
    >
      <span>Legame</span>
    </div>
  );
}

const DIE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];

function FateDiceOverlay({ event }: { event: FateEvent }) {
  const [rolling, setRolling] = useState(true);
  const [face, setFace] = useState(1);
  useEffect(() => {
    setRolling(true);
    const interval = window.setInterval(() => setFace(Math.floor(Math.random() * 6) + 1), 85);
    const reveal = window.setTimeout(() => {
      window.clearInterval(interval);
      setFace(event.roll);
      setRolling(false);
    }, 900);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(reveal);
    };
  }, [event.event_id, event.roll]);
  return (
    <div className="fate-roll-overlay" role="status" aria-live="assertive">
      <div className="fate-roll-card">
        <span className="choice-kicker">Fato · {event.choice}</span>
        <div className={`fate-die ${rolling ? "is-rolling" : "is-revealed"}`} aria-label={rolling ? "Dado in lancio" : `Risultato ${face}`}>
          {DIE_FACES[face - 1]}
        </div>
        <strong>{rolling ? "Il dado sta rotolando…" : `È uscito ${event.roll}`}</strong>
        {!rolling && <p>{event.won ? "Fato vince lo scontro" : "Fato perde lo scontro"}</p>}
      </div>
    </div>
  );
}

function measureBondConnections(board: HTMLElement, game: ManualState): BondTraceState[] {
  const boardRect = board.getBoundingClientRect();
  return game.players.flatMap((player) => player.prayers).flatMap((prayer) => {
    if (prayer.attached_to == null) return [];
    const source = board.querySelector<HTMLElement>(`[data-card-uid="${prayer.uid}"]`);
    const host = board.querySelector<HTMLElement>(`[data-card-uid="${prayer.attached_to}"]`);
    if (!source || !host) return [];
    const sourceRect = source.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
    const x1 = sourceRect.left + sourceRect.width / 2 - boardRect.left;
    const y1 = sourceRect.top + sourceRect.height / 2 - boardRect.top;
    const x2 = hostRect.left + hostRect.width / 2 - boardRect.left;
    const y2 = hostRect.top + hostRect.height / 2 - boardRect.top;
    return [{
      prayerUid: prayer.uid,
      hostUid: prayer.attached_to,
      x: x1,
      y: y1,
      length: Math.hypot(x2 - x1, y2 - y1),
      angle: Math.atan2(y2 - y1, x2 - x1),
    }];
  });
}

function ChoicePanel({
  choice,
  onOption,
  onCard,
  onSkip,
}: {
  choice: ChoiceRequest;
  onOption: (value: string | boolean) => void;
  onCard: (uid: number) => void;
  onSkip: () => void;
}) {
  const drag = useDraggablePanel(`${choice.purpose}-${choice.context ?? ""}`);
  return (
    <aside
      className={`choice-panel ${drag.panelClassName}`}
      ref={drag.panelRef}
      style={drag.panelStyle}
      role="status"
      aria-live="assertive"
    >
      <div className="choice-panel-titlebar">
        <span className="choice-kicker">Scelta richiesta</span>
        <PanelDragHandle handleProps={drag.handleProps} />
      </div>
      <strong>{choice.prompt}</strong>
      <p>{choice.explanation}</p>
      {choice.context && <small>Durante: {choice.context}</small>}
      {choice.kind === "card" && (
        <>
          <em>Puoi cliccare il bersaglio illuminato sul tavolo oppure sceglierlo qui.</em>
          <div className="choice-card-list">
            {(choice.candidates ?? []).map((card) => (
              <button type="button" className="choice-card-option" key={card.uid} onClick={() => onCard(card.uid)}>
                <img src={card.image} alt="" />
                <span>{card.name}</span>
                <small>{card.zone}</small>
              </button>
            ))}
          </div>
        </>
      )}
      {(choice.kind === "option" || choice.kind === "confirm") && (
        <div className="choice-options">
          {(choice.options ?? []).map((option) => (
            <button type="button" key={String(option)} onClick={() => onOption(option)}>
              {typeof option === "boolean" ? (option ? "Sì" : "No") : option}
            </button>
          ))}
        </div>
      )}
      {choice.allow_skip && choice.kind !== "multi_card" && (
        <button type="button" className="skip-choice" onClick={onSkip}>Non applicare</button>
      )}
    </aside>
  );
}

function MulliganDialog({
  choice,
  initial,
  minimized,
  onConfirm,
  onUndo,
  onToggleMinimized,
  tutorialLockedUids,
}: {
  choice: ChoiceRequest;
  initial: boolean;
  minimized: boolean;
  onConfirm: (selection: MulliganSelection) => void;
  onUndo?: () => void;
  onToggleMinimized: () => void;
  tutorialLockedUids?: number[] | null;
}) {
  const candidates = choice.candidates ?? [];
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [chargeUid, setChargeUid] = useState<number | null>(null);
  const [inspected, setInspected] = useState<GameCard | null>(candidates[0] ?? null);
  const drag = useDraggablePanel(`${initial}-${candidates.map((card) => card.uid).join("-")}`);
  const isTutorialMulligan = tutorialLockedUids != null;
  const tutorialLocks = new Set(tutorialLockedUids ?? []);
  const toggle = (uid: number) => {
    if (tutorialLocks.has(uid)) return;
    if (selected.has(uid) && chargeUid === uid) setChargeUid(null);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(uid)) next.delete(uid); else next.add(uid);
      return next;
    });
  };
  const toggleCharge = (uid: number) => {
    setChargeUid((current) => current === uid ? null : uid);
    setSelected((current) => new Set(current).add(uid));
  };
  if (minimized) {
    return (
      <button type="button" className="mulligan-reopen" onClick={onToggleMinimized}>
        <span>Mulligan in attesa</span>
        <b>Riapri la scelta</b>
      </button>
    );
  }
  return (
    <div className="modal-layer mulligan-layer">
      <section className={`mulligan-dialog ${drag.panelClassName}`} ref={drag.panelRef} style={drag.panelStyle}>
        <div className="mulligan-titlebar">
          <span className="choice-kicker">{initial ? "Mano iniziale" : "Fine turno"} · Mulligan</span>
          <div>
            <PanelDragHandle handleProps={drag.handleProps} />
            <button type="button" onClick={onToggleMinimized}>— Guarda il campo</button>
          </div>
        </div>
        <h2>{choice.prompt}</h2>
        <p>{choice.explanation}</p>
        <div className="mulligan-workspace">
          <div className="mulligan-card-picker">
            <span className="mulligan-section-title">La tua mano</span>
            <p>
              Passa su una carta per leggerla. {isTutorialMulligan ? "Scegli liberamente quali cambiare; le carte protette servono per continuare il tutorial" : "Scegli quali cambiare"}
              {choice.allow_charge ? " e indica direttamente una sola carta da Caricare" : ""}.
            </p>
            <div className="mulligan-cards">
              {candidates.map((card) => (
                <div className={`mulligan-card-choice ${chargeUid === card.uid ? "is-charge-choice" : ""} ${tutorialLocks.has(card.uid) ? "is-tutorial-locked" : ""}`} key={card.uid}>
                  <CardView
                    card={card}
                    kind="hand"
                    selected={selected.has(card.uid)}
                    tutorialFocused={tutorialLocks.has(card.uid)}
                    onClick={() => {
                      setInspected(card);
                      toggle(card.uid);
                    }}
                    onInspect={() => setInspected(card)}
                  />
                  <div className="mulligan-card-actions">
                    <button
                      type="button"
                      className={selected.has(card.uid) ? "is-active" : ""}
                      disabled={tutorialLocks.has(card.uid)}
                      onClick={() => toggle(card.uid)}
                    >
                      {tutorialLocks.has(card.uid) ? "Serve nel tutorial" : selected.has(card.uid) ? "Nel Mulligan" : "Mulligan"}
                    </button>
                    {choice.allow_charge && (
                      <button
                        type="button"
                        className={`charge-choice-button ${chargeUid === card.uid ? "is-active" : ""}`}
                        onClick={() => toggleCharge(card.uid)}
                      >
                        {chargeUid === card.uid ? "Carica scelta" : "Carica"}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="mulligan-reader">
            <span className="mulligan-section-title">Dettagli della carta</span>
            <CardInspector card={inspected} variant="mulligan" />
          </div>
        </div>
        <div className="mulligan-summary">
          <span>
            {selected.size
              ? `${selected.size - Number(chargeUid != null)} carte torneranno nel Mazzo${chargeUid != null ? " · 1 diventerà una Carica" : ""}`
              : "Puoi tenere tutta la mano"}
          </span>
          <div>
            {onUndo && <button type="button" className="mulligan-undo" onClick={onUndo}>↶ Annulla Fine turno</button>}
            <button
              type="button"
              onClick={() => onConfirm({
                mulligan_uids: Array.from(selected),
                charge_uid: chargeUid,
              })}
            >
              Conferma Mulligan
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function EffectText({ text }: { text: string }) {
  const content = text || "Nessun effetto.";
  return (
    <span className="effect-copy">
      {content.split(ABILITY_SPLIT_PATTERN).map((part, index) => {
        const ability = ABILITY_HELP.find((candidate) => candidate.pattern.test(part));
        if (!ability || normalizeLogText(part) !== normalizeLogText(ability.name)) {
          return <span key={`${part}-${index}`}>{part}</span>;
        }
        return (
          <AbilityTerm
            description={ability.description}
            name={ability.name}
            key={`${ability.name}-${index}`}
          >
            {part}
          </AbilityTerm>
        );
      })}
    </span>
  );
}

function CardInspector({ card, variant = "table", onClose }: { card: GameCard | null; variant?: "table" | "mulligan"; onClose?: () => void }) {
  if (!card || card.hidden) return <div className="inspector-empty">Passa su una carta per leggerne gli effetti.</div>;
  const eye = card.eye ?? card.base_eye ?? 0;
  const karma = card.karma ?? card.base_karma ?? 0;
  const eyeChanged = card.eye != null && card.base_eye != null && card.eye !== card.base_eye;
  const karmaChanged = card.karma != null && card.base_karma != null && card.karma !== card.base_karma;
  const isMalediction = card.zone === "maledizione";
  const isPrayer = card.zone === "preghiera";
  const showMaledictionEffect = !isPrayer;
  const showPrayerEffect = !isMalediction;
  return (
    <article className={`card-inspector card-inspector-${variant} has-card`}>
      {onClose && <button type="button" className="mobile-inspector-close" aria-label="Chiudi i dettagli della carta" onClick={onClose}>×</button>}
      <img src={card.image} alt={card.name} />
      <div className="card-inspector-copy">
        <div className="inspector-heading">
          <div>
            <span className="inspector-meta">#{card.id} · {card.form}</span>
            <h3>{card.name}</h3>
          </div>
          <div className="inspector-stats" aria-label={`Occhio ${eye}, Karma ${karma}`}>
            <div
              className={`inspector-stat inspector-eye ${eyeChanged ? (eye > Number(card.base_eye) ? "stat-up" : "stat-down") : ""}`}
              aria-label={`Occhio ${eye}${eyeChanged ? `, valore originale ${card.base_eye}` : ""}`}
              title={`Occhio${eyeChanged ? ` · Originale ${card.base_eye}` : ""}`}
            >
              <b>{eye}</b>
            </div>
            <div
              className={`inspector-stat inspector-karma ${karmaChanged ? (karma > Number(card.base_karma) ? "stat-up" : "stat-down") : ""}`}
              aria-label={`Karma ${karma}${karmaChanged ? `, valore originale ${card.base_karma}` : ""}`}
              title={`Karma${karmaChanged ? ` · Originale ${card.base_karma}` : ""}`}
            >
              <b>{karma}</b>
            </div>
          </div>
        </div>
        {Boolean(card.tactical_notes?.length) && (
          <div className="tactical-notes" aria-label="Informazioni contestuali della carta">
            {card.tactical_notes?.map((note) => (
              <p key={`${note.title}-${note.text}`}><b>{note.title}</b><span>{note.text}</span></p>
            ))}
          </div>
        )}
        <div className="inspector-effects">
          {isPrayer && card.open != null && (
            <span className={`inspector-prayer-state ${card.open ? "is-open" : "is-closed"}`}>
              {card.prayer_type} {card.open ? "Aperto" : "Chiuso"}
            </span>
          )}
          {Boolean(card.traits?.length) && (
            <p className="inspector-traits"><b>Tratto</b><span>{card.traits?.map((trait) => <strong key={trait} title={trait === "Esordio" ? "Dopo il Mulligan viene assegnata fuori dal Mazzo e può essere giocata gratuitamente o tenuta in Mano." : trait}>{trait}</strong>)}</span></p>
          )}
          {showMaledictionEffect && <p><b>Maledizione</b><EffectText text={card.malediction_text ?? ""} /></p>}
          {showPrayerEffect && <p><b>Preghiera {card.prayer_type}</b><EffectText text={card.prayer_text ?? ""} /></p>}
          {showPrayerEffect && card.prayer_type === "Sigillo" && <small className="prayer-rule-note">Sigillo: entra Aperto; da Chiuso perde il suo effetto continuo. Invocarlo per riaprirlo costa 1 Azione.</small>}
          {showPrayerEffect && card.prayer_type === "Glifo" && <small className="prayer-rule-note">Glifo: il suo effetto si usa senza spendere Azioni pagando le Cariche indicate. Puoi spendere 1 Carica per evitare che venga Spezzato.</small>}
        </div>
      </div>
    </article>
  );
}

function ZoneDialog({
  title,
  cards,
  facedown,
  ordered = false,
  onInspect,
  playableUids,
  onPlay,
  onClose,
}: {
  title: string;
  cards: GameCard[];
  facedown: boolean;
  ordered?: boolean;
  onInspect?: (card: GameCard) => void;
  playableUids?: ReadonlySet<number>;
  onPlay?: (card: GameCard) => void;
  onClose: () => void;
}) {
  const [revealed, setRevealed] = useState(!facedown);
  const [preview, setPreview] = useState<GameCard | null>(ordered ? cards[0] ?? null : null);
  const columns = Math.max(1, Math.min(cards.length || 1, Math.ceil(Math.sqrt(Math.max(1, cards.length) * 2.2))));
  const inspect = (card: GameCard) => {
    setPreview(card);
    onInspect?.(card);
  };
  return (
    <div className={`modal-layer ${ordered ? "void-modal-layer" : ""}`}>
      <button type="button" className="modal-backdrop" aria-label={`Chiudi ${title}`} onClick={onClose} />
      <section className={`zone-dialog ${ordered ? "zone-dialog-ordered" : ""}`} style={{ "--zone-columns": columns } as CSSProperties}>
        <header>
          <div><span>Zona consultabile</span><h2>{title} · {cards.length}</h2></div>
          <div>
            {facedown && <button type="button" onClick={() => setRevealed((value) => !value)}>{revealed ? "Copri" : "Rivela"}</button>}
            <button type="button" onClick={onClose}>Chiudi</button>
          </div>
        </header>
        <div className={`zone-dialog-content ${ordered ? "is-ordered" : ""}`}>
          <div className={ordered ? "zone-card-list" : "zone-card-grid"}>
            {cards.map((card, index) => ordered ? (
              <article
                className={`zone-list-entry ${index === 0 ? "is-top-card" : ""} ${preview?.uid === card.uid ? "is-previewed" : ""}`}
                key={card.uid}
                onMouseEnter={() => inspect(card)}
                onFocusCapture={() => inspect(card)}
              >
                <span className="zone-list-position"><b>{index + 1}°</b><small>{index === 0 ? "In cima" : "Posizione"}</small></span>
                <CardView card={card} kind="hand" motion={false} onInspect={() => inspect(card)} onClick={() => inspect(card)} />
                <span className="zone-list-card-name">
                  <b>{card.name}</b><small>{card.form}</small>
                  {index === 0 && playableUids?.has(card.uid) && onPlay && (
                    <button type="button" className="zone-list-play" onClick={() => onPlay(card)}>Gioca dalla cima</button>
                  )}
                </span>
              </article>
            ) : (
              <CardView card={revealed ? card : { ...card, hidden: true }} kind="hand" motion={false} key={card.uid} onInspect={() => onInspect?.(card)} />
            ))}
            {!cards.length && <p>Non ci sono ancora carte in questa zona.</p>}
          </div>
          {ordered && (
            <aside className="zone-dialog-reader" aria-live="polite">
              <span className="mulligan-section-title">Dettagli della carta</span>
              <CardInspector card={preview} variant="mulligan" />
            </aside>
          )}
        </div>
      </section>
    </div>
  );
}

function GameOverDialog({
  game,
  onRestart,
  onSaveReplay,
  savedReplayId,
}: {
  game: ManualState;
  onRestart: () => void;
  onSaveReplay: () => string | null;
  savedReplayId: string | null;
}) {
  const human = game.players[game.human_player];
  const bot = game.players[game.bot_player];
  const humanActivity = game.replay?.player_activity?.[game.human_player];
  const opponentActivity = game.replay?.player_activity?.[game.bot_player];
  const won = game.winner === game.human_player;
  const [saveError, setSaveError] = useState("");
  const [exportMessage, setExportMessage] = useState("");
  const saveReplay = () => {
    const replayId = onSaveReplay();
    if (replayId) {
      setSaveError("");
    } else {
      setSaveError("Non è stato possibile salvare il replay su questo dispositivo.");
    }
  };
  const exportReplays = () => {
    const replayId = savedReplayId ?? onSaveReplay();
    if (!replayId) {
      setExportMessage("Non è stato possibile preparare il file.");
      return;
    }
    const records = readSavedReplays<ManualReplay>();
    const count = downloadSavedReplayArchive(records);
    setExportMessage(
      count > 0
        ? `File scaricato con ${count} ${count === 1 ? "partita" : "partite"}.`
        : "Non è stato possibile preparare il file.",
    );
  };
  return (
    <div className="modal-layer result-layer">
      <section className="result-dialog">
        <span className="choice-kicker">Partita terminata</span>
        <h2>{won ? "Hai vinto" : game.winner == null ? "Pareggio" : `${bot.name} ha vinto`}</h2>
        <div className="final-score"><strong>{human.score}</strong><span>–</span><strong>{bot.score}</strong></div>
        <div className="post-game-review">
          <div className="review-heading"><span>Review rapida</span><b>contro {bot.name}</b></div>
          <div className="review-metrics">
            <span><b>{game.replay?.turns ?? game.turn}</b> Turni</span>
            <span><b>{game.replay?.actions.length ?? 0}</b> Azioni</span>
            <span><b>{human.altar_count}</b> Altare</span>
            {game.learning && <span><b>{game.learning.summary.prayer_share.toFixed(0)}%</b> Preghiere</span>}
            {!game.learning && <span><b>{humanActivity?.invocations ?? 0}</b> Invocazioni</span>}
          </div>
          {game.deck_id === "tuono-sabbia" && (game.learning || humanActivity) && (
            <div className="review-ts-activity">
              <span><b>Invocazioni</b> Tu {game.learning?.summary.invocations ?? humanActivity?.invocations ?? 0} · {bot.name} {game.learning?.summary.opponent_invocations ?? opponentActivity?.invocations ?? 0}</span>
              <span><b>Effetti Glifo</b> Tu {game.learning?.summary.glyph_uses ?? humanActivity?.glyph_uses ?? 0} · {bot.name} {game.learning?.summary.opponent_glyph_uses ?? opponentActivity?.glyph_uses ?? 0}</span>
              <span><b>Carte Caricate</b> Tu {game.learning?.summary.charges_created ?? humanActivity?.charges_created ?? 0} · {bot.name} {game.learning?.summary.opponent_charges_created ?? opponentActivity?.charges_created ?? 0}</span>
            </div>
          )}
          {game.learning && <small>Potenziamenti Occhio {game.learning.summary.own_eye_buffs} · Setup Karma alto {game.learning.summary.high_karma_eye_buffs}</small>}
        </div>
        {savedReplayId && <p className="replay-saved-note">✓ Replay conservato su questo dispositivo.</p>}
        {saveError && <p className="save-replay-error">{saveError}</p>}
        {exportMessage && <p className="replay-export-note" role="status">{exportMessage}</p>}
        <div className="result-actions">
          <button type="button" onClick={onRestart}>Nuova partita</button>
          {!savedReplayId && game.replay && <button type="button" className="save-replay-button" onClick={saveReplay}>Riprova il salvataggio</button>}
          {game.replay && <button type="button" className="export-replay-button" onClick={exportReplays}>Scarica dati per Sim. Bless</button>}
          {savedReplayId && <a href="/gioco">Torna alla scelta della partita</a>}
        </div>
      </section>
    </div>
  );
}

export default function PlayBlessPage() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [seed, setSeed] = useState(20260810);
  const [firstPlayer, setFirstPlayer] = useState<"human" | "bot" | "random">("human");
  const [deck, setDeck] = useState<DeckName>("Luce-Ombra");
  const [game, setGame] = useState<ManualState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedUid, setSelectedUid] = useState<number | null>(null);
  const [targetPlan, setTargetPlan] = useState<TargetPlan | null>(null);
  const [inspected, setInspected] = useState<GameCard | null>(null);
  const [zoneModal, setZoneModal] = useState<ZoneModal>(null);
  const [logExpanded, setLogExpanded] = useState(false);
  const [fastBot, setFastBot] = useState(false);
  const [attackTrace, setAttackTrace] = useState<AttackTraceState | null>(null);
  const [bondTraces, setBondTraces] = useState<BondTraceState[]>([]);
  const [fateDisplay, setFateDisplay] = useState<FateEvent | null>(null);
  const [impulseDisplay, setImpulseDisplay] = useState<ImpulseStageEvent<GameCard> | null>(null);
  const [mulliganMinimized, setMulliganMinimized] = useState(false);
  const [savedReplayId, setSavedReplayId] = useState<string | null>(null);
  const [tutorialMode, setTutorialMode] = useState(false);
  const [tutorialIntroOpen, setTutorialIntroOpen] = useState(false);
  const [tutorialCoachMinimized, setTutorialCoachMinimized] = useState(false);
  const targetPanelDrag = useDraggablePanel(targetPlan?.title ?? "nessun-bersaglio");
  const workerRef = useRef<Worker | null>(null);
  const timerRef = useRef<number | null>(null);
  const fastBotRef = useRef(false);
  const tableRef = useRef<HTMLElement | null>(null);
  const battleBoardRef = useRef<HTMLElement | null>(null);
  const gameRef = useRef<ManualState | null>(null);
  const attackTraceRef = useRef<AttackTraceState | null>(null);
  const savedReplayRef = useRef<string | null>(null);
  const fateTimerRef = useRef<number | null>(null);
  const fateSeenRef = useRef<number | null>(null);
  const impulseTimerRef = useRef<number | null>(null);
  const impulseSeenRef = useRef<number | null>(null);

  useEffect(() => {
    const profileFrame = window.requestAnimationFrame(() => {
      const params = new URLSearchParams(window.location.search);
      const isTutorial = params.get("tutorial") === "1";
      const requestedDeck = params.get("mazzo");
      const selectedDeck: DeckName = isTutorial ? "Luce-Ombra" : requestedDeck === "TuonoSabbia" ? "TuonoSabbia" : "Luce-Ombra";
      setDeck(selectedDeck);
      setTutorialMode(isTutorial);
      setTutorialIntroOpen(isTutorial);
      if (isTutorial) startGame({ deck: "Luce-Ombra", seed: randomSeed(), firstPlayer: "human", tutorial: true });
      else startGame({ deck: selectedDeck, seed: randomSeed(), firstPlayer: "random" });
    });
    return () => {
      window.cancelAnimationFrame(profileFrame);
      workerRef.current?.terminate();
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      if (fateTimerRef.current != null) window.clearTimeout(fateTimerRef.current);
      if (impulseTimerRef.current != null) window.clearTimeout(impulseTimerRef.current);
    };
  // L'avvio deve avvenire una sola volta: le dipendenze successive sono stato della partita.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (game?.choice?.purpose !== "mulligan") setMulliganMinimized(false);
  }, [game?.choice?.purpose]);

  useEffect(() => {
    if (!game || screen !== "game" || !battleBoardRef.current) {
      setBondTraces([]);
      return;
    }
    let frame = 0;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        if (battleBoardRef.current) setBondTraces(measureBondConnections(battleBoardRef.current, game));
      });
    };
    update();
    window.addEventListener("resize", update);
    document.addEventListener("fullscreenchange", update);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", update);
      document.removeEventListener("fullscreenchange", update);
    };
  }, [game, screen]);

  const send = (message: Record<string, unknown>) => {
    if (!workerRef.current) return;
    setBusy(true);
    workerRef.current.postMessage(message);
  };

  const scheduleNext = (next: ManualState, delayOverride?: number) => {
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    if (next.game_over || next.choice) return;
    let command: Record<string, unknown> | null = null;
    if (next.mode === "opponent_turn" || next.mode === "opponent_start") command = { type: "opponent_step" };
    if (next.mode === "human_start") command = { type: "human_start" };
    if (!command) return;
    const nextCommand = command;
    const delay = delayOverride ?? (next.tutorial?.active ? 3600 : fastBotRef.current ? 560 : BOT_DELAY);
    timerRef.current = window.setTimeout(() => send(nextCommand), delay);
  };

  const measureAttackTrace = (next: ManualState): AttackTraceState | null => {
    const attack = next.last_attack;
    const board = battleBoardRef.current;
    if (!attack || !board) return null;
    if (attackTraceRef.current?.eventId === attack.event_id) return attackTraceRef.current;
    const attacker = board.querySelector<HTMLElement>(`[data-card-uid="${attack.attacker_uid}"]`);
    const target = attack.target_uid != null
      ? board.querySelector<HTMLElement>(`[data-card-uid="${attack.target_uid}"]`)
      : board.querySelector<HTMLElement>(`[data-player-summary="${attack.target_player}"]`);
    if (!attacker || !target) return null;
    const boardRect = board.getBoundingClientRect();
    const attackerRect = attacker.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const x1 = attackerRect.left + attackerRect.width / 2 - boardRect.left;
    const y1 = attackerRect.top + attackerRect.height / 2 - boardRect.top;
    const x2 = targetRect.left + targetRect.width / 2 - boardRect.left;
    const y2 = targetRect.top + targetRect.height / 2 - boardRect.top;
    return {
      eventId: attack.event_id,
      x: x1,
      y: y1,
      length: Math.hypot(x2 - x1, y2 - y1),
      angle: Math.atan2(y2 - y1, x2 - x1),
      humanAttack: attack.target_player === next.bot_player,
      direct: attack.target_uid == null,
    };
  };

  const handleState = (next: ManualState) => {
    const newFate = next.last_fate && next.last_fate.event_id !== fateSeenRef.current
      ? next.last_fate
      : null;
    if (newFate) {
      fateSeenRef.current = newFate.event_id;
      setFateDisplay(newFate);
      if (fateTimerRef.current != null) window.clearTimeout(fateTimerRef.current);
      fateTimerRef.current = window.setTimeout(() => setFateDisplay(null), 2850);
    }
    const newImpulse = next.last_impulse && next.last_impulse.event_id !== impulseSeenRef.current
      ? next.last_impulse
      : null;
    if (newImpulse) {
      impulseSeenRef.current = newImpulse.event_id;
      setImpulseDisplay(newImpulse);
      if (impulseTimerRef.current != null) window.clearTimeout(impulseTimerRef.current);
      impulseTimerRef.current = window.setTimeout(() => setImpulseDisplay(null), 2400);
    }
    const nextTrace = measureAttackTrace(next);
    attackTraceRef.current = nextTrace;
    const applyState = () => {
      flushSync(() => {
        gameRef.current = next;
        setGame(next);
        setBusy(false);
        setScreen("game");
        setSelectedUid(null);
        setTargetPlan(null);
        setAttackTrace(nextTrace);
      });
    };
    const transitionDocument = document as Document & {
      startViewTransition?: (update: () => void) => {
        ready?: Promise<unknown>;
        updateCallbackDone?: Promise<unknown>;
        finished?: Promise<unknown>;
      };
    };
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let stateApplied = false;
    const applyStateOnce = () => {
      if (stateApplied) return;
      stateApplied = true;
      applyState();
    };
    if (gameRef.current && transitionDocument.startViewTransition && !reduceMotion) {
      try {
        const transition = transitionDocument.startViewTransition(applyStateOnce);
        // Un cambio di viewport o un aggiornamento rapido puo' interrompere
        // legittimamente la transizione. Se il callback non parte, applichiamo
        // comunque lo stato una sola volta e non lasciamo il tavolo in attesa.
        transition.ready?.catch(() => undefined);
        transition.updateCallbackDone?.catch(() => applyStateOnce());
        transition.finished?.catch(() => undefined);
      } catch {
        applyStateOnce();
      }
    } else {
      applyStateOnce();
    }
    if (next.game_over && next.replay && !savedReplayRef.current) {
      const replayId = persistManualReplay(next);
      savedReplayRef.current = replayId;
      setSavedReplayId(replayId);
    }
    scheduleNext(next, newFate ? 2850 : newImpulse ? 2400 : undefined);
  };

  function startGame(override?: { deck?: DeckName; seed?: number; firstPlayer?: "human" | "bot" | "random"; tutorial?: boolean }) {
    workerRef.current?.terminate();
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    savedReplayRef.current = null;
    setSavedReplayId(null);
    setError("");
    setGame(null);
    gameRef.current = null;
    attackTraceRef.current = null;
    setAttackTrace(null);
    setBondTraces([]);
    setFateDisplay(null);
    fateSeenRef.current = null;
    setImpulseDisplay(null);
    impulseSeenRef.current = null;
    if (fateTimerRef.current != null) window.clearTimeout(fateTimerRef.current);
    if (impulseTimerRef.current != null) window.clearTimeout(impulseTimerRef.current);
    setMulliganMinimized(false);
    setTutorialCoachMinimized(false);
    setLogExpanded(false);
    setScreen("loading");
    setBusy(true);
    const worker = new Worker("/manual-worker.mjs", { type: "module" });
    workerRef.current = worker;
    worker.onerror = (event) => {
      setError(event.message || "Il tavolo non si è avviato.");
      setScreen("error");
      setBusy(false);
    };
    worker.onmessage = (event: MessageEvent<{ type: string; payload?: string; message?: string }>) => {
      if (event.data.type === "ready") {
        worker.postMessage({
          type: "start",
          config: {
            bot: "Bot",
            seed: override?.seed ?? seed,
            deck: override?.deck ?? deck,
            first_player: override?.firstPlayer ?? firstPlayer,
            tutorial: override?.tutorial ?? tutorialMode,
            learning_weights: { Bot: {} },
          },
        });
      } else if (event.data.type === "state" && event.data.payload) {
        handleState(JSON.parse(event.data.payload));
      } else if (event.data.type === "error") {
        const detail = String(event.data.message ?? "Errore durante la partita").split("\n").filter(Boolean).at(-1) ?? "Errore durante la partita";
        setError(detail);
        setScreen("error");
        setBusy(false);
      }
    };
    worker.postMessage({ type: "init" });
  }

  const returnToSetup = () => {
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    workerRef.current?.terminate();
    workerRef.current = null;
    setBusy(false);
    setError("");
    setGame(null);
    gameRef.current = null;
    savedReplayRef.current = null;
    setSavedReplayId(null);
    attackTraceRef.current = null;
    setAttackTrace(null);
    setBondTraces([]);
    setFateDisplay(null);
    fateSeenRef.current = null;
    setImpulseDisplay(null);
    impulseSeenRef.current = null;
    if (fateTimerRef.current != null) window.clearTimeout(fateTimerRef.current);
    if (impulseTimerRef.current != null) window.clearTimeout(impulseTimerRef.current);
    setMulliganMinimized(false);
    setSelectedUid(null);
    setTargetPlan(null);
    setZoneModal(null);
    setLogExpanded(false);
    window.location.href = "/gioco";
  };

  const human = game?.players[game.human_player];
  const opponent = game?.players[game.bot_player];
  const allVisibleCards = useMemo(() => game ? [
    ...game.players.flatMap((player) => [...player.maledictions, ...player.prayers]),
    ...game.players[game.human_player].hand,
    ...game.players[game.human_player].charges,
    ...game.void,
  ] : [], [game]);

  const pendingTargets = useMemo(() => {
    if (game?.choice?.kind === "card") return new Set(game.choice.candidate_uids ?? []);
    if (targetPlan) return new Set(targetPlan.actions.map((action) => Number(action.target_uid)).filter(Boolean));
    return new Set<number>();
  }, [game, targetPlan]);

  const selectedActions = useMemo(
    () => game?.legal_actions.filter((action) => action.card_uid === selectedUid) ?? [],
    [game?.legal_actions, selectedUid],
  );

  const performLegalAction = (action: LegalAction) => send({ type: "action", action_id: action.id });

  const chooseActionGroup = (actions: LegalAction[], title: string, alwaysChooseTarget = false) => {
    if (actions.length === 1 && !alwaysChooseTarget) performLegalAction(actions[0]);
    else setTargetPlan({ title, actions });
  };

  const handleCard = (card: GameCard) => {
    setInspected(card.hidden ? null : card);
    if (busy || !game) return;
    if (game.choice?.kind === "card" && (game.choice.candidate_uids ?? []).includes(card.uid)) {
      send({ type: "choice", value: card.uid });
      return;
    }
    if (targetPlan) {
      const action = targetPlan.actions.find((candidate) => candidate.target_uid === card.uid);
      if (action) performLegalAction(action);
      return;
    }
    if (game.mode === "human_turn") setSelectedUid((current) => current === card.uid ? null : card.uid);
  };

  const handleDrop = (mode: "Maledizione" | "Preghiera", uid: number) => {
    if (!game || busy || game.mode !== "human_turn") return;
    const kind = mode === "Maledizione" ? "play_malediction" : "play_prayer";
    const actions = game.legal_actions.filter((action) => action.card_uid === uid && action.kind === kind);
    if (actions.length) {
      const cardName = allVisibleCards.find((card) => card.uid === uid)?.name ?? "questa carta";
      const title = actions.some((action) => action.mode === "MaledizioneCarica")
        ? `Come vuoi calare ${cardName}?`
        : `Scegli il bersaglio per giocare come ${mode}`;
      chooseActionGroup(actions, title);
    }
  };

  const playableDropModes = useMemo(() => {
    const byCard = new Map<number, CardDropMode[]>();
    for (const action of game?.legal_actions ?? []) {
      if (action.card_uid == null) continue;
      const mode: CardDropMode | null = action.kind === "play_malediction"
        ? "Maledizione"
        : action.kind === "play_prayer" ? "Preghiera" : null;
      if (!mode) continue;
      const modes = byCard.get(action.card_uid) ?? [];
      if (!modes.includes(mode)) modes.push(mode);
      byCard.set(action.card_uid, modes);
    }
    return byCard;
  }, [game?.legal_actions]);

  const cardDragResetKey = [
    screen,
    busy ? "busy" : "ready",
    game?.turn ?? "no-turn",
    game?.active_player ?? "no-player",
    game?.mode ?? "no-mode",
    game?.choice ? "choice" : "no-choice",
    [...playableDropModes].map(([uid, modes]) => `${uid}:${modes.join("+")}`).join("|"),
  ].join(":");
  const cardDrag = useCardDrag(handleDrop, cardDragResetKey);

  const commandButtons = useMemo(() => {
    const groups: Array<{ label: string; actions: LegalAction[]; tone?: string; detail?: string; alwaysChooseTarget?: boolean }> = [];
    const byKind = (kind: string) => selectedActions.filter((action) => action.kind === kind);
    const selectedCard = allVisibleCards.find((card) => card.uid === selectedUid);
    const paidMaledictions = byKind("play_malediction").filter((action) => action.mode !== "MaledizioneCarica");
    const chargedMaledictions = byKind("play_malediction").filter((action) => action.mode === "MaledizioneCarica");
    if (paidMaledictions.length) groups.push({ label: "Maledizione", actions: paidMaledictions, tone: "light" });
    if (byKind("play_prayer").length) groups.push({ label: "Preghiera", actions: byKind("play_prayer"), tone: "shadow" });
    if (chargedMaledictions.length) groups.push({ label: "Maledizione (0 Azioni)", actions: chargedMaledictions, tone: "charge", detail: "Spendi 1 Carica" });
    if (byKind("attack").length) groups.push({ label: "Attacca", actions: byKind("attack"), tone: "danger", alwaysChooseTarget: true });
    if (byKind("attack_direct").length) groups.push({ label: "Attacco diretto", actions: byKind("attack_direct"), tone: "danger" });
    if (byKind("remove_stasis").length) groups.push({ label: "Rimuovi Stasi", actions: byKind("remove_stasis") });
    if (byKind("invoke").length) groups.push({ label: selectedCard?.prayer_type === "Sigillo" ? "Apri Sigillo" : "Invoca Eco", actions: byKind("invoke"), tone: "shadow" });
    if (byKind("use_glyph").length) groups.push({ label: "Usa Glifo", actions: byKind("use_glyph"), tone: "shadow" });
    if (byKind("sigil_remove_stasis").length) groups.push({ label: "Rimuovi Stasi con il Sigillo", actions: byKind("sigil_remove_stasis"), alwaysChooseTarget: true });
    return groups;
  }, [allVisibleCards, selectedActions, selectedUid]);

  const selectedCombatPreviews = useMemo(
    () => game?.combat_previews.filter((preview) => preview.attacker_uid === selectedUid) ?? [],
    [game?.combat_previews, selectedUid],
  );

  const openFullscreen = async () => {
    if (!tableRef.current) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await tableRef.current.requestFullscreen();
  };

  const undoMove = () => {
    if (!game?.can_undo || busy) return;
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    send({ type: "undo" });
  };

  const saveCurrentReplay = (): string | null => {
    if (!game?.replay) return null;
    const replayId = savedReplayRef.current ?? persistManualReplay(game);
    savedReplayRef.current = replayId;
    setSavedReplayId(replayId);
    return replayId;
  };

  if (screen === "loading" || screen === "error") {
    return (
      <main className="play-setup-page">
        <header className="play-setup-nav">
          <Link href="/gioco">← Scegli un’altra partita</Link>
          <span>BLESS · Tavolo ufficiale</span>
        </header>
        <section className="play-setup-hero">
          <div className="setup-copy">
            <span className="play-eyebrow">{tutorialMode ? "Tutorial Luce Ombra" : "Modalità contro il Bot"}</span>
            <h1>{tutorialMode ? <>La prima partita,<br /><em>passo dopo passo.</em></> : <>Prepariamo<br /><em>il tavolo.</em></>}</h1>
            <p>
              {tutorialMode
                ? "Sto preparando una partita guidata: userai il vero tavolo e imparerai ogni regola mentre giochi."
                : "Sto mescolando il mazzo e preparando il tuo avversario. La partita inizierà tra pochi istanti."}
            </p>
          </div>
          <aside className="game-config-card">
            <span>{screen === "error" ? "Serve un nuovo tentativo" : "Preparazione in corso"}</span>
            <h2>{deck === "TuonoSabbia" ? "Tuono · Sabbia" : "Luce · Ombra"}</h2>
            <div className="single-bot-note"><span>Avversario</span><strong>Bot</strong><small>Gioca senza conoscere la tua mano, le tue Cariche o l’ordine del Mazzo.</small></div>
            {screen === "loading" && <button className="start-game" type="button" disabled>Sto preparando carte e Bot…</button>}
            {screen === "error" && <><p className="setup-error">{error}</p><button className="start-game" type="button" onClick={() => startGame({ deck, seed: randomSeed(), firstPlayer: tutorialMode ? "human" : "random", tutorial: tutorialMode })}>Riprova</button></>}
          </aside>
        </section>
      </main>
    );
  }

  if (!game || !human || !opponent) return null;

  const inspectedLive = inspected
    ? allVisibleCards.find((card) => card.uid === inspected.uid) ?? inspected
    : null;
  const topVoidCard = game.void[0] ?? null;
  const finalsActivatedNow = game.final_turns_remaining != null && game.final_trigger_turn === game.turn;
  const turnLog = buildTurnLog(game.history, game.turn, game.active_player, game.players);
  const fullTurnLog = buildTurnLog(game.history, game.turn, game.active_player, game.players, true);
  const targetPreview = targetPlan?.actions.length === 1 ? targetPlan.actions[0].combat_preview : null;
  const combatTargetPlan = targetPlan?.actions[0]?.kind === "attack";
  const targetlessActionPlan = Boolean(targetPlan?.actions.length)
    && targetPlan!.actions.every((action) => action.target_uid == null);
  const excludedCombatPreviews = combatTargetPlan
    ? selectedCombatPreviews.filter((preview) => !preview.allowed)
    : [];
  const tutorialFocusUids = new Set(game.tutorial?.focus_uids ?? []);
  const tutorialFocusClass = game.tutorial?.focus ? `tutorial-focus-${game.tutorial.focus.replaceAll("_", "-")}` : "";

  return (
    <main className={`manual-table ${game.deck === "TuonoSabbia" ? "deck-thunder-sand" : "deck-light-shadow"} ${game.tutorial?.active ? "tutorial-active" : ""} ${tutorialFocusClass}`} ref={tableRef} style={{ "--hand-count": Math.max(1, human.hand.length) } as CSSProperties}>
      <OrientationGate />
      <header className="table-topbar">
        <Link href="/gioco" className="table-brand" aria-label="Bless · Torna alla scelta della partita">
          <img src="/logo.png" alt="Bless" />
          <span>{game.tutorial?.active ? "Luce · Ombra · Tutorial" : game.deck === "TuonoSabbia" ? "Tuono · Sabbia" : "Luce · Ombra"}</span>
        </Link>
        <div className="phase-track" aria-label={`Stato del turno: ${game.phase}`}>
          {["Inizio turno", "Fase principale", "Fine turno"].map((phase) => (
            <span className={game.phase === phase ? "active" : ""} key={phase}>{phase}</span>
          ))}
        </div>
        <div className="table-tools-live">
          {!game.tutorial?.active && <button
              type="button"
              onClick={() => setFastBot((value) => {
                fastBotRef.current = !value;
                return !value;
              })}
            >
              {fastBot ? "Ritmo rapido" : "Ritmo leggibile"}
            </button>}
          {!game.tutorial?.active && <button
              type="button"
              className="undo-button"
              disabled={busy || !game.can_undo}
              title={game.can_undo && game.undo_label ? `Annulla: ${game.undo_label}` : "Disponibile dopo una tua mossa"}
              onClick={undoMove}
            >
              ↶ Indietro di 1 mossa
            </button>}
          <button type="button" className="fullscreen-button" onClick={openFullscreen}>⛶ Schermo intero</button>
          <button type="button" onClick={returnToSetup}>{game.tutorial?.active ? "Esci dal tutorial" : "Nuova partita"}</button>
        </div>
      </header>

      <div className="turn-banner">
        <span>Turno {game.turn}</span>
        <strong>{game.game_over ? "Partita terminata" : game.active_player === game.human_player ? "Il tuo turno" : `Turno di ${opponent.name}`}</strong>
        <em aria-live="polite">{busy ? "Risoluzione in corso…" : game.active_player === game.human_player ? "Scegli la prossima azione" : "Il bot sta valutando il tavolo"}</em>
      </div>

      {game.tutorial?.active && !tutorialIntroOpen && (
        <TutorialCoach
          guide={game.tutorial}
          minimized={tutorialCoachMinimized}
          onToggle={() => setTutorialCoachMinimized((value) => !value)}
        />
      )}

      <div className="game-layout">
        <aside className="left-rail">
          <ScoreDifferenceMeter humanScore={human.score} botScore={opponent.score} />
          <div className="left-rail-panels">
            <OpponentPanel player={opponent} finalsActivator={game.final_trigger_player === opponent.id} />
            <VoidPreview
              card={topVoidCard}
              count={game.void.length}
              onOpen={() => setZoneModal("void")}
              onInspect={() => topVoidCard && setInspected(topVoidCard)}
            />
            <CompactActionLog turns={turnLog} onExpand={() => setLogExpanded(true)} />
          </div>
        </aside>

        <section className="battle-board" ref={battleBoardRef}>
          <PlayerField
            player={opponent}
            isHuman={false}
            active={game.active_player === game.bot_player}
            selectedUid={selectedUid}
            targetUids={pendingTargets}
            onCard={handleCard}
            onInspect={setInspected}
            finalsActivator={game.final_trigger_player === opponent.id}
            tutorialFocusUids={tutorialFocusUids}
          />

          <div className="table-midline">
            <div className="deck-zone-compact"><img src="/cards/back.png" alt="Retro del Mazzo" /><span>Mazzo <b>{game.deck_count}</b></span></div>
            <div className={`final-turns-status ${game.final_turns_remaining != null ? "finals-live" : ""}`}>
              <span>Turni Finali</span>
              <b>{game.final_turns_remaining == null ? "—" : finalsActivatedNow ? "Attivati" : game.final_turns_remaining}</b>
            </div>
            <div className="turn-counter-center"><span>Turno</span><b>{game.turn}</b></div>
          </div>

          <PlayerField
            player={human}
            isHuman
            active={game.active_player === game.human_player}
            selectedUid={selectedUid}
            targetUids={pendingTargets}
            onCard={handleCard}
            onInspect={setInspected}
            onOpenCharges={() => setZoneModal("charges")}
            finalsActivator={game.final_trigger_player === human.id}
            tutorialFocusUids={tutorialFocusUids}
          />
          <div className="table-effects-layer" aria-hidden="true">
            {bondTraces.map((trace) => <BondTrace key={`${trace.prayerUid}-${trace.hostUid}`} trace={trace} />)}
            {attackTrace && <AttackTrace key={attackTrace.eventId} trace={attackTrace} />}
          </div>
          {impulseDisplay && <ImpulseStage key={impulseDisplay.event_id} event={impulseDisplay} viewer={game.human_player} />}
        </section>

        <aside className="right-rail">
          <CardInspector card={inspectedLive} onClose={() => setInspected(null)} />
          <section className="side-hand-section">
            <div className="hand-heading">
              <div><span>La tua mano</span><strong>{human.hand.length} carte</strong></div>
              <p>Trascina una carta sul campo oppure cliccala per scegliere come giocarla.</p>
            </div>
            <div className="modern-hand">
              {human.hand.map((card) => (
                <CardView
                  card={card}
                  kind="hand"
                  key={card.uid}
                  selected={selectedUid === card.uid}
                  targetable={pendingTargets.has(card.uid)}
                  tutorialFocused={tutorialFocusUids.has(card.uid)}
                  onClick={() => handleCard(card)}
                  onInspect={() => setInspected(card)}
                  dragProps={cardDrag.bindCard({
                    uid: card.uid,
                    label: card.name ?? "Carta Bless",
                    validModes: playableDropModes.get(card.uid) ?? [],
                    disabled: busy || game.mode !== "human_turn" || Boolean(game.choice),
                  })}
                />
              ))}
              {!human.hand.length && <span className="empty-hand">Non hai carte in mano.</span>}
            </div>
          </section>
          <PlayerControls
            player={human}
            disabled={busy || game.mode !== "human_turn" || Boolean(game.choice) || Boolean(game.tutorial?.active && !game.tutorial.allow_end_turn)}
            finalsActivator={game.final_trigger_player === human.id}
            onOpenAltar={() => setZoneModal("altar")}
            onEndTurn={() => send({ type: "end_turn" })}
          />
        </aside>
      </div>

      {selectedUid != null && !game.choice && (commandButtons.length > 0 || selectedCombatPreviews.length > 0) && (
        <div className="action-dock">
          <span>{allVisibleCards.find((card) => card.uid === selectedUid)?.name}</span>
          {commandButtons.map((group) => (
            <button type="button" className={group.tone ?? ""} key={group.label} disabled={busy} onClick={() => chooseActionGroup(group.actions, group.label, group.alwaysChooseTarget)}>
              {group.label}<small>{group.detail ?? `${group.actions[0]?.cost ?? 1} ${group.actions[0]?.cost === 1 ? "Azione" : "Azioni"}`}</small>
            </button>
          ))}
          {commandButtons.every((group) => group.actions[0]?.kind !== "attack") && selectedCombatPreviews.some((preview) => !preview.allowed) && (
            <span className="combat-blocked-note">
              <b>Nessun attacco valido</b>
              <small>{selectedCombatPreviews.find((preview) => !preview.allowed)?.reason}</small>
            </span>
          )}
          <button type="button" className="dock-close" onClick={() => setSelectedUid(null)}>×</button>
        </div>
      )}

      {targetPlan && (
        <aside
          className={`choice-panel target-plan-panel ${targetPanelDrag.panelClassName}`}
          ref={targetPanelDrag.panelRef}
          style={targetPanelDrag.panelStyle}
        >
          <div className="choice-panel-titlebar">
            <span className="choice-kicker">{targetlessActionPlan ? "Scegli come calare" : "Scegli il bersaglio"}</span>
            <PanelDragHandle handleProps={targetPanelDrag.handleProps} />
          </div>
          <strong>{targetPlan.title}</strong>
          <p>
            {targetlessActionPlan
              ? "Scegli se pagare normalmente oppure usare l'alternativa gratuita disponibile."
              : `${targetPlan.actions.length === 1 ? "1 solo bersaglio valido" : `${targetPlan.actions.length} bersagli validi`}.${targetPreview
                ? ` Previsione silenziosa: ${targetPreview.attacker_eye} contro ${targetPreview.defender_eye}${targetPreview.attacker_rivalry_applied ? ", Rivalità applicata" : ""}.`
                : " Solo le carte illuminate possono essere scelte."}`}
          </p>
          {targetlessActionPlan && (
            <div className="action-choice-list" aria-label="Modalità disponibili">
              {targetPlan.actions.map((action) => (
                <button type="button" key={action.id} onClick={() => performLegalAction(action)}>
                  <b>{action.mode === "MaledizioneCarica" ? "Maledizione (0 Azioni)" : action.label}</b>
                  <small>{action.mode === "MaledizioneCarica" ? "Sceglierai 1 Carica da spendere" : `${action.cost} ${action.cost === 1 ? "Azione" : "Azioni"}`}</small>
                </button>
              ))}
            </div>
          )}
          {combatTargetPlan && (
            <div className="combat-target-list" aria-label="Bersagli validi dell'attacco">
              {targetPlan.actions.map((action) => {
                const preview = action.combat_preview;
                const target = allVisibleCards.find((card) => card.uid === action.target_uid);
                return (
                  <button type="button" key={action.id} onClick={() => performLegalAction(action)}>
                    <b>{target?.name ?? "Maledizione avversaria"}</b>
                    {preview && (
                      <small>
                        {preview.attacker_eye} contro {preview.defender_eye}
                        {preview.attacker_rivalry_applied ? " · Rivalità +3" : ""}
                      </small>
                    )}
                  </button>
                );
              })}
            </div>
          )}
          {excludedCombatPreviews.length > 0 && (
            <div className="combat-exclusion-list">
              <span>Non selezionabili dopo la previsione</span>
              {excludedCombatPreviews.map((preview) => (
                <p key={preview.target_uid}>
                  <b>{allVisibleCards.find((card) => card.uid === preview.target_uid)?.name ?? "Maledizione"}</b>
                  <small>{preview.reason}</small>
                </p>
              ))}
            </div>
          )}
          <button type="button" className="skip-choice" onClick={() => setTargetPlan(null)}>Annulla</button>
        </aside>
      )}

      {game.choice && game.choice.kind !== "multi_card" && (
        <ChoicePanel
          choice={game.choice}
          onOption={(value) => send({ type: "choice", value })}
          onCard={(uid) => send({ type: "choice", value: uid })}
          onSkip={() => send({ type: "choice", value: null })}
        />
      )}
      {game.choice?.kind === "multi_card" && (
        <MulliganDialog
          key={`${game.turn}-${(game.choice.candidate_uids ?? []).join("-")}`}
          choice={game.choice}
          initial={game.turn === 0}
          minimized={mulliganMinimized}
          onConfirm={(uids) => send({ type: "choice", value: uids })}
          onUndo={game.can_undo ? undoMove : undefined}
          onToggleMinimized={() => setMulliganMinimized((value) => !value)}
          tutorialLockedUids={game.tutorial?.mulligan_locked_uids}
        />
      )}
      {fateDisplay && <FateDiceOverlay key={fateDisplay.event_id} event={fateDisplay} />}
      {zoneModal === "void" && (
        <ZoneDialog
          title="Vuoto"
          cards={game.void}
          facedown={false}
          ordered
          onInspect={setInspected}
          playableUids={new Set(game.legal_actions.filter((action) => action.card_uid != null).map((action) => Number(action.card_uid)))}
          onPlay={(card) => {
            setZoneModal(null);
            handleCard(card);
          }}
          onClose={() => setZoneModal(null)}
        />
      )}
      {zoneModal === "altar" && <ZoneDialog title="Il tuo Altare" cards={human.altar} facedown onClose={() => setZoneModal(null)} />}
      {zoneModal === "charges" && <ZoneDialog title="Le tue Cariche private" cards={human.charges} facedown={false} onClose={() => setZoneModal(null)} />}
      {logExpanded && <ExpandedLogDialog turns={fullTurnLog} onClose={() => setLogExpanded(false)} />}
      {game.game_over && (
        <GameOverDialog
          game={game}
          onRestart={returnToSetup}
          onSaveReplay={saveCurrentReplay}
          savedReplayId={savedReplayId}
        />
      )}
      {game.tutorial?.active && tutorialIntroOpen && <TutorialIntro onStart={() => setTutorialIntroOpen(false)} />}
      <CardDragAccessibility announcement={cardDrag.announcement} />
      {error && <div className="live-error"><span>{error}</span><button type="button" onClick={() => setError("")}>×</button></div>}
    </main>
  );
}
