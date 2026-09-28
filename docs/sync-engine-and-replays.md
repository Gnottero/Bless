# Motore condiviso e scambio partite

## Obiettivo

Il sito ufficiale e il simulatore devono usare la stessa versione delle regole e
degli stessi dati carta. Una partita del sito deve inoltre poter essere portata
nel simulatore senza collegare direttamente i due servizi.

## Sorgente unica raccomandata

Creare una repository privata `Bless-cardgame/Bless-core` contenente:

- `bless_sim/*.py`, cioè il solo motore regolamentare;
- i JSON strutturati dei mazzi;
- la suite completa dei test regolamentari;
- il numero di versione del motore e del formato replay;
- un unico generatore Excel -> JSON per i dati carta.

Il sito e il simulatore devono fissare una versione/tag di `Bless-core`, non
copiare modifiche a mano. Ogni correzione segue quindi questo flusso:

1. si modifica `Bless-core` e si aggiunge almeno un test di regressione;
2. i test regolamentari devono passare;
3. si crea un nuovo tag del motore;
4. sito e simulatore aggiornano quel tag su branch separati;
5. le rispettive preview vengono controllate prima della pubblicazione.

Il file `version.py` introdotto nel sito è il primo passo: ogni replay dichiara
la versione del motore che lo ha prodotto. Finché la repository condivisa non
esiste, il simulatore può confrontare quel valore e segnalare una versione non
allineata invece di analizzare silenziosamente dati incompatibili.

Gli Excel originali restano la fonte autorevole dei testi e dei valori carta.
Il generatore deve fallire se mancano carte, ci sono ID duplicati o i valori non
sono validi; il JSON generato viene poi usato da entrambi i progetti.

## Archivio portatile delle partite

Il sito salva automaticamente i replay completati nel browser e permette di
scaricarli da `/gioco` o dalla schermata di fine partita. Il file ha estensione
`.json` e questa struttura:

```json
{
  "format": "bless.replay.archive",
  "version": 1,
  "source": "blesscardgame.com",
  "exported_at": "2026-08-14T12:00:00.000Z",
  "records": [
    {
      "id": "...",
      "saved_at": "...",
      "title": "...",
      "replay": {
        "schema": "bless.replay",
        "schema_version": 1,
        "engine_version": "2026.08.21.1"
      },
      "review": {}
    }
  ]
}
```

Il simulatore dovrà importare soltanto archivi con formato e versione
riconosciuti, convalidare i replay e ignorare i duplicati tramite `record.id`.
L'importazione può aggiungere le partite all'archivio locale del simulatore e al
dataset umano, ma non deve aggiornare direttamente il Bot pubblicato. I dati
umani e quelli di auto-sfida restano immutabili e separati; l'allenamento crea
un candidato che viene promosso soltanto dopo la valutazione prevista.

Questo scambio è manuale: nessun replay viene inviato automaticamente a un
server esterno e il file resta sotto il controllo del giocatore.

## Pacchetto completo per Sim. Bless

Finché `Bless-core` non viene separato in una repository autonoma, il comando
`npm run export:game-system` crea in `artifacts/` un archivio versionato con:

- il motore Python canonico e i dati strutturati dei due mazzi;
- i ponti per browser e partita manuale;
- tutti i test regolamentari;
- il servizio multiplayer e la UI del tavolo come riferimenti separati;
- un manifesto con versione del motore, revisione Git e impronta SHA-256 di
  ogni file.

Sim. Bless deve importare prima `public/python/bless_sim` e
`public/python/data`, eseguire l'intera suite regolamentare e solo dopo adattare
le proprie parti di analisi e interfaccia. Le copie server sotto `api/_engine`
sono generate dal motore canonico e non sono incluse per evitare due sorgenti
divergenti. Le immagini delle carte non vengono duplicate nell'archivio: i due
progetti continuano a usare i propri asset già presenti.
