from __future__ import annotations

import csv
import json
import math
import os
import statistics
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .bots import BOT_NAMES, FEATURE_LABELS, FEATURE_NAMES
from .cards import get_deck_definitions, get_deck_name, normalize_deck_id
from .engine import GameEngine, GameResult
from .replay import replay_payload as _replay_payload


ProgressCallback = Callable[[int, int], None]


@dataclass(slots=True)
class SimulationConfig:
    games: int = 1000
    deck: str = "Luce-Ombra"
    mode: str = "Sfida diretta"
    bot_1: str = "Bot"
    bot_2: str = "Bot"
    seed: int = 20260809
    workers: int = field(default_factory=lambda: max(1, min(8, (os.cpu_count() or 2) - 1)))
    learning_enabled: bool = True
    learning_generation: int = 0
    learning_total_games: int = 0
    learning_weights: dict[str, dict[str, float]] = field(default_factory=dict)

    def validate(self) -> None:
        if not 1 <= int(self.games) <= 10_000:
            raise ValueError("Il numero di partite deve essere compreso tra 1 e 10.000.")
        self.deck = get_deck_name(normalize_deck_id(self.deck))
        if self.mode != "Sfida diretta":
            raise ValueError(f"Modalità non disponibile: {self.mode}")
        if self.bot_1 not in BOT_NAMES or self.bot_2 not in BOT_NAMES:
            raise ValueError("Famiglia di bot sconosciuta.")
        if not 1 <= int(self.workers) <= 16:
            raise ValueError("Il numero di processi deve essere compreso tra 1 e 16.")
        if int(self.learning_generation) < 0 or int(self.learning_total_games) < 0:
            raise ValueError("Lo stato di apprendimento non e' valido.")
        for bot, weights in self.learning_weights.items():
            if bot not in BOT_NAMES or not isinstance(weights, dict):
                raise ValueError("I pesi di apprendimento non sono validi.")
            for feature, value in weights.items():
                if feature not in FEATURE_NAMES or not math.isfinite(float(value)):
                    raise ValueError("I pesi di apprendimento contengono un valore sconosciuto.")


@dataclass(slots=True)
class SimulationReport:
    generated_at: str
    config: dict[str, Any]
    summary: dict[str, Any]
    bot_stats: list[dict[str, Any]]
    pair_stats: list[dict[str, Any]]
    card_stats: list[dict[str, Any]]
    ability_stats: list[dict[str, Any]]
    insights: list[dict[str, str]]
    learning: dict[str, Any]
    replay: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _percent(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(100.0 * numerator / denominator, 2)


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return float(ordered[lower])
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _strategy_pairs(config: SimulationConfig) -> list[tuple[str, str]]:
    return [("Bot", "Bot")]


SimulationJob = tuple[int, tuple[str, str], int, dict[str, dict[str, float]], str]


def _jobs(config: SimulationConfig) -> list[SimulationJob]:
    pairs = _strategy_pairs(config)
    jobs: list[SimulationJob] = []
    for index in range(config.games):
        # Ogni accoppiamento viene giocato due volte di seguito, invertendo chi
        # ha il primo turno: così strategia e ordine di partenza non sono
        # correlati nel Torneo.
        pair = pairs[(index // 2) % len(pairs)]
        first_player = index % 2
        seed = int(config.seed) + index * 7_919
        jobs.append((seed, pair, first_player, config.learning_weights, config.deck))
    return jobs


def _play_job(job: SimulationJob) -> GameResult:
    seed, bots, first_player, bot_weights, deck = job
    return GameEngine(
        seed,
        bots,
        first_player=first_player,
        record_replay=False,
        bot_weights=bot_weights,
        deck=deck,
    ).play_game()


def _play_replay_job(job: SimulationJob) -> GameResult:
    seed, bots, first_player, bot_weights, deck = job
    return GameEngine(
        seed,
        bots,
        first_player=first_player,
        record_replay=True,
        bot_weights=bot_weights,
        deck=deck,
    ).play_game()


def _iter_results(
    config: SimulationConfig,
    jobs: list[SimulationJob],
    progress: ProgressCallback | None,
) -> Iterable[GameResult]:
    if not jobs:
        return
    first = _play_replay_job(jobs[0])
    if progress:
        progress(1, len(jobs))
    yield first

    remaining = jobs[1:]
    if not remaining:
        return
    if config.workers <= 1 or len(remaining) < 24:
        for completed, job in enumerate(remaining, start=2):
            yield _play_job(job)
            if progress:
                progress(completed, len(jobs))
        return

    chunksize = max(1, len(remaining) // (config.workers * 12))
    with ProcessPoolExecutor(max_workers=config.workers) as executor:
        for completed, result in enumerate(
            executor.map(_play_job, remaining, chunksize=chunksize),
            start=2,
        ):
            yield result
            if progress:
                progress(completed, len(jobs))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _learning_update(config: SimulationConfig, results: list[GameResult]) -> dict[str, Any]:
    """Calcola il nuovo stato dei pesi senza modificare retroattivamente il campione.

    Ogni partita usa i pesi presenti all'avvio del set. Al termine, l'esito e
    i progressi concreti (Bless, Altare e corruzioni preparate) attribuiscono un
    vantaggio alle caratteristiche delle mosse scelte rispetto alle alternative.
    I nuovi pesi saranno quindi usati dal set successivo.
    """
    current = {
        bot: {
            feature: _clamp(
                float(config.learning_weights.get(bot, {}).get(feature, 0.0)),
                -1.5,
                1.5,
            )
            for feature in FEATURE_NAMES
        }
        for bot in BOT_NAMES
    }
    diagnostics: dict[str, dict[str, float]] = {
        bot: {
            "games": 0.0,
            "wins": 0.0,
            "decisions": 0.0,
            "reward_sum": 0.0,
            "bless_points": 0.0,
            "bless_events": 0.0,
            "altar_offers": 0.0,
            "enemy_corruptions": 0.0,
            "unused_actions": 0.0,
            "stasis_wasted": 0.0,
            "own_eye_buffs": 0.0,
            "high_karma_eye_buffs": 0.0,
            "enemy_eye_debuffs": 0.0,
        }
        for bot in BOT_NAMES
    }
    gradients: dict[str, dict[str, float]] = {
        bot: {feature: 0.0 for feature in FEATURE_NAMES} for bot in BOT_NAMES
    }

    for result in results:
        rewards: list[float] = []
        for player in (0, 1):
            telemetry = result.telemetry
            bless_points = float(sum(telemetry.card_bless_points[player].values()))
            bless_events = float(sum(telemetry.card_bless_events[player].values()))
            outcome = 1.0 if result.winner == player else (-1.0 if result.winner is not None else 0.0)
            margin = result.scores[player] - result.scores[1 - player]
            progress_reward = (
                0.030 * bless_points
                + 0.045 * telemetry.altar_offers[player]
                + 0.018 * telemetry.enemy_corruptions_created[player]
                + 0.012 * telemetry.own_eye_buffs[player]
                + 0.090 * telemetry.high_karma_eye_buffs[player]
                + 0.018 * telemetry.enemy_eye_debuffs[player]
                - 0.055 * telemetry.unused_actions[player]
                - 0.110 * telemetry.stasis_wasted[player]
            )
            rewards.append(1.35 * outcome + 0.45 * _clamp(margin / 10.0, -1.0, 1.0) + progress_reward)

            bot = result.bot_names[player]
            bucket = diagnostics[bot]
            bucket["games"] += 1
            bucket["wins"] += float(result.winner == player)
            bucket["decisions"] += telemetry.learning_decisions[player]
            bucket["bless_points"] += bless_points
            bucket["bless_events"] += bless_events
            bucket["altar_offers"] += telemetry.altar_offers[player]
            bucket["enemy_corruptions"] += telemetry.enemy_corruptions_created[player]
            bucket["unused_actions"] += telemetry.unused_actions[player]
            bucket["stasis_wasted"] += telemetry.stasis_wasted[player]
            bucket["own_eye_buffs"] += telemetry.own_eye_buffs[player]
            bucket["high_karma_eye_buffs"] += telemetry.high_karma_eye_buffs[player]
            bucket["enemy_eye_debuffs"] += telemetry.enemy_eye_debuffs[player]
            for kind, count in telemetry.chosen_action_kinds[player].items():
                key = f"action_{kind}"
                bucket[key] = bucket.get(key, 0.0) + count

        for player in (0, 1):
            bot = result.bot_names[player]
            advantage = rewards[player] - rewards[1 - player]
            diagnostics[bot]["reward_sum"] += rewards[player]
            decisions = max(1, result.telemetry.learning_decisions[player])
            for feature in FEATURE_NAMES:
                gradient = result.telemetry.learning_gradients[player].get(feature, 0.0)
                gradients[bot][feature] += advantage * gradient / decisions

    next_weights = {bot: dict(weights) for bot, weights in current.items()}
    changes: list[dict[str, Any]] = []
    if config.learning_enabled and results:
        learning_rate = 0.048
        for bot in BOT_NAMES:
            experiences = max(1.0, diagnostics[bot]["games"])
            for feature in FEATURE_NAMES:
                average_gradient = gradients[bot][feature] / experiences
                step = _clamp(learning_rate * average_gradient, -0.10, 0.10)
                if feature == "eye_karma_setup":
                    # Questo obiettivo e' richiesto esplicitamente dal gioco:
                    # il segnale non dipende soltanto dalla vittoria finale,
                    # ma premia anche il progresso osservabile del setup. Il
                    # bonus resta piccolo e nullo se il bot non potenzia una
                    # Maledizione davvero redditizia o non riduce l'avversario.
                    high_karma_rate = diagnostics[bot]["high_karma_eye_buffs"] / experiences
                    debuff_rate = diagnostics[bot]["enemy_eye_debuffs"] / experiences
                    step += (
                        0.012 * min(1.5, high_karma_rate)
                        + 0.004 * min(1.0, debuff_rate)
                    )
                    step = _clamp(step, -0.10, 0.10)
                # Una lievissima regolarizzazione evita che molte generazioni
                # rendano irreversibile un segnale occasionale.
                before = current[bot][feature]
                after = _clamp(before * 0.998 + step, -1.5, 1.5)
                next_weights[bot][feature] = after
                changes.append(
                    {
                        "bot": bot,
                        "feature": feature,
                        "label": FEATURE_LABELS[feature],
                        "before": _round(before, 4),
                        "after": _round(after, 4),
                        "delta": _round(after - before, 4),
                    }
                )

    readable_diagnostics: dict[str, dict[str, Any]] = {}
    for bot, bucket in diagnostics.items():
        games = bucket["games"]
        malediction_plays = bucket.get("action_play_malediction", 0.0)
        prayer_plays = bucket.get("action_play_prayer", 0.0)
        total_plays = malediction_plays + prayer_plays
        prayer_share = _percent(prayer_plays, total_plays)
        attacks = bucket.get("action_attack", 0.0) + bucket.get("action_attack_direct", 0.0)
        mean_points_per_bless = (
            bucket["bless_points"] / bucket["bless_events"]
            if bucket["bless_events"]
            else 0.0
        )
        if games and total_plays:
            mode_name = "Preghiere" if (prayer_share or 0) >= 50 else "Maledizioni"
            mode_share = (prayer_share or 0) if mode_name == "Preghiere" else 100 - (prayer_share or 0)
            tendencies = [
                f"Il {mode_share:.1f}% delle carte calate viene usato come {mode_name}.",
                f"Effettua {attacks / games:.2f} attacchi e ottiene {bucket['bless_points'] / games:.2f} PV di Bless per partita.",
                f"Ogni Bless vale in media {mean_points_per_bless:.2f} PV; prepara {bucket['enemy_corruptions'] / games:.2f} corruzioni avversarie per partita.",
                f"Potenzia l'Occhio di proprie Maledizioni {bucket['own_eye_buffs'] / games:.2f} volte per partita; {bucket['high_karma_eye_buffs'] / games:.2f} bersagli hanno Karma alto e Occhio basso.",
                f"Riduce o prepara la riduzione dell'Occhio avversario {bucket['enemy_eye_debuffs'] / games:.2f} volte per partita.",
            ]
        else:
            tendencies = ["Questo bot non è stato usato nel set: non ci sono ancora tendenze osservabili."]
        if games and bucket["unused_actions"] / games <= 0.10 and bucket["stasis_wasted"] / games <= 0.05:
            tendencies.append("Quasi non lascia Azioni inutilizzate e non spreca la rimozione della Stasi.")
        readable_diagnostics[bot] = {
            "games": int(games),
            "wins": int(bucket["wins"]),
            "win_rate": _percent(bucket["wins"], games),
            "decisions": int(bucket["decisions"]),
            "mean_reward": _round(bucket["reward_sum"] / games if games else 0.0, 3),
            "bless_points_per_game": _round(bucket["bless_points"] / games if games else 0.0),
            "bless_events_per_game": _round(bucket["bless_events"] / games if games else 0.0),
            "altar_offers_per_game": _round(bucket["altar_offers"] / games if games else 0.0),
            "enemy_corruptions_per_game": _round(bucket["enemy_corruptions"] / games if games else 0.0),
            "unused_actions_per_game": _round(bucket["unused_actions"] / games if games else 0.0),
            "wasted_stasis_per_game": _round(bucket["stasis_wasted"] / games if games else 0.0),
            "own_eye_buffs_per_game": _round(bucket["own_eye_buffs"] / games if games else 0.0),
            "high_karma_eye_buffs_per_game": _round(bucket["high_karma_eye_buffs"] / games if games else 0.0),
            "enemy_eye_debuffs_per_game": _round(bucket["enemy_eye_debuffs"] / games if games else 0.0),
            "malediction_plays_per_game": _round(malediction_plays / games if games else 0.0),
            "prayer_plays_per_game": _round(prayer_plays / games if games else 0.0),
            "prayer_play_share": prayer_share,
            "attacks_per_game": _round(attacks / games if games else 0.0),
            "mean_points_per_bless": _round(mean_points_per_bless),
            "tendencies": tendencies,
        }

    changes.sort(key=lambda item: abs(item["delta"] or 0.0), reverse=True)
    generation_after = int(config.learning_generation) + int(bool(config.learning_enabled and results))
    total_games_after = int(config.learning_total_games) + (len(results) if config.learning_enabled else 0)
    return {
        "enabled": bool(config.learning_enabled),
        "generation_before": int(config.learning_generation),
        "generation_after": generation_after,
        "games_in_set": len(results),
        "total_games_after": total_games_after,
        "reward_formula": "esito + margine PV + Bless + Altare + corruzioni + Occhio utile su Karma alto - azioni sprecate",
        "diagnostics": readable_diagnostics,
        "changes": changes,
        "top_changes": changes[:10],
        "next_state": {
            "version": 2,
            "generation": generation_after,
            "total_games": total_games_after,
            "weights": next_weights,
        },
    }


def _aggregate(config: SimulationConfig, results: list[GameResult]) -> SimulationReport:
    card_definitions = get_deck_definitions(config.deck)
    games = len(results)
    turns = [result.turns for result in results]
    winner_counts = Counter(result.winner for result in results)
    first_wins = sum(result.winner == result.first_player for result in results)
    second_wins = sum(
        result.winner is not None and result.winner != result.first_player
        for result in results
    )
    triggered = [result for result in results if result.final_trigger_player is not None]
    trigger_wins = sum(result.final_trigger_won is True for result in triggered)
    cause_counts = Counter(result.final_trigger_cause or "Non attivati" for result in results)
    action_counts: Counter[str] = Counter()
    for result in results:
        action_counts.update(result.telemetry.actions)

    invocation_totals = [
        sum(result.telemetry.invocations[player] for result in results)
        for player in (0, 1)
    ]
    glyph_use_totals = [
        sum(result.telemetry.glyph_uses[player] for result in results)
        for player in (0, 1)
    ]
    charge_totals = [
        sum(result.telemetry.charges_created[player] for result in results)
        for player in (0, 1)
    ]

    summary = {
        "games": games,
        "completed_games": sum(not result.stalemate for result in results),
        "technical_stalemates": sum(result.stalemate for result in results),
        "player_1_win_rate": _percent(winner_counts[0], games),
        "player_2_win_rate": _percent(winner_counts[1], games),
        "first_player_win_rate": _percent(first_wins, games),
        "second_player_win_rate": _percent(second_wins, games),
        "mean_turns": _round(statistics.mean(turns) if turns else 0),
        "median_turns": _round(statistics.median(turns) if turns else 0),
        "p90_turns": _round(_percentile(turns, 0.90)),
        "min_turns": min(turns, default=0),
        "max_turns": max(turns, default=0),
        "turn_distribution": dict(sorted(Counter(turns).items())),
        "finals_triggered": len(triggered),
        "final_trigger_win_rate": _percent(trigger_wins, len(triggered)),
        "final_trigger_causes": dict(cause_counts),
        "mean_score_player_1": _round(statistics.mean(r.scores[0] for r in results) if results else 0),
        "mean_score_player_2": _round(statistics.mean(r.scores[1] for r in results) if results else 0),
        "mean_combats": _round(statistics.mean(r.telemetry.combats for r in results) if results else 0),
        "mean_direct_attacks": _round(statistics.mean(r.telemetry.direct_attacks for r in results) if results else 0),
        "mean_mulliganed_cards": _round(statistics.mean(r.telemetry.mulliganed for r in results) if results else 0),
        "mean_stasis_removed_with_action": _round(statistics.mean(r.telemetry.stasis_removed for r in results) if results else 0),
        "mean_altar_offers": _round(statistics.mean(sum(r.telemetry.altar_offers) for r in results) if results else 0),
        "mean_enemy_corruptions_created": _round(statistics.mean(sum(r.telemetry.enemy_corruptions_created) for r in results) if results else 0),
        "mean_unused_actions": _round(statistics.mean(sum(r.telemetry.unused_actions) for r in results) if results else 0),
        "mean_wasted_stasis": _round(statistics.mean(sum(r.telemetry.stasis_wasted) for r in results) if results else 0),
        "invocations_total": sum(invocation_totals),
        "invocations_player_1": invocation_totals[0],
        "invocations_player_2": invocation_totals[1],
        "mean_invocations_per_game": _round(sum(invocation_totals) / games if games else 0),
        "glyph_uses_total": sum(glyph_use_totals),
        "glyph_uses_player_1": glyph_use_totals[0],
        "glyph_uses_player_2": glyph_use_totals[1],
        "mean_glyph_uses_per_game": _round(sum(glyph_use_totals) / games if games else 0),
        "charges_created_total": sum(charge_totals),
        "charges_created_player_1": charge_totals[0],
        "charges_created_player_2": charge_totals[1],
        "mean_charges_created_per_game": _round(sum(charge_totals) / games if games else 0),
        "action_counts": dict(action_counts),
    }

    bots: dict[str, dict[str, int]] = defaultdict(lambda: {"player_games": 0, "wins": 0, "losses": 0, "first": 0})
    pairs: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"games": 0, "left_wins": 0, "right_wins": 0, "stalemates": 0})
    card_acc: dict[int, dict[str, int]] = {
        card_id: defaultdict(int) for card_id in card_definitions
    }
    card_bot_appearances: dict[int, Counter[str]] = {
        card_id: Counter() for card_id in card_definitions
    }
    ability_acc: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    ability_bot_appearances: dict[str, Counter[str]] = defaultdict(Counter)

    total_player_wins = 0
    total_player_games = games * 2
    for result in results:
        pair_bucket = pairs[result.bot_names]
        pair_bucket["games"] += 1
        if result.winner == 0:
            pair_bucket["left_wins"] += 1
        elif result.winner == 1:
            pair_bucket["right_wins"] += 1
        else:
            pair_bucket["stalemates"] += 1

        for player in (0, 1):
            won = result.winner == player
            lost = result.winner is not None and result.winner != player
            bot = result.bot_names[player]
            bots[bot]["player_games"] += 1
            bots[bot]["wins"] += int(won)
            bots[bot]["losses"] += int(lost)
            bots[bot]["first"] += int(result.first_player == player)
            total_player_wins += int(won)

            telemetry = result.telemetry
            played_ids = set(telemetry.card_modes[player])
            for card_id, mode_counts in telemetry.card_modes[player].items():
                bucket = card_acc[card_id]
                maledictions = mode_counts.get("Maledizione", 0)
                prayers = mode_counts.get("Preghiera", 0)
                bucket["plays"] += maledictions + prayers
                bucket["maledictions"] += maledictions
                bucket["prayers"] += prayers
            for card_id in played_ids:
                bucket = card_acc[card_id]
                bucket["appearances"] += 1
                bucket["wins"] += int(won)
                bucket["losses"] += int(lost)
                bucket["drawn_results"] += int(result.winner is None)
                card_bot_appearances[card_id][bot] += 1
            for card_id, count in telemetry.card_draws[player].items():
                card_acc[card_id]["draws"] += count
            for card_id, points in telemetry.card_bless_points[player].items():
                card_acc[card_id]["bless_points"] += points
            for card_id, events in telemetry.card_bless_events[player].items():
                card_acc[card_id]["bless_events"] += events

            for ability, triggers in telemetry.ability_by_player[player].items():
                bucket = ability_acc[ability]
                bucket["triggers"] += triggers
                bucket["appearances"] += 1
                bucket["wins"] += int(won)
                bucket["losses"] += int(lost)
                ability_bot_appearances[ability][bot] += 1

    baseline_win_rate = _percent(total_player_wins, total_player_games) or 0.0
    bot_stats = []
    for name, bucket in bots.items():
        bot_stats.append(
            {
                "bot": name,
                **bucket,
                "win_rate": _percent(bucket["wins"], bucket["player_games"]),
                "first_share": _percent(bucket["first"], bucket["player_games"]),
            }
        )
    bot_stats.sort(key=lambda item: (item["win_rate"] or -1, item["player_games"]), reverse=True)
    bot_baselines = {
        item["bot"]: (item["wins"] / item["player_games"] if item["player_games"] else 0.0)
        for item in bot_stats
    }

    pair_stats = []
    for (left, right), bucket in pairs.items():
        pair_stats.append(
            {
                "pair": f"{left} → {right}",
                "bot_1": left,
                "bot_2": right,
                **bucket,
                "bot_1_win_rate": _percent(bucket["left_wins"], bucket["games"]),
                "bot_2_win_rate": _percent(bucket["right_wins"], bucket["games"]),
            }
        )
    pair_stats.sort(key=lambda item: (item["bot_1"], item["bot_2"]))

    card_stats: list[dict[str, Any]] = []
    for card_id, definition in card_definitions.items():
        bucket = card_acc[card_id]
        plays = bucket["plays"]
        appearances = bucket["appearances"]
        maledictions = bucket["maledictions"]
        prayers = bucket["prayers"]
        win_rate = _percent(bucket["wins"], appearances)
        expected_wins = sum(
            count * bot_baselines.get(bot, 0.0)
            for bot, count in card_bot_appearances[card_id].items()
        )
        adjusted_delta = (
            100 * (bucket["wins"] - expected_wins) / appearances
            if appearances
            else None
        )
        malediction_share = _percent(maledictions, plays)
        if plays == 0:
            preferred_mode = "Mai giocata"
        elif maledictions == prayers:
            preferred_mode = "Equilibrata"
        elif maledictions > prayers:
            preferred_mode = "Maledizione"
        else:
            preferred_mode = "Preghiera"
        card_stats.append(
            {
                "id": card_id,
                "name": definition.name,
                "form": definition.form.value,
                "prayer_type": definition.prayer_type.value,
                "draws": bucket["draws"],
                "plays": plays,
                "plays_per_100_games": _round(100 * plays / games if games else 0),
                "maledictions": maledictions,
                "prayers": prayers,
                "malediction_share": malediction_share,
                "preferred_mode": preferred_mode,
                "player_game_appearances": appearances,
                "wins_when_played": bucket["wins"],
                "losses_when_played": bucket["losses"],
                "win_rate_when_played": win_rate,
                "win_delta_pp": _round((win_rate - baseline_win_rate) if win_rate is not None else None),
                "adjusted_win_delta_pp": _round(adjusted_delta),
                "bless_events": bucket["bless_events"],
                "bless_points": bucket["bless_points"],
                "mean_points_per_bless": _round(
                    bucket["bless_points"] / bucket["bless_events"]
                    if bucket["bless_events"]
                    else None
                ),
            }
        )

    ability_stats = []
    for ability, bucket in ability_acc.items():
        win_rate = _percent(bucket["wins"], bucket["appearances"])
        expected_wins = sum(
            count * bot_baselines.get(bot, 0.0)
            for bot, count in ability_bot_appearances[ability].items()
        )
        adjusted_delta = (
            100 * (bucket["wins"] - expected_wins) / bucket["appearances"]
            if bucket["appearances"]
            else None
        )
        ability_stats.append(
            {
                "ability": ability,
                "triggers": bucket["triggers"],
                "player_game_appearances": bucket["appearances"],
                "wins_when_triggered": bucket["wins"],
                "win_rate_when_triggered": win_rate,
                "win_delta_pp": _round((win_rate - baseline_win_rate) if win_rate is not None else None),
                "adjusted_win_delta_pp": _round(adjusted_delta),
                "triggers_per_100_games": _round(100 * bucket["triggers"] / games if games else 0),
            }
        )
    ability_stats.sort(key=lambda item: item["triggers"], reverse=True)

    learning = _learning_update(config, results)
    insights = _build_insights(summary, bot_stats, card_stats, ability_stats, games)
    if config.learning_enabled:
        strongest_change = learning["top_changes"][0] if learning["top_changes"] else None
        if strongest_change and abs(strongest_change["delta"] or 0) >= 0.0001:
            direction = "premiato" if strongest_change["delta"] > 0 else "ridotto"
            learning_text = (
                f"Generazione {learning['generation_after']}: per {strongest_change['bot']} il segnale piu' modificato e' "
                f"{strongest_change['label']} ({direction} di {abs(strongest_change['delta']):.3f}). "
                "I nuovi pesi saranno usati dal prossimo set."
            )
        else:
            learning_text = (
                f"Generazione {learning['generation_after']} completata; il campione non ha prodotto "
                "una variazione di peso rilevante."
            )
        insights.insert(
            0,
            {
                "title": "Apprendimento dei bot",
                "text": learning_text,
                "level": "info",
            },
        )
    return SimulationReport(
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        config=asdict(config),
        summary=summary,
        bot_stats=bot_stats,
        pair_stats=pair_stats,
        card_stats=card_stats,
        ability_stats=ability_stats,
        insights=insights,
        learning=learning,
        replay=_replay_payload(results[0]),
    )


def _build_insights(
    summary: dict[str, Any],
    bot_stats: list[dict[str, Any]],
    card_stats: list[dict[str, Any]],
    ability_stats: list[dict[str, Any]],
    games: int,
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    first = summary["first_player_win_rate"] or 0
    if abs(first - 50) < 4:
        text = f"Il vantaggio del primo turno è contenuto: {first:.1f}% di vittorie."
        level = "ok"
    else:
        direction = "primo" if first > 50 else "secondo"
        text = f"Segnale da verificare: vince più spesso il {direction} giocatore ({first:.1f}% al primo)."
        level = "warning"
    insights.append({"title": "Ordine di turno", "text": text, "level": level})

    final_rate = summary["final_trigger_win_rate"]
    if final_rate is not None:
        level = "warning" if final_rate >= 62 or final_rate <= 38 else "ok"
        insights.append(
            {
                "title": "Turni Finali",
                "text": f"Chi li attiva vince il {final_rate:.1f}% delle partite in cui vengono attivati.",
                "level": level,
            }
        )

    eligible_bots = [item for item in bot_stats if item["player_games"] >= max(12, games // 25)]
    if len(eligible_bots) >= 2:
        best = eligible_bots[0]
        next_best = eligible_bots[1]
        gap = (best["win_rate"] or 0) - (next_best["win_rate"] or 0)
        level = "warning" if (best["win_rate"] or 0) >= 58 and gap >= 5 else "info"
        insights.append(
            {
                "title": "Strategia dominante",
                "text": (
                    f"{best['bot']} è la famiglia migliore nel campione: "
                    f"{best['win_rate']:.1f}% su {best['player_games']} presenze "
                    f"({gap:+.1f} punti sulla seconda)."
                ),
                "level": level,
            }
        )

    minimum_sample = max(12, int(games * 0.025))
    reliable = [
        card for card in card_stats
        if card["player_game_appearances"] >= minimum_sample
        and card["adjusted_win_delta_pp"] is not None
    ]
    if reliable:
        strongest = max(reliable, key=lambda card: card["adjusted_win_delta_pp"])
        weakest = min(reliable, key=lambda card: card["adjusted_win_delta_pp"])
        spread = strongest["adjusted_win_delta_pp"] - weakest["adjusted_win_delta_pp"]
        if spread < 0.5:
            insights.append(
                {
                    "title": "Carte associate all'esito",
                    "text": (
                        "Il campione non contiene abbastanza variazione di esito tra posti al tavolo e semi "
                        "per isolare un segnale carta-vittoria. Ripeti la sfida con un seed diverso."
                    ),
                    "level": "neutral",
                }
            )
        else:
            insights.append(
                {
                    "title": "Carte associate all'esito",
                    "text": (
                        f"{strongest['name']} ha il delta carta-vittoria più alto "
                        f"({strongest['adjusted_win_delta_pp']:+.1f} punti); {weakest['name']} il più basso "
                        f"({weakest['adjusted_win_delta_pp']:+.1f}). Il dato è corretto per il posto al tavolo del Bot."
                    ),
                    "level": "warning" if abs(strongest["adjusted_win_delta_pp"]) >= 12 or abs(weakest["adjusted_win_delta_pp"]) >= 12 else "info",
                }
            )

    polarized = [
        card for card in card_stats
        if card["plays"] >= minimum_sample
        and card["malediction_share"] is not None
        and (card["malediction_share"] >= 85 or card["malediction_share"] <= 15)
    ]
    polarized.sort(key=lambda card: abs(card["malediction_share"] - 50), reverse=True)
    if polarized:
        names = ", ".join(
            f"{card['name']} ({card['preferred_mode']})" for card in polarized[:4]
        )
        insights.append(
            {
                "title": "Scelta quasi obbligata",
                "text": f"I bot polarizzano soprattutto: {names}.",
                "level": "info",
            }
        )

    play_counts = [card["plays"] for card in card_stats]
    median_plays = statistics.median(play_counts) if play_counts else 0
    underplayed = sorted(card_stats, key=lambda card: card["plays"])
    underplayed = [card for card in underplayed if card["plays"] < median_plays * 0.45][:4]
    if underplayed:
        insights.append(
            {
                "title": "Carte poco usate",
                "text": ", ".join(f"{card['name']} ({card['plays']} giocate)" for card in underplayed),
                "level": "info",
            }
        )

    reliable_abilities = [
        ability for ability in ability_stats
        if ability["player_game_appearances"] >= minimum_sample
    ]
    if reliable_abilities:
        best = max(
            reliable_abilities,
            key=lambda ability: (
                ability["adjusted_win_delta_pp"]
                if ability["adjusted_win_delta_pp"] is not None
                else -999
            ),
        )
        if any(abs(ability["adjusted_win_delta_pp"] or 0) >= 0.5 for ability in reliable_abilities):
            insights.append(
                {
                    "title": "Abilità",
                    "text": (
                        f"Tra le abilità con campione sufficiente, {best['ability']} mostra la maggiore "
                        f"associazione con la vittoria corretta per posto al tavolo ({best['adjusted_win_delta_pp']:+.1f} punti)."
                    ),
                    "level": "info",
                }
            )

    insights.append(
        {
            "title": "Come leggere il report",
            "text": (
                "I risultati descrivono il Bot e le sue euristiche. Un segnale stabile tra posti al tavolo e semi diversi "
                "è più affidabile di una singola percentuale."
            ),
            "level": "neutral",
        }
    )
    return insights


def run_simulation(
    config: SimulationConfig,
    progress: ProgressCallback | None = None,
) -> SimulationReport:
    config.validate()
    jobs = _jobs(config)
    results = list(_iter_results(config, jobs, progress))
    return _aggregate(config, results)


def _markdown_report(report: SimulationReport) -> str:
    summary = report.summary
    lines = [
        "# Report simulazione Bless",
        "",
        f"Generato: {report.generated_at}",
        f"Partite: {summary['games']} - Mazzo: {report.config['deck']}",
        "",
        "## Risultati principali",
        "",
        f"- Durata media: {summary['mean_turns']} turni (mediana {summary['median_turns']}, P90 {summary['p90_turns']})",
        f"- Vittorie primo giocatore: {summary['first_player_win_rate']}%",
        f"- Vittorie secondo giocatore: {summary['second_player_win_rate']}%",
        f"- Vittorie di chi attiva i Turni Finali: {summary['final_trigger_win_rate']}%",
        f"- Scontri medi: {summary['mean_combats']} (Attacchi Diretti: {summary['mean_direct_attacks']})",
    ]
    if report.config["deck"] == "TuonoSabbia":
        lines.extend(
            [
                f"- Invocazioni: {summary['invocations_total']} totali ({summary['mean_invocations_per_game']} per partita)",
                f"- Effetti Glifo usati: {summary['glyph_uses_total']} totali ({summary['mean_glyph_uses_per_game']} per partita)",
                f"- Carte Caricate: {summary['charges_created_total']} totali ({summary['mean_charges_created_per_game']} per partita)",
            ]
        )
    lines.extend(["", "## Feedback automatico", ""])
    for insight in report.insights:
        lines.append(f"- **{insight['title']}**: {insight['text']}")
    learning = report.learning
    lines.extend(
        [
            "",
            "## Apprendimento dei bot",
            "",
            f"- Generazione completata: {learning['generation_after']}",
            f"- Partite di addestramento cumulative: {learning['total_games_after']}",
            f"- Criterio: {learning['reward_formula']}",
        ]
    )
    for change in learning.get("top_changes", [])[:6]:
        lines.append(
            f"- {change['bot']} - {change['label']}: {change['before']:+.3f} -> "
            f"{change['after']:+.3f} ({change['delta']:+.3f})"
        )
    lines.extend(
        [
            "",
            "## Bot",
            "",
            "| Famiglia | Presenze | Vittorie | Win rate |",
            "|---|---:|---:|---:|",
        ]
    )
    for item in report.bot_stats:
        lines.append(f"| {item['bot']} | {item['player_games']} | {item['wins']} | {item['win_rate']}% |")
    lines.extend(
        [
            "",
            "## Carte con maggiore associazione positiva",
            "",
            "| ID | Carta | Giocate | Modalità prevalente | Win rate quando giocata | Delta |",
            "|---:|---|---:|---|---:|---:|",
        ]
    )
    cards = [card for card in report.card_stats if card["adjusted_win_delta_pp"] is not None]
    cards.sort(key=lambda card: card["adjusted_win_delta_pp"], reverse=True)
    for card in cards[:12]:
        lines.append(
            f"| {card['id']} | {card['name']} | {card['plays']} | {card['preferred_mode']} | "
            f"{card['win_rate_when_played']}% | {card['adjusted_win_delta_pp']:+.1f} pp |"
        )
    lines.extend(
        [
            "",
            "> Nota: le associazioni carta-vittoria non dimostrano da sole che una carta sia troppo forte o debole.",
            "",
        ]
    )
    return "\n".join(lines)


def export_report_bundle(report: SimulationReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = directory / f"bless-report-{stamp}"
    json_path = base.with_suffix(".json")
    cards_path = directory / f"bless-carte-{stamp}.csv"
    abilities_path = directory / f"bless-abilita-{stamp}.csv"
    replay_path = directory / f"bless-replay-{stamp}.json"
    markdown_path = base.with_suffix(".md")

    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    replay_path.write_text(json.dumps(report.replay, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")

    with cards_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report.card_stats[0]))
        writer.writeheader()
        writer.writerows(report.card_stats)
    if report.ability_stats:
        with abilities_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(report.ability_stats[0]))
            writer.writeheader()
            writer.writerows(report.ability_stats)

    zip_path = directory / f"bless-report-{stamp}.zip"
    paths = [json_path, cards_path, replay_path, markdown_path]
    if abilities_path.exists():
        paths.append(abilities_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)
    return zip_path
