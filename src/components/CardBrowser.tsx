"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import {
  CARDS,
  CARD_HEIGHT,
  CARD_WIDTH,
  FORMS,
  PRAYER_TYPES,
  cardImage,
  type Card,
  type Form,
  type PrayerType,
} from "@/data/cards";
import { normalize } from "@/lib/text";
import styles from "./CardBrowser.module.css";

/* Filters live in the URL so searches can be shared. Param names and values
   are user-facing, so they're in Italian. */
const PARAM = { query: "q", form: "forma", type: "tipo", sort: "ordine" } as const;

/** Keyed by the `ordine` param value. */
const SORTS = {
  numero: { label: "Numero", cmp: (a: Card, b: Card) => a.id - b.id },
  nome: { label: "Nome", cmp: (a: Card, b: Card) => a.name.localeCompare(b.name, "it") },
  occhio: {
    label: "Occhio ↓",
    cmp: (a: Card, b: Card) => b.eye - a.eye || a.id - b.id,
  },
  karma: {
    label: "Karma ↓",
    cmp: (a: Card, b: Card) => b.karma - a.karma || a.id - b.id,
  },
} as const;

type SortKey = keyof typeof SORTS;
const DEFAULT_SORT: SortKey = "numero";

/** Parses a comma-separated param into an array. */
function splitList(value: string | null): string[] {
  return value?.split(",").filter(Boolean) ?? [];
}

export default function CardBrowser() {
  const router = useRouter();
  const params = useSearchParams();

  const urlQuery = params.get(PARAM.query) ?? "";
  const formsParam = params.get(PARAM.form) ?? "";
  const typesParam = params.get(PARAM.type) ?? "";
  const sortParam = params.get(PARAM.sort) ?? DEFAULT_SORT;
  const sort: SortKey = sortParam in SORTS ? (sortParam as SortKey) : DEFAULT_SORT;

  const forms = useMemo(() => splitList(formsParam) as Form[], [formsParam]);
  const types = useMemo(() => splitList(typesParam) as PrayerType[], [typesParam]);

  const [q, setQ] = useState(urlQuery);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const deferredQ = useDeferredValue(q);
  const firstRender = useRef(true);

  function replaceParams(update: (p: URLSearchParams) => void) {
    const p = new URLSearchParams(params.toString());
    update(p);
    router.replace(p.toString() ? `/database?${p}` : "/database", { scroll: false });
  }

  function setParam(key: string, value: string | null) {
    replaceParams((p) => (value ? p.set(key, value) : p.delete(key)));
  }

  function toggle(key: string, value: string) {
    const current = splitList(params.get(key));
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    setParam(key, next.length ? next.join(",") : null);
  }

  // Keep the search box in local state and debounce the URL update, so we
  // don't push a history entry per keystroke. Only `q` needs this, the
  // other params are read fresh on every render anyway.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const t = window.setTimeout(() => setParam(PARAM.query, q || null), 300);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => setQ(urlQuery), [urlQuery]);

  const results = useMemo(() => {
    const query = normalize(deferredQ.trim());
    return CARDS.filter((c) => {
      if (forms.length && !forms.includes(c.form)) return false;
      if (types.length && !types.includes(c.prayer.type)) return false;
      if (!query) return true;
      return normalize(`${c.name} ${c.curse} ${c.prayer.text} ${c.prayer.type}`).includes(query);
    }).sort(SORTS[sort].cmp);
  }, [deferredQ, forms, types, sort]);

  const activeFilters = forms.length + types.length + (urlQuery ? 1 : 0);

  return (
    <>
      <div className={styles.bar}>
        <div className={styles.field}>
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Cerca per nome o testo dell'effetto…"
            aria-label="Cerca fra le carte di Bless"
            className={styles.input}
          />
        </div>

        <button
          type="button"
          className={styles.filtersToggle}
          aria-expanded={filtersOpen}
          aria-controls="card-filters"
          onClick={() => setFiltersOpen((v) => !v)}
        >
          Filtri
          {activeFilters > 0 && <span className={styles.badge}>{activeFilters}</span>}
        </button>
      </div>

      <div id="card-filters" className={styles.filters} data-open={filtersOpen}>
        <fieldset className={styles.group}>
          <legend className={styles.legend}>Forma</legend>
          <div className={styles.chips}>
            {FORMS.map((f) => (
              <button
                key={f}
                type="button"
                className={styles.chip}
                data-form={f}
                aria-pressed={forms.includes(f)}
                onClick={() => toggle(PARAM.form, f)}
              >
                {f}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className={styles.group}>
          <legend className={styles.legend}>Tipo di Preghiera</legend>
          <div className={styles.chips}>
            {PRAYER_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                className={styles.chip}
                aria-pressed={types.includes(t)}
                onClick={() => toggle(PARAM.type, t)}
              >
                {t}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className={styles.group}>
          <legend className={styles.legend}>Ordina per</legend>
          <div className={styles.chips}>
            {(Object.keys(SORTS) as SortKey[]).map((k) => (
              <button
                key={k}
                type="button"
                className={styles.chip}
                aria-pressed={sort === k}
                onClick={() => setParam(PARAM.sort, k === DEFAULT_SORT ? null : k)}
              >
                {SORTS[k].label}
              </button>
            ))}
          </div>
        </fieldset>
      </div>

      <div className={styles.count}>
        <p className="mono" aria-live="polite">
          {results.length} {results.length === 1 ? "carta" : "carte"} su {CARDS.length}
        </p>
        {activeFilters > 0 && (
          <Link href="/database" className={styles.reset} scroll={false}>
            Azzera filtri
          </Link>
        )}
      </div>

      {results.length === 0 ? (
        <p className={styles.empty}>
          Nessuna carta corrisponde alla ricerca. Prova con un termine di gioco come
          «Rivalità», «Blessa» o «Occhio».
        </p>
      ) : (
        <ul className={styles.grid}>
          {results.map((c) => (
            <li key={c.id}>
              <Link href={`/database/${c.id}`} className={styles.card} data-form={c.form}>
                <span className={styles.figure}>
                  <Image
                    src={cardImage(c.id)}
                    alt=""
                    width={CARD_WIDTH}
                    height={CARD_HEIGHT}
                    sizes="(max-width: 700px) 46vw, (max-width: 1100px) 30vw, 200px"
                    placeholder="blur"
                    blurDataURL={c.blurDataURL}
                    loading="lazy"
                  />
                </span>
                <span className={styles.name}>{c.name}</span>
                <span className={`mono ${styles.meta}`}>
                  <span className={styles.stat} title="Occhio">
                    {c.eye}
                  </span>
                  <span aria-hidden="true">/</span>
                  <span className={styles.stat} title="Karma">
                    {c.karma}
                  </span>
                  <span className={styles.form}>{c.form}</span>
                </span>
                <span className="sr-only">
                  Occhio {c.eye}, Karma {c.karma}, Forma {c.form}, Preghiera{" "}
                  {c.prayer.type}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
