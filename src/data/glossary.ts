// Game terms and their definitions. Everything else reads from here.
// Text copied from the glossary in the full rulebook (section VII, pp. 49-57).

import { normalize } from "@/lib/text";

export type GlossaryEntry = {
  term: string;
  /** Other forms of the term to match in card text (lowercase, accents are normalized elsewhere). */
  aliases?: string[];
  definition: string;
  category: "Icona" | "Abilità" | "Preghiera" | "Zona" | "Azione" | "Stato" | "Termine";
};

export const GLOSSARY: GlossaryEntry[] = [
  {
    term: "Occhio",
    category: "Icona",
    definition:
      "Il valore di forza della carta. Durante uno scontro vince la carta con Occhio maggiore.",
  },
  {
    term: "Karma",
    category: "Icona",
    definition:
      "I Punti Vittoria che la carta fa guadagnare al suo controllore quando Blessa.",
  },
  {
    term: "Forma",
    category: "Termine",
    definition:
      "L'archetipo della carta, riconoscibile da colore e simbolo. Nel mazzo LuceOmbra le Forme sono Luce e Ombra; le carte Duali sono contemporaneamente entrambe.",
  },
  {
    term: "Maledizione",
    aliases: ["maledizioni"],
    category: "Zona",
    definition:
      "Carta giocata nella Zona Maledizione. Usa il suo effetto Maledizione, sempre attivo, e può attaccare o essere attaccata.",
  },
  {
    term: "Preghiera",
    aliases: ["preghiere"],
    category: "Zona",
    definition:
      "Carta giocata nella Zona Preghiera. Usa il suo effetto Preghiera secondo la propria tipologia. Non attacca e non può essere attaccata.",
  },
  {
    term: "Impulso",
    category: "Preghiera",
    definition:
      "Tipo di Preghiera: usa il suo effetto quando viene giocata e, risolto l'effetto, si spezza. Nessun limite di quantità.",
  },
  {
    term: "Eco",
    category: "Preghiera",
    definition:
      "Tipo di Preghiera invocabile: usa il suo effetto quando viene giocata e resta in campo. Ogni volta che una tua altra Eco usa il suo effetto, usano l'effetto anche le altre Eco in campo, al massimo una volta per turno ciascuna. Limite: 2 Eco per giocatore.",
  },
  {
    term: "Legame",
    aliases: ["legata", "legare", "lega"],
    category: "Preghiera",
    definition:
      "Tipo di Preghiera: quando viene giocata si lega a una Maledizione in campo, propria o avversaria, trasferendole il proprio effetto. Se la Maledizione lascia la zona, la Legame si spezza. Limite: 1 Legame per Maledizione.",
  },
  {
    term: "Rivalità",
    category: "Abilità",
    definition:
      "La carta ha +3 Occhio durante lo scontro contro una carta di un'altra Forma. Le carte Duali sono immuni: non possono usarla e non la subiscono.",
  },
  {
    term: "Impatto",
    category: "Abilità",
    definition:
      "Quando la carta Corrompe una carta avversaria per via di uno scontro, Blessa.",
  },
  {
    term: "Barriera",
    category: "Abilità",
    definition:
      "Quando la carta si Corrompe, non può essere attaccata fino alla fine del turno.",
  },
  {
    term: "Fato",
    category: "Abilità",
    definition:
      "Gli scontri Fato ignorano la regola per cui una carta corrotta può attaccare solo carte contro cui vincerà. Quando la carta partecipa a uno scontro si tira un dado e si sceglie Pari o Dispari: indovinando, questa carta vince lo scontro.",
  },
  {
    term: "Blessare",
    aliases: ["blessa", "blessando", "blessano"],
    category: "Azione",
    definition:
      "La carta fa guadagnare a chi la controlla Punti Vittoria pari al proprio Karma. Dopo aver spezzato una carta in seguito a uno scontro puoi decidere di Blessare: la carta sconfitta va nel tuo Altare invece che nel Vuoto.",
  },
  {
    term: "Calare",
    aliases: ["cala", "calata", "calo"],
    category: "Azione",
    definition:
      "Giocare una carta dalla mano. CALO indica un effetto che si usa quando la carta viene calata in campo.",
  },
  {
    term: "Invocare",
    aliases: ["invoca", "invocazione", "invocabile"],
    category: "Azione",
    definition: "Usare l'effetto speciale di una tua Preghiera già in campo.",
  },
  {
    term: "Spezzare",
    aliases: ["spezza", "spezzata", "spezzate"],
    category: "Azione",
    definition: "La carta va dal campo al Vuoto.",
  },
  {
    term: "Scartare",
    aliases: ["scarta", "scartata"],
    category: "Azione",
    definition: "La carta va dalla mano al Vuoto.",
  },
  {
    term: "Offrire",
    aliases: ["offerta", "offerte", "offri"],
    category: "Azione",
    definition: "Mettere la carta avversaria sconfitta nel proprio Altare.",
  },
  {
    term: "Prendere",
    aliases: ["prendi", "prende"],
    category: "Azione",
    definition: "Aggiungere alla propria mano una carta da una zona specifica.",
  },
  {
    term: "Convertire",
    aliases: ["converti", "convertita"],
    category: "Azione",
    definition:
      "Una Maledizione diventa una Preghiera, o viceversa, cambiando zona del campo.",
  },
  {
    term: "Purificare",
    aliases: ["purifica", "pura", "pure"],
    category: "Stato",
    definition:
      "Una Maledizione Pura è orientata verticalmente. Se perde uno scontro non si spezza: diventa Corrotta.",
  },
  {
    term: "Corrotta",
    aliases: ["corrotte", "corrompe", "corrompere", "corrompono", "si corrompe"],
    category: "Stato",
    definition:
      "Una Maledizione Corrotta è orientata orizzontalmente. Se perde un altro scontro si spezza.",
  },
  {
    term: "Stasi",
    category: "Stato",
    definition:
      "Stato in cui entra una Maledizione appena calata: non può attaccare. La Stasi viene rimossa da tutte le carte alla fine di ogni turno.",
  },
  {
    term: "Altare",
    category: "Zona",
    definition:
      "La zona in cui il giocatore posiziona le carte che ha Offerto. La partita entra nei Turni Finali quando un giocatore mette la sua 5ª carta nell'Altare.",
  },
  {
    term: "Vuoto",
    category: "Zona",
    definition: "La zona degli scarti: ci finiscono le carte scartate e quelle spezzate.",
  },
  {
    term: "Mazzo",
    category: "Zona",
    definition:
      "L'unico mazzo da 62 carte, condiviso: entrambi i giocatori pescano da lì.",
  },
  {
    term: "Bersaglio",
    category: "Termine",
    definition:
      "Quando un effetto dice «bersaglio», chi lo gioca deve scegliere una carta valida per quell'effetto.",
  },
  {
    term: "Originale",
    category: "Termine",
    definition:
      "Il valore di Occhio o Karma stampato sulla carta, senza alcuna modifica applicata.",
  },
  {
    term: "Gratuitamente",
    category: "Termine",
    definition: "Compiere l'Azione indicata senza spendere Azioni.",
  },
  {
    term: "Sempre",
    category: "Termine",
    definition:
      "Un effetto «sempre» non può essere sovrastato da altri effetti, a meno che anche l'altro effetto non sia «sempre»: in quel caso i due interagiscono come se la parola non ci fosse.",
  },
];

const INDEX = new Map<string, GlossaryEntry>();
for (const entry of GLOSSARY) {
  INDEX.set(entry.term.toLowerCase(), entry);
  for (const alias of entry.aliases ?? []) INDEX.set(alias.toLowerCase(), entry);
}

/** All matchable keys, longest first. */
export const KNOWN_TERMS = [...INDEX.keys()].sort((a, b) => b.length - a.length);

export function findTerm(word: string): GlossaryEntry | undefined {
  return INDEX.get(word.toLowerCase());
}

/**
 * Anchor for a term in the /rules glossary. Used both for the `id` there and
 * for the links in card text, so they always match.
 */
export function glossaryAnchor(term: string): string {
  return `gloss-${normalize(term)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")}`;
}
