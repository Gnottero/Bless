import LegalPage, { legalMetadata, type LegalPageContent } from "@/components/LegalPage";

const CONTENT: LegalPageContent = {
  path: "/contatti",
  title: "Contatti",
  eyebrow: "Informazioni",
  intro: "Come raggiungere Luminous Vine Studio per assistenza, stampa o collaborazioni.",
  missing: [
    "Indirizzo email di contatto.",
    "Ragione sociale, sede legale e partita IVA.",
    "Riferimento per la stampa e per le collaborazioni.",
    "Canale per l'assistenza sugli ordini.",
  ],
};

export const metadata = legalMetadata(CONTENT);

export default function ContactsPage() {
  return <LegalPage {...CONTENT} />;
}
