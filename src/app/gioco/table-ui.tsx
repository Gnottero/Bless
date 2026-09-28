"use client";

import {
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  useEffect,
  useRef,
  useState,
} from "react";

interface PanelOffset {
  x: number;
  y: number;
}

interface DragSnapshot extends PanelOffset {
  pointerId: number;
  startX: number;
  startY: number;
  rect: DOMRect;
}

export function useDraggablePanel(resetKey: unknown) {
  const panelRef = useRef<HTMLElement | null>(null);
  const dragRef = useRef<DragSnapshot | null>(null);
  const [offset, setOffset] = useState<PanelOffset>({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    setOffset({ x: 0, y: 0 });
    dragRef.current = null;
    setDragging(false);
  }, [resetKey]);

  const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || !panelRef.current) return;
    const rect = panelRef.current.getBoundingClientRect();
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      rect,
      ...offset,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    event.preventDefault();
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const margin = 8;
    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;
    const boundedX = Math.min(
      window.innerWidth - margin - drag.rect.right,
      Math.max(margin - drag.rect.left, deltaX),
    );
    const boundedY = Math.min(
      window.innerHeight - margin - drag.rect.bottom,
      Math.max(margin - drag.rect.top, deltaY),
    );
    setOffset({ x: drag.x + boundedX, y: drag.y + boundedY });
  };

  const finishDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    setDragging(false);
  };

  return {
    panelRef,
    panelClassName: dragging ? "draggable-panel is-dragging" : "draggable-panel",
    panelStyle: {
      "--panel-shift-x": `${offset.x}px`,
      "--panel-shift-y": `${offset.y}px`,
    } as CSSProperties,
    handleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp: finishDrag,
      onPointerCancel: finishDrag,
    },
  };
}

export function PanelDragHandle({
  handleProps,
}: {
  handleProps: ReturnType<typeof useDraggablePanel>["handleProps"];
}) {
  return (
    <button
      type="button"
      className="panel-drag-handle"
      aria-label="Sposta questa finestra"
      title="Trascina per spostare la finestra"
      {...handleProps}
    >
      <span aria-hidden="true">⠿</span>
      Sposta
    </button>
  );
}

export function InspectCue({ label = "Apri" }: { label?: string }) {
  return (
    <span className="inspect-cue" aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false">
        <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
        <circle cx="12" cy="12" r="2.8" />
      </svg>
      <span>{label}</span>
    </span>
  );
}

export function OrientationGate() {
  return (
    <div className="orientation-gate" role="status" aria-live="polite">
      <span className="orientation-phone" aria-hidden="true"><i /></span>
      <strong>Ruota il telefono</strong>
      <small>Il tavolo di Bless si gioca in orizzontale.</small>
    </div>
  );
}

export interface ImpulseStageEvent<Card> {
  event_id: number;
  card_uid: number;
  controller: number;
  card: Card;
}

export function ImpulseStage({
  event,
  viewer,
}: {
  event: ImpulseStageEvent<{ name?: string; image?: string }>;
  viewer: number;
}) {
  const owner = event.controller === viewer ? "Tu" : "Avversario";
  return (
    <div className={`impulse-stage ${event.controller === viewer ? "is-human" : "is-opponent"}`} role="status" aria-live="polite">
      <span>{owner} gioca un Impulso</span>
      {event.card.image && <img src={event.card.image} alt={event.card.name ?? "Carta Impulso"} />}
      <div>
        <strong>{event.card.name ?? "Impulso"}</strong>
        <em>Effetto in risoluzione</em>
        <small>Al termine raggiunge il Vuoto</small>
      </div>
    </div>
  );
}
