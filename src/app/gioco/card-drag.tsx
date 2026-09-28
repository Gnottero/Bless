"use client";

import {
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

export type CardDropMode = "Maledizione" | "Preghiera";

export const CARD_DRAG_HELP_ID = "bless-card-drag-help";

interface CardDragOptions {
  uid: number;
  label: string;
  validModes: readonly CardDropMode[];
  disabled?: boolean;
}

export interface CardDragButtonProps {
  draggable: false;
  "aria-describedby": typeof CARD_DRAG_HELP_ID;
  onPointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onPointerUp: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onPointerCancel: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onLostPointerCapture: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onClickCapture: (event: ReactMouseEvent<HTMLButtonElement>) => void;
}

interface DragSession {
  pointerId: number;
  pointerType: string;
  uid: number;
  label: string;
  source: HTMLButtonElement;
  root: HTMLElement;
  validModes: Set<CardDropMode>;
  startX: number;
  startY: number;
  lastX: number;
  lastY: number;
  offsetX: number;
  offsetY: number;
  rect: DOMRect;
  active: boolean;
  ghost: HTMLElement | null;
  target: HTMLElement | null;
  targetMode: CardDropMode | null;
  frame: number | null;
}

const DRAG_THRESHOLD = 7;

function readDropMode(element: Element | null): CardDropMode | null {
  const target = element?.closest<HTMLElement>("[data-card-drop-mode]");
  const mode = target?.dataset.cardDropMode;
  return mode === "Maledizione" || mode === "Preghiera" ? mode : null;
}

function findDropTarget(session: DragSession, x: number, y: number): HTMLElement | null {
  const element = document.elementFromPoint(x, y);
  const target = element?.closest<HTMLElement>("[data-card-drop-mode]") ?? null;
  if (!target || !session.root.contains(target)) return null;
  const mode = readDropMode(target);
  return mode && session.validModes.has(mode) ? target : null;
}

function positionGhost(session: DragSession) {
  if (!session.ghost) return;
  const touchLift = session.pointerType === "touch" ? Math.min(44, session.rect.height * 0.36) : 0;
  session.ghost.style.setProperty("--card-drag-x", `${Math.round(session.lastX - session.offsetX)}px`);
  session.ghost.style.setProperty("--card-drag-y", `${Math.round(session.lastY - session.offsetY - touchLift)}px`);
}

function releaseCapture(session: DragSession) {
  try {
    if (session.source.hasPointerCapture(session.pointerId)) {
      session.source.releasePointerCapture(session.pointerId);
    }
  } catch {
    // Il nodo puo' essere stato rimosso da un aggiornamento della partita.
  }
}

function cleanSession(session: DragSession) {
  if (session.frame != null) window.cancelAnimationFrame(session.frame);
  session.frame = null;
  session.target?.classList.remove("is-card-drop-over");
  session.root.querySelectorAll<HTMLElement>("[data-card-drop-mode]").forEach((zone) => {
    zone.classList.remove("is-card-drop-eligible", "is-card-drop-over");
  });
  session.source.classList.remove("is-card-drag-origin");
  session.ghost?.remove();
  session.ghost = null;
  document.body.classList.remove("is-card-dragging");
}

function createGhost(session: DragSession) {
  const ghost = session.source.cloneNode(true) as HTMLElement;
  ghost.removeAttribute("data-card-uid");
  ghost.removeAttribute("aria-describedby");
  ghost.removeAttribute("aria-pressed");
  ghost.setAttribute("aria-hidden", "true");
  ghost.setAttribute("tabindex", "-1");
  ghost.classList.remove("is-selected", "is-targetable", "is-card-drag-origin");
  ghost.classList.add("card-drag-ghost");
  if (session.pointerType === "touch") ghost.classList.add("is-touch-drag");
  ghost.querySelectorAll<HTMLElement>("[id]").forEach((element) => element.removeAttribute("id"));
  ghost.style.width = `${session.rect.width}px`;
  ghost.style.height = `${session.rect.height}px`;
  ghost.style.viewTransitionName = "none";
  if ("inert" in ghost) (ghost as HTMLElement & { inert: boolean }).inert = true;
  session.ghost = ghost;
  (document.fullscreenElement ?? document.body).appendChild(ghost);
  positionGhost(session);
}

export function useCardDrag(
  onDrop: (mode: CardDropMode, uid: number) => void,
  resetKey: unknown,
) {
  const sessionRef = useRef<DragSession | null>(null);
  const onDropRef = useRef(onDrop);
  const suppressedClickRef = useRef<{ uid: number; until: number } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  onDropRef.current = onDrop;

  const cancel = useCallback((announce = true) => {
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    releaseCapture(session);
    cleanSession(session);
    if (session.active) {
      suppressedClickRef.current = { uid: session.uid, until: Date.now() + 1_500 };
      if (announce) setAnnouncement(`Trascinamento di ${session.label} annullato.`);
    }
  }, []);

  useEffect(() => {
    cancel(false);
  }, [cancel, resetKey]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && sessionRef.current?.active) {
        event.preventDefault();
        cancel();
      }
    };
    const onVisibilityChange = () => {
      if (document.hidden) cancel(false);
    };
    const onWindowInterruption = () => cancel(false);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("blur", onWindowInterruption);
    window.addEventListener("resize", onWindowInterruption);
    document.addEventListener("visibilitychange", onVisibilityChange);
    document.addEventListener("fullscreenchange", onWindowInterruption);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("blur", onWindowInterruption);
      window.removeEventListener("resize", onWindowInterruption);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      document.removeEventListener("fullscreenchange", onWindowInterruption);
      cancel(false);
    };
  }, [cancel]);

  const activate = useCallback((session: DragSession) => {
    session.active = true;
    session.source.classList.add("is-card-drag-origin");
    document.body.classList.add("is-card-dragging");
    session.root.querySelectorAll<HTMLElement>("[data-card-drop-mode]").forEach((zone) => {
      const mode = readDropMode(zone);
      if (mode && session.validModes.has(mode)) zone.classList.add("is-card-drop-eligible");
    });
    createGhost(session);
    const destinations = [...session.validModes].join(" o ");
    setAnnouncement(`${session.label} presa. Rilascia su ${destinations}. Premi Esc per annullare.`);
  }, []);

  const update = useCallback((session: DragSession) => {
    session.frame = null;
    positionGhost(session);
    const target = findDropTarget(session, session.lastX, session.lastY);
    if (target === session.target) return;
    session.target?.classList.remove("is-card-drop-over");
    session.target = target;
    session.targetMode = readDropMode(target);
    session.target?.classList.add("is-card-drop-over");
    if (session.targetMode) setAnnouncement(`${session.label}: rilascia per giocarla come ${session.targetMode}.`);
  }, []);

  const bindCard = useCallback((options: CardDragOptions): CardDragButtonProps | undefined => {
    if (options.disabled || options.validModes.length === 0) return undefined;

    const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
      if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
      cancel(false);
      const source = event.currentTarget;
      const rect = source.getBoundingClientRect();
      const root = source.closest<HTMLElement>(".manual-table");
      if (!root) return;
      const session: DragSession = {
        pointerId: event.pointerId,
        pointerType: event.pointerType,
        uid: options.uid,
        label: options.label,
        source,
        root,
        validModes: new Set(options.validModes),
        startX: event.clientX,
        startY: event.clientY,
        lastX: event.clientX,
        lastY: event.clientY,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
        rect,
        active: false,
        ghost: null,
        target: null,
        targetMode: null,
        frame: null,
      };
      sessionRef.current = session;
      try {
        source.setPointerCapture(event.pointerId);
      } catch {
        // Un aggiornamento del tavolo puo' aver rimosso il nodo o il puntatore.
        cancel(false);
      }
    };

    const onPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
      const session = sessionRef.current;
      if (!session || session.pointerId !== event.pointerId) return;
      session.lastX = event.clientX;
      session.lastY = event.clientY;
      if (!session.active) {
        const distance = Math.hypot(event.clientX - session.startX, event.clientY - session.startY);
        if (distance < DRAG_THRESHOLD) return;
        activate(session);
      }
      event.preventDefault();
      if (session.frame == null) session.frame = window.requestAnimationFrame(() => update(session));
    };

    const onPointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
      const session = sessionRef.current;
      if (!session || session.pointerId !== event.pointerId) return;
      session.lastX = event.clientX;
      session.lastY = event.clientY;
      sessionRef.current = null;
      releaseCapture(session);
      if (!session.active) {
        cleanSession(session);
        return;
      }
      event.preventDefault();
      suppressedClickRef.current = { uid: session.uid, until: Date.now() + 1_500 };
      const target = findDropTarget(session, event.clientX, event.clientY);
      const mode = readDropMode(target);
      cleanSession(session);
      if (mode && session.validModes.has(mode)) {
        setAnnouncement(`${session.label} rilasciata come ${mode}.`);
        onDropRef.current(mode, session.uid);
      } else {
        setAnnouncement(`${session.label} riportata nella mano.`);
      }
    };

    const onPointerCancel = (event: ReactPointerEvent<HTMLButtonElement>) => {
      if (sessionRef.current?.pointerId === event.pointerId) cancel();
    };

    const onLostPointerCapture = (event: ReactPointerEvent<HTMLButtonElement>) => {
      if (sessionRef.current?.pointerId === event.pointerId) cancel();
    };

    const onClickCapture = (event: ReactMouseEvent<HTMLButtonElement>) => {
      const suppressed = suppressedClickRef.current;
      if (!suppressed || suppressed.uid !== options.uid || suppressed.until < Date.now()) return;
      suppressedClickRef.current = null;
      event.preventDefault();
      event.stopPropagation();
    };

    return {
      draggable: false,
      "aria-describedby": CARD_DRAG_HELP_ID,
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel,
      onLostPointerCapture,
      onClickCapture,
    };
  }, [activate, cancel, update]);

  return { announcement, bindCard, cancel };
}

export function CardDragAccessibility({ announcement }: { announcement: string }) {
  return (
    <div className="card-drag-a11y">
      <span id={CARD_DRAG_HELP_ID}>
        Trascina la carta sul campo. In alternativa, selezionala e usa i comandi di gioco.
      </span>
      <span role="status" aria-live="polite" aria-atomic="true">{announcement}</span>
    </div>
  );
}
