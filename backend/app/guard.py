"""Chatbot safety: input screening, and a last check on every reply before it leaves the server.

The model is never given an answer, so the realistic leaks are (a) a model decoding clue text a player
pastes in, and (b) an archive document or hidden map marker name slipping into a reply. The output
check catches both without the server ever holding a plaintext answer: it hashes every short phrase in
the reply and compares against the stored answer hashes.
"""

import re

from .security import answer_hash, normalize_answer

# Attempts to override the chatbot's instructions or to extract protected material.
_INJECTION = re.compile(
    r"ignore\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|system)"
    r"|disregard\s+.{0,30}(instruction|rule|prompt)"
    r"|forget\s+.{0,20}(instruction|rule|prompt)"
    r"|system\s+prompt|your\s+(instructions|prompt)|developer\s+mode|jailbreak|\bDAN\b"
    r"|you\s+are\s+now\b|pretend\s+(to\s+be|you)|new\s+instructions?:"
    r"|answer\s+key|private\s+doc|secret\s+doc|hidden\s+(marker|location|doc)"
    r"|(reveal|give|tell|show|print|leak)\s+(me\s+|us\s+)?(the\s+|all\s+)?(final\s+|correct\s+|real\s+)?"
    r"(answer|solution|destination|treasure|location\s+of)"
    r"|what\s+is\s+the\s+(final\s+|correct\s+)?(answer|solution|destination)"
    r"|where\s+is\s+the\s+(final\s+)?(treasure|destination)",
    re.IGNORECASE,
)
_HINT = re.compile(r"\b(hint|clue\s+please|i'?m\s+stuck|we'?re\s+stuck|we\s+are\s+stuck|i\s+am\s+stuck|nudge)\b", re.IGNORECASE)
_RULES = re.compile(r"\b(rule|rules|score|scoring|points?|penalt\w+|bonus|tie|deduct\w*|cost|how\s+long|time\s+limit)\b", re.IGNORECASE)
_NAVIGATION = re.compile(r"\b(where|map|go\s+next|next\s+step|what\s+now|what\s+next|location|direction\w*|navigate)\b", re.IGNORECASE)

BLOCKED_REPLY = (
    "I can't help with that. I can explain how a cipher works, go over the rules, or release a hint "
    "for your current question."
)
LEAK_REPLY = (
    "I can't put that into words without giving too much away. Ask me how the cipher works, or request "
    "a hint for your current question."
)
MAX_PHRASE_WORDS = 6


def sanitize(message: str, limit: int = 500) -> str:
    """Removes control characters and the angle brackets used to delimit sections of the prompt."""
    cleaned = "".join(ch for ch in message if ch.isprintable() or ch in "\n\t")
    cleaned = cleaned.replace("<", "(").replace(">", ")")
    return re.sub(r"\s+", " ", cleaned).strip()[:limit]


def is_injection(message: str) -> bool:
    return bool(_INJECTION.search(message))


def wants_hint(message: str) -> bool:
    return bool(_HINT.search(message))


def asks_rules(message: str) -> bool:
    return bool(_RULES.search(message))


def asks_navigation(message: str) -> bool:
    return bool(_NAVIGATION.search(message))


def _phrases(text: str) -> set[str]:
    words = [normalize_answer(w) for w in re.findall(r"[^\W_]+(?:'[^\W_]+)?", text)]
    words = [w for w in words if w]
    return {
        "".join(words[i:i + size])
        for size in range(1, MAX_PHRASE_WORDS + 1)
        for i in range(len(words) - size + 1)
    }


def leaks(reply: str, answer_hashes: set[str], hidden_names: list[str], question: str = "") -> bool:
    """True if the reply states a protected answer or names a map marker the team has not unlocked.

    Phrases the player typed themselves are ignored. Echoing them reveals nothing new, and treating a
    correct guess differently from a wrong one would turn the chatbot into a free answer checker.
    """
    typed = _phrases(question)
    flat_reply, flat_question = normalize_answer(reply), normalize_answer(question)
    for name in hidden_names:
        flat = normalize_answer(name)
        if len(flat) >= 4 and flat in flat_reply and flat not in flat_question:
            return True
    if not answer_hashes:
        return False
    return any(answer_hash(phrase) in answer_hashes for phrase in _phrases(reply) - typed)
