"use client";

import { useEffect, useMemo, useState } from "react";
import GameText from "./GameText";
import { SECTIONS, type Block, type Section } from "@/data/rules";
import { GLOSSARY, glossaryAnchor } from "@/data/glossary";
import { normalize } from "@/lib/text";
import styles from "./RulesReader.module.css";

/** Glossary anchor. Shows up in URLs, so it's in Italian. */
const GLOSSARY_ID = "glossario";

function sectionText(s: Section) {
  return normalize(
    [
      s.title,
      s.summary,
      ...s.blocks.flatMap((b) => ("items" in b ? b.items : [b.text])),
    ].join(" ")
  );
}

/** Computed once, the rules never change at runtime. */
const SECTION_TEXTS = Object.fromEntries(SECTIONS.map((s) => [s.id, sectionText(s)]));

const TOC_ENTRIES = [
  ...SECTIONS.map((s) => ({ id: s.id, title: s.title })),
  { id: GLOSSARY_ID, title: "Glossario" },
];

function RuleBlock({ block }: { block: Block }) {
  if (block.type === "p" || block.type === "note") {
    return (
      <p className={block.type === "p" ? styles.paragraph : styles.note}>
        <GameText text={block.text} />
      </p>
    );
  }
  const List = block.type === "steps" ? "ol" : "ul";
  return (
    <List className={block.type === "steps" ? styles.steps : styles.list}>
      {block.items.map((item, j) => (
        <li key={j}>
          <GameText text={item} />
        </li>
      ))}
    </List>
  );
}

export default function RulesReader() {
  const [q, setQ] = useState("");
  const [activeId, setActiveId] = useState<string>(SECTIONS[0].id);

  const query = normalize(q.trim());
  const visible = useMemo(() => {
    if (!query) return new Set(SECTIONS.map((s) => s.id));
    return new Set(SECTIONS.filter((s) => SECTION_TEXTS[s.id].includes(query)).map((s) => s.id));
  }, [query]);

  const visibleGlossary = useMemo(() => {
    if (!query) return GLOSSARY;
    return GLOSSARY.filter((v) => normalize(`${v.term} ${v.definition}`).includes(query));
  }, [query]);

  // Scrollspy: highlight the current section in the table of contents.
  useEffect(() => {
    const targets = TOC_ENTRIES.map((v) => document.getElementById(v.id)).filter(
      (el): el is HTMLElement => Boolean(el)
    );
    if (!targets.length) return;

    const obs = new IntersectionObserver(
      (entries) => {
        const topmost = entries
          .filter((v) => v.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (topmost) setActiveId(topmost.target.id);
      },
      { rootMargin: "-88px 0px -65% 0px", threshold: 0 }
    );
    targets.forEach((t) => obs.observe(t));
    return () => obs.disconnect();
  }, [visible.size]);

  const noResults = query && visible.size === 0 && visibleGlossary.length === 0;

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <nav aria-label="Indice del regolamento">
          <p className={styles.tocTitle}>Indice</p>
          <ol className={styles.toc}>
            {TOC_ENTRIES.map((v) => {
              const dimmed = Boolean(query) && v.id !== GLOSSARY_ID && !visible.has(v.id);
              return (
                <li key={v.id}>
                  <a
                    href={`#${v.id}`}
                    className={styles.tocLink}
                    data-active={activeId === v.id}
                    data-dimmed={dimmed}
                    aria-current={activeId === v.id ? "true" : undefined}
                  >
                    {v.title}
                  </a>
                </li>
              );
            })}
          </ol>
        </nav>
      </aside>

      <div>
        <div className={styles.search}>
          <label htmlFor="rules-search" className="sr-only">
            Cerca nel regolamento
          </label>
          <input
            id="rules-search"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Cerca nel regolamento: «Stasi», «pareggio», «Limite»…"
            className={styles.input}
          />
          {query && (
            <p className={`mono ${styles.resultCount}`} aria-live="polite">
              {visible.size} {visible.size === 1 ? "sezione" : "sezioni"} ·{" "}
              {visibleGlossary.length} voci di glossario
            </p>
          )}
        </div>

        {noResults && (
          <p className={styles.empty}>
            Nessun risultato per «{q}». Prova con un termine di gioco: Occhio, Karma,
            Blessare, Stasi, Altare.
          </p>
        )}

        {SECTIONS.filter((s) => visible.has(s.id)).map((s) => (
          <section key={s.id} id={s.id} className={styles.section}>
            <h2 className={styles.h2}>{s.title}</h2>
            <p className={styles.summary}>{s.summary}</p>
            {s.blocks.map((b, i) => (
              <RuleBlock key={i} block={b} />
            ))}
          </section>
        ))}

        <section id={GLOSSARY_ID} className={styles.section}>
          <h2 className={styles.h2}>Glossario</h2>
          <p className={styles.summary}>Tutti i termini di gioco, in ordine.</p>
          <dl className={styles.glossary}>
            {visibleGlossary.map((v) => (
              <div key={v.term} id={glossaryAnchor(v.term)} className={styles.entry}>
                <dt>
                  {v.term}
                  <span className={styles.category}>{v.category}</span>
                </dt>
                <dd>{v.definition}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </div>
  );
}
