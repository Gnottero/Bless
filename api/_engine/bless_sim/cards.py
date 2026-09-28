from __future__ import annotations

import json
from pathlib import Path

from .model import CardDefinition, Form, PrayerType


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DECK_FILES = {
    "luce-ombra": DATA_DIR / "luce_ombra.json",
    "tuono-sabbia": DATA_DIR / "tuono_sabbia.json",
}
DECK_ALIASES = {
    "luce-ombra": "luce-ombra",
    "luceombra": "luce-ombra",
    "Luce-Ombra": "luce-ombra",
    "Luce–Ombra": "luce-ombra",
    "tuono-sabbia": "tuono-sabbia",
    "tuonosabbia": "tuono-sabbia",
    "TuonoSabbia": "tuono-sabbia",
    "Tuono-Sabbia": "tuono-sabbia",
}


def normalize_deck_id(deck: str | None) -> str:
    if deck is None:
        return "luce-ombra"
    key = str(deck).strip()
    normalized = DECK_ALIASES.get(key) or DECK_ALIASES.get(key.lower())
    if normalized is None:
        raise ValueError(f"Mazzo non disponibile: {deck}")
    return normalized


def _load_deck(deck_id: str) -> tuple[dict[str, object], dict[int, CardDefinition]]:
    payload = json.loads(DECK_FILES[deck_id].read_text(encoding="utf-8"))
    definitions: dict[int, CardDefinition] = {}
    for raw in payload["cards"]:
        definition = CardDefinition(
            id=int(raw["id"]),
            name=str(raw["name"]),
            form=Form(raw["form"]),
            eye=int(raw["eye"]),
            karma=int(raw["karma"]),
            malediction_text=str(raw["malediction_text"]),
            prayer_text=str(raw["prayer_text"]),
            prayer_type=PrayerType(raw["prayer_type"]),
            image=raw.get("image"),
            traits=tuple(str(trait) for trait in raw.get("traits", [])),
        )
        definitions[definition.id] = definition
    if sorted(definitions) != list(range(1, 63)):
        raise ValueError(f"Il mazzo {payload.get('name', deck_id)} deve contenere esattamente gli ID 1-62")
    return payload, definitions


DECK_PAYLOADS: dict[str, dict[str, object]] = {}
DECK_DEFINITIONS: dict[str, dict[int, CardDefinition]] = {}
for _deck_id in DECK_FILES:
    _payload, _definitions = _load_deck(_deck_id)
    DECK_PAYLOADS[_deck_id] = _payload
    DECK_DEFINITIONS[_deck_id] = _definitions

# Compatibilita' con l'API originale: senza mazzo esplicito si usa Luce-Ombra.
CARD_DEFINITIONS = DECK_DEFINITIONS["luce-ombra"]


def get_deck_definitions(deck: str | None = None) -> dict[int, CardDefinition]:
    return DECK_DEFINITIONS[normalize_deck_id(deck)]


def get_deck_name(deck: str | None = None) -> str:
    payload = DECK_PAYLOADS[normalize_deck_id(deck)]
    return str(payload.get("name") or deck)


def get_card_definition(card_id: int, deck: str | None = None) -> CardDefinition:
    return get_deck_definitions(deck)[card_id]


def card_image_path(deck: str | None, card_id: int) -> str:
    deck_id = normalize_deck_id(deck)
    definition = DECK_DEFINITIONS[deck_id][card_id]
    if deck_id == "tuono-sabbia":
        filename = definition.image or f"ThunderSand_{card_id:02d}.png"
        return f"/cards/tuono-sabbia/{filename}"
    return f"/cards/{card_id}.jpg"


# Valori euristici iniziali. Non sono punteggi di bilanciamento: servono ai bot
# per confrontare azioni immediate. Il report usa solo risultati osservati.
MALEDICTION_EFFECT_VALUE: dict[int, float] = {
    1: 3.0, 2: 2.0, 3: 1.5, 4: 2.6, 5: 1.2, 6: 3.2, 7: 3.0,
    8: 2.0, 9: 1.7, 10: 2.8, 11: 0.0, 12: 2.4, 13: 2.3, 14: 2.2,
    15: 2.0, 16: 2.0, 17: 1.7, 18: 2.0, 19: 2.4, 20: 1.7, 21: 1.8,
    22: 3.0, 23: 2.3, 24: 2.1, 25: 2.0, 26: 2.1, 27: 1.8, 28: 3.0,
    29: 2.4, 30: 3.0, 31: 2.0, 32: 1.5, 33: 2.7, 34: 2.4, 35: 2.3,
    36: 3.0, 37: 2.8, 38: 2.0, 39: 3.0, 40: 2.7, 41: 1.7, 42: 2.2,
    43: 1.8, 44: 3.0, 45: 2.2, 46: 2.0, 47: 2.0, 48: 2.8, 49: 2.2,
    50: 1.3, 51: 0.0, 52: 2.1, 53: 2.2, 54: 2.6, 55: 2.4, 56: 2.1,
    57: 2.0, 58: 2.4, 59: 2.0, 60: 3.0, 61: 0.0, 62: 2.5,
}


PRAYER_EFFECT_VALUE: dict[int, float] = {
    1: 2.2, 2: 2.7, 3: 2.2, 4: 2.2, 5: 2.8, 6: 3.3, 7: 2.3,
    8: 2.1, 9: 2.0, 10: 2.8, 11: 3.2, 12: 3.5, 13: 2.8, 14: 2.4,
    15: 2.5, 16: 2.1, 17: 2.8, 18: 3.4, 19: 2.6, 20: 3.0, 21: 2.5,
    22: 4.0, 23: 2.0, 24: 2.8, 25: 3.0, 26: 2.6, 27: 2.1, 28: 3.0,
    29: 3.1, 30: 2.2, 31: 2.7, 32: 2.2, 33: 2.8, 34: 3.6, 35: 3.4,
    36: 2.5, 37: 2.8, 38: 2.0, 39: 4.0, 40: 2.6, 41: 3.0, 42: 2.5,
    43: 2.1, 44: 3.0, 45: 2.8, 46: 3.2, 47: 2.6, 48: 3.0, 49: 2.5,
    50: 2.5, 51: 3.5, 52: 2.8, 53: 2.6, 54: 3.3, 55: 3.0, 56: 2.0,
    57: 3.0, 58: 3.1, 59: 2.6, 60: 2.8, 61: 3.7, 62: 2.4,
}


def _text_value(text: str, prayer_type: PrayerType) -> float:
    lowered = text.lower()
    value = 1.45
    for keyword, bonus in {
        "punto vittoria": 0.9,
        "blessa": 0.8,
        "spezza": 0.65,
        "corrompi": 0.55,
        "occhio": 0.35,
        "karma": 0.45,
        "carica": 0.30,
        "marchia": 0.35,
        "gioca": 0.35,
        "vince": 0.45,
    }.items():
        if keyword in lowered:
            value += bonus
    if prayer_type in {PrayerType.GLYPH, PrayerType.SIGIL}:
        value += 0.35
    return min(4.5, value)


def malediction_effect_value(deck: str | None, card_id: int) -> float:
    deck_id = normalize_deck_id(deck)
    if deck_id == "luce-ombra":
        return MALEDICTION_EFFECT_VALUE[card_id]
    definition = DECK_DEFINITIONS[deck_id][card_id]
    value = _text_value(definition.malediction_text, definition.prayer_type)
    if "Colosso" in definition.malediction_text:
        value += 0.75
    return min(4.8, value)


def prayer_effect_value(deck: str | None, card_id: int) -> float:
    deck_id = normalize_deck_id(deck)
    if deck_id == "luce-ombra":
        return PRAYER_EFFECT_VALUE[card_id]
    definition = DECK_DEFINITIONS[deck_id][card_id]
    return _text_value(definition.prayer_text, definition.prayer_type)


ABILITY_LABELS = {
    "rivalita": "Rivalità",
    "impatto": "Impatto",
    "barriera": "Barriera",
    "fato": "Fato",
    "schermatura": "Schermatura",
    "emblema": "Emblema",
    "colosso": "Colosso",
    "cadenza": "Cadenza",
    "vince": "Vince",
    "vince_sempre": "Vince sempre",
}
