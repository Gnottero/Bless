import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import CardMarquee from "@/components/CardMarquee";
import ExternalLink from "@/components/ExternalLink";
import Faq, { QUESTIONS } from "@/components/Faq";
import JsonLd from "@/components/JsonLd";
import YouTubeLite from "@/components/YouTubeLite";
import HeroDeck from "@/components/anim/HeroDeck";
import SplitHeadline from "@/components/anim/SplitHeadline";
import TwoZones from "@/components/anim/TwoZones";
import { CARD_HEIGHT, CARD_WIDTH, cardById, cardImage, type Card, type Form } from "@/data/cards";
import {
  EXPANSION,
  OG_BASE,
  OG_IMAGE,
  PRODUCT,
  RESOURCES,
  SITE,
  STUDIO_ID,
  socialHref,
} from "@/lib/site";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: `${SITE.name} · Il gioco di carte per due giocatori`,
  description:
    "Un duello per due giocatori con un solo mazzo da 62 carte: ogni carta è una Maledizione o una Preghiera. Gioca gratis contro il Bot, poi porta Bless sul tavolo.",
  alternates: { canonical: "/" },
  openGraph: {
    ...OG_BASE,
    url: "/",
    title: "Bless · Un mazzo, due destini",
    description:
      "Gioca gratis contro il Bot e scopri le 62 carte di Bless, il gioco di carte strategico per due giocatori.",
    images: [{ ...OG_IMAGE, alt: "Bless — gioco di carte" }],
  },
  twitter: {
    title: "Bless · Un mazzo, due destini",
    description: "Il gioco di carte strategico per due giocatori. Provalo gratis online.",
    images: [OG_IMAGE.url],
  },
};

const STEPS = [
  {
    n: "01",
    title: "Tre azioni per turno",
    text:
      "Cala una carta, togli la Stasi, attacca con una Maledizione o invoca una Preghiera. Poi peschi, e il turno finisce.",
  },
  {
    n: "02",
    title: "Vince l'Occhio più alto",
    text:
      "Negli scontri conta l'Occhio. Chi perde si Corrompe, e se era già corrotto si spezza e finisce nel Vuoto.",
  },
  {
    n: "03",
    title: "Benedici e fai punti",
    text:
      "Dopo aver spezzato una carta puoi Blessare: la offri al tuo Altare e guadagni Punti Vittoria pari al Karma. Alla quinta carta si va ai Turni Finali.",
  },
];

const FACTS = [
  { k: "Giocatori", v: PRODUCT.players },
  { k: "Durata", v: "30 min" },
  { k: "Età", v: PRODUCT.age },
  { k: "Carte", v: String(PRODUCT.cards) },
];

type Deck = {
  name: string;
  status: string;
  statusKind: "ok" | "pending" | "upcoming";
  text: string;
  form: Form;
  cta: { label: string; href: string; external: boolean };
};

const DECKS: Deck[] = [
  {
    name: "Luce · Ombra",
    status: "In vendita",
    statusKind: "ok",
    text:
      "Il mazzo originale: Rivalità, Fato, Impatto e Barriera. 29 carte Luce, 29 Ombra, 4 Duali.",
    form: "Luce",
    cta: { label: `Acquista a ${PRODUCT.price} €`, href: PRODUCT.shop, external: true },
  },
  {
    name: "Tuono · Sabbia",
    status: "Solo digitale",
    statusKind: "pending",
    text:
      "La nuova sfida: Cariche, Marchi, Sigilli, Glifi ed Esordio. Giocabile nel simulatore, scatola non ancora in vendita.",
    form: "Duale",
    cta: { label: "Provalo nel simulatore", href: "/gioco", external: false },
  },
  {
    name: EXPANSION.shortTitle,
    status: EXPANSION.status,
    statusKind: "upcoming",
    text: EXPANSION.text,
    form: "Ombra",
    cta: { label: "Seguine l'uscita", href: EXPANSION.href, external: true },
  },
];

const PREVIEW_IDS = [1, 12, 31, 42, 48, 61];

export default function Home() {
  const preview = PREVIEW_IDS.map(cardById).filter((c): c is Card => Boolean(c));

  /* The expansion isn't listed here on purpose: Google flags a Product/Offer
     without a price, and marking it as PreOrder wouldn't be true. Add it
     once there's a real price and availability. */
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "Game",
      name: SITE.name,
      alternateName: PRODUCT.name,
      url: SITE.url,
      description: SITE.description,
      image: `${SITE.url}${OG_IMAGE.url}`,
      inLanguage: "it",
      genre: ["Gioco di carte", "Strategia"],
      numberOfPlayers: { "@type": "QuantitativeValue", value: 2 },
      typicalAgeRange: "12-",
      publisher: { "@id": STUDIO_ID },
      award: PRODUCT.award,
      gameItem: { "@type": "Thing", name: `Mazzo da ${PRODUCT.cards} carte` },
    },
    {
      "@context": "https://schema.org",
      "@type": "Product",
      name: PRODUCT.name,
      description:
        "Gioco di carte strategico per due giocatori con un unico mazzo da 62 carte uniche.",
      image: `${SITE.url}/img/scatola.webp`,
      brand: { "@type": "Brand", name: SITE.studio },
      award: PRODUCT.award,
      offers: {
        "@type": "Offer",
        price: String(PRODUCT.price),
        priceCurrency: PRODUCT.currency,
        availability: "https://schema.org/InStock",
        url: PRODUCT.shop,
      },
    },
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: QUESTIONS.map((d) => ({
        "@type": "Question",
        name: d.q,
        acceptedAnswer: { "@type": "Answer", text: d.a },
      })),
    },
  ];

  return (
    <>
      <JsonLd data={jsonLd} />

      {/* ------------------------------ hero ------------------------------ */}
      <section className={styles.hero}>
        <div className={`wrap ${styles.heroInner}`}>
          <div className={styles.heroText}>
            <p className={`eyebrow ${styles.award}`}>{PRODUCT.award}</p>
            <SplitHeadline text="Un mazzo. Due destini." />
            <p className="lede">
              Bless è un duello per due giocatori che pescano dallo{" "}
              <strong>stesso mazzo</strong>. Ogni carta è due scelte: giocala come{" "}
              <strong>Maledizione</strong> per combattere, o come{" "}
              <strong>Preghiera</strong> per ribaltare il tavolo.
            </p>
            <div className={styles.cta}>
              <Link href="/gioco" className="btn">
                Gioca gratis contro il Bot
              </Link>
              <ExternalLink href={PRODUCT.shop} className="btn btn--ghost">
                Acquista il mazzo · {PRODUCT.price} €
                <span aria-hidden="true">↗</span>
              </ExternalLink>
            </div>
            <dl className={styles.facts}>
              {FACTS.map((d) => (
                <div key={d.k}>
                  <dt>{d.k}</dt>
                  <dd className="mono">{d.v}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className={styles.heroDeck}>
            <HeroDeck />
            <p className={styles.hint}>
              Trascina una carta per aprirla nel database
            </p>
          </div>
        </div>
      </section>

      <CardMarquee />

      {/* --------------------------- how to play --------------------------- */}
      <section className="section" id="come-si-gioca">
        <div className="wrap">
          <p className="eyebrow">Come si gioca</p>
          <h2 className="section-title">Tre azioni, un Altare, cinque carte per vincere.</h2>
          <p className="lede">
            Niente costruzione del mazzo, niente carte da rincorrere per stare al
            passo: si apre la scatola e si gioca. La profondità sta nelle scelte,
            non nel setup.
          </p>

          <ol className={styles.steps} data-reveal-group>
            {STEPS.map((p) => (
              <li key={p.n} className={`panel ${styles.step}`} data-reveal>
                <span className={styles.stepNumber}>{p.n}</span>
                <h3 className={styles.stepTitle}>{p.title}</h3>
                <p className={styles.stepText}>{p.text}</p>
              </li>
            ))}
          </ol>

          <div className={styles.twoZones} data-reveal>
            <TwoZones />
          </div>

          <div className={styles.video} data-reveal>
            <YouTubeLite id={RESOURCES.videoId} title="Bless — come si gioca" />
          </div>
        </div>
      </section>

      {/* ----------------------------- product ----------------------------- */}
      <section className={`section ${styles.product}`} id="scatola">
        <div className={`wrap ${styles.productInner}`}>
          <div className={styles.box} data-reveal="scale">
            <Image
              src="/img/scatola.webp"
              alt="La scatola di Bless LuceOmbra, con il coperchio sollevato"
              width={600}
              height={600}
              sizes="(max-width: 860px) 80vw, 440px"
            />
          </div>

          <div data-reveal="right">
            <p className="eyebrow">La scatola</p>
            <h2 className="section-title">{PRODUCT.name}</h2>
            <p className="lede">
              Un duello fulmineo, ricco di tensione e colpi di scena: riuscirai a
              benedire il tuo destino prima del tuo avversario?
            </p>

            <ul className={styles.contents}>
              <li>{PRODUCT.cards} carte uniche, illustrate a mano</li>
              <li>Segnalini per Punti Vittoria e Azioni</li>
              <li>Dado per gli scontri Fato</li>
              <li>Regolamento completo e guida rapida</li>
            </ul>

            <div className={styles.priceRow}>
              <p className={styles.price}>{PRODUCT.price} €</p>
              <ExternalLink href={PRODUCT.shop} className="btn">
                Acquista su Luminous Vine
                <span aria-hidden="true">↗</span>
              </ExternalLink>
            </div>
            <p className={styles.shopNote}>
              Spedizione e pagamento gestiti dallo shop di {SITE.studio}.
            </p>
          </div>
        </div>
      </section>

      <div className="wrap">
        <hr className="divider" />
      </div>

      {/* ------------------------------ decks ------------------------------ */}
      <section className="section" id="mazzi">
        <div className="wrap">
          <p className="eyebrow">Mazzi ed espansioni</p>
          <h2 className="section-title">Tre modi di giocare Bless.</h2>
          <p className="lede">
            Il mazzo base è in vendita, il secondo si prova nel simulatore e la
            prima espansione è stata annunciata.
          </p>

          <div className={styles.decks} data-reveal-group>
            {DECKS.map((m) => (
              <article
                key={m.name}
                className={`panel ${styles.deck}`}
                data-form={m.form}
                data-reveal
              >
                <p className={styles.status} data-status={m.statusKind}>
                  {m.status}
                </p>
                <h3 className={styles.deckName}>{m.name}</h3>
                <p className={styles.deckText}>{m.text}</p>
                {m.cta.external ? (
                  <ExternalLink href={m.cta.href} className="btn btn--sm">
                    {m.cta.label}
                    <span aria-hidden="true">↗</span>
                  </ExternalLink>
                ) : (
                  <Link href={m.cta.href} className="btn btn--sm btn--ghost">
                    {m.cta.label}
                  </Link>
                )}
              </article>
            ))}
          </div>
        </div>
      </section>

      <div className="wrap">
        <hr className="divider" />
      </div>

      {/* ---------------------------- preview ---------------------------- */}
      <section className="section" id="carte">
        <div className="wrap">
          <div className={styles.previewHeader}>
            <div>
              <p className="eyebrow">Database</p>
              <h2 className="section-title">Tutte le {PRODUCT.cards} carte, in chiaro.</h2>
            </div>
            <Link href="/database" className="btn btn--ghost">
              Vedi tutte le carte
            </Link>
          </div>

          <ul className={styles.grid} data-reveal-group>
            {preview.map((c) => (
              <li key={c.id} data-reveal="scale">
                <Link href={`/database/${c.id}`} className={styles.thumb}>
                  <Image
                    src={cardImage(c.id)}
                    alt={`${c.name} — carta di Bless`}
                    width={CARD_WIDTH}
                    height={CARD_HEIGHT}
                    sizes="(max-width: 700px) 44vw, 180px"
                    placeholder="blur"
                    blurDataURL={c.blurDataURL}
                    loading="lazy"
                  />
                  <span className={styles.thumbName}>{c.name}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <div className="wrap">
        <hr className="divider" />
      </div>

      {/* ------------------------------- FAQ ------------------------------- */}
      <section className="section" id="faq">
        <div className="wrap">
          <p className="eyebrow">Domande frequenti</p>
          <h2 className="section-title">Prima di sederti al tavolo.</h2>
          <Faq />
        </div>
      </section>

      {/* ---------------------------- community ---------------------------- */}
      <section className="section">
        <div className="wrap">
          <div className={`panel ${styles.community}`} data-reveal>
            <div>
              <p className="eyebrow">Community</p>
              <h2 className={styles.communityTitle}>Trova un avversario stasera.</h2>
              <p className={styles.communityText}>
                Sul Discord si organizzano partite in stanza privata, si discutono le
                carte e si prova il mazzo Tuono · Sabbia prima che esca la scatola.
              </p>
            </div>
            <ExternalLink href={socialHref("Discord")} className="btn">
              Entra nel Discord
              <span aria-hidden="true">↗</span>
            </ExternalLink>
          </div>
        </div>
      </section>
    </>
  );
}
