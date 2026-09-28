"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

type RevealTarget = Parameters<typeof import("animejs").animate>[0];

/** Starting offset for each `data-reveal` value. */
function entrance(el: Element): Record<string, number[]> {
  const dir = el.getAttribute("data-reveal");
  if (dir === "left") return { x: [-28, 0], opacity: [0, 1] };
  if (dir === "right") return { x: [28, 0], opacity: [0, 1] };
  if (dir === "scale") return { scale: [0.94, 1], opacity: [0, 1] };
  return { y: [26, 0], opacity: [0, 1] };
}

/**
 * Mounted once in the layout. Animates every element with `data-reveal` when
 * it scrolls into view, so server components just add the attribute instead
 * of wrapping things in a client component.
 *
 * - `data-reveal-group` on a container staggers its children.
 * - `data-reveal="left" | "right" | "scale"` picks the direction.
 *
 * Without JS nothing is hidden, since the initial state is set from here and
 * not in the HTML.
 */
export default function ScrollReveal() {
  const pathname = usePathname();

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    // Only the home page and /gioco use `data-reveal`. If there's nothing to
    // animate, don't bother downloading animejs at all.
    if (!document.querySelector("[data-reveal]")) return;

    let cancelled = false;
    const cleanups: Array<() => void> = [];

    (async () => {
      const { animate, stagger, onScroll, utils } = await import("animejs");
      if (cancelled) return;

      const arm = (els: HTMLElement[]) =>
        els.forEach((el) => el.setAttribute("data-reveal-armed", "1"));
      const disarm = (els: HTMLElement[]) =>
        els.forEach((el) => el.removeAttribute("data-reveal-armed"));

      const reveal = (els: HTMLElement[], target: RevealTarget, extra: object) => {
        arm(els);
        const anim = animate(target, {
          ...entrance(els[0]),
          ...extra,
          ease: "out(3)",
          onBegin: () => disarm(els),
          autoplay: onScroll({ enter: "bottom-=60 top", repeat: false }),
        });
        cleanups.push(() => anim.revert());
      };

      const grouped = new Set<Element>();

      for (const group of document.querySelectorAll<HTMLElement>("[data-reveal-group]")) {
        const children = Array.from(group.querySelectorAll<HTMLElement>("[data-reveal]"));
        if (!children.length) continue;
        children.forEach((c) => grouped.add(c));
        reveal(children, children, { duration: 760, delay: stagger(70) });
      }

      for (const el of document.querySelectorAll<HTMLElement>("[data-reveal]")) {
        if (grouped.has(el)) continue;
        reveal([el], el, { duration: 720 });
      }

      cleanups.push(() => disarm(utils.$("[data-reveal]") as HTMLElement[]));
    })();

    return () => {
      cancelled = true;
      cleanups.forEach((c) => c());
    };
  }, [pathname]);

  return null;
}
