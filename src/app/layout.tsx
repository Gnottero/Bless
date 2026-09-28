import type { Metadata, Viewport } from "next";
import { EB_Garamond, Inter } from "next/font/google";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import GlossaryTouch from "@/components/GlossaryTouch";
import JsonLd from "@/components/JsonLd";
import ScrollReveal from "@/components/anim/ScrollReveal";
import { OG_BASE, OG_IMAGE, SITE, SOCIAL, STUDIO_ID } from "@/lib/site";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

/* Serif for headings, close to the lettering on the cards, and it has the
   small caps and italics we need for the rulebook.

   No `weight` on purpose: that way Next uses the variable font, so it's two
   files (regular + italic) instead of eight, and we get every weight. */
const garamond = EB_Garamond({
  subsets: ["latin"],
  display: "swap",
  style: ["normal", "italic"],
  variable: "--font-garamond",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: {
    default: `${SITE.name} · Il gioco di carte per due giocatori`,
    template: `%s · ${SITE.name}`,
  },
  description: SITE.description,
  applicationName: SITE.name,
  openGraph: {
    ...OG_BASE,
    images: [{ ...OG_IMAGE, alt: `${SITE.name} — gioco di carte` }],
  },
  twitter: { card: "summary_large_image", images: [OG_IMAGE.url] },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#f0e4cb",
  colorScheme: "light",
};

/* Publisher of the site and the game. Defined once here, everything else
   refers to it by `@id`. */
const JSON_LD = [
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": STUDIO_ID,
    name: SITE.studio,
    url: SITE.studioUrl,
    sameAs: SOCIAL.map((s) => s.href),
  },
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE.name,
    url: SITE.url,
    inLanguage: "it",
    publisher: { "@id": STUDIO_ID },
  },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`${inter.variable} ${garamond.variable}`}>
      <body>
        <JsonLd data={JSON_LD} />
        <a href="#contenuto" className="skip-link">
          Vai al contenuto
        </a>
        <Header />
        <main id="contenuto">{children}</main>
        <Footer />
        <ScrollReveal />
        <GlossaryTouch />
      </body>
    </html>
  );
}
