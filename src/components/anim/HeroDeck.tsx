"use client";

import type { JSAnimation } from "animejs";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CARDS, CARD_HEIGHT, CARD_WIDTH, FORMS, cardById, cardImage } from "@/data/cards";
import styles from "./HeroDeck.module.css";

/**
 * Cards used for the server render: one per Form plus two with nice art.
 * After hydration we swap them for a random hand.
 */
const SELECTION = [61, 31, 1, 21, 48];

function shuffle<T>(items: readonly T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Random hand of the same size, with at least one card of each Form. */
function randomHand(): number[] {
  const deck = shuffle(CARDS);
  const onePerForm = FORMS.map((f) => deck.find((c) => c.form === f)!);
  const rest = deck
    .filter((c) => !onePerForm.includes(c))
    .slice(0, SELECTION.length - onePerForm.length);
  return shuffle([...onePerForm, ...rest]).map((c) => c.id);
}

/**
 * Where each card sits in the fan, left to right. x and y are relative to the
 * stage width so the layout adapts without scaling everything down (which
 * would also shrink the text).
 */
const POSES = [
  { x: -0.35, y: 0.046, r: -15, z: 1 },
  { x: -0.18, y: -0.011, r: -7.5, z: 2 },
  { x: 0, y: -0.043, r: 0, z: 3 },
  { x: 0.18, y: -0.011, r: 7.5, z: 2 },
  { x: 0.35, y: 0.046, r: 15, z: 1 },
];

export default function HeroDeck() {
  const root = useRef<HTMLDivElement>(null);
  const router = useRouter();
  // null until mounted, picking random cards during render would cause a hydration mismatch.
  const [hand, setHand] = useState<number[] | null>(null);

  useEffect(() => setHand(randomHand()), []);

  useEffect(() => {
    const el = root.current;
    if (!el || !hand) return;

    const cards = Array.from(el.querySelectorAll<HTMLElement>("[data-card]"));
    /** Converts the poses to pixels for the current stage width. */
    let poses = POSES;
    const measure = () => {
      const w = el.clientWidth || 560;
      poses = POSES.map((p) => ({ ...p, x: p.x * w, y: p.y * w }));
    };
    measure();

    const atRest = () =>
      cards.forEach((c, i) => {
        c.style.zIndex = String(poses[i].z);
        c.style.transform = `translate(${poses[i].x}px, ${poses[i].y}px) rotate(${poses[i].r}deg)`;
      });

    // Set the final pose right away so the fan looks right even if the animation never runs.
    atRest();

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const ro = new ResizeObserver(() => {
        measure();
        atRest();
      });
      ro.observe(el);
      return () => ro.disconnect();
    }

    let cancelled = false;
    const cleanups: Array<() => void> = [];
    const isDragged = (c: HTMLElement) => c.dataset.dragged === "1";

    (async () => {
      const { animate, createDraggable, createSpring, stagger, utils } = await import(
        "animejs"
      );
      if (cancelled || !root.current) return;

      const poseValue = (key: "x" | "y" | "r") => (_t?: unknown, i?: number) =>
        poses[i ?? 0][key];

      // 1. Deal: cards start stacked in the centre and fan out.
      utils.set(cards, { x: 0, y: 90, rotate: 0, scale: 0.86, opacity: 0 });
      const deal = animate(cards, {
        x: poseValue("x"),
        y: poseValue("y"),
        rotate: poseValue("r"),
        scale: 1,
        opacity: 1,
        duration: 1100,
        delay: stagger(110, { start: 180 }),
        ease: createSpring({ stiffness: 90, damping: 14 }),
      });
      cleanups.push(() => deal.revert());

      const backToPlace = (c: HTMLElement, i: number, spring = false) =>
        animate(c, {
          x: poses[i].x,
          y: poses[i].y,
          rotate: poses[i].r,
          scale: 1,
          duration: 900,
          ease: spring
            ? createSpring({ stiffness: 110, damping: 16 })
            : ("out(3)" as const),
        });

      // Recompute the poses on resize and move the cards back.
      const ro = new ResizeObserver(() => {
        measure();
        cards.forEach((c, i) => {
          if (isDragged(c)) return;
          utils.set(c, { x: poses[i].x, y: poses[i].y, rotate: poses[i].r });
        });
      });
      ro.observe(el);
      cleanups.push(() => ro.disconnect());

      // 2. Subtle parallax following the mouse.
      const onMove = (e: PointerEvent) => {
        const r = el.getBoundingClientRect();
        const nx = (e.clientX - r.left) / r.width - 0.5;
        const ny = (e.clientY - r.top) / r.height - 0.5;
        cards.forEach((c, i) => {
          if (isDragged(c)) return;
          const weight = 6 + poses[i].z * 5;
          animate(c, {
            x: poses[i].x + nx * weight * 2.2,
            y: poses[i].y + ny * weight,
            rotate: poses[i].r + nx * 3,
            duration: 900,
            ease: "out(3)",
          });
        });
      };
      const onLeave = () => {
        cards.forEach((c, i) => {
          if (!isDragged(c)) backToPlace(c, i);
        });
      };

      // 3. Cards can be dragged around the hero, and dropping one opens its
      // page. We also handle plain clicks on release, because anime.js
      // disables pointer events on the card as soon as it moves while held,
      // so the link's own click doesn't always fire. Keyboard (click with
      // detail 0) and ctrl/cmd clicks still go through the link normally.
      cards.forEach((c, i) => {
        let modified = false;
        let grabAt = { x: 0, y: 0 };
        let centering: JSAnimation | null = null;
        const onDown = (e: PointerEvent) => {
          modified = e.metaKey || e.ctrlKey || e.shiftKey || e.altKey;
          grabAt = { x: e.clientX, y: e.clientY };
        };
        const onClick = (e: MouseEvent) => {
          if (e.detail > 0 && !modified) e.preventDefault();
        };
        c.addEventListener("pointerdown", onDown);
        c.addEventListener("click", onClick);
        cleanups.push(() => {
          c.removeEventListener("pointerdown", onDown);
          c.removeEventListener("click", onClick);
        });

        const d = createDraggable(c, {
          // Use the whole hero as bounds. The stage is barely taller than a
          // card, so the cards could hardly move inside it.
          container: el.closest("section") ?? el,
          // No rubber band, the card stays inside the hero.
          containerFriction: 1,
          releaseEase: createSpring({ stiffness: 110, damping: 16 }),
          onGrab: (self) => {
            c.dataset.dragged = "1";
            c.style.zIndex = "20";
            animate(c, { scale: 1.06, duration: 220, ease: "out(3)" });

            // Slide the card so its centre ends up under the cursor. anime.js
            // moves a held card by adding pointer deltas to `coords`, so we add
            // our offset there a bit at a time and it combines with whatever
            // the user is doing meanwhile.
            const r = c.getBoundingClientRect();
            const pull = { x: 0, y: 0 };
            let done = { x: 0, y: 0 };
            centering = animate(pull, {
              x: grabAt.x - (r.left + r.width / 2),
              y: grabAt.y - (r.top + r.height / 2),
              duration: 220,
              ease: "out(3)",
              onUpdate: () => {
                self.coords[0] += pull.x - done.x;
                self.coords[1] += pull.y - done.y;
                done = { ...pull };
                const [top, right, bottom, left] = self.containerBounds;
                self.setX(utils.clamp(self.coords[0], left, right));
                self.setY(utils.clamp(self.coords[1], top, bottom));
              },
            });
          },
          onRelease: () => {
            centering?.pause();
            if (!modified) {
              // Leave it where it was dropped (dragged = "1" turns off parallax for it).
              animate(c, { scale: 1, duration: 220, ease: "out(3)" });
              router.push(c.getAttribute("href")!);
              return;
            }
            backToPlace(c, i, true).then(() => {
              c.dataset.dragged = "0";
              c.style.zIndex = String(poses[i].z);
            });
          },
        });
        cleanups.push(() => d.revert());
      });

      if (window.matchMedia("(pointer: fine)").matches) {
        el.addEventListener("pointermove", onMove);
        el.addEventListener("pointerleave", onLeave);
        cleanups.push(() => {
          el.removeEventListener("pointermove", onMove);
          el.removeEventListener("pointerleave", onLeave);
        });
      }
    })();

    return () => {
      cancelled = true;
      cleanups.forEach((c) => c());
    };
  }, [hand, router]);

  return (
    <div className={styles.stage} ref={root}>
      <div className={styles.rays} aria-hidden="true" />
      {(hand ?? SELECTION).map((id, i) => {
        const card = cardById(id);
        if (!card) return null;
        return (
          <Link
            key={id}
            href={`/database/${id}`}
            data-card
            className={styles.card}
            style={{ zIndex: POSES[i].z }}
            data-form={card.form}
            // Links are draggable by default and Firefox would start its own
            // drag (the ghost image), so anime.js never gets the pointer.
            draggable={false}
            onDragStart={(e) => e.preventDefault()}
          >
            <Image
              src={cardImage(id)}
              alt={`${card.name} — carta di Bless`}
              width={CARD_WIDTH}
              height={CARD_HEIGHT}
              sizes="(max-width: 700px) 30vw, 170px"
              placeholder="blur"
              blurDataURL={card.blurDataURL}
              priority={i === 2}
              draggable={false}
            />
          </Link>
        );
      })}
    </div>
  );
}
