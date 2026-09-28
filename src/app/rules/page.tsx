import type { Metadata } from "next";
import ExternalLink from "@/components/ExternalLink";
import JsonLd from "@/components/JsonLd";
import RulesReader from "@/components/RulesReader";
import YouTubeLite from "@/components/YouTubeLite";
import { OG_BASE, OG_IMAGE, RESOURCES, SITE } from "@/lib/site";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: { absolute: "Regolamento di Bless" },
  description:
    "Il regolamento completo di Bless, consultabile e cercabile: turno, azioni, scontri, Blessare, Turni Finali e glossario dei termini di gioco.",
  alternates: { canonical: "/rules" },
  openGraph: {
    ...OG_BASE,
    url: "/rules",
    title: "Regolamento di Bless",
    description:
      "Turno, azioni, scontri, Blessare e glossario: tutte le regole di Bless in una pagina cercabile.",
    images: [{ ...OG_IMAGE, alt: "Regolamento di Bless" }],
  },
  twitter: { title: "Regolamento di Bless", images: [OG_IMAGE.url] },
};

const PDFS = [
  {
    ...RESOURCES.fullRulebook,
    name: "Rulebook completo",
    note: "Tutte le regole, esempi illustrati e glossario.",
  },
  {
    ...RESOURCES.quickRulebook,
    name: "Guida rapida",
    note: "Una pagina per iniziare subito a giocare.",
  },
];

export default function RulesPage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "HowTo",
    name: "Come si gioca a Bless",
    description:
      "Le regole del gioco di carte Bless per due giocatori: turno, azioni, scontri e condizioni di vittoria.",
    inLanguage: "it",
    url: `${SITE.url}/rules`,
    step: [
      { "@type": "HowToStep", name: "Preparazione", text: "Mischiate l'unico mazzo, date 4 carte a testa, scegliete il Primo Giocatore ed effettuate un Mulligan." },
      { "@type": "HowToStep", name: "Il turno", text: "Inizio Turno, Fase Principale con 3 Azioni, Fine Turno con rimozione della Stasi e Mulligan." },
      { "@type": "HowToStep", name: "Lo scontro", text: "Si applicano gli effetti sull'Occhio, si confrontano i valori, vince l'Occhio maggiore e si aggiornano gli stati Pura e Corrotta." },
      { "@type": "HowToStep", name: "Vincere", text: "Blessando si guadagnano Punti Vittoria pari al Karma. Alla 5ª carta nell'Altare iniziano i Turni Finali: vince chi ha più Punti Vittoria." },
    ],
  };

  return (
    <div className={`wrap ${styles.page}`}>
      <JsonLd data={jsonLd} />

      <header className={styles.header}>
        <p className="eyebrow">Regolamento</p>
        <h1 className={styles.title}>Le regole di Bless</h1>
        <p className="lede">
          Il regolamento completo del mazzo LuceOmbra, consultabile e cercabile. I
          termini sottolineati portano la definizione dal glossario.
        </p>
      </header>

      <RulesReader />

      <section className={styles.resources} aria-labelledby="risorse">
        <h2 id="risorse" className={styles.resourcesTitle}>
          Da scaricare e da guardare
        </h2>

        <div className={styles.pdfList}>
          {PDFS.map((p) => (
            <ExternalLink key={p.name} href={p.href} className={`panel ${styles.pdf}`}>
              <span className={styles.pdfTag}>
                {p.format} · {p.size}
              </span>
              <span className={styles.pdfName}>{p.name}</span>
              <span className={styles.pdfNote}>{p.note}</span>
              <span className={styles.pdfAction}>Apri il PDF ↗</span>
            </ExternalLink>
          ))}
        </div>

        <div className={styles.video}>
          <YouTubeLite id={RESOURCES.videoId} title="Bless — come si gioca" />
        </div>
      </section>
    </div>
  );
}
