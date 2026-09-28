from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Mapping

from .model import Action, PrayerType, Zone

if TYPE_CHECKING:
    from .engine import GameEngine


FEATURE_LABELS: dict[str, str] = {
    "bless_points": "Punti Bless immediati",
    "high_karma_bless": "Bless con Karma alto",
    "future_bless": "Preparazione di un Bless futuro",
    "corruption_setup": "Corruzione preparata",
    "combat_control": "Controllo degli scontri",
    "curse_development": "Sviluppo delle Maledizioni",
    "prayer_support": "Supporto delle Preghiere",
    "protection": "Protezione delle proprie carte",
    "tempo": "Velocita' di chiusura",
    "action_efficiency": "Efficienza delle Azioni",
    "replacement_cost": "Costo di sostituzione",
    "exposure_risk": "Rischio concesso all'avversario",
    "pass_waste": "Azioni non utilizzate",
    "stasis_followup": "Stasi seguita da attacco",
    "position_gain": "Vantaggio complessivo di posizione",
    "effect_relevance": "Effetto realmente applicabile",
    "combo_setup": "Combinazioni e setup futuri",
    "prayer_engine": "Uso coordinato di Impulso ed Eco",
    "eye_karma_setup": "Occhio aggiunto a Maledizioni di Karma alto",
    "next_turn_plan": "Piano dopo la risposta avversaria",
}

FEATURE_NAMES = tuple(FEATURE_LABELS)


@dataclass(frozen=True, slots=True)
class BotProfile:
    name: str
    style: str
    feature_weights: Mapping[str, float] = field(default_factory=dict)
    eye_weight: float = 1.0
    karma_weight: float = 1.2
    prayer_weight: float = 1.0
    board_weight: float = 1.0
    score_weight: float = 2.0
    aggression: float = 1.0
    control: float = 1.0
    risk: float = 0.2
    exploration: float = 0.04
    lookahead_candidates: int = 3
    lookahead_rounds: int = 1


PROFILES: dict[str, BotProfile] = {
    "Bot": BotProfile(
        name="Bot",
        style="stratega",
        # Profilo unico: conserva il ritmo dell'Aggressivo e la capacita' di
        # preparare Preghiere, Bless ad alto Karma e risposte del turno seguente
        # dello Stratega. I pesi appresi dagli umani si sommano a questa base.
        eye_weight=1.18,
        karma_weight=1.46,
        prayer_weight=1.22,
        score_weight=2.55,
        aggression=1.20,
        control=1.24,
        risk=0.16,
        exploration=0.04,
        lookahead_candidates=3,
        lookahead_rounds=1,
        feature_weights={
            "bless_points": 2.66,
            "high_karma_bless": 1.76,
            "future_bless": 1.62,
            "corruption_setup": 1.42,
            "combat_control": 1.18,
            "curse_development": 1.30,
            "prayer_support": 1.18,
            "protection": 1.27,
            "tempo": 1.16,
            "action_efficiency": 1.12,
            "replacement_cost": -2.30,
            "exposure_risk": -1.22,
            "pass_waste": -2.86,
            "stasis_followup": 1.42,
            "position_gain": 0.62,
            "effect_relevance": 1.62,
            "combo_setup": 1.52,
            "prayer_engine": 1.30,
            "eye_karma_setup": 1.78,
            "next_turn_plan": 1.52,
        },
    ),
}


def _blank_features() -> dict[str, float]:
    return {name: 0.0 for name in FEATURE_NAMES}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class StrategicBot:
    """Bot a obiettivi con un piccolo pianificatore tattico e pesi apprendibili."""

    def __init__(self, profile: BotProfile, learned_weights: Mapping[str, float] | None = None):
        self.profile = profile
        self.name = profile.name
        learned = learned_weights or {}
        self.learned_weights = {
            feature: _clamp(float(learned.get(feature, 0.0)), -1.5, 1.5)
            for feature in FEATURE_NAMES
        }
        self.weights = {
            feature: float(profile.feature_weights.get(feature, 0.0)) + self.learned_weights[feature]
            for feature in FEATURE_NAMES
        }
        self.intent_turn = -1
        self.intent_attacker_uid: int | None = None
        self.lookahead_turn = -1
        self.lookahead_rounds_used = 0
        self.support_actions_turn = 0

    # ------------------------------------------------------------------
    # Decisione delle azioni
    # ------------------------------------------------------------------
    def choose_action(self, engine: GameEngine, player: int, actions: list[Action]) -> Action:
        actions = self._policy_actions(engine, player, actions)
        if len(actions) <= 1:
            return actions[0]
        if self.intent_turn != engine.turn_number:
            self.intent_turn = engine.turn_number
            self.intent_attacker_uid = None
            self.lookahead_turn = engine.turn_number
            self.lookahead_rounds_used = 0
            self.support_actions_turn = 0

        features = {action: self._rough_action_features(engine, player, action) for action in actions}
        rough_scores = {action: self._score(vector) for action, vector in features.items()}

        # La previsione fino al turno seguente confronta anche il miglior
        # attacco con la migliore linea di Preghiera: altrimenti solo le carte
        # riceverebbero il valore della risposta avversaria simulata.
        refinable = [
            action
            for action in actions
            if action.kind in {
                "attack",
                "attack_direct",
                "play_malediction",
                "play_prayer",
                "invoke",
                "use_glyph",
                "sigil_remove_stasis",
            }
        ]
        refinable.sort(key=lambda action: rough_scores[action], reverse=True)
        lookahead = self.profile.lookahead_candidates
        if self.lookahead_turn != engine.turn_number:
            self.lookahead_turn = engine.turn_number
            self.lookahead_rounds_used = 0
        if self.lookahead_rounds_used >= self.profile.lookahead_rounds:
            lookahead = 0

        selected: list[Action] = []
        if refinable and lookahead:
            # Lo Stratega mette sempre a confronto il miglior piano di
            # Preghiera e il miglior attacco credibile.
            selected.append(refinable[0])
            prayer_candidates = [
                action for action in refinable
                if action.kind in {"play_prayer", "invoke", "use_glyph"}
            ]
            if self.profile.style == "stratega":
                attack_candidates = [
                    action for action in refinable
                    if action.kind in {"attack", "attack_direct"}
                ]
                opposite = (
                    attack_candidates
                    if selected[0].kind in {"play_prayer", "invoke", "use_glyph"}
                    else prayer_candidates
                )
                if opposite and opposite[0] not in selected and len(selected) < lookahead:
                    selected.append(opposite[0])
            elif prayer_candidates and prayer_candidates[0] not in selected and len(selected) < lookahead:
                selected.append(prayer_candidates[0])
            for candidate in refinable:
                if len(selected) >= lookahead:
                    break
                if candidate not in selected:
                    selected.append(candidate)
        if selected:
            self.lookahead_rounds_used += 1
        for action in selected:
            features[action] = self._refine_with_clone(engine, player, action, features[action])

        scored = sorted(
            ((self._score(vector), action) for action, vector in features.items()),
            key=lambda item: item[0],
            reverse=True,
        )
        best_score = scored[0][0]
        credible = [item for item in scored if item[0] >= best_score - 2.4][:6]

        chosen: Action
        exploratory = [
            item for item in credible[1:4]
            if item[1].kind != "pass" and item[0] >= best_score - 1.65
        ]
        if exploratory and engine.rng.random() < self.profile.exploration:
            chosen = engine.rng.choice(exploratory)[1]
        else:
            tolerance = 0.08 if self.profile.style == "stratega" else 0.14
            finalists = [action for score, action in credible if score >= best_score - tolerance]
            chosen = engine.rng.choice(finalists)

        comparison = _blank_features()
        alternatives = [vector for action, vector in features.items() if action != chosen]
        if alternatives:
            # Il confronto apprende rispetto alle migliori alternative, non a
            # mosse manifestamente illegittime o senza senso.
            comparison_actions = [action for _, action in credible if action != chosen]
            comparison_vectors = [features[action] for action in comparison_actions] or alternatives
            for feature in FEATURE_NAMES:
                comparison[feature] = sum(vector[feature] for vector in comparison_vectors) / len(comparison_vectors)
        engine.telemetry.record_learning_decision(
            player,
            chosen.kind,
            features[chosen],
            comparison,
        )

        if chosen.kind == "remove_stasis":
            self.intent_attacker_uid = chosen.card_uid
        elif chosen.kind in {"attack", "attack_direct"}:
            if chosen.card_uid == self.intent_attacker_uid:
                self.intent_attacker_uid = None
        elif chosen.kind == "pass":
            self.intent_attacker_uid = None
        if chosen.kind in {"play_prayer", "invoke", "use_glyph"}:
            self.support_actions_turn += 1
        return chosen

    def _policy_actions(
        self,
        engine: GameEngine,
        player: int,
        actions: list[Action],
    ) -> list[Action]:
        """Rimuove linee formalmente legali ma contrarie all'obiettivo del bot."""
        filtered: list[Action] = []
        for action in actions:
            if (
                action.kind == "play_prayer"
                and action.card_uid is not None
                and action.target_uid is not None
                and engine.cards[action.target_uid].controller != player
                and engine.definition(action.card_uid).prayer_type == PrayerType.BOND
                and engine.definition(action.card_uid).id not in {36, 60}
            ):
                # Questi Legami aumentano statistiche o proteggono: il bot non
                # li regala mai a una Maledizione avversaria. Ali di Som e
                # Cancelli di Mezzo restano eccezioni tattiche non assimilabili
                # a un semplice potenziamento d'Occhio.
                continue
            filtered.append(action)
        return filtered or [Action("pass", cost=0, label="Termina il turno")]

    def _score(self, features: Mapping[str, float]) -> float:
        return sum(self.weights[name] * float(features.get(name, 0.0)) for name in FEATURE_NAMES)

    def _rough_action_features(self, engine: GameEngine, player: int, action: Action) -> dict[str, float]:
        features = _blank_features()
        state = engine.players[player]
        opponent = 1 - player

        if action.kind == "pass":
            features["pass_waste"] = float(max(1, state.actions))
            return features

        features["action_efficiency"] = 1.0 + (0.65 if action.cost == 0 else 0.0)
        if action.card_uid is None:
            return features

        uid = action.card_uid
        definition = engine.definition(uid)

        if action.kind == "play_malediction":
            effect_value, relevance, setup = self._malediction_context(engine, player, uid)
            raw_value = (
                definition.eye * self.profile.eye_weight
                + definition.karma * self.profile.karma_weight
                + effect_value
            )
            board_count = len(state.maledictions)
            scarcity_bonus = {0: 4.0, 1: 2.7, 2: 1.35, 3: 0.35}.get(board_count, 0.0)
            features["curse_development"] = 0.70 + raw_value / 6.8 + scarcity_bonus
            features["tempo"] = 0.70
            features["effect_relevance"] = relevance
            features["combo_setup"] = setup
            features["next_turn_plan"] = setup * 0.28
            corrupted_targets = [
                target for target in engine.players[opponent].maledictions
                if engine.cards[target].corrupted
            ]
            if corrupted_targets:
                likely_wins = sum(
                    engine.predict_combat(uid, target) in {"attacker_win", "tie", "fato"}
                    for target in corrupted_targets
                )
                features["future_bless"] += (definition.karma / 4.0) * min(1.0, likely_wins)
            if engine.used_malediction_slots(player) + engine.malediction_weight(uid) > 4:
                removable = [target for target in state.maledictions if not engine.cards[target].corrupted]
                weakest = min((engine.card_value(target, player) for target in removable), default=raw_value)
                improvement = raw_value - weakest
                features["replacement_cost"] = 0.85 + max(0.0, -improvement) / 5.0
                features["curse_development"] += max(0.0, improvement) / 5.0
            return features

        if action.kind == "play_prayer":
            board_count = len(state.maledictions)
            readiness = {0: 0.30, 1: 0.58, 2: 0.82}.get(board_count, 1.0)
            relevance, setup, prayer_engine = self._prayer_context(engine, player, action)
            eye_setup, next_eye_setup = self._eye_prayer_plan(engine, player, action)
            features["prayer_support"] = readiness * (
                0.62 + engine.prayer_effect_value(uid) / 3.6
            )
            features["future_bless"] = readiness * (0.20 + definition.karma / 20.0)
            features["protection"] = 0.20
            features["exposure_risk"] = max(0, 2 - board_count) * 0.72
            features["effect_relevance"] = relevance
            features["combo_setup"] = setup
            features["prayer_engine"] = prayer_engine
            features["eye_karma_setup"] = _clamp(eye_setup, -1.8, 3.2)
            features["next_turn_plan"] = _clamp(next_eye_setup, -1.2, 1.8)
            if eye_setup > 0:
                # Evita di contare tre volte lo stesso +Occhio: il valore
                # principale e' gia' espresso da eye_karma_setup.
                features["prayer_support"] *= 0.72
                features["prayer_engine"] *= 0.68
            if self.support_actions_turn >= 1 and action.cost > 0:
                immediate_conversion = (
                    eye_setup >= 1.0
                    and state.actions - action.cost >= 1
                )
                if not immediate_conversion:
                    features["prayer_support"] *= 0.28
                    features["prayer_engine"] *= 0.28
                    features["combo_setup"] *= 0.45
                    features["exposure_risk"] += 1.25
            if definition.prayer_type == PrayerType.ECHO:
                features["prayer_support"] += 0.40
            elif definition.prayer_type == PrayerType.BOND:
                features["prayer_support"] += 0.20
            elif engine.is_thunder_sand and definition.prayer_type == PrayerType.GLYPH:
                has_glyph = any(
                    engine.definition(prayer).prayer_type == PrayerType.GLYPH
                    for prayer in state.prayers
                )
                # Il valore di un Glifo comprende la nuova economia di Cariche
                # che abilita a ogni fine turno. Questo rende credibile calarlo
                # come motore, anziche' scegliere quasi sempre il lato
                # Maledizione della stessa carta.
                features["prayer_support"] += 0.85 + (0.45 if not has_glyph else 0.0)
                features["combo_setup"] += 0.52
                features["next_turn_plan"] += 1.05 + (0.35 if not has_glyph else 0.0)
            if action.target_uid is not None:
                target = engine.cards[action.target_uid]
                target_value = engine.card_value(action.target_uid, player) / 8.0
                if target.controller == player:
                    features["protection"] += 0.35 + target_value
                    features["future_bless"] += max(0.0, engine.karma(action.target_uid)) / 12.0
                else:
                    # Quasi tutti i Legami sono potenziamenti: collegarli a una
                    # Maledizione avversaria è normalmente un regalo, salvo i
                    # pochi casi in cui la forma o il Karma sono il vero piano.
                    if definition.id in {36, 60}:
                        features["combat_control"] += 0.18 + target_value * 0.18
                    else:
                        features["exposure_risk"] += 0.65 + target_value * 0.45
            return features

        if action.kind in {"invoke", "use_glyph"}:
            relevance, setup, prayer_engine = self._prayer_context(engine, player, action)
            eye_setup, next_eye_setup = self._eye_prayer_plan(engine, player, action)
            features["prayer_support"] = 0.90 + engine.prayer_effect_value(uid) / 3.0
            features["future_bless"] = 0.35
            features["effect_relevance"] = relevance
            features["combo_setup"] = setup
            features["prayer_engine"] = prayer_engine
            features["eye_karma_setup"] = _clamp(eye_setup, -1.8, 3.2)
            features["next_turn_plan"] = _clamp(next_eye_setup, -1.2, 1.8)
            if eye_setup > 0:
                features["prayer_support"] *= 0.72
                features["prayer_engine"] *= 0.68
            if self.support_actions_turn >= 1 and action.cost > 0:
                immediate_conversion = (
                    eye_setup >= 1.0
                    and state.actions - action.cost >= 1
                )
                if not immediate_conversion:
                    features["prayer_support"] *= 0.28
                    features["prayer_engine"] *= 0.28
                    features["combo_setup"] *= 0.45
                    features["exposure_risk"] += 1.25
            return features

        if action.kind == "sigil_remove_stasis" and action.target_uid is not None:
            followup = self._best_attack_value(engine, player, action.target_uid)
            if followup > 0:
                features["stasis_followup"] = 0.75 + followup
                features["future_bless"] = 0.42 * followup
                features["action_efficiency"] += 0.55
            else:
                features["pass_waste"] = 1.5
            return features

        if action.kind == "remove_stasis":
            followup = self._best_attack_value(engine, player, uid)
            if state.actions - action.cost >= 1 and followup > 0:
                features["stasis_followup"] = 0.8 + followup
                features["future_bless"] = followup * 0.45
                features["tempo"] = 0.40
            else:
                features["pass_waste"] = 1.8
                features["exposure_risk"] = 0.35
            return features

        if action.kind == "attack_direct":
            karma = engine.karma(uid)
            features["bless_points"] = float(karma)
            features["high_karma_bless"] = karma * karma / 5.0
            features["tempo"] = 1.55 + karma / 5.0
            if uid == self.intent_attacker_uid:
                features["stasis_followup"] = 1.35
            return features

        if action.kind == "attack" and action.target_uid is not None:
            target_uid = action.target_uid
            target = engine.cards[target_uid]
            outcome = engine.predict_combat(uid, target_uid)
            win_probability = 0.5 if outcome == "fato" else float(outcome in {"attacker_win", "tie"})
            loses_probability = 0.5 if outcome == "fato" else float(outcome in {"defender_win", "tie"})
            target_loses_probability = win_probability
            own_karma = engine.karma(uid)
            own_value = engine.card_value(uid, player)
            target_value = engine.card_value(target_uid, player)

            features["tempo"] = 0.72 + 0.48 * win_probability
            features["combat_control"] = target_loses_probability * (0.45 + target_value / 7.5)

            if target.corrupted and target_loses_probability > 0:
                expected = own_karma * target_loses_probability
                features["bless_points"] = expected
                features["high_karma_bless"] = expected * own_karma / 5.0
                features["tempo"] += 0.65

                # Lo Stratega puo' rinviare un Bless piccolo se una propria
                # Maledizione molto piu' redditizia e' quasi pronta.
                highest_karma = max(
                    (engine.karma(card_uid) for card_uid in state.maledictions),
                    default=own_karma,
                )
                if self.profile.style == "stratega" and highest_karma >= own_karma + 2:
                    features["future_bless"] += (highest_karma - own_karma) * 0.48
                    features["tempo"] -= 0.35
            elif not target.corrupted:
                features["corruption_setup"] = 1.15 + target_value / 10.0
                best_future_karma = max(
                    (engine.karma(card_uid) for card_uid in state.maledictions),
                    default=own_karma,
                )
                features["future_bless"] += 0.45 + best_future_karma / 6.0
                if engine.has_ability(uid, "impatto"):
                    features["bless_points"] += own_karma
                    features["high_karma_bless"] += own_karma * own_karma / 5.0

            if loses_probability > 0 and not engine.cards[uid].corrupted:
                # Perdere contro una pura e' una preparazione consapevole; il
                # costo e' l'esposizione della propria carta appena corrotta.
                features["exposure_risk"] = loses_probability * (0.55 + own_value / 9.0)
                if not target.corrupted:
                    features["corruption_setup"] += 0.45
            elif loses_probability > 0:
                features["exposure_risk"] = loses_probability * (0.9 + own_value / 7.0)

            if uid == self.intent_attacker_uid:
                features["stasis_followup"] = 1.45
            return features

        return features

    def _malediction_context(
        self,
        engine: GameEngine,
        player: int,
        uid: int,
    ) -> tuple[float, float, float]:
        """Valore dell'effetto stampato nello stato reale, non nel vuoto.

        Le tabelle delle carte restano il punto di partenza, ma una condizione
        non soddisfatta non può valere come se fosse già attiva. Il terzo
        valore premia invece una condizione costruibile nei turni successivi.
        """
        definition_id = engine.definition(uid).id
        state = engine.players[player]
        opponent = engine.players[1 - player]
        if engine.is_thunder_sand:
            definition = engine.definition(uid)
            printed = engine.malediction_effect_value(uid)
            text = definition.malediction_text.lower()
            relevance = 0.45
            setup = 0.30
            if "cadenza" in text:
                relevance += 0.95
                setup += 0.45
            if "emblema" in text:
                setup += 0.55 + 0.15 * definition.karma
            if "colosso" in text:
                relevance += 0.55 if state.actions >= 2 else -0.65
                setup += 0.50
            if "schermatura" in text:
                relevance += 0.30 + 0.18 * len(state.maledictions)
            if "carica" in text:
                setup += 0.18 * engine.effective_charge_count(player)
            if "march" in text:
                setup += 0.28 * sum(engine.is_marked(target) for target in engine.all_field_cards())
            if "calo" in text and not state.maledictions and definition_id not in {1, 11}:
                relevance -= 0.25
            if any(engine.cards[target].corrupted for target in opponent.maledictions):
                relevance += 0.18 * definition.karma
            return printed, relevance, setup
        projected = list(state.maledictions)
        if uid not in projected:
            projected.append(uid)

        printed = engine.malediction_effect_value(uid)
        effect_value = printed
        relevance = 0.16
        setup = 0.0

        if definition_id in {21, 59}:
            corrupted = [target for target in state.maledictions if engine.cards[target].corrupted]
            if corrupted:
                best = max(engine.card_value(target, player) for target in corrupted)
                relevance = 0.85 + best / 12.0
                setup = 0.35
            else:
                # Il CALO è facoltativo: senza bersaglio non si scarta e il
                # valore dell'effetto immediato è quasi nullo.
                effect_value = printed * 0.12
                relevance = -1.20
                setup = 0.18 if state.maledictions else 0.0

        elif definition_id in {22, 39}:
            required = "Luce" if definition_id == 22 else "Ombra"
            incompatible = [target for target in projected if required not in engine.forms(target)]
            if not incompatible:
                relevance = 0.85 + 0.24 * len(projected)
                setup = 0.42 * len(projected)

                # Se l'Obelisco sarebbe la prima Maledizione del campo, il
                # suo bonus non viene valutato isolatamente: anticipiamo la
                # seconda carta che il bot vorrebbe calare nello stesso turno.
                # Evita piani autocontraddittori come Obelisco del Buio seguito
                # da Orizzonte, che spegne immediatamente il +2 Occhio.
                if len(projected) == 1 and state.actions >= 2:
                    companions = [card_uid for card_uid in state.hand if card_uid != uid]
                    if companions:
                        def companion_value(card_uid: int) -> float:
                            companion = engine.definition(card_uid)
                            return (
                                companion.eye * self.profile.eye_weight
                                + companion.karma * self.profile.karma_weight
                                + engine.malediction_effect_value(card_uid)
                            )

                        likely_companion = max(companions, key=companion_value)
                        if required not in engine.forms(likely_companion):
                            effect_value = printed * 0.12
                            relevance = -1.08
                            setup = 0.0
            else:
                effect_value = 0.0
                relevance = -0.92 - 0.18 * len(incompatible)
                # Crepuscolo Eco può trasformare una carta e riaccendere il
                # piano monocolore: è un setup possibile, non un bonus attivo.
                has_form_tool = any(
                    engine.definition(card_uid).id == 59
                    for card_uid in state.hand + state.prayers
                )
                setup = 0.35 if has_form_tool and len(incompatible) == 1 else 0.0

        elif definition_id in {7, 36}:
            visible_targets = [
                target for target in opponent.maledictions
                if engine.eye(target) >= 6
            ]
            if visible_targets:
                relevance = 0.85 + 0.18 * len(visible_targets)
                setup = 0.42
            else:
                effect_value = printed * 0.55
                relevance = 0.10
                setup = 0.34

        elif definition_id in {1, 30}:
            required = "Luce" if definition_id == 1 else "Ombra"
            matching = [target for target in opponent.maledictions if required in engine.forms(target)]
            relevance = 0.90 if matching else -0.18
            effect_value = printed if matching else printed * 0.48
            setup = 0.24

        elif definition_id in {3, 32}:
            required = "Ombra" if definition_id == 3 else "Luce"
            count = sum(required in engine.forms(target) for target in projected)
            active = count == 1
            effect_value = printed if active else printed * 0.12
            relevance = 0.78 if active else -0.62
            setup = 0.30 if count <= 1 else 0.0

        elif definition_id == 15:
            other_lights = [
                target for target in projected
                if target != uid and "Luce" in engine.forms(target)
            ]
            active = not other_lights
            effect_value = printed if active else printed * 0.10
            relevance = 0.82 if active else -0.68
            setup = 0.28 if active else 0.0

        elif definition_id == 25:
            light_prayers = sum("Luce" in engine.forms(prayer) for prayer in state.prayers)
            effect_value = printed * min(1.4, 0.22 + 0.42 * light_prayers)
            relevance = 0.22 + 0.38 * light_prayers
            setup = 0.35 * light_prayers

        elif definition_id == 42:
            other_shadows = sum(
                target != uid and "Ombra" in engine.forms(target)
                for target in engine.all_field_cards()
            )
            effect_value = printed * min(1.5, 0.28 + 0.28 * other_shadows)
            relevance = 0.18 + 0.22 * other_shadows
            setup = 0.24 * min(3, other_shadows)

        elif definition_id == 50:
            other_shadows = [
                target for target in projected
                if target != uid and "Ombra" in engine.forms(target)
            ]
            active = not other_shadows
            effect_value = printed if active else printed * 0.18
            relevance = 0.72 if active else -0.42

        elif definition_id == 6:
            excess = len(opponent.maledictions) - len(projected)
            if excess > 0:
                relevance = 0.95 + 0.35 * excess
            else:
                effect_value = printed * 0.15
                relevance = -0.72

        elif definition_id == 12:
            if opponent.hand:
                relevance = 0.78
            else:
                effect_value = printed * 0.10
                relevance = -0.75

        elif definition_id == 23:
            relevance = 1.05

        elif definition_id == 26:
            light_prayers = [
                card_uid for card_uid in state.hand
                if card_uid != uid and "Luce" in engine.forms(card_uid)
            ]
            if light_prayers:
                relevance = 1.05
                setup = 0.50
            else:
                effect_value = printed * 0.18
                relevance = -0.70

        elif definition_id == 46:
            ready_echoes = [
                prayer for prayer in state.prayers
                if engine.definition(prayer).prayer_type == PrayerType.ECHO
                and engine.cards[prayer].echo_used_turn != engine.turn_number
            ]
            if ready_echoes:
                relevance = 1.05 + 0.20 * len(ready_echoes)
                setup = 0.75 + 0.22 * len(ready_echoes)
            else:
                effect_value = printed * 0.14
                relevance = -0.78

        elif definition_id == 56:
            valid_void = [target for target in engine.void if engine.original_eye(target) >= 4]
            if valid_void:
                relevance = 0.85
                setup = 0.35
            else:
                effect_value = printed * 0.15
                relevance = -0.68

        elif definition_id in {28, 44}:
            relevance = 0.58
            setup = 0.72

        return effect_value, relevance, setup

    def _prayer_context(
        self,
        engine: GameEngine,
        player: int,
        action: Action,
    ) -> tuple[float, float, float]:
        """Applicabilità e valore di motore della Preghiera nello stato attuale."""
        if action.card_uid is None:
            return 0.0, 0.0, 0.0
        uid = action.card_uid
        definition = engine.definition(uid)
        definition_id = definition.id
        state = engine.players[player]
        opponent = engine.players[1 - player]
        own_maledictions = list(state.maledictions)
        enemy_maledictions = list(opponent.maledictions)
        own_prayers = list(state.prayers)
        enemy_prayers = list(opponent.prayers)
        field = engine.all_field_cards()

        if engine.is_thunder_sand:
            scale = engine.prayer_effect_value(uid)
            charges = engine.effective_charge_count(player)
            if definition.prayer_type == PrayerType.SIGIL:
                replacement = any(
                    engine.definition(prayer).prayer_type == PrayerType.SIGIL
                    for prayer in own_prayers
                    if prayer != uid
                )
                active_bonus = 0.55 if action.kind == "invoke" else 0.35
                return (
                    0.55 + scale / 12.0 - (0.55 if replacement else 0.0),
                    0.95 + active_bonus,
                    1.05 + scale / 8.0,
                )
            if definition.prayer_type == PrayerType.GLYPH:
                cost = engine.glyph_cost(uid)
                usable = charges >= cost
                marked = sum(engine.is_marked(target) for target in field)
                controlled_glyphs = [
                    prayer
                    for prayer in own_prayers
                    if prayer != uid
                    and engine.definition(prayer).prayer_type == PrayerType.GLYPH
                ]
                if action.kind == "use_glyph":
                    relevance = 1.05 if usable else -0.65
                    return relevance, 1.00 + 0.24 * marked, 1.28 + scale / 7.0

                # Un Glifo messo in campo abilita la Carica nel Mulligan di
                # fine turno. Valutiamo quindi anche la Carica che il bot puo'
                # preparare subito dopo, invece di scartare il piano soltanto
                # perche' al momento non ha ancora la risorsa da spendere.
                charge_next_mulligan = 1
                usable_next_turn = charges + charge_next_mulligan >= cost
                relevance = 0.74 if usable_next_turn else 0.28
                setup = 1.22 + 0.24 * marked
                engine_value = 1.34 + scale / 7.5
                if not controlled_glyphs:
                    relevance += 0.42
                    setup += 0.58
                elif all(engine.definition(prayer).id != definition_id for prayer in controlled_glyphs):
                    # Il bot deve poter cambiare Glifo quando il nuovo effetto
                    # apre un piano diverso, non restare bloccato sull'Esordio.
                    setup += 0.32
                if cost > charges and usable_next_turn:
                    engine_value += 0.38
                return relevance, setup, engine_value

            text = definition.prayer_text.lower()
            relevance = 0.48 + scale / 14.0
            setup = 0.30
            engine_value = 0.45
            if "occhio" in text or "karma" in text or "emblema" in text:
                relevance += 0.28 if own_maledictions else -0.65
                setup += 0.45
            if "spezza" in text:
                relevance += 0.20 if field else -0.70
            if "corrompi" in text:
                relevance += 0.25 if any(not engine.cards[target].corrupted for target in engine.all_maledictions()) else -0.55
            if "carica" in text:
                setup += 0.22
                engine_value += 0.22
            if "march" in text:
                setup += 0.35
            return relevance, setup, engine_value

        if definition.prayer_type == PrayerType.BOND:
            if action.target_uid is None:
                return -1.2, 0.0, -0.5
            target = engine.cards[action.target_uid]
            own_target = target.controller == player
            forms = engine.forms(action.target_uid)
            condition_live = True
            if definition_id == 2:
                condition_live = "Luce" in forms
            elif definition_id == 31:
                condition_live = "Ombra" in forms
            elif definition_id in {7, 19, 49}:
                condition_live = target.corrupted
            elif definition_id == 21:
                condition_live = bool(enemy_maledictions)
            elif definition_id == 47:
                condition_live = any(
                    engine.original_eye(other) > engine.original_eye(action.target_uid)
                    for other in engine.all_maledictions()
                )
            elif definition_id == 50:
                condition_live = (
                    "Ombra" in forms
                    and sum("Ombra" in engine.forms(other) for other in own_maledictions) == 1
                )

            if own_target:
                relevance = 0.62 if condition_live else -0.08
                setup = 0.68 + (0.28 if condition_live else 0.48)
                engine_value = 0.46
                if definition_id in {13, 48}:
                    ready_echoes = sum(
                        engine.definition(prayer).prayer_type == PrayerType.ECHO
                        and engine.cards[prayer].echo_used_turn != engine.turn_number
                        for prayer in own_prayers
                    )
                    setup += 0.45 * ready_echoes
                    engine_value += 0.38 * ready_echoes
                return relevance, setup, engine_value

            if definition_id == 60:
                return 0.18, 0.48, 0.25
            if definition_id == 36:
                return -0.18, 0.22, 0.10
            return -1.05, -0.25, -0.48

        live, future = self._prayer_effect_live(engine, player, definition_id, action)
        eye_effect_ids = {1, 4, 14, 15, 16, 23, 24, 30, 38, 40, 42, 45, 52}
        if definition_id in eye_effect_ids:
            eye_now, eye_future = self._eye_prayer_plan(engine, player, action)
            live = eye_now >= 0.50 or eye_future >= 0.70
            future = max(future * (1.0 if live else 0.35), eye_future * 0.42)
        effect_scale = engine.prayer_effect_value(uid)
        if definition.prayer_type == PrayerType.ECHO:
            if action.kind == "invoke":
                if live:
                    return 0.90 + effect_scale / 10.0, 0.35 + future, 1.15 + effect_scale / 7.0
                return -1.55, future * 0.25, -0.78
            if live:
                return 0.58 + effect_scale / 13.0, 0.78 + future, 1.02 + effect_scale / 8.0
            # Un'Eco rimane in campo: può essere un investimento, ma l'uso
            # immediato a vuoto resta un costo reale.
            return -0.48, 0.45 + future, 0.38

        if live:
            return 0.72 + effect_scale / 11.0, 0.28 + future, 0.78 + effect_scale / 7.5
        return -1.28, future * 0.20, -0.62

    def _eye_prayer_plan(
        self,
        engine: GameEngine,
        player: int,
        action: Action,
    ) -> tuple[float, float]:
        """Valuta la conversione Occhio -> Bless ora e dopo il turno avversario."""
        if action.card_uid is None:
            return 0.0, 0.0
        source_uid = action.card_uid
        definition = engine.definition(source_uid)
        definition_id = definition.id
        state = engine.players[player]
        own_maledictions = list(state.maledictions)
        enemy_maledictions = list(engine.players[1 - player].maledictions)

        if engine.is_thunder_sand:
            def gain_for(target: int) -> int:
                if definition_id in {5, 24}:
                    return 2
                if definition_id == 9:
                    return 2 if "Tuono" in engine.forms(target) else 0
                if definition_id == 28:
                    return 1 if "Tuono" in engine.forms(target) else 0
                if definition_id == 36:
                    return 1 if "Sabbia" in engine.forms(target) else 0
                if definition_id == 57:
                    return (
                        2
                        if engine.definition(target).prayer_type == PrayerType.GLYPH
                        else 0
                    )
                if definition_id in {18, 27}:
                    if engine.cards[target].corrupted and not engine.has_ability(target, "emblema"):
                        return engine.eye(target)
                    return 0
                return 0

            best = max(
                (
                    self._eye_conversion_value(engine, player, target, gain_for(target))
                    for target in own_maledictions
                ),
                default=0.0,
            )
            future = best * (0.55 if definition.prayer_type in {PrayerType.SIGIL, PrayerType.GLYPH} else 0.22)
            return best, future

        if definition.prayer_type == PrayerType.BOND:
            target = action.target_uid
            if target is None or engine.cards[target].controller != player:
                return -1.8, -0.8
            gain = self._bond_eye_gain(engine, player, target, source_uid)
            if gain <= 0:
                return 0.0, 0.20
            value = self._eye_conversion_value(engine, player, target, gain)
            can_attack_now = (
                state.actions - action.cost >= 1
                and not engine.cards[target].stasis
                and engine.cards[target].attacked_turn != engine.turn_number
            )
            # Il Legame resta sul tavolo e viene quindi valutato soprattutto
            # come piano resistente alla risposta dell'avversario.
            return value if can_attack_now else value * 0.16, 0.42 + value * 0.46

        if definition_id in {23, 38, 40}:
            watched_form = (
                "Luce" if definition_id == 23
                else ("Ombra" if definition_id == 38 else None)
            )
            reduction = 2
            best = 0.0
            for attacker in own_maledictions:
                if watched_form is not None and watched_form not in engine.forms(attacker):
                    continue
                for target in enemy_maledictions:
                    if engine.cannot_be_attacked(target, attacker):
                        continue
                    if definition_id == 40:
                        reduction = max(0, engine.original_eye(target) - 3)
                    if reduction <= 0:
                        continue
                    before = engine.predict_combat(attacker, target)
                    attacker_eye = engine.combat_eye(attacker, target)
                    defender_eye = engine.projected_defender_eye(attacker, target)
                    karma = engine.karma(attacker)
                    swing = before not in {"attacker_win", "tie"} and attacker_eye >= defender_eye - reduction
                    target_value = (
                        1.20 + 0.62 * karma
                        if engine.cards[target].corrupted
                        else 0.42 + 0.18 * karma
                    )
                    can_attack_now = (
                        state.actions - action.cost >= 1
                        and not engine.cards[attacker].stasis
                        and engine.cards[attacker].attacked_turn != engine.turn_number
                    )
                    immediate_scale = 1.0 if can_attack_now else 0.14
                    best = max(
                        best,
                        target_value * (1.0 if swing else 0.12) * immediate_scale,
                    )
            if definition_id == 40:
                return 0.0, best + (0.25 if best else 0.0)
            future = (
                best * 0.42 + 0.24
                if action.kind == "play_prayer" and definition.prayer_type == PrayerType.ECHO
                else 0.0
            )
            return best, future

        target_specs: list[tuple[int, int]] = []
        if definition_id in {1, 30}:
            required = "Luce" if definition_id == 1 else "Ombra"
            target_specs = [
                (target, 2)
                for target in own_maledictions
                if required in engine.forms(target)
            ]
        elif definition_id == 4:
            gain = max(
                0,
                len(engine.all_prayers()) - int(source_uid in engine.all_prayers()),
            )
            target_specs = [(target, gain) for target in own_maledictions]
        elif definition_id == 14:
            target_specs = [(target, 1) for target in own_maledictions]
        elif definition_id == 15:
            target_specs = [
                (target, 2)
                for target in own_maledictions
                if engine.cards[target].corrupted
            ]
        elif definition_id == 16:
            target_specs = [(target, 2) for target in own_maledictions]
        elif definition_id in {24, 52}:
            required = "Luce" if definition_id == 24 else "Ombra"
            target_specs = [
                (target, 1)
                for target in own_maledictions
                if required in engine.forms(target)
            ]
        elif definition_id == 42:
            target_specs = [
                (
                    target,
                    self._estimated_eye_gain(engine, player, source_uid, target),
                )
                for target in own_maledictions
            ]
        elif definition_id == 45:
            gain = len(enemy_maledictions)
            target_specs = [(target, gain) for target in own_maledictions]

        potential_values = sorted(
            [
                (
                    self._eye_conversion_value(engine, player, target, gain),
                    target,
                )
                for target, gain in target_specs
                if gain > 0
            ],
            reverse=True,
        )
        if not potential_values:
            return 0.0, 0.0
        immediate_values = sorted(
            (
                value
                if (
                    state.actions - action.cost >= 1
                    and not engine.cards[target].stasis
                    and engine.cards[target].attacked_turn != engine.turn_number
                )
                else value * 0.14
                for value, target in potential_values
            ),
            reverse=True,
        )
        immediate = (
            sum(immediate_values[:2])
            if definition_id in {14, 15, 24, 52}
            else immediate_values[0]
        )
        best_potential = potential_values[0][0]
        lasting_ids = {1, 14, 24, 30, 45, 52}
        if action.kind == "play_prayer" and definition.prayer_type == PrayerType.ECHO:
            echo_future = 0.34 * best_potential + 0.24
        elif action.kind == "invoke" and definition_id in lasting_ids:
            echo_future = 0.25 * best_potential
        else:
            echo_future = 0.0
        return immediate, echo_future

    def _eye_conversion_value(
        self,
        engine: GameEngine,
        player: int,
        attacker_uid: int,
        gain: int,
    ) -> float:
        if gain <= 0 or engine.cards[attacker_uid].zone != Zone.MALEDICTION:
            return 0.0
        eye = engine.eye(attacker_uid)
        karma = engine.karma(attacker_uid)
        low_eye = max(0, 6 - eye)
        value = gain * (0.05 + 0.045 * karma + 0.025 * low_eye)
        opponent = 1 - player
        for target in engine.players[opponent].maledictions:
            if engine.cannot_be_attacked(target, attacker_uid):
                continue
            outcome = engine.predict_combat(attacker_uid, target)
            if outcome in {"attacker_win", "tie"}:
                continue
            attacker_eye = engine.combat_eye(attacker_uid, target)
            defender_eye = engine.projected_defender_eye(attacker_uid, target)
            if attacker_eye + gain < defender_eye:
                continue
            if engine.cards[target].corrupted:
                value += 1.35 + 0.68 * karma
            else:
                value += 0.42 + 0.20 * karma
        return value

    def _prayer_effect_live(
        self,
        engine: GameEngine,
        player: int,
        definition_id: int,
        action: Action,
    ) -> tuple[bool, float]:
        """Dice se Impulso/Eco produce ora un risultato utile e quanto prepara il futuro."""
        state = engine.players[player]
        opponent = engine.players[1 - player]
        own_maledictions = list(state.maledictions)
        enemy_maledictions = list(opponent.maledictions)
        own_prayers = list(state.prayers)
        enemy_prayers = list(opponent.prayers)
        field = engine.all_field_cards()

        if definition_id in {1, 30}:
            required = "Luce" if definition_id == 1 else "Ombra"
            return any(required in engine.forms(target) for target in own_maledictions), 0.52
        if definition_id == 4:
            other_prayers = sum(prayer != action.card_uid for prayer in engine.all_prayers())
            return bool(own_maledictions and other_prayers), 0.48
        if definition_id in {5, 17, 33, 37}:
            return bool(enemy_prayers), 0.18
        if definition_id == 6:
            return bool(enemy_prayers), 0.22
        if definition_id == 8:
            return bool(enemy_maledictions), 0.45
        if definition_id == 9:
            return bool(own_maledictions), 0.50
        if definition_id == 10:
            return bool(own_prayers) or action.kind == "play_prayer", 0.42
        if definition_id in {11, 46}:
            sources = [
                target for target in own_maledictions
                if engine.definition(target).prayer_type in {PrayerType.ECHO, PrayerType.IMPULSE}
                and not engine.is_suppressed(target)
            ]
            return bool(sources), 0.62 if sources else 0.18
        if definition_id == 12:
            remaining_actions = state.actions - action.cost
            return bool(engine.deck) and remaining_actions <= 0, 0.22
        if definition_id == 14:
            return bool(own_maledictions), 0.58
        if definition_id == 15:
            return any(engine.cards[target].corrupted for target in own_maledictions), 0.38
        if definition_id == 16:
            return bool(own_maledictions), 0.48
        if definition_id == 18:
            return (
                any(not engine.cards[target].corrupted for target in own_maledictions)
                and bool(field),
                0.46,
            )
        if definition_id in {20, 41}:
            return bool(enemy_maledictions), 0.34
        if definition_id in {22, 39}:
            broken_form = "Ombra" if definition_id == 22 else "Luce"
            enemy_value = sum(
                engine.card_value(target, player)
                for target in enemy_maledictions
                if broken_form in engine.forms(target)
            )
            own_value = sum(
                engine.card_value(target, player)
                for target in own_maledictions
                if broken_form in engine.forms(target)
            )
            return enemy_value > own_value + 0.5, 0.12
        if definition_id in {23, 38}:
            attacking_form = "Luce" if definition_id == 23 else "Ombra"
            attackers = [target for target in own_maledictions if attacking_form in engine.forms(target)]
            return bool(attackers and enemy_maledictions), 0.58
        if definition_id in {24, 52}:
            own_form = "Luce" if definition_id == 24 else "Ombra"
            return any(own_form in engine.forms(target) for target in own_maledictions), 0.55
        if definition_id in {27, 43}:
            target_form = "Luce" if definition_id == 27 else "Ombra"
            return any(target_form in engine.forms(target) for target in own_maledictions), 0.55
        if definition_id in {28, 44}:
            return bool(engine.deck), 0.72
        if definition_id == 29:
            return any("Luce" in engine.forms(target) for target in engine.void), 0.32
        if definition_id == 34:
            return bool(enemy_maledictions), 0.18
        if definition_id == 35:
            return (
                bool(own_maledictions and enemy_maledictions)
                and any(not engine.cards[target].corrupted for target in own_maledictions + enemy_maledictions),
                0.42,
            )
        if definition_id == 40:
            useful_targets = [
                target for target in enemy_maledictions
                if engine.original_eye(target) > 3
            ]
            return bool(useful_targets), 0.42
        if definition_id == 42:
            has_reference = any(
                target != action.card_uid and "Ombra" in engine.forms(target)
                for target in own_maledictions + own_prayers
            )
            return bool((own_maledictions or enemy_maledictions) and has_reference), 0.52
        if definition_id == 45:
            return bool(own_maledictions and enemy_maledictions), 0.62
        if definition_id == 51:
            other_prayers = [
                target for target in state.hand
                if target != action.card_uid
                and engine.definition(target).prayer_type in {PrayerType.IMPULSE, PrayerType.ECHO, PrayerType.BOND}
            ]
            return state.actions - action.cost > 0 and bool(other_prayers), 0.80 if len(other_prayers) >= 2 else 0.35
        if definition_id == 54:
            return len(own_maledictions) < len(enemy_maledictions) and bool(engine.void), 0.34
        if definition_id == 55:
            return bool(enemy_maledictions), 0.25
        if definition_id == 56:
            return any(engine.cards[target].stasis for target in own_maledictions), 0.48
        if definition_id == 57:
            return bool(engine.deck), 0.40
        if definition_id == 58:
            return any("Ombra" in engine.forms(target) for target in engine.void), 0.34
        if definition_id == 59:
            form_payoffs = any(
                engine.definition(target).id in {1, 3, 15, 22, 30, 32, 39, 42, 50}
                for target in own_maledictions + state.hand
            )
            return bool(field and form_payoffs), 0.82 if form_payoffs else 0.28
        if definition_id == 61:
            own_pure = any(not engine.cards[target].corrupted for target in own_maledictions)
            return len(enemy_maledictions) >= 2 and own_pure, 0.48
        if definition_id == 62:
            return bool(own_maledictions), 0.52
        return bool(field), 0.24

    def _setup_potential(self, engine: GameEngine, player: int) -> float:
        """Misura piani già costruiti che possono convertire Azioni future in Bless."""
        state = engine.players[player]
        opponent = engine.players[1 - player]
        score = self._best_bless_potential(engine, player) * 0.42

        if engine.is_thunder_sand:
            score += 0.32 * engine.effective_charge_count(player)
            score += 0.42 * sum(engine.is_marked(target) for target in opponent.maledictions)
            score += 0.48 * sum(
                engine.definition(prayer).prayer_type in {PrayerType.SIGIL, PrayerType.GLYPH}
                for prayer in state.prayers
            )
            return score

        enemy_corrupted = sum(engine.cards[target].corrupted for target in opponent.maledictions)
        best_karma = max((engine.karma(target) for target in state.maledictions), default=0)
        score += enemy_corrupted * best_karma * 0.16

        echoes = [
            prayer for prayer in state.prayers
            if engine.definition(prayer).prayer_type == PrayerType.ECHO
        ]
        ready_echoes = [
            prayer for prayer in echoes
            if engine.cards[prayer].echo_used_turn != engine.turn_number
        ]
        score += 0.48 * len(echoes) + 0.20 * len(ready_echoes)

        conversion_targets = [
            target
            for target in state.maledictions
            if engine.karma(target) >= 3 and engine.eye(target) <= 4
        ]
        eye_echo_ids = {1, 4, 14, 15, 16, 23, 24, 30, 38, 42, 45, 52}
        eye_echoes = [
            prayer
            for prayer in echoes
            if engine.definition(prayer).id in eye_echo_ids
        ]
        if conversion_targets and eye_echoes:
            score += 0.72 + 0.22 * min(3, len(conversion_targets))
        if conversion_targets and any(
            engine.definition(card_uid).id in eye_echo_ids
            for card_uid in state.hand
        ):
            score += 0.48

        hand_ids = {engine.definition(target).id for target in state.hand}
        if echoes and ({13, 46} & hand_ids):
            score += 1.05
        if 51 in hand_ids:
            prayer_cards = sum(
                engine.definition(target).prayer_type in {PrayerType.IMPULSE, PrayerType.ECHO, PrayerType.BOND}
                for target in state.hand
            )
            score += max(0, prayer_cards - 1) * 0.38
        if any(engine.definition(target).id == 13 for target in state.maledictions) and ready_echoes:
            bond_cards = sum(engine.definition(target).prayer_type == PrayerType.BOND for target in state.hand)
            score += min(1.4, bond_cards * 0.48)

        for obelisk_id, required in ((22, "Luce"), (39, "Ombra")):
            if any(engine.definition(target).id == obelisk_id for target in state.maledictions):
                matching = sum(required in engine.forms(target) for target in state.maledictions)
                if matching == len(state.maledictions):
                    score += 0.52 * matching

        return score

    def _refine_with_clone(
        self,
        engine: GameEngine,
        player: int,
        action: Action,
        rough: Mapping[str, float],
    ) -> dict[str, float]:
        features = dict(rough)
        opponent = 1 - player
        before_position = engine.evaluate_position(player)
        before_score = engine.players[player].score
        before_altar = len(engine.players[player].altar)
        before_enemy_corrupted = sum(
            engine.cards[uid].corrupted for uid in engine.players[opponent].maledictions
        )
        before_threat = self._opponent_bless_threat(engine, player)
        before_future = self._best_bless_potential(engine, player)
        before_setup = self._setup_potential(engine, player)

        clone = engine.clone_for_search(observer_player=player)
        clone.execute_action(action, player, from_search=True)
        if action.kind in {"play_prayer", "invoke"}:
            clone.bots[player].support_actions_turn += 1

        score_gain = clone.players[player].score - before_score
        altar_gain = len(clone.players[player].altar) - before_altar
        enemy_corrupted_gain = sum(
            clone.cards[uid].corrupted for uid in clone.players[opponent].maledictions
        ) - before_enemy_corrupted
        position_delta = clone.evaluate_position(player) - before_position
        threat_delta = before_threat - self._opponent_bless_threat(clone, player)
        future_delta = self._best_bless_potential(clone, player) - before_future
        setup_delta = self._setup_potential(clone, player) - before_setup

        if score_gain > 0:
            features["bless_points"] = max(features["bless_points"], float(score_gain))
            features["high_karma_bless"] = max(
                features["high_karma_bless"],
                float(score_gain * score_gain) / 5.0,
            )
        if altar_gain > 0:
            features["tempo"] += altar_gain * 0.65
        if enemy_corrupted_gain > 0:
            features["corruption_setup"] += enemy_corrupted_gain * 0.8
        features["protection"] += _clamp(threat_delta / 4.0, -1.5, 1.5)
        features["future_bless"] += _clamp(future_delta / 3.0, -1.2, 1.2)
        features["combo_setup"] += _clamp(setup_delta / 2.2, -1.35, 1.75)
        features["position_gain"] = _clamp(position_delta / 8.0, -2.2, 2.2)

        next_turn_value = self._project_after_opponent_turn(
            clone,
            player,
            before_position,
            before_setup,
        )
        features["next_turn_plan"] = _clamp(
            features["next_turn_plan"] + next_turn_value,
            -2.4,
            3.2,
        )
        if next_turn_value < 0:
            features["exposure_risk"] += min(1.4, -next_turn_value * 0.42)

        if action.kind in {"play_prayer", "invoke"}:
            # Il contesto testuale dice se l'effetto puo' funzionare; il clone
            # conferma se ha davvero spostato il tavolo nella direzione giusta.
            tactical_result = (
                score_gain * 1.40
                + altar_gain * 1.10
                + enemy_corrupted_gain * 0.90
                + max(0.0, threat_delta) * 0.28
                + max(0.0, position_delta) * 0.10
            )
            if tactical_result > 0:
                features["effect_relevance"] += _clamp(tactical_result / 3.2, 0.0, 1.35)
                features["prayer_engine"] += _clamp(tactical_result / 4.5, 0.0, 1.10)

        # Pianificazione di una seconda Azione: confronta le linee rimaste
        # prima e dopo la mossa. In questo modo un buff che rende vincente un
        # attacco, Zodiaco che rende gratuite le Preghiere o una nuova Eco da
        # combinare ricevono valore solo quando aprono davvero una continuazione.
        if not clone.force_end_turn and clone.players[player].actions > 0:
            remaining = clone.players[player].actions

            def signature(candidate: Action) -> tuple[str, int | None, int | None, str | None]:
                return (
                    candidate.kind,
                    candidate.card_uid,
                    candidate.target_uid,
                    candidate.mode,
                )

            useful_kinds = {"attack", "attack_direct", "invoke"}
            # Le giocate di Preghiera successive sono una vera combo nello
            # stesso turno soprattutto quando la prima mossa le ha rese
            # gratuite (Zodiaco). Gli investimenti per turni futuri sono gia'
            # misurati da _setup_potential senza scandire tutta la mano.
            if clone.free_prayers_active(player):
                useful_kinds.add("play_prayer")
            before_followups: dict[tuple[str, int | None, int | None, str | None], float] = {}
            for candidate in engine.legal_actions(player):
                if (
                    candidate.kind not in useful_kinds
                    or candidate.cost > remaining
                    or candidate.card_uid == action.card_uid
                ):
                    continue
                vector = self._rough_action_features(engine, player, candidate)
                before_followups[signature(candidate)] = self._score(vector)

            best_synergy = 0.0
            best_kind: str | None = None
            for candidate in clone.legal_actions(player):
                if candidate.kind not in useful_kinds or candidate.card_uid == action.card_uid:
                    continue
                vector = self._rough_action_features(clone, player, candidate)
                delta = self._score(vector) - before_followups.get(signature(candidate), 0.0)
                if delta > best_synergy:
                    best_synergy = delta
                    best_kind = candidate.kind

            if best_synergy > 0:
                features["combo_setup"] += _clamp(best_synergy / 6.5, 0.0, 1.45)
                if best_kind in {"play_prayer", "invoke"}:
                    features["prayer_engine"] += _clamp(best_synergy / 8.0, 0.0, 1.15)
        return features

    def _project_after_opponent_turn(
        self,
        position_after_action: GameEngine,
        player: int,
        baseline_position: float,
        baseline_setup: float,
    ) -> float:
        """Completa il turno, prevede la risposta rivale e apre il turno seguente.

        Il rollout usa solo le euristiche rapide: non richiama a sua volta il
        pianificatore e resta quindi abbastanza leggero per grandi campioni.
        """
        simulation = position_after_action.clone_for_search()
        current_limit = 1
        opponent_limit = 2

        self._rollout_turn_actions(simulation, simulation.active_player, current_limit)
        simulation.end_turn()
        if simulation.game_over:
            return self._finished_projection_value(simulation, player)

        simulation.start_turn()
        self._rollout_turn_actions(simulation, simulation.active_player, opponent_limit)
        simulation.end_turn()
        if simulation.game_over:
            return self._finished_projection_value(simulation, player)

        if simulation.active_player != player:
            return 0.0
        simulation.start_turn()
        if simulation.game_over:
            return self._finished_projection_value(simulation, player)

        position_delta = simulation.evaluate_position(player) - baseline_position
        setup_delta = self._setup_potential(simulation, player) - baseline_setup
        bless_ready = self._best_bless_potential(simulation, player)
        threat = self._opponent_bless_threat(simulation, player)

        next_bot = simulation.bots[player]
        next_bot.intent_turn = simulation.turn_number
        next_bot.support_actions_turn = 0
        next_actions = next_bot._policy_actions(
            simulation,
            player,
            simulation.legal_actions(player),
        )
        next_actions = self._rollout_candidates(
            simulation,
            player,
            next_actions,
        )
        next_scores = [
            next_bot._score(next_bot._rough_action_features(simulation, player, candidate))
            for candidate in next_actions
            if candidate.kind != "pass"
        ]
        next_action_quality = max(next_scores, default=0.0)
        value = (
            position_delta / 9.5
            + setup_delta / 3.8
            + bless_ready / 4.5
            - threat / 5.5
            + max(0.0, next_action_quality) / 24.0
        )
        return _clamp(value, -2.4, 2.8)

    def _rollout_turn_actions(
        self,
        engine: GameEngine,
        player: int,
        limit: int,
    ) -> None:
        seen: set[tuple[object, ...]] = set()
        for _ in range(limit):
            if engine.game_over or engine.force_end_turn or engine.active_player != player:
                break
            bot = engine.bots[player]
            if bot.intent_turn != engine.turn_number:
                bot.intent_turn = engine.turn_number
                bot.intent_attacker_uid = None
                bot.support_actions_turn = 0
            actions = bot._policy_actions(engine, player, engine.legal_actions(player))
            actions = self._rollout_candidates(engine, player, actions)
            scored = [
                (bot._score(bot._rough_action_features(engine, player, candidate)), candidate)
                for candidate in actions
            ]
            if not scored:
                break
            _, chosen = max(scored, key=lambda item: item[0])
            engine.execute_action(chosen, player, from_search=True)
            if chosen.kind in {"play_prayer", "invoke"}:
                bot.support_actions_turn += 1
            signature = engine.state_signature()
            if signature in seen:
                engine.force_end_turn = True
                break
            seen.add(signature)
            if chosen.kind == "pass":
                break

    @staticmethod
    def _rollout_candidates(
        engine: GameEngine,
        player: int,
        actions: list[Action],
    ) -> list[Action]:
        """Preselezione economica per non rallentare i campioni da 10.000 partite."""
        if len(actions) <= 7:
            return actions
        profile = engine.bots[player].profile
        ranked = sorted(
            actions,
            key=lambda action: engine.estimate_action(action, player, profile),
            reverse=True,
        )
        selected = list(ranked[:4])
        for kind in ("play_prayer", "invoke", "attack", "pass"):
            candidate = next((action for action in ranked if action.kind == kind), None)
            if candidate is not None and candidate not in selected:
                selected.append(candidate)
        return selected

    @staticmethod
    def _finished_projection_value(engine: GameEngine, player: int) -> float:
        if engine.winner == player:
            return 2.8
        if engine.winner is None:
            return 0.0
        return -2.4

    def _best_attack_value(self, engine: GameEngine, player: int, attacker_uid: int) -> float:
        opponent = 1 - player
        best = 0.0
        targets = engine.eclissi_targets(opponent) or list(engine.players[opponent].maledictions)
        for target_uid in targets:
            if engine.cannot_be_attacked(target_uid, attacker_uid):
                continue
            target = engine.cards[target_uid]
            outcome = engine.predict_combat(attacker_uid, target_uid)
            probability = 0.5 if outcome == "fato" else float(outcome in {"attacker_win", "tie"})
            if target.corrupted:
                best = max(best, probability * (1.0 + engine.karma(attacker_uid) / 3.0))
            else:
                best = max(best, 0.75 + probability * 0.45)
        if not targets:
            best = max(best, 1.0 + engine.karma(attacker_uid) / 3.0)
        return best

    def _best_bless_potential(self, engine: GameEngine, player: int) -> float:
        opponent = 1 - player
        best = 0.0
        for attacker_uid in engine.players[player].maledictions:
            attacker = engine.cards[attacker_uid]
            if attacker.attacked_turn == engine.turn_number or engine.cannot_attack(attacker_uid):
                continue
            readiness = 0.55 if attacker.stasis else 1.0
            for target_uid in engine.players[opponent].maledictions:
                if not engine.cards[target_uid].corrupted or engine.cannot_be_attacked(target_uid, attacker_uid):
                    continue
                outcome = engine.predict_combat(attacker_uid, target_uid)
                probability = 0.5 if outcome == "fato" else float(outcome in {"attacker_win", "tie"})
                best = max(best, readiness * probability * engine.karma(attacker_uid))
        return best

    def _opponent_bless_threat(self, engine: GameEngine, player: int) -> float:
        opponent = 1 - player
        threat = 0.0
        for attacker_uid in engine.players[opponent].maledictions:
            for target_uid in engine.players[player].maledictions:
                if not engine.cards[target_uid].corrupted:
                    continue
                if engine.cannot_be_attacked(target_uid, attacker_uid):
                    continue
                outcome = engine.predict_combat(attacker_uid, target_uid)
                probability = 0.5 if outcome == "fato" else float(outcome in {"attacker_win", "tie"})
                threat = max(threat, probability * engine.karma(attacker_uid))
        return threat

    # ------------------------------------------------------------------
    # Scelte secondarie ed effetti
    # ------------------------------------------------------------------
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
        own_only = {
            "attach_benefit",
            "attack_setup",
            "attack_source",
            "bless",
            "buff_eye",
            "buff_karma",
            "convert",
            "convert_charge",
            "effect_source",
            "extra_attacks",
            "eye_reference",
            "protect_own",
            "purify",
            "open_own_sigil",
            "swap_stats",
            "toggle_corruption",
        }
        if purpose in own_only:
            choices = [uid for uid in choices if engine.cards[uid].controller == player]
        elif purpose == "debuff_eye":
            choices = [uid for uid in choices if engine.cards[uid].controller == 1 - player]
        if not choices:
            return None

        def score(uid: int) -> float:
            card = engine.cards[uid]
            value = engine.card_value(uid, player)
            own = card.controller == player
            karma_bonus = engine.karma(uid) * (0.45 if self.profile.style == "stratega" else 0.22)
            if purpose in {"break", "suppress", "debuff", "steal"}:
                return value + karma_bonus if not own else -value
            if purpose == "debuff_eye":
                return self._enemy_eye_debuff_priority(engine, player, uid, source_uid)
            if purpose == "debuff_eye_any":
                return (
                    self._enemy_eye_debuff_priority(engine, player, uid, source_uid)
                    if not own
                    else -value - 0.8 * engine.karma(uid)
                )
            if purpose == "darkness_target":
                references = [
                    card_uid
                    for card_uid in engine.players[player].maledictions + engine.players[player].prayers
                    if card_uid != source_uid and "Ombra" in engine.forms(card_uid)
                ]
                if not references:
                    return -50.0
                current_eye = engine.eye(uid)
                own = card.controller == player
                best_eye = (
                    max(engine.original_eye(card_uid) for card_uid in references)
                    if own
                    else min(engine.original_eye(card_uid) for card_uid in references)
                )
                useful_change = best_eye - current_eye if own else current_eye - best_eye
                return 1.35 * useful_change + 0.18 * value + 0.25 * engine.karma(uid)
            if purpose in {"discard_own", "limit_remove", "cost", "sacrifice"}:
                corruption_discount = 2.5 if card.zone == Zone.MALEDICTION and card.corrupted else 0.0
                return -value + corruption_discount
            if purpose == "convert_charge":
                # Tomo del Titano trasforma davvero la Carica scelta in una
                # Maledizione: qui conviene quindi usare la carta migliore,
                # non sacrificare automaticamente quella di minor valore come
                # nelle normali scelte di Carica o Marchio.
                return self.hand_value(engine, uid, player) + 0.20 * value
            if purpose in {"charge", "mark_from_hand"}:
                special = 2.2 if engine.is_thunder_sand and engine.definition(uid).id in {27, 38} else 0.0
                return special - self.hand_value(engine, uid, player)
            if purpose == "spend_charge":
                special = 5.0 if engine.is_thunder_sand and engine.definition(uid).id in {27, 38} else 0.0
                return special - 0.20 * value
            if purpose in {"take", "draw", "play"}:
                return self.hand_value(engine, uid, player)
            if purpose == "buff_eye":
                return self._eye_target_priority(engine, player, uid, source_uid)
            if purpose == "buff_eye_any":
                if own:
                    return self._eye_target_priority(engine, player, uid, source_uid)
                # Un bonus avversario e' normalmente negativo, ma puo' creare
                # apposta un bersaglio superiore per Piramide nel Cielo.
                pyramid_setup = 0.0
                for attacker in engine.players[player].maledictions:
                    if engine.definition(attacker).id != 45 or engine.cards[attacker].stasis:
                        continue
                    before = engine.simulate_combat_silently(attacker, uid)
                    if int(before["attacker_eye"]) >= int(before["defender_eye"]):
                        pyramid_setup = max(
                            pyramid_setup,
                            4.0 + 0.8 * engine.karma(attacker),
                        )
                return pyramid_setup - value - 0.4 * engine.karma(uid)
            if purpose == "buff_karma":
                return (
                    0.45 * value
                    + 0.85 * engine.karma(uid)
                    + 0.65 * self._best_attack_value(engine, player, uid)
                )
            if purpose == "buff_karma_any":
                return (
                    0.45 * value
                    + 0.85 * engine.karma(uid)
                    + 0.65 * self._best_attack_value(engine, player, uid)
                    if own
                    else -value - 1.2 * engine.karma(uid)
                )
            if purpose == "attack_setup_any":
                return (
                    self._best_attack_value(engine, player, uid) + 0.8 * engine.karma(uid)
                    if own
                    else -value
                )
            if purpose == "grant_emblem_any":
                if own:
                    eye_gain = engine.eye(uid) if engine.cards[uid].corrupted and not engine.has_ability(uid, "emblema") else 0
                    return self._eye_target_priority(
                        engine,
                        player,
                        uid,
                        source_uid,
                        gain_override=eye_gain,
                    ) - 0.55
                enemy_eye_risk = engine.eye(uid) if engine.cards[uid].corrupted and not engine.has_ability(uid, "emblema") else 0
                return 1.15 * engine.karma(uid) - 1.4 * enemy_eye_risk - 0.15 * value
            if purpose == "attach_benefit":
                gain = self._bond_eye_gain(engine, player, uid, source_uid)
                return (
                    self._eye_target_priority(engine, player, uid, source_uid, gain_override=gain)
                    + 0.20 * value
                )
            if purpose in {"protect_own", "purify"}:
                threat = self._opponent_bless_threat_for_target(engine, player, uid)
                return value + karma_bonus + 0.70 * threat
            if purpose == "protect_any":
                if not own:
                    return -value - karma_bonus
                threat = self._opponent_bless_threat_for_target(engine, player, uid)
                return value + karma_bonus + 0.70 * threat
            if purpose == "purify_any":
                if not own:
                    return -value - 0.9 * engine.karma(uid)
                threat = self._opponent_bless_threat_for_target(engine, player, uid)
                return value + karma_bonus + 0.70 * threat
            if purpose == "eye_reference":
                return 2.0 * engine.original_eye(uid) + 0.15 * value
            if purpose == "eye_reference_any":
                side = card.controller
                if side is None:
                    return -50.0
                partners = [
                    other
                    for other in engine.players[side].maledictions
                    if other != uid
                ]
                if not partners:
                    return -50.0
                direction = 1.0 if own else -1.0
                return max(
                    direction
                    * (
                        (engine.original_eye(other) - engine.original_eye(uid))
                        * (0.55 + 0.35 * engine.karma(uid))
                        + (engine.original_eye(uid) - engine.original_eye(other))
                        * (0.30 + 0.18 * engine.karma(other))
                    )
                    for other in partners
                )
            if purpose == "eye_reference_partner":
                first = engine.cards[source_uid].effect_target_uid if source_uid is not None else None
                if first is None:
                    return -50.0
                first_own = engine.cards[first].controller == player
                direction = 1.0 if first_own else -1.0
                return direction * (
                    (engine.original_eye(uid) - engine.original_eye(first))
                    * (0.55 + 0.35 * engine.karma(first))
                    + (engine.original_eye(first) - engine.original_eye(uid))
                    * (0.30 + 0.18 * engine.karma(uid))
                )
            if purpose == "darkness_reference_own":
                return 2.0 * engine.original_eye(uid) + 0.15 * value
            if purpose == "darkness_reference_enemy":
                return -2.0 * engine.original_eye(uid) - 0.05 * value
            if purpose == "effect_source":
                definition = engine.definition(uid)
                return engine.prayer_effect_value(uid) + 0.20 * value
            if purpose in {"attack_source", "extra_attacks"}:
                return self._best_attack_value(engine, player, uid) + 0.8 * engine.karma(uid)
            if purpose == "attack_target":
                return value + 0.55 * engine.karma(uid)
            if purpose == "must_attack_any":
                return value + 0.55 * engine.karma(uid) if not own else -value
            if purpose == "highest_eye_block":
                return value + 0.8 * engine.karma(uid) if not own else 0.65 * value
            if purpose == "optional_corrupt":
                return value + 0.35 * engine.karma(uid)
            if purpose in {"mark", "mark_any"}:
                return value * (1.0 if not own else 0.35)
            if purpose == "remove_mark":
                return value * (1.0 if own else 0.45)
            if purpose in {"sigil_state", "sigil_state_required", "open_own_sigil"}:
                is_open = engine.cards[uid].seal_open
                return (2.2 if own and not is_open else 1.8 if not own and is_open else 0.2) + value * 0.12
            if purpose in {"bless", "toggle_corruption", "swap_stats"}:
                return value + 0.75 * engine.karma(uid)
            if purpose == "bless_any":
                return engine.karma(uid) + 0.15 * value if own else -2.0 * engine.karma(uid) - value
            if purpose == "convert":
                return value + 0.55 * engine.karma(uid)
            if purpose == "form_setup":
                own_bias = 0.35 if own else 0.0
                return value * (0.35 if own else 0.50) + own_bias
            if purpose == "attach_harm":
                return value if not own else -value
            if purpose == "return_own":
                replay_bonus = 1.4 if engine.definition(uid).id in {6, 12, 21, 23, 26, 46, 56, 59} else 0.0
                return replay_bonus + value * 0.2
            return value

        best = max(score(uid) for uid in choices)
        finalists = [uid for uid in choices if score(uid) >= best - 1e-9]
        return engine.rng.choice(finalists)

    def _eye_target_priority(
        self,
        engine: GameEngine,
        player: int,
        uid: int,
        source_uid: int | None,
        *,
        gain_override: int | None = None,
    ) -> float:
        """Premia Occhio aggiunto dove puo' trasformarsi in PV di Karma alto."""
        if engine.cards[uid].zone != Zone.MALEDICTION:
            return -50.0
        eye = engine.eye(uid)
        karma = engine.karma(uid)
        low_eye = max(0, 6 - eye)
        gain = gain_override if gain_override is not None else self._estimated_eye_gain(
            engine,
            player,
            source_uid,
            uid,
        )
        score = 0.85 * karma + 0.34 * low_eye + gain * (0.35 + 0.16 * karma)
        if engine.cards[uid].stasis:
            score -= 0.22

        opponent = 1 - player
        for target in engine.players[opponent].maledictions:
            if not engine.cards[target].corrupted or engine.cannot_be_attacked(target, uid):
                continue
            outcome = engine.predict_combat(uid, target)
            if outcome in {"attacker_win", "tie"}:
                score += 0.30 * karma
                continue
            attacker_eye = engine.combat_eye(uid, target)
            defender_eye = engine.projected_defender_eye(uid, target)
            if attacker_eye + gain >= defender_eye:
                score += 3.4 + 1.05 * karma
            else:
                score += max(0, gain - (defender_eye - attacker_eye) + 1) * 0.20
        return score

    def _estimated_eye_gain(
        self,
        engine: GameEngine,
        player: int,
        source_uid: int | None,
        target_uid: int,
    ) -> int:
        if source_uid is None:
            return 1
        definition_id = engine.definition(source_uid).id
        if engine.is_thunder_sand:
            if definition_id in {5, 24}:
                return 2
            if definition_id in {18, 27}:
                if engine.cards[target_uid].corrupted and not engine.has_ability(target_uid, "emblema"):
                    return engine.eye(target_uid)
                return 0
            if definition_id == 28:
                return int("Tuono" in engine.forms(target_uid))
            if definition_id == 36:
                return int("Sabbia" in engine.forms(target_uid))
            if definition_id == 9:
                return 2 if "Tuono" in engine.forms(target_uid) else 0
            if definition_id == 57:
                return 2 if engine.definition(target_uid).prayer_type == PrayerType.GLYPH else 0
            if definition_id in {10, 50}:
                return 0
            return 1
        if definition_id in {1, 30, 16}:
            return 2
        if definition_id == 4:
            return max(0, len(engine.all_prayers()) - int(source_uid in engine.all_prayers()))
        if definition_id == 14:
            return 1
        if definition_id == 15:
            return 2 if engine.cards[target_uid].corrupted else 0
        if definition_id in {24, 52}:
            required = "Luce" if definition_id == 24 else "Ombra"
            return int(required in engine.forms(target_uid))
        if definition_id == 42:
            references = [
                card_uid
                for card_uid in engine.players[player].maledictions + engine.players[player].prayers
                if card_uid != source_uid and "Ombra" in engine.forms(card_uid)
            ]
            best_reference = max(
                (engine.original_eye(card_uid) for card_uid in references),
                default=engine.eye(target_uid),
            )
            return max(0, best_reference - engine.eye(target_uid))
        if definition_id == 45:
            return len(engine.players[1 - player].maledictions)
        return 1

    def _bond_eye_gain(
        self,
        engine: GameEngine,
        player: int,
        target_uid: int,
        source_uid: int | None,
    ) -> int:
        if source_uid is None:
            return 0
        definition_id = engine.definition(source_uid).id
        if definition_id in {13, 48}:
            return 1
        if definition_id in {7, 19, 49}:
            return (1 if definition_id == 7 else 2) if engine.cards[target_uid].corrupted else 0
        if definition_id == 21:
            return len(engine.players[1 - player].maledictions)
        if definition_id == 25:
            return max(0, 5 - engine.eye(target_uid))
        if definition_id == 26:
            maximum = max(
                (engine.original_eye(uid) for uid in engine.players[1 - player].maledictions),
                default=engine.eye(target_uid),
            )
            return max(0, maximum - engine.eye(target_uid))
        if definition_id == 47:
            return sum(
                engine.original_eye(other) > engine.original_eye(target_uid)
                for other in engine.all_maledictions()
            )
        if definition_id == 50:
            is_only_shadow = (
                "Ombra" in engine.forms(target_uid)
                and sum("Ombra" in engine.forms(other) for other in engine.players[player].maledictions) == 1
            )
            return 3 if is_only_shadow else 0
        return 0

    def _enemy_eye_debuff_priority(
        self,
        engine: GameEngine,
        player: int,
        target_uid: int,
        source_uid: int | None,
    ) -> float:
        target_value = engine.card_value(target_uid, player)
        score = 0.30 * target_value
        definition_id = engine.definition(source_uid).id if source_uid is not None else 0
        if engine.is_thunder_sand:
            reduction = 3 if definition_id == 19 else max(1, engine.effective_charge_count(1 - player))
            for attacker in engine.players[player].maledictions:
                if engine.cannot_be_attacked(target_uid, attacker):
                    continue
                karma = engine.karma(attacker)
                attacker_eye = engine.combat_eye(attacker, target_uid)
                defender_eye = engine.projected_defender_eye(attacker, target_uid)
                if attacker_eye < defender_eye <= attacker_eye + reduction:
                    score += 3.2 + karma
            return score
        watched_form = "Luce" if definition_id == 23 else ("Ombra" if definition_id == 38 else None)
        reduction = 2 if watched_form is not None else max(0, engine.original_eye(target_uid) - 3)
        for attacker in engine.players[player].maledictions:
            if watched_form is not None and watched_form not in engine.forms(attacker):
                continue
            if engine.cannot_be_attacked(target_uid, attacker):
                continue
            karma = engine.karma(attacker)
            outcome = engine.predict_combat(attacker, target_uid)
            attacker_eye = engine.combat_eye(attacker, target_uid)
            defender_eye = engine.projected_defender_eye(attacker, target_uid)
            if outcome not in {"attacker_win", "tie"} and attacker_eye >= defender_eye - reduction:
                score += 3.1 + 1.0 * karma
            elif engine.cards[target_uid].corrupted:
                score += 0.28 * karma
        return score

    def _opponent_bless_threat_for_target(
        self,
        engine: GameEngine,
        player: int,
        target_uid: int,
    ) -> float:
        opponent = 1 - player
        threat = 0.0
        if not engine.cards[target_uid].corrupted:
            return threat
        for attacker in engine.players[opponent].maledictions:
            if engine.cannot_be_attacked(target_uid, attacker):
                continue
            outcome = engine.predict_combat(attacker, target_uid)
            probability = 0.5 if outcome == "fato" else float(outcome in {"attacker_win", "tie"})
            threat = max(threat, probability * engine.karma(attacker))
        return threat

    def choose_mulligan(
        self,
        engine: GameEngine,
        player: int,
        *,
        initial: bool = False,
    ) -> list[int]:
        hand = list(engine.players[player].hand)
        if not hand:
            return []
        ranked = sorted(hand, key=lambda uid: self.hand_value(engine, uid, player), reverse=True)
        threshold = 4.15 if self.profile.style == "stratega" else 3.90
        low = [uid for uid in reversed(ranked) if self.hand_value(engine, uid, player) < threshold]

        # Tiene almeno due piani giocabili e non svuota una mano corta. Con una
        # mano lunga puo' riciclare piu' carte che non servono nei prossimi due turni.
        maximum = min(len(low), max(0, len(hand) - 2))
        if len(hand) <= 4:
            maximum = min(maximum, 2)
        else:
            maximum = min(maximum, max(2, len(hand) - 4))

        # Con un Glifo in campo il Mulligan di fine turno e' anche la fonte
        # ordinaria delle Cariche. Se il motore non ha ancora una riserva utile,
        # conserva intenzionalmente almeno una carta da trasformare in Carica,
        # anche quando la mano non contiene scarti sotto la soglia generale.
        if (
            engine.is_thunder_sand
            and not initial
            and engine.can_charge_during_mulligan(player, initial=False)
        ):
            glyphs = [
                uid
                for uid in engine.players[player].prayers + hand
                if engine.definition(uid).prayer_type == PrayerType.GLYPH
            ]
            useful_reserve = min(
                3,
                max((engine.glyph_cost(uid) for uid in glyphs), default=1),
            )
            if engine.effective_charge_count(player) < max(1, useful_reserve):
                candidate = min(hand, key=lambda uid: self.hand_value(engine, uid, player))
                if candidate not in low:
                    low.insert(0, candidate)
                maximum = max(1, maximum)
        return low[:maximum]

    def choose_mulligan_charge(
        self,
        engine: GameEngine,
        player: int,
        selected: Iterable[int],
    ) -> int | None:
        choices = list(selected)
        if not choices:
            return None
        special = [uid for uid in choices if engine.definition(uid).id in {27, 38}]
        if special:
            return max(special, key=lambda uid: self.hand_value(engine, uid, player))
        return min(choices, key=lambda uid: self.hand_value(engine, uid, player))

    def choose_esordio(self, engine: GameEngine, player: int, uid: int) -> str:
        # I due Esordi di TuonoSabbia sono Glifi a costo zero: metterli in
        # campo crea subito un motore di Marchi senza consumare Azioni.
        if engine.definition(uid).prayer_type == PrayerType.GLYPH:
            return "Preghiera"
        return "Maledizione" if not engine.players[player].maledictions else "Mano"

    def hand_value(self, engine: GameEngine, uid: int, player: int) -> float:
        definition = engine.definition(uid)
        own_board = engine.players[player].maledictions
        opponent_board = engine.players[1 - player].maledictions
        malediction_effect, malediction_relevance, malediction_setup = self._malediction_context(
            engine,
            player,
            uid,
        )
        malediction = (
            definition.eye * self.profile.eye_weight
            + definition.karma * self.profile.karma_weight
            + malediction_effect
        ) / 2.15
        malediction += 0.24 * malediction_relevance + 0.30 * malediction_setup
        if not own_board:
            malediction += 1.35
        elif engine.used_malediction_slots(player) >= 4:
            weakest = min(engine.card_value(target, player) for target in own_board)
            incoming = definition.eye + 1.35 * definition.karma + engine.malediction_effect_value(uid)
            malediction += _clamp((incoming - weakest) / 4.0, -1.8, 1.2)
        if any(engine.cards[target].corrupted for target in opponent_board):
            malediction += definition.karma / 5.0

        if definition.prayer_type == PrayerType.BOND:
            prayer_actions = [
                Action("play_prayer", uid, target_uid=target, mode="Preghiera")
                for target in engine.all_maledictions()
                if not (definition.id == 60 and engine.forms(target) == {"Luce", "Ombra"})
            ]
            prayer_contexts = [
                self._prayer_context(engine, player, prayer_action)
                for prayer_action in prayer_actions
            ]
            relevance, setup, prayer_engine = max(
                prayer_contexts,
                key=lambda values: values[0] + values[1] + values[2],
                default=(-0.85, 0.0, -0.25),
            )
            eye_setup, next_eye_setup = max(
                (
                    self._eye_prayer_plan(engine, player, prayer_action)
                    for prayer_action in prayer_actions
                ),
                key=lambda values: values[0] + values[1],
                default=(0.0, 0.0),
            )
        else:
            prayer_action = Action("play_prayer", uid, mode="Preghiera")
            relevance, setup, prayer_engine = self._prayer_context(
                engine,
                player,
                prayer_action,
            )
            eye_setup, next_eye_setup = self._eye_prayer_plan(engine, player, prayer_action)
        prayer = engine.prayer_effect_value(uid) * self.profile.prayer_weight
        prayer += 0.28 * relevance + 0.42 * setup + 0.34 * prayer_engine
        prayer += 0.46 * eye_setup + 0.38 * next_eye_setup
        if definition.prayer_type in {PrayerType.ECHO, PrayerType.SIGIL, PrayerType.GLYPH}:
            prayer += 0.55 * self.profile.prayer_weight
        if definition.prayer_type == PrayerType.BOND and not own_board and not opponent_board:
            prayer -= 0.85
        if self.profile.style == "aggressivo" and not own_board:
            prayer -= 0.75
        return max(malediction, prayer)

    def choose_mode(self, engine: GameEngine, player: int, uid: int, legal_modes: list[str]) -> str:
        if len(legal_modes) == 1:
            return legal_modes[0]
        definition = engine.definition(uid)
        effect_value, relevance, setup = self._malediction_context(engine, player, uid)
        malediction = (
            definition.eye * self.profile.eye_weight
            + definition.karma * self.profile.karma_weight
            + effect_value
            + 0.55 * relevance
            + 0.45 * setup
        )
        if engine.used_malediction_slots(player) >= 4:
            malediction -= 4.5
        if not engine.players[player].maledictions:
            malediction += 2.0
        if definition.prayer_type == PrayerType.BOND:
            prayer_actions = [
                Action("play_prayer", uid, target_uid=target, mode="Preghiera")
                for target in engine.all_maledictions()
                if not (definition.id == 60 and engine.forms(target) == {"Luce", "Ombra"})
            ]
            prayer_contexts = [
                self._prayer_context(engine, player, prayer_action)
                for prayer_action in prayer_actions
            ]
            prayer_relevance, prayer_setup, prayer_engine = max(
                prayer_contexts,
                key=lambda values: values[0] + values[1] + values[2],
                default=(-0.85, 0.0, -0.25),
            )
            eye_setup, next_eye_setup = max(
                (
                    self._eye_prayer_plan(engine, player, prayer_action)
                    for prayer_action in prayer_actions
                ),
                key=lambda values: values[0] + values[1],
                default=(0.0, 0.0),
            )
        else:
            prayer_action = Action("play_prayer", uid, mode="Preghiera")
            prayer_relevance, prayer_setup, prayer_engine = self._prayer_context(
                engine,
                player,
                prayer_action,
            )
            eye_setup, next_eye_setup = self._eye_prayer_plan(engine, player, prayer_action)
        prayer = engine.prayer_effect_value(uid) * self.profile.prayer_weight * 2.1
        prayer += 0.65 * prayer_relevance + 0.75 * prayer_setup + 0.65 * prayer_engine
        prayer += 0.82 * eye_setup + 0.70 * next_eye_setup
        return "Maledizione" if malediction >= prayer else "Preghiera"

    def should_pay_purification(
        self,
        engine: GameEngine,
        player: int,
        source_uid: int,
        candidates: Iterable[int],
    ) -> bool:
        """Decide se pagare davvero lo scarto richiesto dal CALO.

        Senza una Maledizione corrotta l'effetto non parte. Con bersagli validi
        confronta la carta meno utile in mano con il valore e il rischio della
        Maledizione che tornerebbe Pura.
        """
        targets = list(candidates)
        if engine.is_thunder_sand:
            return bool(targets and engine.players[player].charges)
        hand = list(engine.players[player].hand)
        if not targets or not hand:
            return False

        target = max(targets, key=lambda card_uid: engine.card_value(card_uid, player))
        target_value = engine.card_value(target, player)
        target_karma = engine.karma(target)
        opponent = 1 - player
        bless_risk = 0.0
        for attacker in engine.players[opponent].maledictions:
            if engine.cannot_be_attacked(target, attacker):
                continue
            outcome = engine.predict_combat(attacker, target)
            probability = 0.5 if outcome == "fato" else float(outcome in {"attacker_win", "tie"})
            bless_risk = max(bless_risk, probability * engine.karma(attacker))

        discard_cost = min(self.hand_value(engine, card_uid, player) for card_uid in hand)
        benefit = 1.45 + target_value * 0.18 + target_karma * 0.22 + bless_risk * 0.48
        caution = 0.78 if self.profile.style == "stratega" else 0.66
        return benefit >= discard_cost * caution

    def choose_form(self, engine: GameEngine, player: int, target_uid: int) -> str:
        target_controller = engine.cards[target_uid].controller
        if target_controller == player:
            own_light = engine.count_form_on_side(player, "Luce")
            own_shadow = engine.count_form_on_side(player, "Ombra")
            return "Luce" if own_light >= own_shadow else "Ombra"
        opponent = 1 - player
        opp_light = engine.count_form_on_side(opponent, "Luce")
        opp_shadow = engine.count_form_on_side(opponent, "Ombra")
        return "Ombra" if opp_light >= opp_shadow else "Luce"

    def choose_declared_form(
        self,
        engine: GameEngine,
        player: int,
        source_uid: int,
        options: list[str],
    ) -> str:
        opponent = 1 - player
        return max(
            options,
            key=lambda form: engine.count_form_on_side(opponent, form),
        )

    def choose_option(
        self,
        engine: GameEngine,
        player: int,
        options: list[str | bool],
        purpose: str,
        *,
        source_uid: int | None = None,
    ) -> str | bool:
        if purpose in {
            "spend_charges",
            "recover_impulse",
            "charge_broken",
            "open_sigil_after_attack",
            "play_spent_charge",
            "take_removed_mark",
        }:
            return True if True in options else options[0]
        if purpose == "stat_bonus":
            if engine.players[player].actions > 0:
                for attacker in engine.players[player].maledictions:
                    if engine.cards[attacker].stasis or engine.cannot_attack(attacker):
                        continue
                    previews = engine.attack_target_previews(player, attacker)
                    if any(
                        preview["allowed"]
                        and engine.cards[int(preview["target_uid"])].corrupted
                        for preview in previews
                    ):
                        return "+1 Karma" if "+1 Karma" in options else options[0]
            return "+2 Occhio" if "+2 Occhio" in options else options[0]
        if purpose == "pangolino_mode" and len(options) > 1:
            baseline = engine.evaluate_position(player)
            own_sigils = [
                uid
                for uid in engine.players[player].prayers
                if engine.definition(uid).prayer_type == PrayerType.SIGIL
            ]
            enemy_sigils = [
                uid
                for uid in engine.players[1 - player].prayers
                if engine.definition(uid).prayer_type == PrayerType.SIGIL
            ]
            convert_value = -99.0
            for target in own_sigils:
                clone = engine.clone_for_search(observer_player=player)
                if clone.convert_prayer_to_malediction(target, player, stasis=True):
                    convert_value = max(convert_value, clone.evaluate_position(player) - baseline)
            break_value = -99.0
            for target in enemy_sigils:
                clone = engine.clone_for_search(observer_player=player)
                if clone.break_card(target, reason="valutazione Pangolino"):
                    break_value = max(break_value, clone.evaluate_position(player) - baseline)
            preferred = (
                "Converti un tuo Sigillo"
                if convert_value >= break_value
                else "Spezza un Sigillo avversario"
            )
            if preferred in options:
                return preferred
        if purpose == "eye_direction":
            own_karma = max((engine.karma(uid) for uid in engine.players[player].maledictions), default=0)
            enemy_eye = max((engine.eye(uid) for uid in engine.players[1 - player].maledictions), default=0)
            if own_karma >= 3 and "Potenzia una tua Maledizione" in options:
                return "Potenzia una tua Maledizione"
            if enemy_eye >= 6 and "Indebolisci una Maledizione avversaria" in options:
                return "Indebolisci una Maledizione avversaria"
        return options[0]

    def should_prevent_glyph_break(
        self,
        engine: GameEngine,
        player: int,
        uid: int,
        reason: str,
    ) -> bool:
        if not engine.players[player].charges:
            return False
        glyph_value = engine.card_value(uid, player)
        cheapest_charge = min(
            (engine.card_value(charge, player) for charge in engine.players[player].charges),
            default=99.0,
        )
        return glyph_value >= 0.55 * cheapest_charge

    def choose_fate(self, engine: GameEngine, player: int, source_uid: int) -> bool:
        """Restituisce True per Pari e False per Dispari.

        Per i bot le due scelte hanno la stessa probabilita'; il metodo
        separato permette invece al giocatore umano di dichiararla davvero.
        """
        return bool(engine.rng.choice([True, False]))

    def choose_offer(self, engine: GameEngine, player: int, defender_uid: int) -> bool:
        if engine.is_thunder_sand:
            definition_id = engine.definition(defender_uid).id
            if definition_id == 54 and not engine.is_suppressed(defender_uid):
                return False
            if (
                definition_id == 41
                and not engine.is_suppressed(defender_uid)
                and not engine.players[player].charges
            ):
                return False
        # Senza Offerta non c'e' Bless: normalmente e' sempre la conversione
        # corretta. Se i Turni Finali sono gia' iniziati non esiste piu' alcun
        # motivo di rinunciare, nemmeno nell'ultimo turno o a partita decisa.
        if engine.final_turns_remaining is not None:
            return True
        if len(engine.players[player].altar) < 4:
            return True
        opponent = 1 - player
        attacking = [
            uid
            for uid in engine.players[player].maledictions
            if engine.cards[uid].attacked_turn == engine.turn_number
        ]
        expected_points = max((engine.karma(uid) for uid in attacking), default=0)
        projected_margin = (
            engine.players[player].score + expected_points - engine.players[opponent].score
        )
        # La quinta Offerta attiva i Turni Finali. Il Bot la rinvia soltanto se
        # il Bless vale 0/1 PV e consegnerebbe all'avversario il vantaggio della
        # sequenza 5-3-1 mentre il Bot resta ancora dietro nel punteggio.
        if expected_points >= 2:
            return True
        return projected_margin >= 0


def make_bot(name: str, learned_weights: Mapping[str, float] | None = None) -> StrategicBot:
    if name not in PROFILES:
        raise KeyError(f"Bot sconosciuto: {name}")
    return StrategicBot(PROFILES[name], learned_weights)


BOT_NAMES = list(PROFILES)
