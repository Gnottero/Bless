import Image from "next/image";
import { CARDS, CARD_HEIGHT, CARD_WIDTH, cardImage } from "@/data/cards";
import styles from "./CardMarquee.module.css";

/**
 * Endless scrolling strip of card art. Pure CSS: the row is rendered twice
 * and a single keyframe slides it. Decorative, so it's hidden from screen
 * readers.
 */
export default function CardMarquee() {
  const row = CARDS.filter((c) => c.id % 4 === 1);
  const doubled = [...row, ...row];

  return (
    <div className={styles.ribbon} aria-hidden="true">
      <div className={styles.track}>
        {doubled.map((c, i) => (
          <div key={`${c.id}-${i}`} className={styles.slot} data-form={c.form}>
            <Image
              src={cardImage(c.id)}
              alt=""
              width={CARD_WIDTH}
              height={CARD_HEIGHT}
              sizes="140px"
              placeholder="blur"
              blurDataURL={c.blurDataURL}
              loading="lazy"
              draggable={false}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
