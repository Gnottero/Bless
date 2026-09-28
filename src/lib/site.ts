export const SITE = {
  name: "Bless",
  url: "https://blesscardgame.com",
  description:
    "Bless è un gioco di carte strategico per due giocatori con un unico mazzo da 62 carte. Gioca gratis contro il Bot o acquista la scatola.",
  studio: "Luminous Vine Studio",
  studioUrl: "https://luminousvinestudio.com",
  locale: "it_IT",
} as const;

/**
 * Spread this into every page's `openGraph`. Next replaces the layout's
 * `openGraph` instead of merging it, so without this you lose site_name,
 * locale and type.
 */
export const OG_BASE = {
  type: "website",
  siteName: SITE.name,
  locale: SITE.locale,
} as const;

/** JSON-LD `@id` for the studio. The full Organization is in the layout,
    pages just point to it. */
export const STUDIO_ID = `${SITE.url}/#studio`;

/** Default OG image, 1200x630. */
export const OG_IMAGE = { url: "/og.jpg", width: 1200, height: 630 } as const;

/** Screen reader hint added to links that open in a new tab. */
export const NEW_TAB_NOTE = "(si apre in una nuova scheda)";

export const NAV = [
  { href: "/", label: "Home" },
  { href: "/gioco", label: "Gioca" },
  { href: "/database", label: "Carte" },
  { href: "/rules", label: "Regolamento" },
] as const;

export const SOCIAL = [
  {
    name: "Instagram",
    href: "https://www.instagram.com/luminous_vine_studio",
    label: "Instagram di Luminous Vine Studio",
  },
  {
    name: "X",
    href: "https://x.com/bless_26games",
    label: "Profilo X di Bless",
  },
  {
    name: "TikTok",
    href: "https://www.tiktok.com/@bless_26games",
    label: "TikTok di Bless",
  },
  {
    name: "Discord",
    href: "https://discord.gg/tWzWrqXPHe",
    label: "Server Discord di Bless",
  },
] as const;

export type SocialName = (typeof SOCIAL)[number]["name"];

export function socialHref(name: SocialName): string {
  return SOCIAL.find((s) => s.name === name)!.href;
}

export const PRODUCT = {
  name: "Bless LuceOmbra",
  price: 25,
  currency: "EUR",
  shop: "https://luminousvinestudio.com/prodotto/bless-luceombra/",
  players: "2",
  age: "12+",
  cards: 62,
  award: "Miglior Prototipo dell'anno 2024",
} as const;

/**
 * First expansion. It's been announced but isn't on sale yet, so this only
 * has what the studio has published so far. No price or release date until
 * they're official.
 */
export const EXPANSION = {
  name: "Bless · Il Cerchio",
  shortTitle: "Il Cerchio",
  cards: 40,
  status: "In arrivo",
  text:
    "40 carte uniche che si aggiungono al mazzo LuceOmbra. Annunciata da Luminous Vine Studio: prezzo, contenuto della scatola e data di uscita non sono ancora stati pubblicati.",
  href: "https://luminousvinestudio.com/",
} as const;

export const RESOURCES = {
  video: "https://youtu.be/mNChgJ-WAA8",
  videoId: "mNChgJ-WAA8",
  fullRulebook: {
    href: "https://luminousvinestudio.com/wp-content/uploads/2026/01/Rulebook-Completo-Bless.pdf",
    format: "PDF",
    size: "3,8 MB",
  },
  quickRulebook: {
    href: "https://luminousvinestudio.com/wp-content/uploads/2026/01/Rulebook-riassuntivo-aggiornato-1-26.pdf",
    format: "PDF",
    size: "2,4 MB",
  },
} as const;
