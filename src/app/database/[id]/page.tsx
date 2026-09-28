import type { Metadata, Viewport } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import FormEmblem from "@/components/FormEmblem";
import GameText from "@/components/GameText";
import JsonLd from "@/components/JsonLd";
import PrayerTypeIcon from "@/components/PrayerTypeIcon";
import ToonCard from "@/components/three/ToonCard";
import {
  CARDS,
  CARD_HEIGHT,
  CARD_WIDTH,
  FORM_THEME,
  cardById,
  cardImage,
  type Card,
  type Form,
} from "@/data/cards";
import { findTerm } from "@/data/glossary";
import { OG_BASE, SITE } from "@/lib/site";
import styles from "./page.module.css";

type Props = { params: Promise<{ id: string }> };

export function generateStaticParams() {
  return CARDS.map((c) => ({ id: String(c.id) }));
}

/** Tagline under the card name, one per Form. It's about the Form itself,
    not abilities, since those (e.g. Rivalità) only apply to some cards. */
const REGISTER: Record<Form, { badge: string; motto: string }> = {
  Luce: {
    badge: "Forma Luce",
    motto: "Combatte allo scoperto, dalla parte della Luce.",
  },
  Ombra: {
    badge: "Forma Ombra",
    motto: "Lavora da sotto il tavolo, dalla parte dell'Ombra.",
  },
  Duale: {
    badge: "Forma Duale",
    motto: "Luce e Ombra nella stessa carta: vale come entrambe le Forme.",
  },
};

function describe(c: Card) {
  return `${c.name}: Occhio ${c.eye}, Karma ${c.karma}, Forma ${c.form}. Maledizione: ${c.curse} Preghiera (${c.prayer.type}): ${c.prayer.text}`
    .replace(/\s+/g, " ")
    .slice(0, 300);
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const card = cardById(Number(id));
  if (!card) return { title: "Carta non trovata" };

  const title = `${card.name} · Carta di Bless`;
  const description = describe(card);

  // The OG image comes from `opengraph-image.tsx` in this folder.
  return {
    title: { absolute: title },
    description,
    alternates: { canonical: `/database/${card.id}` },
    openGraph: {
      ...OG_BASE,
      type: "article",
      url: `/database/${card.id}`,
      title,
      description,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

/* Match the browser bar to the Form background, otherwise it stays gold on
   a lavender page. */
export async function generateViewport({ params }: Props): Promise<Viewport> {
  const { id } = await params;
  const card = cardById(Number(id));
  return { themeColor: card ? FORM_THEME[card.form].background : "#f0e4cb" };
}

export default async function CardPage({ params }: Props) {
  const { id } = await params;
  const number = Number(id);
  const card = cardById(number);
  if (!card) notFound();

  const previous = cardById(number === 1 ? CARDS.length : number - 1)!;
  const next = cardById(number === CARDS.length ? 1 : number + 1)!;
  const register = REGISTER[card.form];
  const type = card.prayer.type;
  const typeEntry = findTerm(type);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: SITE.url },
      { "@type": "ListItem", position: 2, name: "Carte", item: `${SITE.url}/database` },
      {
        "@type": "ListItem",
        position: 3,
        name: card.name,
        item: `${SITE.url}/database/${card.id}`,
      },
    ],
  };

  return (
    <div className={styles.page} data-form={card.form} data-form-theme={card.form}>
      <JsonLd data={jsonLd} />

      {/* Hatched background in the Form colour. */}
      <div className={styles.hatching} aria-hidden="true" />

      <div className={`wrap ${styles.content}`}>
        <nav aria-label="Percorso" className={styles.breadcrumbs}>
          <Link href="/database" className={styles.back}>
            ← Tutte le carte
          </Link>
          <span className={`mono ${styles.number}`}>
            {String(card.id).padStart(2, "0")} / {CARDS.length}
          </span>
        </nav>

        <article className={styles.layout}>
          <div className={styles.imageColumn}>
            <ToonCard src={cardImage(card.id)} form={card.form} name={card.name}>
              <Image
                src={cardImage(card.id)}
                alt={`${card.name} — carta di Bless`}
                width={CARD_WIDTH}
                height={CARD_HEIGHT}
                sizes="(max-width: 900px) 84vw, 420px"
                placeholder="blur"
                blurDataURL={card.blurDataURL}
                priority
              />
            </ToonCard>
          </div>

          <div className={styles.textColumn}>
            {/* Badge, name, tagline and stats all in one row so the effects
                still make it above the fold on short screens. */}
            <header className={styles.header}>
              <p className={styles.badge}>
                <span className={styles.emblem} aria-hidden="true">
                  <FormEmblem form={card.form} size={22} />
                </span>
                {register.badge}
              </p>

              <h1 className={styles.name}>{card.name}</h1>
              <p className={styles.motto}>{register.motto}</p>

              {/* Same layout as the card: Occhio top left, Karma top
                  right. */}
              <div className={styles.tokens}>
                <div className={styles.token} data-token="eye">
                  <span className={styles.digit}>{card.eye}</span>
                  <div>
                    <p className={styles.tokenName}>Occhio</p>
                    <p className={styles.tokenNote}>Forza negli scontri</p>
                  </div>
                </div>
                <div className={styles.token} data-token="karma">
                  <span className={styles.digit}>{card.karma}</span>
                  <div>
                    <p className={styles.tokenName}>Karma</p>
                    <p className={styles.tokenNote}>Punti Vittoria quando Blessa</p>
                  </div>
                </div>
              </div>
            </header>

            <p className={styles.choice}>
              Una carta sola, due modi di giocarla. Quando la cali scegli la
              zona: come <b>Maledizione</b> scende in campo e combatte, come{" "}
              <b>Preghiera</b> resta fuori dagli scontri e piega le regole del
              tavolo. Mai tutte e due insieme, e dalla zona scelta non si
              torna indietro.
            </p>

            <div className={styles.modes}>
              <section className={styles.mode} data-mode="curse">
                <header className={styles.band}>
                  <span className={styles.bandIcon} aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 5.5 12 3l8 2.5v6.2c0 4.4-3.1 7.6-8 9.3-4.9-1.7-8-4.9-8-9.3Z" />
                      <path d="m9 11 6 5M15 11l-6 5" />
                    </svg>
                  </span>
                  <h2 className={styles.bandTitle}>Zona Maledizione</h2>
                  <p className={styles.bandNote}>Combatte</p>
                </header>

                <p className={styles.body}>
                  <GameText text={card.curse} />
                </p>

                <p className={styles.modeNote}>
                  Sta in campo con l&apos;effetto sempre attivo. Attacca, può essere
                  attaccata e, quando Blessa, ti fa <b>{card.karma}</b> Punti
                  Vittoria.
                </p>
              </section>

              <section className={styles.mode} data-mode="prayer" data-type={type}>
                <header className={styles.band}>
                  <span className={styles.bandIcon} aria-hidden="true">
                    <PrayerTypeIcon type={type} size={19} />
                  </span>
                  <h2 className={styles.bandTitle}>Zona Preghiera</h2>
                  <p className={styles.bandNote}>{type}</p>
                </header>

                <p className={styles.body}>
                  <GameText text={card.prayer.text} />
                </p>

                {typeEntry && (
                  <p className={styles.typeDefinition}>
                    <b>{type}</b> — {typeEntry.definition}
                  </p>
                )}

                <p className={styles.modeNote}>
                  Non attacca e non può essere attaccata: non fa punti, cambia le
                  regole del tavolo.
                </p>
              </section>
            </div>

            <p className={styles.help}>
              I termini sottolineati portano la definizione dal regolamento.
            </p>
          </div>
        </article>

        <nav aria-label="Altre carte" className={styles.pager}>
          <Link href={`/database/${previous.id}`} className={styles.neighbor}>
            <span className={styles.dir}>← Precedente</span>
            <span className={styles.neighborName}>{previous.name}</span>
          </Link>
          <Link href={`/database/${next.id}`} className={styles.neighbor} data-next>
            <span className={styles.dir}>Successiva →</span>
            <span className={styles.neighborName}>{next.name}</span>
          </Link>
        </nav>
      </div>
    </div>
  );
}
