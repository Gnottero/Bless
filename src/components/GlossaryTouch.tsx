"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

/**
 * The glossary tooltip (see GameText) only opens on `:hover` and
 * `:focus-visible`. On touch screens you never get either: tapping a term is
 * just a click on the link and takes you straight to the rulebook.
 *
 * This makes the first tap open the tooltip, and a second tap on the same
 * term follow the link. Tapping anywhere else or pressing Esc closes it.
 *
 * We deliberately don't close it on scroll. On small screens the tooltip is
 * `position: fixed` so it can't drift away anyway, and the tiny scroll that
 * comes with a tap was enough to close it right after opening.
 *
 * It's mounted once in the layout and bails out immediately on devices that
 * can hover, so desktop keeps the plain CSS behaviour.
 */
export default function GlossaryTouch() {
  const pathname = usePathname();

  useEffect(() => {
    // Check for hover support rather than trying to detect phones.
    if (window.matchMedia("(hover: hover)").matches) return;

    let openTerm: HTMLElement | null = null;

    const close = () => {
      if (!openTerm) return;
      openTerm.removeAttribute("data-open");
      openTerm = null;
    };

    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      const term = target?.closest<HTMLElement>("[data-glossary]");

      if (!term) {
        close();
        return;
      }

      // Second tap on the same term: let the link navigate.
      if (term === openTerm) return;

      e.preventDefault();
      close();
      openTerm = term;
      term.setAttribute("data-open", "1");
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };

    // Capture phase so we run before Next's Link handles the click.
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onKey);

    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("keydown", onKey);
      close();
    };
  }, [pathname]);

  return null;
}
