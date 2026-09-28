"use client";

import { useEffect, useRef } from "react";
import styles from "./SplitHeadline.module.css";

/**
 * Headline that animates in word by word. The server renders a normal
 * `<h1>` (good for crawlers and screen readers) and we only split it up
 * after hydration. If that fails you just get the plain heading.
 */
export default function SplitHeadline({ text }: { text: string }) {
  const ref = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let cancelled = false;
    let cleanup: (() => void) | undefined;

    (async () => {
      const { animate, stagger, text: splitText, createSpring } = await import("animejs");
      if (cancelled || !ref.current) return;

      // Wrap each word too, so lines only break between words and not in the
      // middle of one.
      const splitter = splitText.split(el, {
        words: { wrap: "clip" },
        chars: true,
        accessible: true,
      });

      const anim = animate(splitter.chars, {
        y: ["105%", "0%"],
        opacity: [0, 1],
        duration: 900,
        delay: stagger(22),
        ease: createSpring({ stiffness: 120, damping: 20 }),
      });

      cleanup = () => {
        anim.revert();
        splitter.revert();
      };
    })();

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [text]);

  return (
    <h1 ref={ref} className={styles.title}>
      {text}
    </h1>
  );
}
