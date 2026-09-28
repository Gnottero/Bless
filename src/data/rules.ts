// The full rulebook, transcribed from the official PDF (LuceOmbra deck).
// The PDFs are still linked for download.

export type Block =
  | { type: "p"; text: string }
  | { type: "list"; items: string[] }
  | { type: "steps"; items: string[] }
  | { type: "note"; text: string };

export type Section = {
  id: string;
  title: string;
  summary: string;
  blocks: Block[];
};

export const SECTIONS: Section[] = [
  {
    id: "che-cose",
    title: "Che cos'è Bless",
    summary: "Il gioco in tre righe.",
    blocks: [
      {
        type: "p",
        text:
          "Bless è un gioco di carte per due giocatori con un unico mazzo condiviso da 62 carte uniche. Non richiede alcuna preparazione: si apre la scatola e si gioca.",
      },
      {
        type: "p",
        text:
          "Durante il proprio turno ogni giocatore può giocare ogni carta in due modi: come Maledizione, per attaccare e guadagnare Punti Vittoria, o come Preghiera, per attivare effetti speciali.",
      },
      {
        type: "p",
        text:
          "Sconfiggendo le carte avversarie le Maledizioni Blessano, facendo guadagnare Punti Vittoria al proprietario. Alla fine della partita chi ha più Punti Vittoria vince.",
      },
    ],
  },
  {
    id: "occorrente",
    title: "Che cosa serve",
    summary: "Un mazzo, un foglio, un tavolo.",
    blocks: [
      {
        type: "list",
        items: [
          "Un mazzo di Bless.",
          "Un foglietto per segnare i Punti Vittoria.",
          "Un luogo che diventi il Campo da gioco.",
        ],
      },
      { type: "note", text: "Non serve altro." },
    ],
  },
  {
    id: "campo",
    title: "Il campo di gioco",
    summary: "Due lati identici e due zone comuni.",
    blocks: [
      {
        type: "p",
        text:
          "Il campo è diviso in due lati identici, uno per giocatore. Ogni lato contiene una Zona Preghiera, una Zona Maledizione e un Altare.",
      },
      {
        type: "list",
        items: [
          "Zona Maledizione: le carte giocate qui diventano Maledizioni e possono combattere.",
          "Zona Preghiera: le carte giocate qui diventano Preghiere e attivano effetti.",
          "Altare: dove il giocatore conserva, coperte, le carte che ha Offerto.",
        ],
      },
      {
        type: "p",
        text:
          "Due zone sono condivise: il Vuoto, la pila degli scarti a faccia in su e sempre consultabile, e il Mazzo, da cui pescano entrambi i giocatori.",
      },
    ],
  },
  {
    id: "carte",
    title: "Le caratteristiche delle carte",
    summary: "Occhio, Karma, Forma.",
    blocks: [
      {
        type: "p",
        text:
          "Ogni carta riporta in alto a sinistra l'Occhio, in alto a destra il Karma, e al centro il simbolo della Forma. In basso trovi il nome dell'illustratore, il numero della carta e il simbolo del mazzo.",
      },
      {
        type: "list",
        items: [
          "Occhio — il valore di forza. Negli scontri vince la carta con Occhio maggiore.",
          "Karma — i Punti Vittoria che la carta fa guadagnare quando Blessa.",
          "Forma — l'archetipo della carta. Nel mazzo LuceOmbra le Forme sono Luce e Ombra; le carte Duali sono contemporaneamente entrambe.",
        ],
      },
      {
        type: "note",
        text:
          "La notazione «3/2 — Luce» usata nel database si legge: Occhio 3, Karma 2, Forma Luce.",
      },
    ],
  },
  {
    id: "due-zone",
    title: "Maledizione o Preghiera",
    summary: "La scelta che definisce Bless.",
    blocks: [
      {
        type: "p",
        text:
          "Ogni carta può essere giocata in una delle due zone del campo, e la zona decide quale dei suoi due effetti userà. Una volta scelta la zona, la carta ci rimane.",
      },
      {
        type: "p",
        text:
          "Maledizione: usa il suo effetto Maledizione, sempre attivo. Può attaccare e può essere attaccata. Non può usare il suo effetto Preghiera.",
      },
      {
        type: "p",
        text:
          "Preghiera: usa il suo effetto Preghiera secondo la propria tipologia (Impulso, Eco o Legame). Non attacca e non può essere attaccata. Non può usare il suo effetto Maledizione.",
      },
      {
        type: "note",
        text:
          "Se una Maledizione lascia la sua zona torna a essere una carta qualunque, e potrà essere rigiocata in entrambi i modi.",
      },
    ],
  },
  {
    id: "inizio-partita",
    title: "Iniziare una partita",
    summary: "Cinque passaggi prima del primo turno.",
    blocks: [
      {
        type: "steps",
        items: [
          "Scegliete insieme quale mazzo di Bless giocare.",
          "Mischiate il mazzo e posizionatelo a lato del tavolo.",
          "Date 4 carte a ciascun giocatore: è la mano iniziale.",
          "Scegliete il Primo Giocatore.",
          "Effettuate un Mulligan. Si comincia.",
        ],
      },
      {
        type: "note",
        text:
          "Il Primo Giocatore ha solo 2 Azioni nel suo primo turno. Da lì in poi entrambi ne hanno 3.",
      },
    ],
  },
  {
    id: "mulligan",
    title: "Il Mulligan",
    summary: "Come si pesca in Bless.",
    blocks: [
      {
        type: "p",
        text:
          "Il Mulligan si fa una volta all'inizio della partita e poi obbligatoriamente durante la fase di Fine Turno di ogni proprio turno. Pescare sancisce la fine del turno.",
      },
      {
        type: "steps",
        items: [
          "Metti da parte un numero qualsiasi di carte della tua mano, anche zero.",
          "Pesca dal Mazzo finché non hai 4 carte in mano.",
          "Mescola nel Mazzo le carte messe da parte.",
        ],
      },
      {
        type: "note",
        text: "Durante la partita si possono avere più di 4 carte in mano.",
      },
    ],
  },
  {
    id: "turno",
    title: "Il turno",
    summary: "Inizio, Fase Principale, Fine Turno.",
    blocks: [
      {
        type: "p",
        text:
          "I giocatori si alternano il ruolo di Giocatore Attivo. Il turno ha tre fasi.",
      },
      {
        type: "steps",
        items: [
          "Inizio Turno: si attivano, nell'ordine che preferisci, tutti gli effetti che citano «all'inizio del turno».",
          "Fase Principale: spendi fino a 3 Azioni, in qualunque ordine e con qualunque ripetizione.",
          "Fine Turno: si usano gli effetti «alla fine del turno», si rimuove la Stasi da tutte le Maledizioni, e il Giocatore Attivo effettua il Mulligan.",
        ],
      },
      {
        type: "p",
        text:
          "Si passa alla Fase di Fine Turno quando finiscono le Azioni, quando non è più possibile interagire con il campo, o semplicemente quando lo si desidera.",
      },
    ],
  },
  {
    id: "azioni",
    title: "Le quattro Azioni",
    summary: "Calare, Rimuovere la Stasi, Attaccare, Invocare.",
    blocks: [
      {
        type: "p",
        text:
          "Calare — spendi 1 Azione per giocare una carta dalla mano, scegliendo se calarla come Maledizione o come Preghiera. «Giocare» una carta vuol dire metterla in campo da qualunque zona; «Calare» vuol dire giocarla specificamente dalla mano.",
      },
      {
        type: "p",
        text:
          "Rimuovere la Stasi — spendi 1 Azione per togliere la Stasi da una carta. Ogni Maledizione appena giocata entra in Stasi e non può attaccare; la Stasi viene comunque rimossa da tutte le Maledizioni in campo durante il Fine Turno di ogni giocatore.",
      },
      {
        type: "p",
        text:
          "Attaccare — spendi 1 Azione per scegliere una tua Maledizione che può attaccare e una Maledizione avversaria che può essere attaccata: inizia lo Scontro. Ogni Maledizione può attaccare al massimo una volta per turno. Se l'avversario non ha Maledizioni in campo puoi bersagliare direttamente lui: è l'Attacco Diretto.",
      },
      {
        type: "p",
        text:
          "Invocare — spendi 1 Azione per usare l'effetto speciale di una tua Preghiera che riporta il simbolo dell'Invocazione. Nel mazzo LuceOmbra l'unica Preghiera invocabile è l'Eco, e la sua Invocazione è «usa il suo effetto». Ogni Preghiera può essere Invocata al massimo una volta per turno.",
      },
      {
        type: "note",
        text:
          "Con 1 Azione per calare, 1 per rimuovere la Stasi e 1 per attaccare, una Maledizione può attaccare nello stesso turno in cui è stata giocata.",
      },
    ],
  },
  {
    id: "stati",
    title: "Pura e Corrotta",
    summary: "I due stati di una Maledizione.",
    blocks: [
      {
        type: "p",
        text:
          "Una Maledizione appena giocata è Pura e sta in verticale. Diventa Corrotta quando viene attaccata da una Maledizione avversaria oppure quando perde uno scontro. Una Maledizione Corrotta si mette in orizzontale.",
      },
      {
        type: "p",
        text:
          "Una Maledizione Corrotta può fare tutto quello che fa una Pura, con due differenze: non può attaccare carte contro cui perderebbe lo scontro, e se perde uno scontro si Spezza, lasciando il campo.",
      },
      {
        type: "note",
        text:
          "Prima di attaccare con una Maledizione Corrotta si simula lo scontro: se lo perderebbe, quell'attacco non si può effettuare.",
      },
    ],
  },
  {
    id: "scontro",
    title: "Lo scontro",
    summary: "Quattro fasi, un vincitore.",
    blocks: [
      {
        type: "steps",
        items: [
          "Si attivano gli effetti che modificano l'Occhio delle carte, per esempio Rivalità (+3 Occhio contro una carta di un'altra Forma).",
          "Si confrontano i valori di Occhio delle due carte.",
          "Vince la carta con Occhio maggiore, perde quella con Occhio minore.",
          "Si aggiorna lo stato: chi era Pura si Corrompe, chi era Corrotta si Spezza.",
        ],
      },
      {
        type: "p",
        text:
          "Attenzione: una Maledizione Pura si corrompe anche solo per essere stata attaccata, indipendentemente dall'Occhio avversario. Una Pura con Occhio minore può quindi attaccare una Pura con Occhio maggiore, e si corrompono entrambe.",
      },
      {
        type: "p",
        text:
          "Se le due carte hanno lo stesso Occhio, entrambe perdono lo scontro.",
      },
      {
        type: "p",
        text:
          "Effetto «Vince»: al posto del confronto dell'Occhio si verifica se la condizione indicata si è realizzata. Se sì, quella carta vince a prescindere dai valori. Se entrambe hanno un effetto «Vince» e soddisfano le condizioni, è pareggio.",
      },
      {
        type: "p",
        text:
          "Effetto «Vince sempre»: la carta vince anche contro gli effetti «Vince» delle altre carte. Contro un altro «Vince sempre» si pareggia.",
      },
    ],
  },
  {
    id: "blessare",
    title: "Blessare",
    summary: "La meccanica che fa i punti.",
    blocks: [
      {
        type: "p",
        text:
          "Quando una Maledizione Blessa, il suo proprietario guadagna Punti Vittoria pari al Karma di quella Maledizione. Ci sono due modi principali.",
      },
      {
        type: "p",
        text:
          "Offerta — se in seguito a uno scontro la Maledizione attaccata si Spezza, chi ha attaccato può decidere di non mandarla nel Vuoto ma di Offrirla al proprio Altare. Così la sua Maledizione Blessa.",
      },
      {
        type: "p",
        text:
          "Attacco Diretto — quando l'avversario non ha Maledizioni in campo puoi attaccare direttamente lui. La carta che lo fa Blessa: non aggiungi nulla all'Altare, ma i Punti Vittoria li guadagni comunque.",
      },
      {
        type: "note",
        text:
          "Se le due carte pareggiano, entrambe perdono lo scontro e la carta avversaria può comunque essere offerta.",
      },
      {
        type: "p",
        text:
          "Alcune carte permettono di Blessare in altre situazioni, per esempio con l'abilità Impatto.",
      },
    ],
  },
  {
    id: "fine-partita",
    title: "Fine della partita",
    summary: "Turni Finali e vittoria.",
    blocks: [
      {
        type: "p",
        text:
          "Quando un giocatore posiziona la sua 5ª carta nell'Altare, attiva i Turni Finali: 5 turni al termine dei quali la partita finisce. I Turni Finali si attivano anche se un giocatore dovrebbe pescare e il Mazzo è terminato: in quel caso si mescola il Vuoto, che diventa il nuovo Mazzo.",
      },
      {
        type: "p",
        text:
          "I Turni Finali iniziano con il turno del giocatore che NON li ha attivati, che farà anche il terzo e l'ultimo.",
      },
      {
        type: "p",
        text:
          "Alla fine dell'ultimo Turno Finale vince chi ha più Punti Vittoria. In caso di parità vince il giocatore che ha attivato i Turni Finali.",
      },
      {
        type: "note",
        text:
          "Durata alternativa: 3 carte nell'Altare per una partita breve, 7 per una partita lunga.",
      },
    ],
  },
  {
    id: "regole-specifiche",
    title: "Regole specifiche",
    summary: "I casi limite.",
    blocks: [
      {
        type: "p",
        text:
          "Obblighi — se una carta impone un obbligo va eseguito subito; se non è possibile, l'effetto si risolve senza alcuna applicazione.",
      },
      {
        type: "p",
        text:
          "Carte Duali — sono considerate contemporaneamente di entrambe le Forme, quindi ogni effetto che bersaglia una Forma bersaglia anche loro.",
      },
      {
        type: "p",
        text:
          "Parità in «maggiore» o «minore» — se più bersagli soddisfano il requisito, sceglie il giocatore che ha usato l'effetto.",
      },
      {
        type: "p",
        text:
          "Ordine delle carte — l'ordine lo decide chi controlla le carte; se sono coinvolti entrambi i giocatori, hanno priorità le carte di chi è di turno.",
      },
      {
        type: "p",
        text:
          "Durata degli effetti — ogni effetto è perennemente attivo salvo durata indicata, e gli effetti che leggono un valore sono in continuo aggiornamento.",
      },
      {
        type: "p",
        text:
          "Sovrapposizione — fra due effetti che impostano valori diversi vale l'ultimo usato. Se un effetto imposta un valore e un altro lo somma, prima si imposta e poi si somma; se l'effetto che imposta dice «sempre», vale il valore impostato.",
      },
      {
        type: "p",
        text:
          "Limite — al massimo 4 Maledizioni in campo, e ogni tipologia di Preghiera ha il proprio limite (2 Eco; 1 Legame per Maledizione). Superato un limite, il giocatore manda subito nel Vuoto proprie carte finché non rientra, ma non può scegliere la carta che ha causato il superamento; fra le Maledizioni può mandare nel Vuoto solo carte Pure.",
      },
    ],
  },
];
