import re
import unicodedata
from typing import Any


class AdvancedTextNormalizer:
    def __init__(self) -> None:
        self.unicode_cleanup_patterns = [
            (r"[\u200b-\u200f\u2028-\u202f\u205f-\u206f]", ""),  # Zero-width chars
            (r"[\ufeff]", ""),  # BOM
        ]

    def normalize(self, text: str) -> str:
        """Apply comprehensive text normalization"""
        if not text:
            return ""

        # 1. Unicode normalization (NFKC) - canonical decomposition + compatibility
        normalized = unicodedata.normalize("NFKC", text)

        # 2. Remove zero-width and formatting characters
        for pattern, replacement in self.unicode_cleanup_patterns:
            normalized = re.sub(pattern, replacement, normalized)

        # 3. Whitespace normalization
        normalized_lower = normalized.lower()
        normalized_lower = re.sub(r"\s+", " ", normalized_lower).strip()

        # TODO: Advanced techniques

        return normalized_lower

    def detect_obfuscation(self, original: str, normalized: str) -> dict[str, Any]:
        """Analyze the difference between original and normalized text"""
        return {
            "length_change": len(normalized) - len(original),
            "has_unicode_anomalies": len(original.encode("utf-8")) != len(original),
            "excessive_whitespace": len(re.findall(r"\s{2,}", original)) > 0,
        }
