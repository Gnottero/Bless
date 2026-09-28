import type { Metadata } from "next";
import { Suspense } from "react";
import CardBrowser from "@/components/CardBrowser";
import JsonLd from "@/components/JsonLd";
import { CARDS } from "@/data/cards";
import { OG_BASE, OG_IMAGE, SITE } from "@/lib/site";
import styles from "./page.module.css";

const TITLE = `Tutte le carte di Bless (${CARDS.length})`;

export const metadata: Metadata = {
  title: { absolute: TITLE },
  description: `Il database completo delle ${CARDS.length} carte di Bless: cerca per nome o per testo degli effetti, filtra per Forma e per tipo di Preghiera, ordina per Occhio o Karma.`,
  alternates: { canonical: "/database" },
  openGraph: {
    ...OG_BASE,
    url: "/database",
    title: TITLE,
    description:
      "Cerca, filtra e confronta le 62 carte del mazzo LuceOmbra: Occhio, Karma, Forma, Maledizione e Preghiera.",
    images: [{ ...OG_IMAGE, alt: "Le carte di Bless" }],
  },
  twitter: {
    title: TITLE,
    images: [OG_IMAGE.url],
  },
};

export default function DatabasePage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: TITLE,
    url: `${SITE.url}/database`,
    inLanguage: "it",
    isPartOf: { "@type": "WebSite", name: SITE.name, url: SITE.url },
  };

  return (
    <div className={`wrap ${styles.page}`}>
      <JsonLd data={jsonLd} />

      <header className={styles.header}>
        <p className="eyebrow">Database</p>
        <h1 className={styles.title}>Tutte le carte</h1>
        <p className="lede">
          Le {CARDS.length} carte del mazzo LuceOmbra. La notazione{" "}
          <strong className="mono">3/2 — Luce</strong> si legge:{" "}
          <strong>Occhio 3</strong> (la forza negli scontri),{" "}
          <strong>Karma 2</strong> (i Punti Vittoria quando Blessa),{" "}
          <strong>Forma Luce</strong>.
        </p>
      </header>

      <Suspense fallback={<p className="mono">Caricamento del database…</p>}>
        <CardBrowser />
      </Suspense>
    </div>
  );
}
