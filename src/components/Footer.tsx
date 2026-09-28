import Image from "next/image";
import Link from "next/link";
import ExternalLink from "./ExternalLink";
import SocialLinks from "./SocialLinks";
import { PRODUCT, RESOURCES, SITE, socialHref } from "@/lib/site";
import styles from "./Footer.module.css";

type FooterLink = { label: string; href: string; external?: boolean };

const COLUMNS: { title: string; links: FooterLink[] }[] = [
  {
    title: "Gioco",
    links: [
      { label: "Gioca contro il Bot", href: "/gioco" },
      { label: "Tutte le carte", href: "/database" },
      { label: "Regolamento", href: "/rules" },
      { label: "Acquista il mazzo", href: PRODUCT.shop, external: true },
    ],
  },
  {
    title: "Community",
    links: [
      { label: "Discord", href: socialHref("Discord"), external: true },
      { label: "Instagram", href: socialHref("Instagram"), external: true },
      { label: "Video tutorial", href: RESOURCES.video, external: true },
    ],
  },
  {
    title: "Legale",
    links: [
      { label: "Privacy policy", href: "/privacy" },
      { label: "Cookie policy", href: "/cookie" },
      { label: "Termini e condizioni", href: "/termini" },
      { label: "Contatti", href: "/contatti" },
    ],
  },
];

export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className={styles.footer}>
      <div className={`wrap ${styles.inner}`}>
        <div className={styles.brand}>
          <Link href="/" aria-label="Bless — vai alla home" className={styles.logo}>
            <Image
              src="/logo-footer.png"
              alt="Bless"
              width={237}
              height={237}
              sizes="72px"
            />
          </Link>
          <p className={styles.claim}>
            Un duello fulmineo per due giocatori. Un solo mazzo, {PRODUCT.cards} carte,
            nessuna partita uguale.
          </p>
          <SocialLinks />
        </div>

        <nav className={styles.columns} aria-label="Navigazione secondaria">
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h2 className={styles.colTitle}>{col.title}</h2>
              <ul className={styles.colList}>
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.external ? (
                      <ExternalLink href={l.href} className={styles.colLink}>
                        {l.label}
                        <span className={styles.ext} aria-hidden="true">
                          ↗
                        </span>
                      </ExternalLink>
                    ) : (
                      <Link href={l.href} className={styles.colLink}>
                        {l.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </div>

      <div className={`wrap ${styles.base}`}>
        <p className="mono">
          © {year} {SITE.studio} — {SITE.name}
        </p>
        <p className="mono">Vincitore del premio «{PRODUCT.award}»</p>
      </div>
    </footer>
  );
}
