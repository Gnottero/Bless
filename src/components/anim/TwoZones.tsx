"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import PrayerTypeIcon from "@/components/PrayerTypeIcon";
import ToonCard from "@/components/three/ToonCard";
import type { CardZone } from "@/components/three/toon";
import { CARD_HEIGHT, CARD_WIDTH, cardById, cardImage } from "@/data/cards";
import { findTerm } from "@/data/glossary";
import styles from "./TwoZones.module.css";

const EXAMPLE_ID = 21;
const AUTOPLAY_MS = 5200;

const ZONES: {
  key: CardZone;
  label: string;
  title: string;
  note: string;
}[] = [
  {
    key: "curse",
    label: "Zona Maledizione",
    title: "Giocala come Maledizione",
    note: "Combatte usando l'Occhio, e quando Blessa ti fa punti pari al Karma.",
  },
  {
    key: "prayer",
    label: "Zona Preghiera",
    title: "Giocala come Preghiera",
    note: "Non attacca e non può essere attaccata: cambia le regole del tavolo.",
  },
];

/**
 * Shows the two ways to play the same card.
 *
 * No flipping here: Maledizione and Preghiera are both printed on the front,
 * so switching tabs just moves the spotlight to the right box.
 */
export default function TwoZones() {
  const card = cardById(EXAMPLE_ID);
  const [index, setIndex] = useState(0);
  const [autoplay, setAutoplay] = useState(true);
  const panelRef = useRef<HTMLDivElement>(null);

  const animatePanel = useCallback(async () => {
    const panel = panelRef.current;
    if (!panel) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const { animate } = await import("animejs");
    animate(panel, { opacity: [0, 1], y: [10, 0], duration: 480, ease: "out(3)" });
  }, []);

  const goTo = useCallback(
    (i: number) => {
      setIndex(i);
      setAutoplay(false);
      void animatePanel();
    },
    [animatePanel]
  );

  useEffect(() => {
    if (!autoplay) return;
    const id = window.setInterval(() => {
      setIndex((i) => (i + 1) % ZONES.length);
      void animatePanel();
    }, AUTOPLAY_MS);
    return () => window.clearInterval(id);
  }, [autoplay, animatePanel]);

  if (!card) return null;
  const zone = ZONES[index];
  const isPrayer = zone.key === "prayer";
  const effect = isPrayer ? card.prayer.text : card.curse;
  const typeEntry = findTerm(card.prayer.type);

  return (
    <div className={styles.block}>
      <div className={styles.stage}>
        <ToonCard
          src={cardImage(card.id)}
          form={card.form}
          name={card.name}
          zone={zone.key}
          showFlip={false}
        >
          <Image
            src={cardImage(card.id)}
            alt={`${card.name} — carta di Bless`}
            width={CARD_WIDTH}
            height={CARD_HEIGHT}
            sizes="(max-width: 700px) 60vw, 280px"
            placeholder="blur"
            blurDataURL={card.blurDataURL}
            loading="lazy"
            draggable={false}
          />
        </ToonCard>
      </div>

      <div className={styles.side}>
        <div className={styles.tabs} role="tablist" aria-label="Modi di giocare la carta">
          {ZONES.map((z, i) => (
            <button
              key={z.key}
              type="button"
              role="tab"
              id={`tab-${z.key}`}
              aria-selected={i === index}
              aria-controls={`panel-${z.key}`}
              className={`${styles.tab} ${i === index ? styles.tabActive : ""}`}
              onClick={() => goTo(i)}
            >
              {z.label}
            </button>
          ))}
        </div>

        <div
          className={styles.panel}
          ref={panelRef}
          role="tabpanel"
          id={`panel-${zone.key}`}
          aria-labelledby={`tab-${zone.key}`}
        >
          <h3 className={styles.title}>{zone.title}</h3>
          <p className={styles.effect}>«{effect}»</p>
          <p className={styles.note}>{zone.note}</p>

          {/* Prayer type (how long it lasts / how it works), shown next to
              the effect. */}
          {isPrayer && (
            <p className={styles.type} data-type={card.prayer.type}>
              <span className={styles.typeIcon}>
                <PrayerTypeIcon type={card.prayer.type} size={18} />
              </span>
              <span>
                È una Preghiera di tipo <strong>{card.prayer.type}</strong>
                {typeEntry &&
                  `: ${typeEntry.definition.replace(/^Tipo di Preghiera[^:]*:\s*/, "")}`}
              </span>
            </p>
          )}
        </div>

        <p className={styles.source}>
          Esempio: {card.name} —{" "}
          <span className="mono">
            {card.eye}/{card.karma}
          </span>{" "}
          · {card.form}. Il riflettore sulla carta indica il riquadro che stai
          leggendo: la carta resta a faccia in su, i due effetti sono stampati
          insieme.
        </p>
      </div>
    </div>
  );
}
