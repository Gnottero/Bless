import LegalPage, { legalMetadata, type LegalPageContent } from "@/components/LegalPage";

const CONTENT: LegalPageContent = {
  path: "/termini",
  title: "Termini e condizioni",
  eyebrow: "Legale",
  intro: "Condizioni d'uso del sito e del simulatore online di Bless.",
  missing: [
    "Titolarità dei contenuti e delle illustrazioni delle carte.",
    "Regole d'uso del simulatore e delle stanze private.",
    "Limitazioni di responsabilità.",
    "Foro competente e legge applicabile.",
  ],
};

export const metadata = legalMetadata(CONTENT);

export default function TermsPage() {
  return <LegalPage {...CONTENT} />;
}
