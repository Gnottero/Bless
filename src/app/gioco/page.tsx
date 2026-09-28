import type { Metadata } from "next";
import Link from "next/link";
import ExternalLink from "@/components/ExternalLink";
import { OG_BASE, OG_IMAGE, PRODUCT } from "@/lib/site";
import PlayLauncher from "./PlayLauncher";
import styles from "./page.module.css";

/** Launcher for the game now hosted directly inside the official site. */

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
          <Link href="/rules" className="btn btn--ghost btn--sm">
            Leggi prima le regole
          </Link>
        </div>
      </header>

      <PlayLauncher />

      <section className={`panel ${styles.buy}`}>
        <div>
          <h2 className={styles.h2}>Ti è piaciuto?</h2>
          <p className={styles.buyText}>
            La scatola di {PRODUCT.name} contiene le stesse {PRODUCT.cards} carte,
            illustrate e pronte per il tavolo.
          </p>
        </div>
        <ExternalLink href={PRODUCT.shop} className="btn">
          Acquista a {PRODUCT.price} €<span aria-hidden="true">↗</span>
        </ExternalLink>
      </section>
    </div>
  );
}
