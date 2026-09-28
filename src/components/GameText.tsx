import { Fragment } from "react";
import Link from "next/link";
import { KNOWN_TERMS, findTerm, glossaryAnchor } from "@/data/glossary";
import styles from "./GameText.module.css";

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Terms are already sorted longest first, so "si corrompe" matches before
// "corrompe".
const TERMS_REGEX = new RegExp(
  `(?<!\\p{L})(${KNOWN_TERMS.map(escapeRegExp).join("|")})(?!\\p{L})`,
  "giu"
);

/**
 * Renders card text with game terms turned into links. Hovering a term shows
 * its definition and clicking it goes to the glossary entry in the rulebook.
 * The tooltip is CSS only (hover + focus), so it works with the keyboard too.
 *
 * On touch devices there's no hover, so tapping would just navigate away.
 * `data-glossary` is what GlossaryTouch looks for to make the first tap open
 * the tooltip instead.
 */
export default function GameText({ text }: { text: string }) {
  // Because of the capturing group, split() puts the matches at odd indexes.
  const pieces = text.split(TERMS_REGEX);

  return (
    <>
      {pieces.map((piece, i) => {
        const entry = i % 2 === 1 ? findTerm(piece) : undefined;
        if (!entry) return <Fragment key={i}>{piece}</Fragment>;
        const anchor = glossaryAnchor(entry.term);
        const tooltipId = `${anchor}-tip-${i}`;
        return (
          <span key={i} className={styles.wrapper}>
            <Link
              href={`/rules#${anchor}`}
              className={styles.term}
              aria-describedby={tooltipId}
              data-glossary=""
            >
              {piece}
            </Link>
            <span role="tooltip" id={tooltipId} className={styles.tooltip}>
              <strong className={styles.tipTitle}>
                {entry.term}
                <span className={styles.tipCategory}>{entry.category}</span>
              </strong>
              {entry.definition}
              <span className={styles.tipLink} aria-hidden="true">
                Apri nel regolamento →
              </span>
            </span>
          </span>
        );
      })}
    </>
  );
}
