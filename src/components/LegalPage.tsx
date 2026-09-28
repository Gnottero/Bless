import type { Metadata } from "next";
import Link from "next/link";
import ExternalLink from "./ExternalLink";
import { PRODUCT, SITE, SOCIAL } from "@/lib/site";
import styles from "./LegalPage.module.css";

export type LegalPageContent = {
  /** Route path, also used for the canonical URL. */
  path: string;
  title: string;
  eyebrow: string;
  intro: string;
  /** What we're still waiting on from the studio. Shown on the page. */
  missing: string[];
};

/** noindex until the real texts are in. */
export function legalMetadata({ path, title, intro }: LegalPageContent): Metadata {
  return {
    title,
    description: intro,
    alternates: { canonical: path },
    robots: { index: false, follow: true },
  };
}

/**
 * Shared layout for the legal pages. The actual texts have to come from the
 * studio, so for now the page just says what's missing (and stays out of the
 * index) rather than showing placeholder legalese.
 */
export default function LegalPage({ title, eyebrow, intro, missing }: LegalPageContent) {
  return (
    <div className={`wrap ${styles.page}`}>
      <p className="eyebrow">{eyebrow}</p>
      <h1 className={styles.title}>{title}</h1>
      <p className="lede">{intro}</p>

      <div className={`panel ${styles.notice}`}>
        <p className={styles.tag}>Testo in preparazione</p>
        <p className={styles.noticeText}>
          Questa pagina è pronta come struttura ma attende il testo definitivo di{" "}
          {SITE.studio}. Nel frattempo non è indicizzata dai motori di ricerca.
        </p>
        <ul className={styles.missingList}>
          {missing.map((v) => (
            <li key={v}>{v}</li>
          ))}
        </ul>
      </div>

      <section className={styles.contacts}>
        <h2 className={styles.h2}>Nel frattempo, dove trovarci</h2>
        <ul className={styles.channels}>
          {SOCIAL.map((s) => (
            <li key={s.name}>
              <ExternalLink href={s.href}>{s.name} ↗</ExternalLink>
            </li>
          ))}
          <li>
            <ExternalLink href={PRODUCT.shop}>Shop {SITE.studio} ↗</ExternalLink>
          </li>
        </ul>
        <p className={styles.note}>
          Gli acquisti sono gestiti dallo shop di {SITE.studio}: condizioni di vendita,
          spedizione e recesso sono quelle indicate sul loro sito.
        </p>
        <Link href="/" className="btn btn--ghost">
          Torna alla home
        </Link>
      </section>
    </div>
  );
}
