"""
P14 — NTA Score Import Integration

Imports entrance exam scores from the National Testing Agency (NTA) for:
  - JEE Main / Advanced
  - NEET UG / PG
  - CUET UG / PG
  - CMAT, MAT, GPAT, etc.

The import flow:
  1. Applicant provides their NTA Application Number + Date of Birth
  2. ALIS calls the NTA API to verify and pull the score card
  3. Score is stored in the entrance_test_scores table (via EntranceTestService)
  4. Eligibility evaluation uses the imported NTA score directly

When not configured (settings.nta_enabled == False), the client returns
None so the workflow falls back to manual score entry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Supported NTA exam types and their API slugs
NTA_EXAM_SLUGS = {
    "JEE_MAIN": "jee-main",
    "JEE_ADVANCED": "jee-advanced",
    "NEET_UG": "neet-ug",
    "NEET_PG": "neet-pg",
    "CUET_UG": "cuet-ug",
    "CUET_PG": "cuet-pg",
    "CMAT": "cmat",
    "MAT": "mat",
    "GPAT": "gpat",
}


@dataclass
class NTAScoreCard:
    application_number: str
    candidate_name: str
    dob: str                    # YYYY-MM-DD
    exam_type: str              # JEE_MAIN, NEET_UG, etc.
    roll_number: str
    total_marks: float
    percentile: Optional[float]
    rank: Optional[int]
    category_rank: Optional[int]
    subject_scores: Dict[str, float] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NTAImportResult:
    success: bool
    score_card: Optional[NTAScoreCard] = None
    error: Optional[str] = None


class NTAScoreClient:
    """
    Client for the NTA Score API.

    Usage:
        client = NTAScoreClient()
        if not client.is_enabled():
            return  # manual entry fallback

        result = client.fetch_score(
            exam_type="JEE_MAIN",
            application_number="240110012345",
            dob="2003-05-14",
        )
        if result.success:
            score_card = result.score_card
    """

    def __init__(self) -> None:
        from server.core.settings import settings
        self._settings = settings

    def is_enabled(self) -> bool:
        return self._settings.nta_enabled

    def fetch_score(
        self,
        exam_type: str,
        application_number: str,
        dob: str,
    ) -> NTAImportResult:
        """
        Fetch score card for a candidate from NTA.

        Args:
            exam_type: One of NTA_EXAM_SLUGS keys (e.g. "JEE_MAIN")
            application_number: NTA application / registration number
            dob: Candidate date of birth in YYYY-MM-DD

        Returns:
            NTAImportResult with score_card on success.
        """
        if not self.is_enabled():
            return NTAImportResult(success=False, error="NTA integration not configured.")

        slug = NTA_EXAM_SLUGS.get(exam_type)
        if not slug:
            return NTAImportResult(
                success=False,
                error=f"Unknown exam type '{exam_type}'. Valid: {list(NTA_EXAM_SLUGS.keys())}"
            )

        import httpx
        base_url = self._settings.nta_base_url
        api_key = self._settings.nta_api_key
        timeout = self._settings.nta_timeout_seconds

        try:
            resp = httpx.get(
                f"{base_url}/scores/{slug}",
                params={"application_number": application_number, "dob": dob},
                headers={"X-API-Key": api_key, "Accept": "application/json"},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            score_card = self._parse_score_card(exam_type, application_number, data)
            logger.info(
                "NTA: score fetched [exam=%s, app=%s, percentile=%s]",
                exam_type, application_number, score_card.percentile,
            )
            return NTAImportResult(success=True, score_card=score_card)

        except Exception as exc:
            logger.error("NTA: score fetch failed [exam=%s, app=%s] — %s", exam_type, application_number, exc)
            return NTAImportResult(success=False, error=str(exc))

    def verify_candidate(
        self,
        exam_type: str,
        application_number: str,
        dob: str,
    ) -> bool:
        """
        Quick verification — check if the candidate exists in NTA records.
        Returns True if verified, False otherwise.
        """
        result = self.fetch_score(exam_type, application_number, dob)
        return result.success

    def _parse_score_card(
        self,
        exam_type: str,
        application_number: str,
        data: Dict[str, Any],
    ) -> NTAScoreCard:
        """Parse NTA API response into a typed NTAScoreCard."""
        subject_scores: Dict[str, float] = {}
        for subj in data.get("subjects", []):
            subject_scores[subj.get("name", "Unknown")] = float(subj.get("marks", 0))

        return NTAScoreCard(
            application_number=application_number,
            candidate_name=data.get("candidate_name", ""),
            dob=data.get("dob", ""),
            exam_type=exam_type,
            roll_number=data.get("roll_number", ""),
            total_marks=float(data.get("total_marks", 0)),
            percentile=float(data["percentile"]) if data.get("percentile") is not None else None,
            rank=int(data["rank"]) if data.get("rank") is not None else None,
            category_rank=int(data["category_rank"]) if data.get("category_rank") is not None else None,
            subject_scores=subject_scores,
            raw=data,
        )
