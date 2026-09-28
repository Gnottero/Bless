"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

const TOOLTIP_MAX_WIDTH = 300;
const VIEWPORT_MARGIN = 12;
const TOOLTIP_GAP = 8;

interface TooltipPosition {
  left: number;
  top: number;
  width: number;
}

interface AbilityTermProps {
  children: ReactNode;
  description: string;
  name: string;
}

export function AbilityTerm({ children, description, name }: AbilityTermProps) {
  const anchorRef = useRef<HTMLElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);
  const tooltipId = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const [portalTarget, setPortalTarget] = useState<Element | null>(null);
  const open = hovered || focused;

  const updatePosition = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const width = Math.max(
      0,
      Math.min(TOOLTIP_MAX_WIDTH, viewportWidth - VIEWPORT_MARGIN * 2),
    );
    const anchorRect = anchor.getBoundingClientRect();
    const tooltipHeight = tooltipRef.current?.offsetHeight ?? 0;
    const centeredLeft = anchorRect.left + anchorRect.width / 2 - width / 2;
    const left = Math.max(
      VIEWPORT_MARGIN,
      Math.min(centeredLeft, viewportWidth - width - VIEWPORT_MARGIN),
    );
    const roomBelow = viewportHeight - anchorRect.bottom - TOOLTIP_GAP - VIEWPORT_MARGIN;
    const preferredTop = roomBelow >= tooltipHeight
      ? anchorRect.bottom + TOOLTIP_GAP
      : anchorRect.top - tooltipHeight - TOOLTIP_GAP;
    const top = Math.max(
      VIEWPORT_MARGIN,
      Math.min(preferredTop, viewportHeight - tooltipHeight - VIEWPORT_MARGIN),
    );

    setPosition({ left, top, width });
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }
    updatePosition();
  }, [open, portalTarget, updatePosition]);

  useEffect(() => {
    const updatePortalTarget = () => {
      setPortalTarget(document.fullscreenElement ?? document.body);
    };
    updatePortalTarget();
    document.addEventListener("fullscreenchange", updatePortalTarget);
    return () => document.removeEventListener("fullscreenchange", updatePortalTarget);
  }, []);

  useEffect(() => {
    if (!open) return;
    let frame = 0;
    const scheduleUpdate = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(updatePosition);
    };
    window.addEventListener("resize", scheduleUpdate);
    window.addEventListener("scroll", scheduleUpdate, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", scheduleUpdate);
      window.removeEventListener("scroll", scheduleUpdate, true);
    };
  }, [open, updatePosition]);

  const tooltipStyle: CSSProperties = position
    ? { left: position.left, top: position.top, width: position.width }
    : { left: 0, top: 0, width: TOOLTIP_MAX_WIDTH, visibility: "hidden" };

  return (
    <>
      <strong
        ref={anchorRef}
        className="ability-term"
        tabIndex={0}
        aria-describedby={open ? tooltipId : undefined}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          setHovered(false);
          setFocused(false);
          anchorRef.current?.blur();
        }}
      >
        {children}
      </strong>
      {open && portalTarget && createPortal(
        <span
          ref={tooltipRef}
          id={tooltipId}
          className="ability-tooltip"
          role="tooltip"
          style={tooltipStyle}
        >
          <b>{name}</b>
          <span>{description}</span>
        </span>,
        portalTarget,
      )}
    </>
  );
}
