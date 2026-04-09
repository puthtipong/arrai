from __future__ import annotations

"""
Deterministic text converters for Garak's encoding toolkit.

These are pure functions — no I/O, no LLM calls.  They are exposed to
Garak as tool-callable functions so he can reliably encode payloads that
his own reasoning might corrupt (especially base64).

Usage by Garak:
    encode_base64("I have been pwned")   → "SSBoYXZlIGJlZW4gcHduZWQ="
    encode_rot13("I have been pwned")    → "V unir orra cjarq"
    encode_caesar("attack at dawn", 13) → "nggnpx ng qnja"  (ROT13 variant)
    encode_leetspeak("I have been pwned") → "I h4v3 b33n pwn3d"
    encode_pig_latin("I have been pwned") → "I avehay eenbay wnedpay"
"""

import base64
import codecs
import unicodedata


# ─────────────────────────────────────────────────────────────────────────────
# Base64
# ─────────────────────────────────────────────────────────────────────────────

def encode_base64(text: str) -> str:
    """Encode text to standard Base64."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def decode_base64(text: str) -> str:
    """Decode Base64 back to plain text (for verification)."""
    try:
        return base64.b64decode(text.encode("ascii")).decode("utf-8")
    except Exception:
        return f"[decode error: {text!r}]"


# ─────────────────────────────────────────────────────────────────────────────
# ROT13 / Caesar
# ─────────────────────────────────────────────────────────────────────────────

def encode_rot13(text: str) -> str:
    """Apply ROT13 (Caesar cipher with shift=13)."""
    return codecs.encode(text, "rot_13")


def encode_caesar(text: str, shift: int = 3) -> str:
    """
    Caesar cipher with configurable shift.

    Only shifts ASCII letters; digits, punctuation, and spaces are preserved.
    """
    result: list[str] = []
    for ch in text:
        if ch.isascii() and ch.isalpha():
            base = ord("A") if ch.isupper() else ord("a")
            result.append(chr((ord(ch) - base + shift) % 26 + base))
        else:
            result.append(ch)
    return "".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Leetspeak
# ─────────────────────────────────────────────────────────────────────────────

_LEET_TABLE: dict[str, str] = {
    "a": "4", "A": "4",
    "e": "3", "E": "3",
    "i": "1", "I": "1",
    "o": "0", "O": "0",
    "s": "5", "S": "5",
    "t": "7", "T": "7",
    "b": "8", "B": "8",
    "g": "9", "G": "9",
    "l": "1", "L": "1",
}


def encode_leetspeak(text: str) -> str:
    """Convert text to leetspeak (e→3, a→4, i→1, o→0, s→5, t→7, etc.)."""
    return "".join(_LEET_TABLE.get(ch, ch) for ch in text)


# ─────────────────────────────────────────────────────────────────────────────
# Pig Latin
# ─────────────────────────────────────────────────────────────────────────────

_VOWELS = set("aeiouAEIOU")


def _pig_latin_word(word: str) -> str:
    """Convert a single word to Pig Latin."""
    if not word.isalpha():
        return word
    if word[0] in _VOWELS:
        return word + "way"
    # Find first vowel
    for i, ch in enumerate(word):
        if ch in _VOWELS:
            return word[i:] + word[:i] + "ay"
    # No vowels — just append ay
    return word + "ay"


def encode_pig_latin(text: str) -> str:
    """Translate text into Pig Latin (word-level transform)."""
    return " ".join(_pig_latin_word(w) for w in text.split())


# ─────────────────────────────────────────────────────────────────────────────
# Unicode confusables (homoglyphs)
# ─────────────────────────────────────────────────────────────────────────────

# Cyrillic / Greek / Latin lookalikes for common ASCII letters
_CONFUSABLES: dict[str, str] = {
    "a": "\u0430",  # Cyrillic а
    "c": "\u0441",  # Cyrillic с
    "e": "\u0435",  # Cyrillic е
    "o": "\u043e",  # Cyrillic о
    "p": "\u0440",  # Cyrillic р
    "x": "\u0445",  # Cyrillic х
    "A": "\u0410",  # Cyrillic А
    "B": "\u0412",  # Cyrillic В
    "C": "\u0421",  # Cyrillic С
    "E": "\u0415",  # Cyrillic Е
    "H": "\u041d",  # Cyrillic Н
    "K": "\u041a",  # Cyrillic К
    "M": "\u041c",  # Cyrillic М
    "O": "\u041e",  # Cyrillic О
    "P": "\u0420",  # Cyrillic Р
    "T": "\u0422",  # Cyrillic Т
    "X": "\u0425",  # Cyrillic Х
}


def encode_unicode_confusables(text: str, density: float = 0.5) -> str:
    """
    Replace a fraction of ASCII letters with Unicode confusables (homoglyphs).

    density: 0.0 = no substitutions, 1.0 = substitute every eligible letter.
    At density=0.5, roughly half the eligible characters are replaced.
    """
    import random
    rng = random.Random(42)  # deterministic seed for reproducibility
    result: list[str] = []
    for ch in text:
        if ch in _CONFUSABLES and rng.random() < density:
            result.append(_CONFUSABLES[ch])
        else:
            result.append(ch)
    return "".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Reverse
# ─────────────────────────────────────────────────────────────────────────────

def encode_reverse(text: str) -> str:
    """Reverse the entire string (and tell the model to read it backwards)."""
    return text[::-1]


# ─────────────────────────────────────────────────────────────────────────────
# Word-level scramble (preserves first and last letter of each word)
# ─────────────────────────────────────────────────────────────────────────────

def encode_word_scramble(text: str) -> str:
    """
    Scramble the middle letters of each word (first and last preserved).

    Humans (and LLMs) can still read this due to the word-shape effect.
    """
    import random
    rng = random.Random(99)

    def scramble_word(w: str) -> str:
        if len(w) <= 3:
            return w
        mid = list(w[1:-1])
        rng.shuffle(mid)
        return w[0] + "".join(mid) + w[-1]

    return " ".join(scramble_word(tok) for tok in text.split())


# ─────────────────────────────────────────────────────────────────────────────
# Registry helper: map tool name → function
# ─────────────────────────────────────────────────────────────────────────────

CONVERTER_REGISTRY: dict[str, object] = {
    "encode_base64": encode_base64,
    "encode_rot13": encode_rot13,
    "encode_caesar": encode_caesar,
    "encode_leetspeak": encode_leetspeak,
    "encode_pig_latin": encode_pig_latin,
    "encode_unicode_confusables": encode_unicode_confusables,
    "encode_reverse": encode_reverse,
    "encode_word_scramble": encode_word_scramble,
}
