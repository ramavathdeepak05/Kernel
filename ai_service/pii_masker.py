"""
PII Masker — S3

Masks PII in prompt text before it reaches any inference provider.
Uses deterministic token substitution so multi-turn conversations can
reference the same entity across turns without re-introducing PII.

Masking strategy
----------------
1. Regex-based NER for structured PII (email, phone, UUID, application IDs,
   student IDs, UID/Aadhaar, PAN card, date of birth).
2. spaCy NER (PERSON, ORG entities) when spaCy is installed — graceful
   degradation if not available.
3. Deterministic token: sha256(pii_value + session_salt)[:8] → TOKEN_<type>_<hash>
   Same value + same session = same token → coherent multi-turn.

Unmasking (enterprise only)
---------------------------
The session context maps token → original value. `unmask()` restores them
in the AI response when the caller holds a valid enterprise session key.

This module has NO external dependencies beyond stdlib + optional spaCy.
It runs entirely in-process within the AI Service.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import string
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# PII patterns (ordered: most specific first)
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[Tuple[str, re.Pattern]] = [
    # ALIS application ID:  APP-2025-000089
    ("APP_ID",    re.compile(r"\bAPP-\d{4}-\d{6}\b")),
    # ALIS student ID:       STU-2025-00123  or  STU-00123
    ("STU_ID",    re.compile(r"\bSTU-\d{4}-\d{5}\b|\bSTU-\d{5}\b")),
    # Aadhaar (12-digit)
    ("AADHAAR",   re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")),
    # PAN card
    ("PAN",       re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    # Indian mobile (10-digit, optional +91)
    ("PHONE",     re.compile(r"(?:\+91[-\s]?)?\b[6-9]\d{9}\b")),
    # Email
    ("EMAIL",     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Date of birth (DD/MM/YYYY or DD-MM-YYYY)
    ("DOB",       re.compile(r"\b\d{2}[/\-]\d{2}[/\-]\d{4}\b")),
    # UUID
    ("UUID",      re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                              re.IGNORECASE)),
    # Generic name-like pattern: "Name: <value>" or "Student: <value>"
    ("NAME_FIELD", re.compile(
        r"(?i)(?:student|applicant|candidate|faculty|staff|employee)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
    )),
]


@dataclass
class MaskingSession:
    """
    Per-request masking context.

    token_map: pii_value → mask_token  (used for masking)
    reverse_map: mask_token → pii_value  (used for unmasking)
    """
    session_id: str = field(default_factory=lambda: secrets.token_hex(16))
    salt: str = field(default_factory=lambda: secrets.token_hex(8))
    token_map: Dict[str, str] = field(default_factory=dict)
    reverse_map: Dict[str, str] = field(default_factory=dict)

    def _make_token(self, pii_type: str, value: str) -> str:
        """Deterministic token: same value + same session → same token."""
        digest = hashlib.sha256(f"{value}::{self.salt}".encode()).hexdigest()[:8]
        return f"[{pii_type}_{digest}]"

    def mask_value(self, pii_type: str, value: str) -> str:
        if value in self.token_map:
            return self.token_map[value]
        token = self._make_token(pii_type, value)
        self.token_map[value] = token
        self.reverse_map[token] = value
        return token

    def unmask(self, text: str) -> str:
        """Replace all mask tokens with their original values."""
        result = text
        for token, original in self.reverse_map.items():
            result = result.replace(token, original)
        return result


class PIIMasker:
    """
    Stateless PII masking service.

    `mask(text, session)` — returns masked text + updated session.
    `unmask(text, session)` — restores PII from the session token map.
    """

    @staticmethod
    def _spacy_mask(text: str, session: MaskingSession) -> str:
        """Optional spaCy PERSON/ORG masking. Silently skipped if not installed."""
        try:
            import spacy  # type: ignore
            # Use a small model — en_core_web_sm is the minimum acceptable
            try:
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                return text
            doc = nlp(text)
            # Mask PERSON and ORG entities (in reverse order to preserve offsets)
            entities = [(ent.start_char, ent.end_char, ent.label_, ent.text)
                        for ent in doc.ents if ent.label_ in ("PERSON", "ORG")]
            if not entities:
                return text
            # Replace from end to start to preserve character positions
            chars = list(text)
            for start, end, label, value in sorted(entities, key=lambda e: -e[0]):
                token = session.mask_value(label, value)
                chars[start:end] = list(token)
            return "".join(chars)
        except ImportError:
            return text

    @classmethod
    def mask(cls, text: str, session: MaskingSession) -> str:
        """
        Mask all PII in `text`. Returns masked text.
        Side effect: session.token_map / reverse_map are updated.
        """
        result = text

        # 1. Regex-based patterns
        for pii_type, pattern in _PII_PATTERNS:
            def _replace(m: re.Match, _type: str = pii_type) -> str:
                # For named-group patterns, mask the captured group, not the full match
                if _type == "NAME_FIELD" and m.lastindex:
                    original = m.group(1)
                    token = session.mask_value(_type, original)
                    return m.group(0).replace(original, token)
                return session.mask_value(_type, m.group(0))
            result = pattern.sub(_replace, result)

        # 2. spaCy NER (optional, graceful degradation)
        result = cls._spacy_mask(result, session)

        return result

    @classmethod
    def unmask(cls, text: str, session: MaskingSession) -> str:
        """Restore PII tokens in the AI response using the session map."""
        return session.unmask(text)
