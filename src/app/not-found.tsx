import type { Metadata } from "next";
import Link from "next/link";
import styles from "@/components/LegalPage.module.css";

/* Without this Next's default 404 also picks up the layout metadata, and you
   end up with two <title>s and two conflicting robots tags ("noindex" and
   "index, follow"). */
export const metadata: Metadata = {
  title: "Pagina non trovata",
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return (
    <div className={`wrap ${styles.page}`}>
      <p className="eyebrow">Errore 404</p>
      <h1 className={styles.title}>Questa carta non è nel mazzo</h1>
      <p className="lede">
        La pagina che cerchi non esiste o è stata spostata.
      </p>
      <p className={styles.note}>
        <Link href="/" className="btn">
          Torna alla home
        </Link>{" "}
        <Link href="/database" className="btn btn--ghost">
          Sfoglia le carte
        </Link>
      </p>
    </div>
  );
}
