import { EXPANSION, PRODUCT, RESOURCES } from "@/lib/site";
import styles from "./Faq.module.css";

/** Also used by the home page for the FAQPage JSON-LD. */
export const QUESTIONS = [
  {
    q: "Serve comprare il gioco per provarlo?",
    a: "No. Il simulatore online è gratuito e completo: puoi giocare una partita intera contro il Bot dal browser, senza registrarti e senza installare nulla.",
  },
  {
    q: "In quanto si impara?",
    a: "Una partita dura circa 30 minuti e le regole di base stanno in poche righe: tre azioni per turno, scontri decisi dall'Occhio, cinque carte nell'Altare per vincere. Il rulebook riassuntivo basta per la prima partita.",
  },
  {
    q: "Quante carte ci sono e sono tutte diverse?",
    a: `Il mazzo LuceOmbra contiene ${PRODUCT.cards} carte, tutte uniche: 29 Luce, 29 Ombra e 4 Duali. Entrambi i giocatori pescano dallo stesso mazzo, quindi non esiste un mazzo “migliore”.`,
  },
  {
    q: "Perché ogni carta ha due effetti?",
    a: "Perché ogni carta può essere giocata in due zone diverse. Nella Zona Maledizione combatte e fa punti; nella Zona Preghiera non può essere attaccata ma attiva un effetto di supporto. Ogni pescata è quindi una doppia scelta.",
  },
  {
    q: "Si gioca in più di due?",
    a: "No: Bless è pensato come duello uno contro uno. Il simulatore permette sia la partita contro il Bot sia una stanza privata con un altro giocatore.",
  },
  {
    q: "Che cos'è il mazzo Tuono · Sabbia?",
    a: "È il secondo mazzo, con meccaniche nuove (Cariche, Marchi, Sigilli, Glifi ed Esordio). Oggi è giocabile nel simulatore online; la scatola non è ancora in vendita.",
  },
  {
    q: "Quanto costa e cosa c'è nella scatola?",
    a: `La scatola Bless LuceOmbra costa ${PRODUCT.price} €, contiene le ${PRODUCT.cards} carte del mazzo, i segnalini per Punti Vittoria e Azioni, il dado per gli scontri Fato e il regolamento.`,
  },
  {
    q: "Ci saranno espansioni?",
    a: `Sì: ${EXPANSION.name} è la prima, ${EXPANSION.cards} carte uniche che si aggiungono al mazzo LuceOmbra. È annunciata da Luminous Vine Studio ma non ancora in vendita: prezzo e data di uscita non sono stati comunicati.`,
  },
  {
    q: "Dove trovo il regolamento completo?",
    a: `Sul sito, in versione consultabile, e come PDF scaricabile (${RESOURCES.fullRulebook.format}, ${RESOURCES.fullRulebook.size}). C'è anche un video tutorial.`,
  },
] as const;

export default function Faq() {
  return (
    <div className={styles.list} data-reveal-group>
      {QUESTIONS.map((d) => (
        <details key={d.q} className={styles.item} data-reveal name="faq">
          <summary className={styles.question}>
            <span>{d.q}</span>
            <span className={styles.plus} aria-hidden="true" />
          </summary>
          <div className={styles.answer}>
            <p>{d.a}</p>
          </div>
        </details>
      ))}
    </div>
  );
}
