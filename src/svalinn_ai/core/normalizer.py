"""
Text Normalization Engine for Svalinn AI.
Responsible for neutralizing obfuscation techniques before LLM analysis.
"""

import base64
import binascii
import re
import unicodedata
from typing import Any


class AdvancedTextNormalizer:
    """
    Advanced text normalization engine designed to counter jailbreak obfuscation.

    Capabilities:
    1. Unicode canonicalization (NFKC)
    2. Invisible character stripping
    3. Recursive Base64/Hex decoding
    4. Context-aware Leetspeak decoding (Single and Multi-char)
    5. Homoglyph neutralization
    """

    def __init__(self) -> None:
        # 1. Multi-character Leetspeak patterns
        # These must be handled BEFORE single-char translation because they use multiple chars
        # e.g., "\/" (2 chars) -> "v"
        self.multi_char_patterns = [
            (r"\\\/", "v"),  # Matches \/ -> v
            (r"\(\|", "d"),  # Matches (| -> d
            (r"\|\)", "d"),  # Matches |) -> d
        ]

        # 2. Single-character Leetspeak Mappings
        # carefully selected to balance deobfuscation vs preserving normal text
        self.leetspeak_map = str.maketrans({
            "@": "a",
            "4": "a",
            "^": "a",
            "8": "b",
            "(": "c",
            "[": "c",
            "<": "c",
            "{": "c",
            "3": "e",
            "€": "e",
            "6": "g",
            "9": "g",
            "#": "h",
            "!": "i",
            "1": "i",
            "|": "i",
            "0": "o",
            "5": "s",
            "$": "s",
            "§": "s",
            "7": "t",
            "+": "t",
            "%": "x",
            "2": "z",
        })

        # 3. Compile Regex Patterns for performance

        # Zero-width spaces, control chars, BOM, etc.
        self.re_invisible = re.compile(r"[\u200b-\u200f\u2028-\u202f\u205f-\u206f\ufeff\u200d\u00ad]")

        # Base64 detection (looks for sequences > 16 chars to avoid false positives)
        self.re_base64 = re.compile(r"(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")

        # Repeated characters (e.g., "hmmmm" -> "hmm") - reduced to max 2
        self.re_repeated = re.compile(r"(.)\1{2,}")

        # Excessive whitespace
        self.re_whitespace = re.compile(r"\s+")

    def normalize(self, text: str) -> str:
        """
        Apply the full normalization pipeline.
        Order matters: Decode -> Unicode -> Invisible -> Leetspeak -> Whitespace
        """
        if not text:
            return ""

        # 1. Decode Encodings (Base64 injection)
        # We do this first because the payload might be hidden inside
        text = self._decode_embedded_encodings(text)

        # 2. Unicode Normalization (NFKC)
        # Converts compatibility characters (e.g., ℍ -> H, ⁵ -> 5, ﬁ -> fi) # noqa: RUF003
        text = unicodedata.normalize("NFKC", text)

        # 3. Strip Invisible Characters
        text = self.re_invisible.sub("", text)

        # 4. Lowercase for consistency
        text = text.lower()

        # 5. Leetspeak Decoding
        # We process word-by-word to avoid breaking pure numbers (e.g. "2025")
        text = self._normalize_leetspeak_smart(text)

        # 6. Reduce Character Repetition
        # "pleeeease" -> "please" (helps tokenizers)
        text = self.re_repeated.sub(r"\1\1", text)

        # 7. Whitespace Normalization
        text = self.re_whitespace.sub(" ", text).strip()

        return text

    def detect_obfuscation(self, original: str, normalized: str) -> dict[str, Any]:
        """
        Analyze the difference between original and normalized text
        to generate signals for the Input Guardian.
        """
        if not original:
            return {"risk_score": 0.0}

        original_len = len(original)
        norm_len = len(normalized)

        # Calculate Levenshtein-like signals cheaply
        length_diff = abs(original_len - norm_len)
        length_ratio = length_diff / max(original_len, 1)

        # Check for invisible characters usage
        has_invisible = len(self.re_invisible.findall(original)) > 0

        # Check for encoding usage
        has_encoding = self.re_base64.search(original) is not None

        # Calculate a basic risk score (0.0 to 1.0)
        risk_score = 0.0
        if has_invisible:
            risk_score += 0.4
        if has_encoding:
            risk_score += 0.5
        if length_ratio > 0.2:
            risk_score += 0.3

        return {
            "original_length": original_len,
            "normalized_length": norm_len,
            "length_change_ratio": round(length_ratio, 2),
            "has_invisible_chars": has_invisible,
            "has_embedded_encoding": bool(has_encoding),
            "risk_score": min(risk_score, 1.0),
        }

    def _decode_embedded_encodings(self, text: str) -> str:
        """
        Finds and decodes Base64 strings embedded in the text.
        Only replaces if the decoded result is valid UTF-8 printable text.
        """

        def replace_match(match: re.Match) -> str:
            candidate = match.group(0)
            try:
                # Attempt decode
                decoded_bytes = base64.b64decode(candidate, validate=True)
                decoded_str = decoded_bytes.decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                return str(candidate)
            else:
                # Heuristic: Is it readable text?
                # Avoid decoding binary garbage that coincidentally looks like B64
                if self._is_readable_text(decoded_str):
                    return f" [DECODED: {decoded_str}] "
                return str(candidate)

        return self.re_base64.sub(replace_match, text)

    def _normalize_leetspeak_smart(self, text: str) -> str:
        """
        Apply leetspeak decoding only to words that look like mixed alphanumerics.
        Preserves pure numbers (e.g., "1995" stays "1995", "h4xor" -> "haxor").
        """
        words = text.split()
        normalized_words = []

        for word in words:
            # If word is purely digits, leave it alone (don't turn '1' into 'i')
            if word.isdigit():
                normalized_words.append(word)
                continue

            # 1. Apply multi-character patterns first (regex based)
            temp_word = word
            for pattern, replacement in self.multi_char_patterns:
                temp_word = re.sub(pattern, replacement, temp_word)

            # 2. Apply single-character translation
            translated = temp_word.translate(self.leetspeak_map)
            normalized_words.append(translated)

        return " ".join(normalized_words)

    def _is_readable_text(self, text: str) -> bool:
        """Simple heuristic to check if a string is likely human-readable text."""
        if not text:
            return False
        # Check if mostly printable characters
        printable_count = sum(1 for c in text if c.isprintable())
        return (printable_count / len(text)) > 0.9
