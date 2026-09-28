from __future__ import annotations

import copy
import json
from collections import Counter
from typing import Any, Iterable, Mapping

from .bots import BOT_NAMES, FEATURE_LABELS, FEATURE_NAMES, make_bot
from .engine import GameEngine, GameResult
from .model import Action, PrayerType, Zone
from .replay import replay_payload


HUMAN_PLAYER = 1
BOT_PLAYER = 0

TUTORIAL_FIRST_CURSE = 23  # Orizzonte
TUTORIAL_ECHO = 1  # Re Luce
TUTORIAL_SECOND_CURSE = 19  # Sole Vigilato
TUTORIAL_MULLIGAN_CARD = 44  # Visione Profonda
TUTORIAL_OPTIONAL_CARD = 45
TUTORIAL_IMPULSE = 37  # Eclissi
TUTORIAL_BOND = 25  # Mangrovia Celeste
TUTORIAL_OPPONENT_CURSE = 21  # Tempio di Herset
TUTORIAL_OPPONENT_EXTRA_CURSE = 7  # Ali di Mos
TUTORIAL_OPPONENT_PRAYER = 2  # Zoreo, Campione della Luce


class ChoiceRequired(RuntimeError):
    def __init__(self, request: dict[str, Any]):
        super().__init__(request.get("prompt", "Scelta richiesta"))
        self.request = request


PURPOSE_PROMPTS: dict[str, tuple[str, str]] = {
    "attach_benefit": ("Scegli la Maledizione a cui legare la Preghiera", "Il Legame verra' applicato al bersaglio scelto."),
    "attack_setup": ("Scegli la Maledizione da preparare", "L'effetto le permetterà di vincere contro le carte Marchiate."),
    "attack_source": ("Scegli quale Maledizione deve attaccare", "L'attacco prodotto dall'effetto non spende Azioni."),
    "attack_target": ("Scegli il bersaglio dell'attacco", "Puoi scegliere una Maledizione Marchiata valida."),
    "bless": ("Scegli la Maledizione da Blessare", "La carta guadagnerà PV pari al proprio Karma."),
    "break": ("Scegli una carta da Spezzare", "L'effetto proseguira' sulla carta selezionata."),
    "buff_eye": ("Scegli la Maledizione da potenziare", "Il suo Occhio verra' modificato dall'effetto."),
    "buff_karma": ("Scegli la Maledizione da potenziare", "Il suo Karma verra' modificato dall'effetto."),
    "convert": ("Scegli la Preghiera da convertire", "La carta diventera' una Maledizione."),
    "convert_charge": ("Scegli la Carica da convertire", "La carta scelta diventerà una Maledizione non in Stasi."),
    "cost": ("Scegli la carta con cui pagare il costo", "La seconda parte dell'effetto si risolve solo se il costo viene pagato."),
    "charge": ("Scegli la carta da Caricare", "La carta diventa una Carica privata."),
    "debuff": ("Scegli la carta avversaria", "L'effetto negativo verra' applicato al bersaglio."),
    "debuff_eye": ("Scegli la Maledizione avversaria da indebolire", "La riduzione d'Occhio preparera' uno scontro favorevole."),
    "darkness_target": ("Oscurità: scegli il bersaglio", "Puoi scegliere una Maledizione tua oppure avversaria."),
    "darkness_reference_own": ("Scegli un'altra tua Ombra", "Il bersaglio avrà il suo Occhio originale per questo turno."),
    "darkness_reference_enemy": ("Scegli un'altra tua Ombra", "Il bersaglio avversario avrà il suo Occhio originale per questo turno."),
    "discard_own": ("Scegli una carta dalla tua mano da scartare", "Questa carta verra' mandata nel Vuoto."),
    "effect_source": ("Scegli quale effetto risolvere", "Puoi selezionare la carta che deve attivarsi adesso."),
    "extra_attacks": ("Scegli la Maledizione che attaccherà ancora", "Potrà effettuare due attacchi aggiuntivi gratuiti."),
    "eye_reference": ("Scegli la carta di riferimento", "Il suo Occhio originale verra' usato dall'effetto."),
    "form_setup": ("Scegli la carta da trasformare", "Dopo sceglierai la sua nuova forma."),
    "limit_remove": ("Scegli quale carta sostituire", "Hai raggiunto un limite del campo: la carta scelta andra' nel Vuoto."),
    "mark": ("Scegli la carta da Marchiare", "Una carta verrà posta girata sotto il bersaglio."),
    "mark_any": ("Scegli la Maledizione da Marchiare", "Voce Tonante userà una Carica avversaria come Marchio."),
    "mark_from_hand": ("Scegli la carta da usare come Marchio", "La carta scelta lascia la Mano e viene posta sotto il bersaglio."),
    "must_attack": ("Scegli la Maledizione vincolata", "Nel prossimo turno potrà attaccare soltanto la carta indicata."),
    "optional_corrupt": ("Puoi corrompere una Maledizione avversaria", "Colosso permette di scegliere un bersaglio valido oppure di proseguire senza corrompere."),
    "optional_remove_stasis": ("Puoi rimuovere una Stasi", "Cuore dei Cieli può rimuovere la Stasi da una Maledizione Tuono, anche avversaria."),
    "open_own_sigil": ("Scegli un tuo Sigillo da aprire", "La Carica è già stata pagata: ora scegli quale tuo Sigillo aprire."),
    "play": ("Scegli la carta da giocare", "L'effetto giochera' automaticamente la carta selezionata."),
    "protect_own": ("Scegli la Maledizione da proteggere", "La protezione verra' applicata al bersaglio scelto."),
    "purify": ("Scegli la Maledizione da purificare", "La carta scelta tornera' Pura."),
    "purify_any": ("Scegli un'altra Maledizione da purificare", "Deserto Perla può rendere Pura una Maledizione di qualsiasi giocatore."),
    "remove_mark": ("Scegli il Marchio da rimuovere", "La carta usata come Marchio andrà in fondo al Mazzo."),
    "return_own": ("Scegli una tua Maledizione da riprendere", "La carta scelta tornera' nella tua mano."),
    "sacrifice": ("Scegli una carta da Spezzare", "Questa scelta e' obbligatoria per completare l'effetto."),
    "spend_charge": ("Scegli la Carica da spendere", "La Carica scelta paga il costo prima che venga applicato l'effetto."),
    "steal": ("Scegli la carta di cui prendere il controllo", "La carta passera' sul lato opposto del campo."),
    "sigil_state": ("Scegli un Sigillo da aprire o chiudere", "Cavalcare Sabbia invertirà lo stato del Sigillo scelto."),
    "sigil_state_required": ("Scegli un Sigillo da aprire o chiudere", "Il CALO di Cavalcare Sabbia invertirà lo stato del Sigillo scelto."),
    "spend_charge": ("Scegli quale Carica spendere", "La Carica è privata e andrà in fondo al Mazzo."),
    "swap_stats": ("Scegli la Maledizione", "Occhio e Karma verranno scambiati per questo turno."),
    "suppress": ("Scegli la carta di cui annullare l'effetto", "Testo e abilita' della carta verranno soppressi."),
    "take": ("Scegli la carta da prendere", "La carta selezionata verra' aggiunta alla tua mano."),
    "toggle_corruption": ("Scegli una tua Maledizione", "Potrai Purificarla oppure Corromperla."),
}


class HumanDecisionBot:
    """Adattatore che trasforma le scelte del motore in richieste UI.

    Ogni Azione viene rigiocata da uno stato base finche' tutte le richieste
    hanno una risposta. In questo modo anche effetti con piu' scelte sequenziali
    possono essere messi in pausa senza cambiare le regole del motore.
    """

    def __init__(self, fallback_weights: Mapping[str, float] | None = None):
        self.name = "Umano"
        self._choices: list[Any] = []
        self._cursor = 0
        self._combined_mulligan = False
        self._combined_mulligan_charge: int | None = None
        self._fallback = make_bot("Bot", fallback_weights)

    def __copy__(self) -> Any:
        # Le copie usate dal lookahead del bot devono simulare una risposta
        # umana plausibile, non aprire una finestra di scelta invisibile.
        return copy.copy(self._fallback)

    def __deepcopy__(self, memo: dict[int, Any]) -> HumanDecisionBot:
        result = HumanDecisionBot()
        memo[id(self)] = result
        result._choices = copy.deepcopy(self._choices, memo)
        result._cursor = self._cursor
        result._combined_mulligan = self._combined_mulligan
        result._combined_mulligan_charge = self._combined_mulligan_charge
        result._fallback = copy.deepcopy(self._fallback, memo)
        return result

    def reset_choices(self, choices: list[Any]) -> None:
        self._choices = list(choices)
        self._cursor = 0
        self._combined_mulligan = False
        self._combined_mulligan_charge = None

    def _answer(self, request: dict[str, Any]) -> Any:
        if self._cursor >= len(self._choices):
            raise ChoiceRequired(request)
        value = self._choices[self._cursor]
        self._cursor += 1
        return value

    def choose_card(
        self,
        engine: GameEngine,
        player: int,
        candidates: Iterable[int],
        purpose: str,
        *,
        source_uid: int | None = None,
    ) -> int | None:
        choices = list(candidates)
        if not choices:
            return None
        title, explanation = PURPOSE_PROMPTS.get(
            purpose,
            ("Scegli una carta", "Seleziona uno dei bersagli evidenziati per continuare."),
        )
        if purpose == "charge" and source_uid is not None:
            source_name = engine.definition(source_uid).name
            title = f"{source_name}: scegli una carta da Caricare"
            explanation = (
                "La carta scelta lascia la Mano e diventa una tua Carica privata: "
                "non viene scartata nel Vuoto."
            )
        allow_skip = purpose in {
            "effect_source",
            "optional_corrupt",
            "optional_remove_stasis",
            "sigil_state",
        }
        answer = self._answer(
            {
                "kind": "card",
                "purpose": purpose,
                "prompt": title,
                "explanation": explanation,
                "candidate_uids": choices,
                "source_uid": source_uid,
                "allow_skip": allow_skip,
                "context": engine.current_replay_action_label,
            }
        )
        if answer is None and allow_skip:
            return None
        answer = int(answer)
        if answer not in choices:
            raise ValueError("La carta selezionata non e' un bersaglio valido.")
        return answer

    def choose_mulligan(
        self,
        engine: GameEngine,
        player: int,
        *,
        initial: bool = False,
    ) -> list[int]:
        hand = list(engine.players[player].hand)
        allow_charge = engine.can_charge_during_mulligan(player, initial=initial)
        answer = self._answer(
            {
                "kind": "multi_card",
                "purpose": "mulligan",
                "prompt": "Scegli le carte da mulligare",
                "explanation": (
                    "Scegli le carte da cambiare. Puoi trasformarne una in Carica "
                    "soltanto nei Mulligan di fine turno mentre controlli un Glifo."
                ),
                "candidate_uids": hand,
                "minimum": 0,
                "maximum": len(hand),
                "allow_skip": True,
                "allow_charge": allow_charge,
            }
        )
        if isinstance(answer, dict):
            raw_selected = answer.get("mulligan_uids", [])
            raw_charge = answer.get("charge_uid")
            self._combined_mulligan = True
            self._combined_mulligan_charge = (
                int(raw_charge) if raw_charge is not None else None
            )
        else:
            raw_selected = answer or []
            self._combined_mulligan = False
            self._combined_mulligan_charge = None
        selected = [int(uid) for uid in raw_selected]
        if any(uid not in hand for uid in selected):
            raise ValueError("Il Mulligan contiene una carta non valida.")
        if (
            self._combined_mulligan_charge is not None
            and self._combined_mulligan_charge not in selected
        ):
            raise ValueError("La carta scelta come Carica deve essere inclusa nel Mulligan.")
        return list(dict.fromkeys(selected))

    def choose_mulligan_charge(
        self,
        engine: GameEngine,
        player: int,
        selected: Iterable[int],
    ) -> int | None:
        choices = list(selected)
        if not choices:
            return None
        if self._combined_mulligan:
            charged = self._combined_mulligan_charge
            self._combined_mulligan = False
            self._combined_mulligan_charge = None
            return charged
        answer = self._answer(
            {
                "kind": "card",
                "purpose": "charge_mulligan",
                "prompt": "Vuoi Caricare con una carta del Mulligan?",
                "explanation": "Puoi scegliere al massimo una delle carte che stai rimettendo nel Mazzo. La Carica sarà privata.",
                "candidate_uids": choices,
                "allow_skip": True,
            }
        )
        if answer is None:
            return None
        answer = int(answer)
        if answer not in choices:
            raise ValueError("La carta scelta come Carica non appartiene al Mulligan.")
        return answer

    def choose_esordio(self, engine: GameEngine, player: int, uid: int) -> str:
        answer = str(
            self._answer(
                {
                    "kind": "option",
                    "purpose": "esordio",
                    "prompt": f"Come vuoi usare {engine.definition(uid).name} con Esordio?",
                    "explanation": "Puoi giocarla gratuitamente come Maledizione o Preghiera, oppure tenerla in Mano.",
                    "options": ["Maledizione", "Preghiera", "Mano"],
                    "source_uid": uid,
                }
            )
        )
        if answer not in {"Maledizione", "Preghiera", "Mano"}:
            raise ValueError("Scelta Esordio non valida.")
        return answer

    def choose_mode(self, engine: GameEngine, player: int, uid: int, legal_modes: list[str]) -> str:
        answer = str(
            self._answer(
                {
                    "kind": "option",
                    "purpose": "mode",
                    "prompt": f"Come vuoi giocare {engine.definition(uid).name}?",
                    "explanation": "La carta e' stata giocata da un effetto: scegli la sua zona.",
                    "options": legal_modes,
                    "source_uid": uid,
                }
            )
        )
        if answer not in legal_modes:
            raise ValueError("Modalita' di gioco non valida.")
        return answer

    def choose_form(self, engine: GameEngine, player: int, target_uid: int) -> str:
        answer = str(
            self._answer(
                {
                    "kind": "option",
                    "purpose": "form",
                    "prompt": f"Scegli la nuova forma di {engine.definition(target_uid).name}",
                    "explanation": "La forma scelta sostituisce temporaneamente quella precedente.",
                    "options": ["Luce", "Ombra"],
                    "source_uid": target_uid,
                }
            )
        )
        if answer not in {"Luce", "Ombra"}:
            raise ValueError("Forma non valida.")
        return answer

    def choose_declared_form(
        self,
        engine: GameEngine,
        player: int,
        source_uid: int,
        options: list[str],
    ) -> str:
        answer = str(
            self._answer(
                {
                    "kind": "option",
                    "purpose": "declared_form",
                    "prompt": "Dichiara la Forma bloccata dal Sigillo",
                    "explanation": "Finché il Sigillo rimane aperto, l'avversario non potrà Calare carte della Forma scelta.",
                    "options": options,
                    "source_uid": source_uid,
                }
            )
        )
        if answer not in options:
            raise ValueError("Forma dichiarata non valida.")
        return answer

    def choose_option(
        self,
        engine: GameEngine,
        player: int,
        options: list[str | bool],
        purpose: str,
        *,
        source_uid: int | None = None,
    ) -> str | bool:
        prompts = {
            "stat_bonus": ("Scegli il potenziamento", "Decidi quale statistica modificare."),
            "spend_charges": ("Vuoi spendere le Cariche?", "Il beneficio si applica soltanto pagando il costo."),
            "toggle_corruption": ("Scegli lo stato", "Decidi se Purificare o Corrompere la Maledizione."),
            "recover_impulse": ("Vuoi prendere questa carta?", "Puoi pagare subito il costo indicato: la carta entrerà direttamente nella tua Mano."),
            "charge_broken": ("Vuoi Caricare con la carta Spezzata?", "Se scegli No, la carta raggiungerà il Vuoto."),
            "eye_direction": ("Scegli come modificare l'Occhio", "Puoi potenziare una tua carta oppure indebolire quella avversaria."),
            "open_sigil_after_attack": ("Vuoi spendere 1 Carica?", "Il costo viene pagato prima di scegliere quale tuo Sigillo aprire."),
            "pangolino_mode": ("Scegli come risolvere Pangolino", "Puoi convertire un tuo Sigillo o spezzare un Sigillo avversario."),
            "play_spent_charge": ("Vuoi giocare la Carica spesa?", "Notte della fioritura permette di giocare gratuitamente la prima carta spesa come Carica in questo turno."),
            "play_clessidra_as_prayer": ("Vuoi calare Clessidra di Zhares?", "Puoi spendere 1 Carica per giocarla subito e gratuitamente come Preghiera."),
            "take_removed_mark": ("Vuoi prendere il Marchio rimosso?", "Boato del Marchio può aggiungere alla tua Mano la carta che stava facendo da Marchio."),
        }
        prompt, explanation = prompts.get(purpose, ("Scegli come risolvere l'effetto", "Seleziona una delle opzioni disponibili."))
        answer = self._answer(
            {
                "kind": "confirm" if all(isinstance(option, bool) for option in options) else "option",
                "purpose": purpose,
                "prompt": prompt,
                "explanation": explanation,
                "options": options,
                "source_uid": source_uid,
            }
        )
        if answer not in options:
            raise ValueError("Opzione non valida.")
        return answer

    def choose_offer(self, engine: GameEngine, player: int, defender_uid: int) -> bool:
        return bool(
            self._answer(
                {
                    "kind": "confirm",
                    "purpose": "offer",
                    "prompt": f"Vuoi offrire {engine.definition(defender_uid).name} all'Altare?",
                    "explanation": "Offrendola, la tua Maledizione attaccante Blessa e guadagni il suo Karma in PV.",
                    "options": [True, False],
                    "source_uid": defender_uid,
                }
            )
        )

    def should_pay_purification(
        self,
        engine: GameEngine,
        player: int,
        source_uid: int,
        candidates: Iterable[int],
    ) -> bool:
        if engine.is_thunder_sand:
            prompt = "Vuoi spendere 1 Carica per purificare una Maledizione?"
            explanation = "Se scegli Sì, pagherai prima la Carica e poi sceglierai la Maledizione da Purificare."
        else:
            prompt = "Vuoi scartare una carta per purificare una Maledizione?"
            explanation = "Se scegli Sì, scarterai prima la carta e poi sceglierai la Maledizione da Purificare."
        return bool(
            self._answer(
                {
                    "kind": "confirm",
                    "purpose": "pay_purification",
                    "prompt": prompt,
                    "explanation": explanation,
                    "options": [True, False],
                    "source_uid": source_uid,
                }
            )
        )

    def should_prevent_glyph_break(
        self,
        engine: GameEngine,
        player: int,
        uid: int,
        reason: str,
    ) -> bool:
        return bool(
            self._answer(
                {
                    "kind": "confirm",
                    "purpose": "protect_glyph",
                    "prompt": f"Vuoi proteggere {engine.definition(uid).name}?",
                    "explanation": "Puoi spendere 1 Carica per evitare che il Glifo venga Spezzato.",
                    "options": [True, False],
                    "source_uid": uid,
                }
            )
        )

    def choose_fate(self, engine: GameEngine, player: int, source_uid: int) -> bool:
        answer = str(
            self._answer(
                {
                    "kind": "option",
                    "purpose": "fate",
                    "prompt": "Dichiara Pari o Dispari per Fato",
                    "explanation": "Il dado verra' lanciato dopo la tua dichiarazione.",
                    "options": ["Pari", "Dispari"],
                    "source_uid": source_uid,
                }
            )
        )
        if answer not in {"Pari", "Dispari"}:
            raise ValueError("Dichiarazione di Fato non valida.")
        return answer == "Pari"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class ManualGameSession:
    def __init__(self, config: Mapping[str, Any]):
        self.config = dict(config)
        self.tutorial = bool(self.config.get("tutorial", False))
        self.seed = int(self.config.get("seed", 20_260_810))
        self.bot_name = str(self.config.get("bot", "Bot"))
        self.deck_name = "Luce-Ombra" if self.tutorial else str(self.config.get("deck", "Luce-Ombra"))
        if self.bot_name not in BOT_NAMES:
            raise ValueError("Bot non valido.")
        learning_weights = self.config.get("learning_weights") or {}
        bot_weights = learning_weights.get(self.bot_name, {})
        human_model_weights = learning_weights.get("Bot", {})
        first_choice = "human" if self.tutorial else str(self.config.get("first_player", "human"))
        if first_choice == "random":
            first_player = self.seed % 2
        else:
            first_player = HUMAN_PLAYER if first_choice == "human" else BOT_PLAYER

        self.engine = GameEngine(
            self.seed,
            (self.bot_name, "Bot"),
            first_player=first_player,
            record_replay=True,
            auto_setup=False,
            bot_weights={self.bot_name: bot_weights},
            deck=self.deck_name,
        )
        self.engine.bot_names = (self.bot_name, "Umano")
        self.engine.bots[HUMAN_PLAYER] = HumanDecisionBot(human_model_weights)
        self.observer = make_bot("Bot", human_model_weights)
        self.transaction: dict[str, Any] | None = None
        self.preview_engine: GameEngine | None = None
        self.pending_request: dict[str, Any] | None = None
        self.last_action = "Preparazione della partita"
        self.action_counts: Counter[str] = Counter()
        self.choice_counts: Counter[str] = Counter()
        self.feature_gradient = {feature: 0.0 for feature in FEATURE_NAMES}
        self.feature_decisions = 0
        self.learning_payload: dict[str, Any] | None = None
        self.undo_snapshot: dict[str, Any] | None = None
        self.finished_replay_payload: dict[str, Any] | None = None

        if self.tutorial:
            self._prepare_tutorial_opening()
        else:
            for player in (BOT_PLAYER, HUMAN_PLAYER):
                self.engine.draw(player, 4, "mano iniziale")
        self._begin_operation({"kind": "setup"})

    def _prepare_tutorial_opening(self) -> None:
        """Prepara una partita reale ma ripetibile per il percorso guidato."""
        engine = self.engine
        for uid in (
            TUTORIAL_FIRST_CURSE,
            TUTORIAL_ECHO,
            TUTORIAL_MULLIGAN_CARD,
            TUTORIAL_OPTIONAL_CARD,
        ):
            engine.take_to_hand(uid, HUMAN_PLAYER, "mano del tutorial")
        for uid in (
            TUTORIAL_OPPONENT_CURSE,
            TUTORIAL_OPPONENT_EXTRA_CURSE,
            TUTORIAL_OPPONENT_PRAYER,
            3,
        ):
            engine.take_to_hand(uid, BOT_PLAYER, "mano del tutorial")

    @staticmethod
    def _put_tutorial_draws_on_top(engine: GameEngine, draw_order: Iterable[int]) -> None:
        """Rende certe solo le future pescate indispensabili alla lezione."""
        for uid in reversed(list(draw_order)):
            if uid in engine.players[HUMAN_PLAYER].hand:
                continue
            engine._remove_from_zone_list(uid)
            engine.reset_card_outside_field(uid, Zone.DECK, None)
            engine.deck.append(uid)

    # --------------------------------------------------------------
    # Transazioni ripetibili per le scelte nel mezzo degli effetti
    # --------------------------------------------------------------
    def _human_bot(self, engine: GameEngine) -> HumanDecisionBot:
        bot = engine.bots[HUMAN_PLAYER]
        if not isinstance(bot, HumanDecisionBot):
            raise RuntimeError("Controllore umano non disponibile.")
        return bot

    def _begin_operation(self, operation: dict[str, Any]) -> None:
        if self.transaction is not None:
            raise RuntimeError("C'e' gia' una scelta in corso.")
        self.transaction = {
            "base": copy.deepcopy(self.engine),
            "operation": operation,
            "choices": [],
            "decision_log": [],
        }
        self._attempt_operation()

    def _attempt_operation(self) -> None:
        if self.transaction is None:
            return
        working = copy.deepcopy(self.transaction["base"])
        self._human_bot(working).reset_choices(self.transaction["choices"])
        try:
            label = self._execute_operation(working, self.transaction["operation"])
        except ChoiceRequired as request:
            self.preview_engine = working
            self.pending_request = request.request
            return

        operation = self.transaction["operation"]
        decisions = list(self.transaction["decision_log"])
        self.engine = working
        self._human_bot(self.engine).reset_choices([])
        self.preview_engine = None
        self.pending_request = None
        self.transaction = None
        self.last_action = label
        for decision in decisions:
            self.choice_counts[str(decision.get("purpose", "scelta"))] += 1
        if operation["kind"] == "human_action":
            self._record_human_action(operation)

    def _execute_operation(self, engine: GameEngine, operation: Mapping[str, Any]) -> str:
        kind = str(operation["kind"])
        if kind == "setup":
            engine.perform_mulligan(HUMAN_PLAYER, initial=True)
            if not self.tutorial:
                engine.perform_mulligan(BOT_PLAYER, initial=True)
            if engine.is_thunder_sand:
                engine.resolve_esordio()
            engine.turn_number = 1
            engine.active_player = engine.first_player
            engine.phase = "Inizio turno"
            engine.emit(
                f"Inizia la partita. Il Giocatore {engine.active_player + 1} e' il primo giocatore."
            )
            engine.start_turn()
            return "Partita iniziata"
        if kind in {"start_turn", "human_start"}:
            engine.start_turn()
            return f"Inizio del turno {engine.turn_number}"
        if kind == "human_action":
            action = Action(**dict(operation["action"]))
            engine.execute_action(action, HUMAN_PLAYER)
            return action.label
        if kind in {"human_end", "forced_end"}:
            if kind == "human_end":
                action = Action("pass", cost=0, label="Termina il turno")
                engine.execute_action(action, HUMAN_PLAYER)
            if self.tutorial and engine.turn_number == 1:
                self._put_tutorial_draws_on_top(
                    engine,
                    (TUTORIAL_SECOND_CURSE, TUTORIAL_IMPULSE, TUTORIAL_BOND),
                )
            elif self.tutorial and engine.turn_number == 3:
                self._put_tutorial_draws_on_top(engine, (TUTORIAL_BOND,))
            engine.end_turn()
            return "Fine del tuo turno"
        if kind == "opponent_action":
            actions = engine.legal_actions(BOT_PLAYER)
            chosen = engine.bots[BOT_PLAYER].choose_action(engine, BOT_PLAYER, actions)
            engine.execute_action(chosen, BOT_PLAYER)
            return chosen.label
        if kind == "tutorial_opponent_action":
            action = Action(**dict(operation["action"]))
            engine.execute_action(action, BOT_PLAYER)
            return action.label
        if kind == "opponent_end":
            engine.end_turn()
            return "Fine del turno avversario"
        raise ValueError(f"Operazione manuale sconosciuta: {kind}")

    # --------------------------------------------------------------
    # Tutorial Luce-Ombra
    # --------------------------------------------------------------
    def _tutorial_expected_action_key(self, engine: GameEngine) -> str | None:
        if not self.tutorial or self.pending_request is not None:
            return None
        if engine.active_player != HUMAN_PLAYER or engine.phase != "Fase principale":
            return None
        human = engine.players[HUMAN_PLAYER]
        if engine.turn_number == 1:
            if TUTORIAL_FIRST_CURSE in human.hand:
                return "play_horizon"
            if TUTORIAL_ECHO in human.hand:
                return "play_echo"
            return "end_first_turn"
        if engine.turn_number == 3:
            if TUTORIAL_SECOND_CURSE in human.hand:
                return "play_second_curse"
            if engine.cards[TUTORIAL_ECHO].echo_used_turn != engine.turn_number:
                return "invoke_echo"
            if engine.cards[TUTORIAL_FIRST_CURSE].attacked_turn != engine.turn_number:
                return "first_combat"
            return "end_second_turn"
        if engine.turn_number >= 5:
            if TUTORIAL_OPPONENT_CURSE in engine.players[BOT_PLAYER].maledictions:
                return "bless_combat"
            if TUTORIAL_IMPULSE in human.hand:
                return "play_impulse"
            if TUTORIAL_BOND in human.hand:
                return "play_bond"
            if TUTORIAL_BOND in human.prayers:
                return "complete"
        return None

    @staticmethod
    def _tutorial_action_matches(action: Action, key: str | None) -> bool:
        expected: dict[str, tuple[str, int | None, int | None, str | None]] = {
            "play_horizon": ("play_malediction", TUTORIAL_FIRST_CURSE, None, "Maledizione"),
            "play_echo": ("play_prayer", TUTORIAL_ECHO, None, "Preghiera"),
            "play_second_curse": ("play_malediction", TUTORIAL_SECOND_CURSE, None, "Maledizione"),
            "invoke_echo": ("invoke", TUTORIAL_ECHO, None, None),
            "first_combat": ("attack", TUTORIAL_FIRST_CURSE, TUTORIAL_OPPONENT_CURSE, None),
            "bless_combat": ("attack", TUTORIAL_SECOND_CURSE, TUTORIAL_OPPONENT_CURSE, None),
            "play_impulse": ("play_prayer", TUTORIAL_IMPULSE, None, "Preghiera"),
            "play_bond": ("play_prayer", TUTORIAL_BOND, TUTORIAL_SECOND_CURSE, "Preghiera"),
        }
        if key not in expected:
            return False
        kind, card_uid, target_uid, mode = expected[key]
        return (
            action.kind == kind
            and action.card_uid == card_uid
            and action.target_uid == target_uid
            and (mode is None or action.mode == mode)
        )

    def _tutorial_opponent_action(self, engine: GameEngine) -> Action | None:
        actions = [action for action in engine.legal_actions(BOT_PLAYER) if action.kind != "pass"]
        if engine.turn_number == 2:
            scripted_plays = (
                ("play_malediction", TUTORIAL_OPPONENT_CURSE, None, "Maledizione"),
                ("play_malediction", TUTORIAL_OPPONENT_EXTRA_CURSE, None, "Maledizione"),
                ("play_prayer", TUTORIAL_OPPONENT_PRAYER, TUTORIAL_OPPONENT_EXTRA_CURSE, "Preghiera"),
            )
            for kind, card_uid, target_uid, mode in scripted_plays:
                if card_uid not in engine.players[BOT_PLAYER].hand:
                    continue
                return next(
                    (
                        action
                        for action in actions
                        if action.kind == kind
                        and action.card_uid == card_uid
                        and action.target_uid == target_uid
                        and action.mode == mode
                    ),
                    None,
                )
        if (
            engine.turn_number == 4
            and TUTORIAL_OPPONENT_CURSE in engine.players[BOT_PLAYER].maledictions
            and engine.cards[TUTORIAL_OPPONENT_CURSE].attacked_turn != engine.turn_number
        ):
            return next(
                (
                    action
                    for action in actions
                    if action.kind == "attack"
                    and action.card_uid == TUTORIAL_OPPONENT_CURSE
                    and action.target_uid == TUTORIAL_SECOND_CURSE
                ),
                None,
            )
        return None

    def _tutorial_guide(
        self,
        engine: GameEngine,
        request: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not self.tutorial:
            return None

        def guide(
            step: str,
            progress: int,
            title: str,
            body: str,
            instruction: str,
            *,
            focus: str = "table",
            focus_uids: list[int] | None = None,
            choice_uids: list[int] | None = None,
            choice_options: list[Any] | None = None,
            mulligan_uids: list[int] | None = None,
            mulligan_locked_uids: list[int] | None = None,
            allow_end_turn: bool = False,
            complete: bool = False,
        ) -> dict[str, Any]:
            return {
                "active": True,
                "step": step,
                "progress": progress,
                "total": 12,
                "title": title,
                "body": body,
                "instruction": instruction,
                "focus": focus,
                "focus_uids": focus_uids or [],
                "choice_uids": choice_uids,
                "choice_options": choice_options,
                "mulligan_uids": mulligan_uids,
                "mulligan_locked_uids": mulligan_locked_uids,
                "allow_end_turn": allow_end_turn,
                "complete": complete,
            }

        if request is not None:
            purpose = str(request.get("purpose", ""))
            if purpose == "mulligan":
                if engine.turn_number == 0:
                    return guide(
                        "initial_mulligan",
                        1,
                        "Prepara la mano con il Mulligan",
                        "Il Mulligan cambia le carte che non vuoi tenere. Puoi scegliere liberamente, tranne le carte contrassegnate come necessarie per la lezione.",
                        "Tieni Orizzonte e Re Luce; scegli liberamente se cambiare le altre due carte, poi conferma.",
                        focus="mulligan",
                        focus_uids=[TUTORIAL_FIRST_CURSE, TUTORIAL_ECHO],
                        mulligan_locked_uids=[TUTORIAL_FIRST_CURSE, TUTORIAL_ECHO],
                    )
                required = [
                    uid
                    for uid in (TUTORIAL_SECOND_CURSE, TUTORIAL_IMPULSE, TUTORIAL_BOND)
                    if uid in engine.players[HUMAN_PLAYER].hand
                ]
                return guide(
                    "end_turn_mulligan",
                    4 if engine.turn_number == 1 else 8,
                    "Il Mulligan conclude il turno",
                    "Alla fine del turno puoi cambiare qualunque numero di carte. Le carte necessarie ai prossimi passaggi restano protette, tutte le altre sono una tua scelta.",
                    "Mulliga liberamente le carte non protette, oppure tienile tutte, poi conferma.",
                    focus="mulligan",
                    mulligan_locked_uids=required,
                )
            if purpose == "buff_eye":
                invoking = engine.turn_number >= 3
                return guide(
                    "invoke_echo_target" if invoking else "echo_target",
                    7 if invoking else 3,
                    "Scegli il bersaglio dell'Eco",
                    "Re Luce dà +2 Occhio a una tua Maledizione Luce fino alla fine del prossimo turno. Il valore aggiornato sarà mostrato direttamente sulla carta.",
                    "Scegli Orizzonte.",
                    focus="field",
                    focus_uids=[TUTORIAL_FIRST_CURSE],
                    choice_uids=[TUTORIAL_FIRST_CURSE],
                )
            if purpose == "offer":
                return guide(
                    "offer_to_altar",
                    10,
                    "Offri la carta e Blessa",
                    "Tempio di Herset era già Corrotto e ha perso: ora può essere Spezzato. Se lo offri al tuo Altare, la Maledizione attaccante Blessa e ottieni Punti Vittoria pari al suo Karma.",
                    "Scegli Sì per offrire Tempio di Herset.",
                    focus="choice",
                    focus_uids=[TUTORIAL_OPPONENT_CURSE],
                    choice_options=[True],
                )
            if purpose == "break":
                return guide(
                    "impulse_target",
                    11,
                    "L'Impulso si risolve subito",
                    "Eclissi applica il suo effetto una sola volta e poi va nel Vuoto. Questo la distingue da Eco e Legame, che restano nella zona Preghiere.",
                    "Spezza Zoreo, la Preghiera avversaria, per completare l'effetto di Eclissi.",
                    focus="prayer",
                    focus_uids=[TUTORIAL_OPPONENT_PRAYER],
                    choice_uids=[TUTORIAL_OPPONENT_PRAYER],
                )
            if purpose == "attach_benefit":
                return guide(
                    "bond_target",
                    12,
                    "Lega la Preghiera alla Maledizione",
                    "Un Legame resta in campo ed è collegato a una Maledizione precisa. Il suo testo si applica soltanto alla carta a cui è legato.",
                    "Lega Mangrovia Celeste a Sole Vigilato.",
                    focus="field",
                    focus_uids=[TUTORIAL_SECOND_CURSE],
                    choice_uids=[TUTORIAL_SECOND_CURSE],
                )

        key = self._tutorial_expected_action_key(engine)
        if key == "play_horizon":
            return guide(
                key, 2, "CALO e Punti Vittoria alternativi",
                "CALO si attiva quando giochi una carta dalla Mano come Maledizione. Orizzonte ti fa guadagnare subito 1 Punto Vittoria: Blessare è il modo principale per fare punti, ma alcuni effetti permettono di ottenerli anche diversamente.",
                "Clicca Orizzonte e scegli Maledizione.",
                focus="hand", focus_uids=[TUTORIAL_FIRST_CURSE],
            )
        if key == "play_echo":
            return guide(
                key, 3, "Ora gioca Re Luce come Preghiera",
                "Una carta può essere giocata come Maledizione oppure come Preghiera: conta soltanto il testo della zona scelta. Come Eco, Re Luce resta nelle Preghiere e si attiva quando entra.",
                "Clicca Re Luce, scegli Preghiera e applica il suo effetto a Orizzonte.",
                focus="hand", focus_uids=[TUTORIAL_ECHO],
            )
        if key == "end_first_turn":
            return guide(
                key, 4, "Il primo turno è completo",
                "Il primo giocatore comincia con 2 Azioni: una è servita per Orizzonte e una per Re Luce. Orizzonte ha già assegnato 1 PV e ha ricevuto +2 Occhio dall'Eco.",
                "Premi Fine turno.",
                focus="end_turn", allow_end_turn=True,
            )
        if engine.active_player == BOT_PLAYER:
            if engine.turn_number == 2:
                prayer_played = TUTORIAL_OPPONENT_PRAYER in engine.players[BOT_PLAYER].prayers
                return guide(
                    "opponent_setup_done" if prayer_played else "opponent_setup",
                    5,
                    "L'avversario usa tutte e 3 le Azioni",
                    "Il bot cala Tempio di Herset e Ali di Mos come Maledizioni, poi gioca Zoreo come Preghiera Legame. Anche le Maledizioni avversarie entrano in Stasi e non possono attaccare subito.",
                    "Osserva le tre carte entrare nelle rispettive zone.",
                    focus="opponent", focus_uids=[TUTORIAL_OPPONENT_CURSE, TUTORIAL_OPPONENT_EXTRA_CURSE, TUTORIAL_OPPONENT_PRAYER],
                )
            if engine.turn_number == 4:
                attacked = engine.cards[TUTORIAL_OPPONENT_CURSE].attacked_turn == engine.turn_number
                return guide(
                    "opponent_combat_done" if attacked else "opponent_combat",
                    9,
                    "Una sconfitta non Spezza subito una carta Pura",
                    "Tempio attacca Sole Vigilato: 3 Occhio contro 1. Sole Vigilato era Puro, quindi non viene Spezzato ma diventa Corrotto. Al prossimo turno il suo effetto gli darà +3 Occhio.",
                    "Osserva lo scontro e il cambio di stato della carta.",
                    focus="field", focus_uids=[TUTORIAL_OPPONENT_CURSE, TUTORIAL_SECOND_CURSE],
                )
        if key == "play_second_curse":
            return guide(
                key, 6, "Le nuove Maledizioni entrano in Stasi",
                "Una Maledizione in Stasi non può attaccare. La Stasi viene rimossa automaticamente alla fine del turno, quindi la carta sarà pronta nel tuo turno successivo.",
                "Gioca Sole Vigilato come Maledizione.",
                focus="hand", focus_uids=[TUTORIAL_SECOND_CURSE],
            )
        if key == "invoke_echo":
            return guide(
                key, 7, "Invoca Re Luce",
                "Una Preghiera Eco resta in campo. Nei turni successivi puoi spendere 1 Azione per Invocarla e usare di nuovo il suo effetto.",
                "Clicca Re Luce sul campo, scegli Invoca Eco e applicalo di nuovo a Orizzonte.",
                focus="prayer", focus_uids=[TUTORIAL_ECHO],
            )
        if key == "first_combat":
            return guide(
                key, 8, "Dichiara il primo combattimento",
                "Orizzonte ha 7 Occhio grazie a Re Luce, contro i 3 di Tempio. Chi ha più Occhio vince. Una carta Pura sconfitta diventa Corrotta; una carta già Corrotta sconfitta viene Spezzata. In parità perdono entrambe.",
                "Attacca Tempio di Herset con Orizzonte.",
                focus="field", focus_uids=[TUTORIAL_FIRST_CURSE, TUTORIAL_OPPONENT_CURSE],
            )
        if key == "end_second_turn":
            return guide(
                key, 8, "Tempio di Herset è Corrotto",
                "Hai vinto 7 a 3. Tempio era Puro: è diventato Corrotto ma non è stato ancora Spezzato. Questo prepara la futura Blessatura.",
                "Premi Fine turno e conserva la Mano nel Mulligan.",
                focus="end_turn", focus_uids=[TUTORIAL_OPPONENT_CURSE], allow_end_turn=True,
            )
        if key == "bless_combat":
            return guide(
                key, 10, "Trasforma la vittoria in Punti Vittoria",
                "Sole Vigilato è Corrotto: il suo effetto porta il suo Occhio da 1 a 4. Può quindi battere Tempio, che è già Corrotto, e offrirlo all'Altare per Blessare.",
                "Attacca Tempio di Herset con Sole Vigilato.",
                focus="field", focus_uids=[TUTORIAL_SECOND_CURSE, TUTORIAL_OPPONENT_CURSE],
            )
        if key == "play_impulse":
            return guide(
                key, 11, "Hai Blessato e ottenuto altri 4 PV",
                "Ora hai 5 PV: 1 ottenuto con il CALO di Orizzonte e 4 con Bless. Eclissi è un Impulso: applica il suo effetto una volta e poi va nel Vuoto.",
                "Gioca Eclissi come Preghiera.",
                focus="hand", focus_uids=[TUTORIAL_IMPULSE],
            )
        if key == "play_bond":
            return guide(
                key, 12, "Termina con una Preghiera Legame",
                "Eclissi ha risolto il suo effetto ed è andata nel Vuoto. Un Legame, invece, resta visibile sotto la Maledizione scelta.",
                "Gioca Mangrovia Celeste come Preghiera e legala a Sole Vigilato.",
                focus="hand", focus_uids=[TUTORIAL_BOND],
            )
        if key == "complete":
            return guide(
                key, 12, "Tutorial completato",
                "Hai usato Mulligan, Azioni, CALO, Stasi, Eco, Invocazione, combattimento, Corruzione, Bless, Impulso e Legame. Hai anche ottenuto PV sia con Bless sia tramite l'effetto di una carta.",
                "Torna alla scelta della partita oppure avvia Luce · Ombra contro il Bot.",
                focus="complete", complete=True,
            )
        return guide(
            "transition",
            1,
            "Il tavolo si sta preparando",
            "Il tutorial usa le stesse regole e lo stesso motore della partita completa.",
            "Attendi la prossima mossa guidata.",
        )

    def _validate_tutorial_choice(self, value: Any) -> None:
        if not self.tutorial or self.pending_request is None:
            return
        engine = self.preview_engine or self.engine
        guide = self._tutorial_guide(engine, self.pending_request) or {}
        purpose = str(self.pending_request.get("purpose", ""))
        if purpose == "mulligan":
            raw = value.get("mulligan_uids", []) if isinstance(value, Mapping) else (value or [])
            selected = {int(uid) for uid in raw}
            locked = {int(uid) for uid in (guide.get("mulligan_locked_uids") or [])}
            if selected & locked:
                raise ValueError("Le carte protette servono per i prossimi passaggi del tutorial.")
            return
        allowed_uids = guide.get("choice_uids")
        if allowed_uids is not None and int(value) not in {int(uid) for uid in allowed_uids}:
            raise ValueError("Nel tutorial scegli il bersaglio evidenziato.")
        allowed_options = guide.get("choice_options")
        if allowed_options is not None and value not in allowed_options:
            raise ValueError("Nel tutorial scegli l'opzione indicata.")

    # --------------------------------------------------------------
    # Comandi pubblici
    # --------------------------------------------------------------
    def _remember_for_undo(self, label: str) -> None:
        """Conserva un solo stato completo, prima dell'ultima mossa umana."""
        self.undo_snapshot = {
            "engine": copy.deepcopy(self.engine),
            "observer": copy.deepcopy(self.observer),
            "last_action": self.last_action,
            "action_counts": copy.deepcopy(self.action_counts),
            "choice_counts": copy.deepcopy(self.choice_counts),
            "feature_gradient": dict(self.feature_gradient),
            "feature_decisions": self.feature_decisions,
            "learning_payload": copy.deepcopy(self.learning_payload),
            "label": label,
        }

    def undo_last_move(self) -> dict[str, Any]:
        if self.undo_snapshot is None or self.engine.game_over:
            raise ValueError("Non c'e' una mossa che puoi annullare adesso.")
        snapshot = self.undo_snapshot
        self.engine = copy.deepcopy(snapshot["engine"])
        self.observer = copy.deepcopy(snapshot["observer"])
        self.last_action = f"Mossa annullata: {snapshot['label']}"
        self.action_counts = copy.deepcopy(snapshot["action_counts"])
        self.choice_counts = copy.deepcopy(snapshot["choice_counts"])
        self.feature_gradient = dict(snapshot["feature_gradient"])
        self.feature_decisions = int(snapshot["feature_decisions"])
        self.learning_payload = copy.deepcopy(snapshot["learning_payload"])
        self.transaction = None
        self.preview_engine = None
        self.pending_request = None
        self.undo_snapshot = None
        self._human_bot(self.engine).reset_choices([])
        self.engine.last_attack = None
        self.engine.last_fate = None
        self.engine.last_impulse = None
        self.engine.emit(self.last_action + ".")
        return self.state()

    def submit_choice(self, value: Any) -> dict[str, Any]:
        if self.transaction is None or self.pending_request is None:
            raise ValueError("Non c'e' una scelta in attesa.")
        self._validate_tutorial_choice(value)
        request = dict(self.pending_request)
        operation_kind = str(self.transaction["operation"]["kind"])
        self.transaction["choices"].append(value)
        self.transaction["decision_log"].append(
            {"purpose": request.get("purpose"), "value": value}
        )
        self._attempt_operation()
        if (
            operation_kind == "human_action"
            and self.transaction is None
            and self.engine.force_end_turn
            and not self.engine.game_over
        ):
            self._begin_operation({"kind": "forced_end"})
        return self.state()

    def perform_action(self, action_id: str) -> dict[str, Any]:
        self._ensure_human_main_phase()
        actions = {
            self._action_id(action): action
            for action in self.engine.legal_actions(HUMAN_PLAYER)
            if action.kind != "pass"
        }
        action = actions.get(action_id)
        if action is None:
            raise ValueError("Questa Azione non e' piu' valida.")
        operation = {
            "kind": "human_action",
            "action": {
                "kind": action.kind,
                "card_uid": action.card_uid,
                "target_uid": action.target_uid,
                "mode": action.mode,
                "cost": action.cost,
                "label": action.label,
            },
            "learning": self._action_learning_payload(action),
        }
        self._remember_for_undo(action.label)
        self._begin_operation(operation)
        if self.transaction is None and self.engine.force_end_turn and not self.engine.game_over:
            self._begin_operation({"kind": "forced_end"})
        return self.state()

    def end_human_turn(self) -> dict[str, Any]:
        self._ensure_human_main_phase()
        if self.tutorial:
            guide = self._tutorial_guide(self.engine)
            if not guide or not guide.get("allow_end_turn"):
                raise ValueError("Completa prima la mossa indicata dal tutorial.")
        self._remember_for_undo("Fine turno")
        self._begin_operation({"kind": "human_end"})
        return self.state()

    def opponent_step(self) -> dict[str, Any]:
        if self.pending_request is not None:
            raise ValueError("Completa prima la scelta richiesta.")
        if self.engine.game_over:
            return self.state()
        if self.engine.active_player != BOT_PLAYER:
            raise ValueError("Non e' il turno del bot.")
        # Da questo momento il bot sta reagendo: la mossa umana precedente
        # non puo' piu' essere riscritta senza annullare anche informazioni nuove.
        self.undo_snapshot = None
        if self.engine.phase != "Fase principale":
            self._begin_operation({"kind": "start_turn"})
        elif self.engine.force_end_turn:
            self._begin_operation({"kind": "opponent_end"})
        elif self.tutorial:
            chosen = self._tutorial_opponent_action(self.engine)
            if chosen is None:
                self._begin_operation({"kind": "opponent_end"})
            else:
                self._begin_operation(
                    {
                        "kind": "tutorial_opponent_action",
                        "action": {
                            "kind": chosen.kind,
                            "card_uid": chosen.card_uid,
                            "target_uid": chosen.target_uid,
                            "mode": chosen.mode,
                            "cost": chosen.cost,
                            "label": chosen.label,
                        },
                    }
                )
        else:
            meaningful = [
                action for action in self.engine.legal_actions(BOT_PLAYER)
                if action.kind != "pass"
            ]
            if meaningful:
                self._begin_operation({"kind": "opponent_action"})
            else:
                self._begin_operation({"kind": "opponent_end"})
        return self.state()

    def start_human_turn(self) -> dict[str, Any]:
        if self.pending_request is not None:
            raise ValueError("Completa prima la scelta richiesta.")
        if self.engine.active_player != HUMAN_PLAYER:
            raise ValueError("Il turno umano non puo' iniziare adesso.")
        if self.engine.phase != "Fase principale":
            self._begin_operation({"kind": "human_start"})
        return self.state()

    def _ensure_human_main_phase(self) -> None:
        if self.pending_request is not None:
            raise ValueError("Completa prima la scelta richiesta.")
        if (
            self.engine.game_over
            or self.engine.active_player != HUMAN_PLAYER
            or self.engine.phase != "Fase principale"
        ):
            raise ValueError("Non puoi compiere questa Azione adesso.")

    # --------------------------------------------------------------
    # Profilo osservato e apprendimento per imitazione
    # --------------------------------------------------------------
    def _action_learning_payload(self, chosen: Action) -> dict[str, Any]:
        legal = [
            action for action in self.engine.legal_actions(HUMAN_PLAYER)
            if action.kind != "pass"
        ]
        chosen_features = self.observer._rough_action_features(
            self.engine,
            HUMAN_PLAYER,
            chosen,
        )
        alternatives = [
            self.observer._rough_action_features(self.engine, HUMAN_PLAYER, action)
            for action in legal
            if action != chosen
        ]
        baseline = {
            feature: (
                sum(vector[feature] for vector in alternatives) / len(alternatives)
                if alternatives
                else 0.0
            )
            for feature in FEATURE_NAMES
        }
        return {
            "kind": chosen.kind,
            "mode": chosen.mode,
            "chosen": chosen_features,
            "baseline": baseline,
        }

    def _record_human_action(self, operation: Mapping[str, Any]) -> None:
        payload = dict(operation.get("learning") or {})
        kind = str(payload.get("kind", "azione"))
        self.action_counts[kind] += 1
        chosen = payload.get("chosen") or {}
        baseline = payload.get("baseline") or {}
        for feature in FEATURE_NAMES:
            self.feature_gradient[feature] += float(chosen.get(feature, 0.0)) - float(
                baseline.get(feature, 0.0)
            )
        self.feature_decisions += 1

    def _human_learning(self) -> dict[str, Any]:
        if self.learning_payload is not None:
            return self.learning_payload
        winner = self.engine.winner
        won = winner == HUMAN_PLAYER
        draw = winner is None
        outcome_weight = 1.0 if won else (0.55 if draw else 0.25)
        # Le vittorie alimentano l'imitazione; un pareggio dà un segnale
        # piccolo, mentre una sconfitta allontana lievemente la politica dalle
        # scelte osservate. In questo modo il Bot non impara comunque una linea
        # perdente soltanto perché è stata giocata da un umano.
        imitation_signal = 1.0 if won else (0.25 if draw else -0.18)
        decisions = max(1, self.feature_decisions)
        base_delta = {
            feature: _clamp(
                0.052 * imitation_signal * self.feature_gradient[feature] / decisions,
                -0.08,
                0.08,
            )
            for feature in FEATURE_NAMES
        }

        telemetry = self.engine.telemetry
        modes = Counter()
        for values in telemetry.card_modes[HUMAN_PLAYER].values():
            modes.update(values)
        total_plays = modes["Maledizione"] + modes["Preghiera"]
        prayer_share = modes["Preghiera"] / total_plays if total_plays else 0.0
        base_delta["prayer_support"] += 0.035 * imitation_signal * (prayer_share - 0.30)
        base_delta["prayer_engine"] += 0.025 * imitation_signal * (prayer_share - 0.28)
        base_delta["curse_development"] += 0.025 * imitation_signal * (0.58 - prayer_share)

        bot_deltas = {
            "Bot": {
                feature: round(_clamp(base_delta[feature], -0.08, 0.08), 5)
                for feature in FEATURE_NAMES
            }
        }
        strongest = sorted(
            (
                {
                    "feature": feature,
                    "label": FEATURE_LABELS[feature],
                    "delta": round(base_delta[feature], 4),
                }
                for feature in FEATURE_NAMES
            ),
            key=lambda item: abs(item["delta"]),
            reverse=True,
        )[:5]
        self.learning_payload = {
            "outcome": "vittoria" if won else ("pareggio" if draw else "sconfitta"),
            "outcome_weight": outcome_weight,
            "weight_deltas": bot_deltas,
            "top_signals": strongest,
            "summary": {
                "actions": dict(self.action_counts),
                "choices": dict(self.choice_counts),
                "prayer_share": round(prayer_share * 100, 1),
                "own_eye_buffs": telemetry.own_eye_buffs[HUMAN_PLAYER],
                "high_karma_eye_buffs": telemetry.high_karma_eye_buffs[HUMAN_PLAYER],
                "enemy_eye_debuffs": telemetry.enemy_eye_debuffs[HUMAN_PLAYER],
                "invocations": telemetry.invocations[HUMAN_PLAYER],
                "opponent_invocations": telemetry.invocations[BOT_PLAYER],
                "glyph_uses": telemetry.glyph_uses[HUMAN_PLAYER],
                "opponent_glyph_uses": telemetry.glyph_uses[BOT_PLAYER],
                "charges_created": telemetry.charges_created[HUMAN_PLAYER],
                "opponent_charges_created": telemetry.charges_created[BOT_PLAYER],
                "score": self.engine.players[HUMAN_PLAYER].score,
                "opponent_score": self.engine.players[BOT_PLAYER].score,
            },
        }
        return self.learning_payload

    # --------------------------------------------------------------
    # Stato serializzabile per l'interfaccia
    # --------------------------------------------------------------
    @staticmethod
    def _action_id(action: Action) -> str:
        return ":".join(
            [
                action.kind,
                str(action.card_uid or ""),
                str(action.target_uid or ""),
                str(action.mode or ""),
                str(action.cost),
            ]
        )

    def _tactical_notes(self, engine: GameEngine, uid: int) -> list[dict[str, str]]:
        definition_id = engine.definition(uid).id
        card = engine.cards[uid]
        controller = card.controller
        notes: list[dict[str, str]] = []

        if engine.is_thunder_sand and definition_id in {5, 39} and controller is not None:
            targets = [
                target
                for target in engine.players[1 - controller].maledictions
                if engine.cards[target].attacked_turn >= 0
                and engine.cards[target].attacked_turn == engine.turn_number - 1
            ]
            if card.zone == Zone.MALEDICTION and engine.is_suppressed(uid):
                text = "Il suo effetto e' annullato: non ha Attacchi gratuiti."
            elif targets:
                names = ", ".join(engine.definition(target).name for target in targets)
                text = f"Può attaccare gratuitamente: {names}."
            else:
                text = "Nessuna Maledizione ha attaccato nel turno precedente."
            notes.append({"title": "Attacco gratuito", "text": text})

        if engine.is_thunder_sand and definition_id == 29 and controller is not None:
            targets = [
                target
                for target in engine.players[1 - controller].maledictions
                if engine.cards[target].corrupted
                and engine.cards[target].corrupted_turn >= 0
                and engine.cards[target].corrupted_turn < engine.turn_number
            ]
            if card.zone == Zone.MALEDICTION and engine.is_suppressed(uid):
                text = "Il suo effetto e' annullato: non ottiene la vittoria automatica."
            elif targets:
                names = ", ".join(engine.definition(target).name for target in targets)
                text = f"Se le attacca, vincerebbe contro: {names}."
            else:
                text = "Nessuna Maledizione avversaria è stata Corrotta in un turno precedente."
            notes.append({"title": "Condizione di vittoria", "text": text})

        if engine.is_thunder_sand and definition_id == 60:
            if card.zone == Zone.PRAYER:
                declared = card.declared_form
                if engine.sigil_is_active(uid) and declared:
                    text = f"Forma vietata: {declared}."
                    if controller == BOT_PLAYER:
                        blocked = [
                            target
                            for target in engine.players[HUMAN_PLAYER].hand
                            if declared in engine.forms(target)
                        ]
                        if blocked:
                            names = ", ".join(
                                f"{engine.definition(target).name} ({engine.definition(target).form.value})"
                                for target in blocked
                            )
                            text += f" Nella tua Mano non puoi Calare: {names}."
                        else:
                            text += " Nessuna carta nella tua Mano è attualmente bloccata."
                else:
                    text = "Il Sigillo è Chiuso o annullato: nessuna Forma è attualmente vietata."
            elif card.zone == Zone.HAND:
                text = "Come Sigillo, quando entra dovrai dichiarare Tuono oppure Sabbia."
            else:
                text = "La restrizione delle Forme si applica soltanto quando è un Sigillo Aperto."
            notes.append({"title": "Limitare del Mondo", "text": text})

        return notes

    def _card_payload(self, engine: GameEngine, uid: int, *, hidden: bool = False) -> dict[str, Any]:
        if hidden:
            return {"uid": uid, "hidden": True, "zone": engine.cards[uid].zone.value}
        definition = engine.definition(uid)
        payload = engine.card_summary(uid)
        payload.update(
            {
                "controller": engine.cards[uid].controller,
                "base_eye": definition.eye,
                "base_karma": definition.karma,
                "prayer_type": definition.prayer_type.value,
                "malediction_text": definition.malediction_text,
                "prayer_text": definition.prayer_text,
                "image": engine.image_path(uid),
                "tactical_notes": self._tactical_notes(engine, uid),
            }
        )
        return payload

    def _player_payload(self, engine: GameEngine, player: int) -> dict[str, Any]:
        state = engine.players[player]
        hide_hand = player == BOT_PLAYER
        hide_altar = player == BOT_PLAYER
        return {
            "id": player,
            "name": self.bot_name if player == BOT_PLAYER else "Tu",
            "score": state.score,
            "actions": state.actions,
            "hand": [
                self._card_payload(engine, uid, hidden=hide_hand)
                for uid in state.hand
            ],
            "maledictions": [self._card_payload(engine, uid) for uid in state.maledictions],
            "prayers": [self._card_payload(engine, uid) for uid in state.prayers],
            "altar": [
                self._card_payload(engine, uid, hidden=hide_altar)
                for uid in state.altar
            ],
            "altar_count": len(state.altar),
            "charges": [
                self._card_payload(engine, uid, hidden=hide_hand)
                for uid in state.charges
            ],
            "charges_count": len(state.charges),
        }

    def _legal_action_payload(self, engine: GameEngine) -> list[dict[str, Any]]:
        if (
            self.pending_request is not None
            or engine.game_over
            or engine.active_player != HUMAN_PLAYER
            or engine.phase != "Fase principale"
        ):
            return []
        result: list[dict[str, Any]] = []
        tutorial_key = self._tutorial_expected_action_key(engine) if self.tutorial else None
        for action in engine.legal_actions(HUMAN_PLAYER):
            if action.kind == "pass":
                continue
            if self.tutorial and not self._tutorial_action_matches(action, tutorial_key):
                continue
            payload: dict[str, Any] = {
                "id": self._action_id(action),
                "kind": action.kind,
                "card_uid": action.card_uid,
                "target_uid": action.target_uid,
                "mode": action.mode,
                "cost": action.cost,
                "label": action.label,
            }
            if action.kind == "attack" and action.card_uid is not None and action.target_uid is not None:
                preview = engine.simulate_combat_silently(action.card_uid, action.target_uid)
                preview["allowed"] = True
                preview["reason"] = "Bersaglio valido dopo la previsione dello scontro."
                payload["combat_preview"] = preview
            result.append(payload)
        return result

    def _combat_preview_payload(self, engine: GameEngine) -> list[dict[str, Any]]:
        if (
            self.pending_request is not None
            or engine.game_over
            or engine.active_player != HUMAN_PLAYER
            or engine.phase != "Fase principale"
        ):
            return []
        return [
            preview
            for attacker in engine.players[HUMAN_PLAYER].maledictions
            for preview in engine.attack_target_previews(HUMAN_PLAYER, attacker)
        ]

    def _public_history_message(self, engine: GameEngine, step: Any) -> str:
        """Nasconde soltanto le informazioni che appartengono alla mano del bot.

        Le carte giocate, Spezzate o scartate restano nominate perche' sono gia'
        informazioni pubbliche sul tavolo. Le pescate e i ritorni nella mano
        avversaria, invece, devono mostrare solo il movimento e non l'identita'.
        """
        message = str(step.message)
        draw_prefix = f"Il Giocatore {BOT_PLAYER + 1} prende "
        if message.startswith(draw_prefix):
            current_hand = len(step.snapshot["players"][BOT_PLAYER]["hand"])
            previous_hand = 0
            if step.index > 0:
                previous = engine.replay[step.index - 1]
                previous_hand = len(previous.snapshot["players"][BOT_PLAYER]["hand"])
            drawn = max(1, current_hand - previous_hand)
            noun = "carta" if drawn == 1 else "carte"
            reason_start = message.rfind(" (")
            reason = message[reason_start:-1] if reason_start >= 0 and message.endswith(".") else ""
            return f"Il bot pesca {drawn} {noun}{reason}."

        hidden_return = f" va nella mano del Giocatore {BOT_PLAYER + 1}"
        if hidden_return in message:
            _, suffix = message.split(hidden_return, 1)
            return f"Una carta va nella mano del bot{suffix}"
        return message

    def _finished_replay(self, engine: GameEngine) -> dict[str, Any]:
        if self.finished_replay_payload is None:
            trigger_won = (
                engine.winner == engine.final_trigger_player
                if engine.winner is not None and engine.final_trigger_player is not None
                else None
            )
            result = GameResult(
                seed=engine.seed,
                deck=engine.deck_name,
                bot_names=engine.bot_names,
                first_player=engine.first_player,
                winner=engine.winner,
                scores=(engine.players[0].score, engine.players[1].score),
                turns=engine.completed_turns,
                final_trigger_player=engine.final_trigger_player,
                final_trigger_cause=engine.final_trigger_cause,
                final_trigger_won=trigger_won,
                stalemate=engine.stalemate,
                telemetry=engine.telemetry,
                replay=engine.replay,
            )
            self.finished_replay_payload = replay_payload(result)
        return self.finished_replay_payload

    def _mode(self, engine: GameEngine) -> str:
        if engine.game_over:
            return "game_over"
        if self.pending_request is not None:
            return "choice"
        if engine.active_player == HUMAN_PLAYER:
            return "human_turn" if engine.phase == "Fase principale" else "human_start"
        return "opponent_turn" if engine.phase == "Fase principale" else "opponent_start"

    def state(self) -> dict[str, Any]:
        engine = self.preview_engine or self.engine
        request = dict(self.pending_request) if self.pending_request is not None else None
        tutorial_guide = self._tutorial_guide(engine, request)
        if request is not None:
            if tutorial_guide is not None:
                allowed_uids = tutorial_guide.get("choice_uids")
                if allowed_uids is not None and request.get("kind") == "card":
                    request["candidate_uids"] = [
                        int(uid)
                        for uid in request.get("candidate_uids", [])
                        if int(uid) in {int(item) for item in allowed_uids}
                    ]
                allowed_options = tutorial_guide.get("choice_options")
                if allowed_options is not None:
                    request["options"] = [
                        option for option in request.get("options", []) if option in allowed_options
                    ]
            request["candidates"] = [
                self._card_payload(engine, int(uid))
                for uid in request.get("candidate_uids", [])
                if int(uid) in engine.cards
            ]
            source_uid = request.get("source_uid")
            if source_uid is not None and int(source_uid) in engine.cards:
                request["source"] = self._card_payload(engine, int(source_uid))

        history = [
            {
                "index": step.index,
                "turn": step.turn,
                "player": step.active_player,
                "phase": step.phase,
                "message": self._public_history_message(engine, step),
                "action_index": step.action_index,
                "action_label": step.action_label,
            }
            for step in engine.replay[-120:]
        ]
        result = {
            "seed": self.seed,
            "deck": engine.deck_name,
            "deck_id": engine.deck_id,
            "mode": self._mode(engine),
            "turn": engine.turn_number,
            "active_player": engine.active_player,
            "human_player": HUMAN_PLAYER,
            "bot_player": BOT_PLAYER,
            "phase": engine.phase,
            "force_end_turn": engine.force_end_turn,
            "final_turns_remaining": engine.final_turns_remaining,
            "final_trigger_player": engine.final_trigger_player,
            "final_trigger_turn": engine.final_trigger_turn,
            "last_attack": copy.deepcopy(engine.last_attack),
            "last_fate": copy.deepcopy(engine.last_fate),
            "last_impulse": None,
            "deck_count": len(engine.deck),
            "void": [self._card_payload(engine, uid) for uid in reversed(engine.void)],
            "players": [
                self._player_payload(engine, BOT_PLAYER),
                self._player_payload(engine, HUMAN_PLAYER),
            ],
            "legal_actions": self._legal_action_payload(engine),
            "combat_previews": self._combat_preview_payload(engine),
            "choice": request,
            "history": history,
            "last_action": self.last_action,
            "can_undo": self.undo_snapshot is not None and not engine.game_over and not self.tutorial,
            "undo_label": self.undo_snapshot.get("label") if self.undo_snapshot is not None and not self.tutorial else None,
            "winner": engine.winner,
            "game_over": engine.game_over,
        }
        if tutorial_guide is not None:
            result["tutorial"] = tutorial_guide
        if engine.last_impulse is not None:
            impulse = copy.deepcopy(engine.last_impulse)
            impulse["card"] = self._card_payload(engine, int(impulse["card_uid"]))
            result["last_impulse"] = impulse
        if engine.game_over and self.preview_engine is None:
            result["learning"] = self._human_learning()
            result["replay"] = self._finished_replay(engine)
        return result


def create_manual_session(config_json: str) -> ManualGameSession:
    return ManualGameSession(json.loads(config_json))
