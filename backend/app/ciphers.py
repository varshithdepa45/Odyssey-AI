"""Encoders for the nine hunt ciphers. Organisers use these to turn an answer into a clue."""

import re

CIPHERS = ["binary", "morse", "caesar", "polybius", "vigenere", "hex", "braille", "ascii", "book"]

MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....",
    "I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.",
    "Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..", "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
}
POLYBIUS_GRID = "ABCDEFGHIKLMNOPQRSTUVWXYZ"  # I and J share a cell
# Dot numbers for a-z in grade 1 braille.
BRAILLE_DOTS = [
    "1", "12", "14", "145", "15", "124", "1245", "125", "24", "245", "13", "123", "134",
    "1345", "135", "1234", "12345", "1235", "234", "2345", "136", "1236", "2456", "1346", "13456", "1356",
]
BRAILLE = {
    chr(65 + i): chr(0x2800 + sum(1 << (int(d) - 1) for d in dots)) for i, dots in enumerate(BRAILLE_DOTS)
}


def _shift(ch: str, by: int) -> str:
    return chr((ord(ch) - 65 + by) % 26 + 65) if ch.isalpha() else ch


def binary(text: str) -> str:
    return " ".join(f"{ord(c):08b}" for c in text)


def morse(text: str) -> str:
    return " / ".join(" ".join(MORSE[c] for c in word if c in MORSE) for word in text.split())


def caesar(text: str, shift: int = 3) -> str:
    return "".join(_shift(c, shift) for c in text)


def polybius(text: str) -> str:
    words = []
    for word in text.replace("J", "I").split():
        cells = [divmod(POLYBIUS_GRID.index(c), 5) for c in word if c in POLYBIUS_GRID]
        words.append(" ".join(f"{row + 1}{col + 1}" for row, col in cells))
    return " / ".join(words)


def vigenere(text: str, key: str) -> str:
    key = re.sub(r"[^A-Z]", "", key.upper())
    if not key:
        raise ValueError("Vigenère needs a key made of letters")
    out, i = [], 0
    for c in text:
        if c.isalpha():
            out.append(_shift(c, ord(key[i % len(key)]) - 65))
            i += 1
        else:
            out.append(c)
    return "".join(out)


def hexadecimal(text: str) -> str:
    return " ".join(f"{ord(c):02X}" for c in text)


def braille(text: str) -> str:
    return "".join(BRAILLE.get(c, "⠀" if c == " " else c) for c in text)


def ascii_decimal(text: str) -> str:
    return " ".join(str(ord(c)) for c in text)


def book(text: str, passage: str) -> str:
    """Each letter becomes line.word.letter (all counted from 1) within the passage."""
    positions: dict[str, list[str]] = {}
    for li, line in enumerate(passage.strip().splitlines(), 1):
        for wi, word in enumerate(re.findall(r"[A-Za-z]+", line), 1):
            for ci, ch in enumerate(word.upper(), 1):
                positions.setdefault(ch, []).append(f"{li}.{wi}.{ci}")
    used: dict[str, int] = {}
    words = []
    for word in text.split():
        refs = []
        for ch in word:
            if not ch.isalpha():
                continue
            if ch not in positions:
                raise ValueError(f"The passage has no letter {ch!r}")
            # Rotate through occurrences so a repeated letter gets different references.
            n = used.get(ch, 0)
            refs.append(positions[ch][n % len(positions[ch])])
            used[ch] = n + 1
        words.append(" ".join(refs))
    return " / ".join(words)


def encode(cipher: str, text: str, key: str = "") -> str:
    text = text.upper().strip()
    if cipher == "binary":
        return binary(text)
    if cipher == "morse":
        return morse(text)
    if cipher == "caesar":
        try:
            return caesar(text, int(key or 3))
        except ValueError:
            raise ValueError("Caesar needs a whole-number shift as the key")
    if cipher == "polybius":
        return polybius(text)
    if cipher == "vigenere":
        return vigenere(text, key)
    if cipher == "hex":
        return hexadecimal(text)
    if cipher == "braille":
        return braille(text)
    if cipher == "ascii":
        return ascii_decimal(text)
    if cipher == "book":
        if not key.strip():
            raise ValueError("Book cipher needs the passage as the key")
        return book(text, key)
    raise ValueError(f"Unknown cipher {cipher!r}")
