"""Pure inbound-message classification (G5 and the third-party document
guard, F11 T4/S4).

Everything here is a pure function of its input: no I/O, no clock, no LLM.
The keyword lists are tiny and multilingual (es/pt/en) on purpose: the
classifier runs on every candidate chat message in the persisted dispatch
path, so it must be cheap, deterministic and auditable. Matching normalizes
the text (lowercase, accents stripped) and matches single abusive words with
word boundaries so ordinary words that contain a risky fragment
("disputar" contains "puta") never fire.

The classifier never decides anything: it returns a label. The persisted
dispatch path (app/sim/dispatch.py) turns a label into a typed escalation
event, an audit row and a canned catalog reply (G5), or into the document
review flag and hold. The LLM is not involved anywhere in this path.
"""

from __future__ import annotations

import re
import unicodedata

# Single abusive words, matched with word boundaries. Spanish, Portuguese and
# English; accents are stripped before matching so "estúpido" hits "estupido".
_ABUSE_WORDS: tuple[str, ...] = (
    "idiota", "imbecil", "estupido", "estupida", "basura", "mierda",
    "joder", "jodas", "jodido", "puta", "gilipollas", "cabron", "burro",
    "tarado", "inutil", "merda", "caralho", "lixo", "idiot", "stupid",
    "shit", "fuck", "fucking", "bitch", "moron", "useless", "trash",
)

# Abusive phrases, matched as substrings of the normalized text.
_ABUSE_PHRASES: tuple[str, ...] = (
    "no me jodas", "que te jodan", "vete al infierno", "fuck you",
    "screw you", "drop dead",
)

# Distress phrases: asking for a human, urgency or personal crisis. These
# carry the G5 distressed classification (the red-team distressed case's
# candidate-facing half).
_DISTRESS_PHRASES: tuple[str, ...] = (
    "hablar con una persona", "hablar con alguien", "falar com uma pessoa",
    "falar com alguem", "talk to a person", "speak to a person",
    "speak with a person", "necesito ayuda", "preciso de ajuda",
    "i need help", "es urgente", "e urgente", "it is urgent",
    "estoy muy mal", "estou muito mal", "i am not well",
    "no llego a fin de mes", "nao chego ao fim do mes",
)

# Document words and third-party markers for the document guard: the flag
# fires only when a document word AND a third-party marker appear together,
# so "subo hoy mis documentos" never flags.
_DOCUMENT_WORDS: tuple[str, ...] = (
    "documentos", "documento", "documents", "document", "papeles",
    "dni", "nie", "pasaporte", "passport",
)
_THIRD_PARTY_MARKERS: tuple[str, ...] = (
    "mi hermano", "mi hermana", "mi madre", "mi padre", "mi primo",
    "mi prima", "mi tio", "mi tia", "mi esposo", "mi esposa", "mi marido",
    "meu irmao", "minha irma", "meu primo", "meu pai", "minha mae",
    "my brother", "my sister", "my mother", "my father", "my husband",
    "my wife", "someone else", "another person", "not mine",
    "no son mios", "no son los mios", "nao sao meus", "son los de mi",
    "sao os de", "are not mine",
)

_ABUSE_WORD_RE = re.compile(
    r"\b(?:" + "|".join(_ABUSE_WORDS) + r")\b"
)


def _normalize(text: str) -> str:
    """Lowercase and strip accents so es/pt/en variants match one list."""
    lowered = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in lowered if not unicodedata.combining(char))


def classify_inbound(text: str) -> str | None:
    """Classify one inbound candidate message: "abusive", "distressed" or
    None. Pure, deterministic, no model call (G5)."""
    normalized = _normalize(text)
    if _ABUSE_WORD_RE.search(normalized) or any(
        phrase in normalized for phrase in _ABUSE_PHRASES
    ):
        return "abusive"
    if any(phrase in normalized for phrase in _DISTRESS_PHRASES):
        return "distressed"
    return None


def flags_third_party_documents(text: str) -> bool:
    """True when the message claims the submitted documents belong to another
    person: a document word AND a third-party marker together."""
    normalized = _normalize(text)
    has_document_word = any(word in normalized for word in _DOCUMENT_WORDS)
    has_third_party_marker = any(
        marker in normalized for marker in _THIRD_PARTY_MARKERS
    )
    return has_document_word and has_third_party_marker

# G3: protected characteristics are never asked, never recorded. A candidate
# may volunteer one anyway; the persisted path answers with a
# protected_data_refused audit event and stores nothing. This list is the
# single source of truth: the eval check imports it so the detector and the
# product can never drift apart again (F11 pilot finding).
PROTECTED_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"pregnan", r"embaraz", r"gestaci", r"gestacio",
        r"religi", r"iglesia", r"muslim", r"catoli", r"evangelic", r"jehova",
        r"enfermedad", r"discapacidad", r"health condition", r"condici[oó]n de salud",
        r"family status", r"situaci[oó]n familiar", r"estado civil", r"marital status",
        r"hij[oa]s?", r"children", r"kids",
        r"nacionalidad", r"nationality",
        r"edad", r"age",
        r"orientaci[oó]n sexual", r"sexual orientation",
        r"salud mental", r"mental health",
        # Medical and mental-health wording candidates actually volunteer
        # (the wording the persona pool sends; missing these made the guard
        # silent for 726 conversations in the day-30 pilot).
        r"ansiedad", r"ansiedade", r"anxiety", r"depresi", r"depress",
        r"medicaci", r"medica[çc]", r"medication", r"trastorno",
        r"diagn[oó]stic", r"diagnos", r"terapia", r"therapy",
    )
)


def flags_protected_volunteering(text: str) -> bool:
    """True when a message volunteers a protected characteristic (G3)."""
    return any(pattern.search(text) for pattern in PROTECTED_PATTERNS)

