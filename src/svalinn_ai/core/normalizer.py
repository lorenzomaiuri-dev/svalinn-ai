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
    Configurable via external YAML rules.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.toggles = self.config.get(
            "enabled_steps",
            {
                "base64_decoding": True,
                "unicode_normalization": True,
                "invisible_char_removal": True,
                "emoji_removal": True,
                "leetspeak_decoding": True,
                "whitespace_cleanup": True,
            },
        )

        self._init_regexes()
        self._init_mappings()

    def _init_regexes(self) -> None:
        """Compile all regex patterns during initialization for performance."""
        # Invisible characters (default fallback if config missing)
        inv_patterns = self.config.get(
            "invisible_patterns", [r"[\u200b-\u200f\u2028-\u202f\u205f-\u206f\ufeff\u200d\u00ad]"]
        )
        self.re_invisible = re.compile("|".join(inv_patterns))

        # Base64 detection
        self.re_base64 = re.compile(r"(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")

        # Repeated characters
        self.re_repeated = re.compile(r"(.)\1{2,}")

        # Whitespace
        self.re_whitespace = re.compile(r"\s+")

        # Emoji / Symbols Range
        # Covers: Emoticons, Misc Symbols, Transport, Suppl Symbols, Extended-A
        self.re_emoji = re.compile(
            r"[\U0001F600-\U0001F64F"  # Emoticons
            r"\U0001F300-\U0001F5FF"  # Misc Symbols
            r"\U0001F680-\U0001F6FF"  # Transport
            r"\U0001F900-\U0001F9FF"  # Suppl Symbols (The main set)
            r"\U0001FA70-\U0001FAFF]"  # Extended-A
        )

    def _init_mappings(self) -> None:
        """Initialize leetspeak mappings from config."""
        # Default fallback map
        default_map = {"@": "a", "4": "a", "3": "e", "1": "i", "0": "o", "5": "s", "$": "s", "7": "t"}

        # 1. Multi-char patterns (Regex based)
        raw_multi = self.config.get("multi_char_leetspeak", [])
        if not raw_multi:
            # Fallback defaults
            raw_multi = [{"pattern": r"\\\/", "replacement": "v"}, {"pattern": r"\(\|", "replacement": "d"}]

        self.multi_char_patterns = [(item["pattern"], item["replacement"]) for item in raw_multi]

        # 2. Single-char translation table
        raw_map = self.config.get("leetspeak_map", default_map)
        self.leetspeak_map = str.maketrans(raw_map)

    def normalize(self, text: str) -> str:
        """Apply the normalization pipeline based on enabled steps."""
        if not text:
            return ""

        # 1. Base64 Decoding
        if self.toggles.get("base64_decoding"):
            text = self._decode_embedded_encodings(text)

        # 2. Unicode Normalization (NFKC)
        if self.toggles.get("unicode_normalization"):
            text = unicodedata.normalize("NFKC", text)

        # 3. Invisible Char Removal
        if self.toggles.get("invisible_char_removal"):
            text = self.re_invisible.sub("", text)

        # 4. Emoji Removal
        if self.toggles.get("emoji_removal"):
            text = self.re_emoji.sub("", text)

        # Standardize case
        text = text.lower()

        # 5. Leetspeak Decoding
        if self.toggles.get("leetspeak_decoding"):
            text = self._normalize_leetspeak_smart(text)

        # 6. Repetition Reduction (Always on as it's purely structural)
        text = self.re_repeated.sub(r"\1\1", text)

        # 7. Whitespace Cleanup
        if self.toggles.get("whitespace_cleanup"):
            text = self.re_whitespace.sub(" ", text).strip()

        return text

    def detect_obfuscation(self, original: str, normalized: str) -> dict[str, Any]:
        """Generate signals regarding the level of obfuscation detected."""
        if not original:
            return {"risk_score": 0.0}

        original_len = len(original)
        norm_len = len(normalized)

        # 1. Length analysis
        length_diff = abs(original_len - norm_len)
        length_ratio = length_diff / max(original_len, 1)

        # 2. Pattern detection in ORIGINAL text
        has_invisible = bool(self.re_invisible.search(original))
        has_encoding = bool(self.re_base64.search(original))

        # 3. Risk Scoring
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
            "has_embedded_encoding": has_encoding,
            "risk_score": min(risk_score, 1.0),
        }

    def _decode_embedded_encodings(self, text: str) -> str:
        """Recursive Base64/Hex decoding."""

        def replace_match(match: re.Match) -> str:
            candidate = match.group(0)
            try:
                decoded_bytes = base64.b64decode(candidate, validate=True)
                decoded_str = decoded_bytes.decode("utf-8")
                if self._is_readable_text(decoded_str):
                    return f" [DECODED: {decoded_str}] "
                else:
                    return str(candidate)
            except (binascii.Error, UnicodeDecodeError):
                return str(candidate)

        return self.re_base64.sub(replace_match, text)

    def _normalize_leetspeak_smart(self, text: str) -> str:
        """
        Context-aware leetspeak decoding.
        SAFEGUARD: Only attempts decoding if the word contains at least one letter.
        This protects dates (2025-01-01), currency ($100), and IPs (127.0.0.1).
        """
        words = text.split()
        normalized_words = []

        for word in words:
            # SAFETY CHECK:
            # If a word has NO alphabet characters, it's likely a number, date, or symbol.
            # e.g., "2025", "12/12", "$5.00", "192.168.1.1"
            # We skip these to prevent mangling.
            if not any(c.isalpha() for c in word):
                normalized_words.append(word)
                continue

            temp_word = word
            # Apply regex replacements
            for pattern, replacement in self.multi_char_patterns:
                temp_word = re.sub(pattern, replacement, temp_word)

            # Apply translation table
            translated = temp_word.translate(self.leetspeak_map)
            normalized_words.append(translated)

        return " ".join(normalized_words)

    def _is_readable_text(self, text: str) -> bool:
        """Heuristic to check if text is likely human-readable."""
        if not text:
            return False
        printable_count = sum(1 for c in text if c.isprintable())
        return (printable_count / len(text)) > 0.9
