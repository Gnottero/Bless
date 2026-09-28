import LegalPage, { legalMetadata, type LegalPageContent } from "@/components/LegalPage";

const CONTENT: LegalPageContent = {
  path: "/privacy",
  title: "Privacy policy",
  eyebrow: "Legale",
  intro: "Come vengono trattati i dati personali di chi visita blesscardgame.com e di chi usa il simulatore online.",
  missing: [
    "Titolare del trattamento e dati societari.",
    "Dati raccolti dal simulatore e dove vengono conservati.",
    "Servizi terzi coinvolti: YouTube, lo shop WooCommerce, eventuali strumenti di analisi.",
    "Base giuridica, tempi di conservazione e diritti dell'interessato.",
  ],
};

export const metadata = legalMetadata(CONTENT);

export default function PrivacyPage() {
  return <LegalPage {...CONTENT} />;
}
