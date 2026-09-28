import LegalPage, { legalMetadata, type LegalPageContent } from "@/components/LegalPage";

const CONTENT: LegalPageContent = {
  path: "/cookie",
  title: "Cookie policy",
  eyebrow: "Legale",
  intro: "Quali cookie e tecnologie simili usa il sito, e come gestire il consenso.",
  missing: [
    "Elenco dei cookie tecnici effettivamente impostati dal sito.",
    "Cookie di terze parti: YouTube viene caricato solo dopo un clic esplicito.",
    "Modalità di raccolta e revoca del consenso.",
    "Se serve un banner: quali categorie deve coprire.",
  ],
};

export const metadata = legalMetadata(CONTENT);

export default function CookiePage() {
  return <LegalPage {...CONTENT} />;
}
