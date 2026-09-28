import type { Metadata } from "next";
import Link from "next/link";
import ExternalLink from "@/components/ExternalLink";
import type { Form } from "@/data/cards";
import { OG_BASE, OG_IMAGE, PRODUCT, SITE } from "@/lib/site";
import styles from "./page.module.css";

/**
 * Placeholder for the online simulator.
 *
 * The simulator (bot, private rooms, match history) is a separate app and
 * its code isn't in this repo. This page exists because the header, footer,
 * CTAs and sitemap all link to /gioco.
 *
 * TODO: drop the simulator in here once we have it. Header, footer, colours
 * and animations already come from the layout.
 */

const SIMULATOR_URL = "https://www.blesscardgame.com/gioco";

export const metadata: Metadata = {
  title: { absolute: "Gioca a Bless online, gratis · Bless" },
  description:
    "Affronta il Bot o apri una stanza privata e invita un amico. Stesse regole e stessi mazzi del gioco da tavolo, direttamente dal browser.",
  alternates: { canonical: "/gioco" },
  openGraph: {
    ...OG_BASE,
    url: "/gioco",
    title: "Bless · Il tavolo è pronto",
    description:
      "Gioca gratis contro il Bot o invita un altro giocatore in una stanza privata.",
    images: [{ ...OG_IMAGE, alt: "Il tavolo di Bless" }],
  },
  twitter: {
    title: "Bless · Il tavolo è pronto",
    description: "Gioca gratis contro il Bot o invita un altro giocatore.",
    images: [OG_IMAGE.url],
  },
};

const MODES = [
  {
    tag: "Disponibile subito",
    title: "Gioca contro il Bot",
    text:
      "Una partita completa sul tuo dispositivo. Il Bot non vede la tua mano, le tue Cariche o l'ordine del mazzo.",
  },
  {
    tag: "Partita privata 1 contro 1",
    title: "Invita un giocatore",
    text:
      "Crea una stanza, condividi il link e scegliete insieme lo stesso mazzo prima di iniziare.",
  },
];

const DECKS: { name: string; text: string; form: Form }[] = [
  {
    name: "Luce · Ombra",
    text: "Strategia essenziale: Rivalità, Fato, Impatto, Barriera e le Preghiere.",
    form: "Luce",
  },
  {
    name: "Tuono · Sabbia",
    text: "La nuova sfida: Cariche, Marchi, Sigilli, Glifi ed Esordio.",
    form: "Duale",
  },
];

export default function PlayPage() {
  return (
    <div className={`wrap ${styles.page}`}>
      <header className={styles.header}>
        <p className="eyebrow">Simulatore ufficiale</p>
        <h1 className={styles.title}>Il tavolo è pronto.</h1>
        <p className="lede">
          Affronta il Bot oppure apri una stanza privata e invita un amico. Le regole e
          i due mazzi sono gli stessi del gioco da tavolo. Gratis, senza registrazione.
        </p>
        <div className={styles.cta}>
          <ExternalLink href={SIMULATOR_URL} className="btn">
            Apri il simulatore
            <span aria-hidden="true">↗</span>
          </ExternalLink>
          <Link href="/rules" className="btn btn--ghost">
            Leggi prima le regole
          </Link>
        </div>
      </header>

      <section className={styles.block} aria-labelledby="modi">
        <h2 id="modi" className={styles.h2}>
          Due modi di giocare
        </h2>
        <div className={styles.grid} data-reveal-group>
          {MODES.map((m) => (
            <article key={m.title} className={`panel ${styles.tile}`} data-reveal>
              <p className={styles.tag}>{m.tag}</p>
              <h3 className={styles.tileTitle}>{m.title}</h3>
              <p className={styles.tileText}>{m.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.block} aria-labelledby="mazzi">
        <h2 id="mazzi" className={styles.h2}>
          Un solo mazzo per entrambi
        </h2>
        <div className={styles.grid} data-reveal-group>
          {DECKS.map((m) => (
            <article
              key={m.name}
              className={`panel ${styles.tile}`}
              data-form={m.form}
              data-reveal
            >
              <h3 className={styles.tileTitle}>{m.name}</h3>
              <p className={styles.tileText}>{m.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={`panel ${styles.buy}`}>
        <div>
          <h2 className={styles.h2}>Ti è piaciuto?</h2>
          <p className={styles.tileText}>
            La scatola di {PRODUCT.name} contiene le stesse {PRODUCT.cards} carte,
            illustrate e pronte per il tavolo.
          </p>
        </div>
        <ExternalLink href={PRODUCT.shop} className="btn">
          Acquista a {PRODUCT.price} €<span aria-hidden="true">↗</span>
        </ExternalLink>
      </section>

      <p className={styles.footnote}>
        Il simulatore è un&apos;applicazione separata di {SITE.studio}.
      </p>
    </div>
  );
}
