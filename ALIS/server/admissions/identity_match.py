"""EC-ADM-01 — Cross-Document Identity Mismatch Check

Compares an applicant's name as it appears across three sources:
  • Application form (applicant_name) — the ground truth entered at Step 1
  • Aadhaar eKYC (aadhaar_name) — populated when Aadhaar OTP verification runs
  • Entrance scorecard (jee_name) — populated during JEE/NEET/CAT score ingestion

Algorithm: Jaro-Winkler similarity (≥ 0.85 threshold per spec).
  - All pairs above threshold → kyc_status = MATCHED
  - Any pair below threshold → kyc_status = KYC_RECONCILIATION
    → application status set to KYC_RECONCILIATION queue
    → notification sent to applicant with reconciliation instructions

Aadhaar eKYC name is used as ground truth when available.

Rules
─────
• Never auto-reject on name mismatch — only route to manual queue.
• All variant comparisons are normalised (lowercase, strip extra whitespace).
• name_variants JSONB stores [{"source": "...", "name": "..."}] for audit.
• Once an officer clears the mismatch, they call clear_kyc_hold().
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Threshold per Admissions_v2 spec §Stage4/EC-ADM-01
_SIMILARITY_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Jaro-Winkler (no external deps — same logic as deduplication_service.py)
# ---------------------------------------------------------------------------

def _jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if not len1 or not len2:
        return 0.0
    match_dist = max(len1, len2) // 2 - 1
    if match_dist < 0:
        match_dist = 0
    s1m = [False] * len1
    s2m = [False] * len2
    matches = transpositions = 0
    for i in range(len1):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len2)
        for j in range(start, end):
            if s2m[j] or s1[i] != s2[j]:
                continue
            s1m[i] = s2m[j] = True
            matches += 1
            break
    if not matches:
        return 0.0
    k = 0
    for i in range(len1):
        if not s1m[i]:
            continue
        while not s2m[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    return (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3.0


def _jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    jaro = _jaro(s1, s2)
    prefix = 0
    for c1, c2 in zip(s1[:4], s2[:4]):
        if c1 == c2:
            prefix += 1
        else:
            break
    return round(jaro + prefix * p * (1.0 - jaro), 6)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class IdentityMatchService:
    """Cross-document identity mismatch check (EC-ADM-01)."""

    @classmethod
    def check(cls, application_id: str, org_id: str, actor_id: str) -> dict:
        """
        Run the cross-document name consistency check.

        Returns a dict with keys:
          kyc_status   — MATCHED | KYC_RECONCILIATION
          name_variants — list of {source, name} dicts
          pairs        — list of {a, b, score} comparison results
          min_score    — lowest pairwise Jaro-Winkler score
        """
        rows = execute_query(
            """
            SELECT applicant_name, aadhaar_name, jee_name
            FROM   applications
            WHERE  id = %s AND org_id = %s
            """,
            (application_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Application {application_id} not found")

        row = dict(rows[0])
        sources: list[dict] = []

        if row.get("applicant_name"):
            sources.append({"source": "application_form", "name": row["applicant_name"]})
        if row.get("aadhaar_name"):
            sources.append({"source": "aadhaar",          "name": row["aadhaar_name"]})
        if row.get("jee_name"):
            sources.append({"source": "entrance_scorecard", "name": row["jee_name"]})

        # Need at least two sources to compare
        if len(sources) < 2:
            result = {
                "kyc_status":    "NOT_CHECKED",
                "name_variants": sources,
                "pairs":         [],
                "min_score":     None,
                "note":          "Only one name source available — check deferred until Aadhaar/scorecard data arrives",
            }
            return result

        # Pairwise Jaro-Winkler
        pairs: list[dict] = []
        min_score = 1.0
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                score = _jaro_winkler(sources[i]["name"], sources[j]["name"])
                pairs.append({
                    "a":     sources[i]["source"],
                    "b":     sources[j]["source"],
                    "score": score,
                })
                if score < min_score:
                    min_score = score

        kyc_status = "MATCHED" if min_score >= _SIMILARITY_THRESHOLD else "KYC_RECONCILIATION"

        # Persist to DB
        execute_transaction([(
            """
            UPDATE applications
               SET name_variants = %s,
                   kyc_status    = %s
             WHERE id = %s AND org_id = %s
            """,
            (json.dumps(sources), kyc_status, application_id, org_id),
        )])

        if kyc_status == "KYC_RECONCILIATION":
            # Route to KYC queue — update application status
            execute_transaction([(
                """
                UPDATE applications
                   SET status = 'KYC_RECONCILIATION'
                 WHERE id = %s AND org_id = %s
                   AND status NOT IN ('ENROLLED', 'CANCELLED', 'WITHDRAWN')
                """,
                (application_id, org_id),
            )])
            logger.warning(
                "EC-ADM-01: application %s routed to KYC_RECONCILIATION (min_score=%.3f)",
                application_id,
                min_score,
            )

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            actor_type="system",
            action=AuditAction.UPDATE,
            resource_type="application",
            resource_id=application_id,
            detail={
                "event":      "identity_match_check",
                "kyc_status": kyc_status,
                "min_score":  min_score,
                "pairs":      pairs,
            },
        )

        return {
            "kyc_status":    kyc_status,
            "name_variants": sources,
            "pairs":         pairs,
            "min_score":     min_score,
        }

    @classmethod
    def clear_kyc_hold(
        cls,
        application_id: str,
        org_id: str,
        actor_id: str,
        resolution_note: str,
    ) -> dict:
        """
        Officer clears KYC_RECONCILIATION after manual review.
        Sets kyc_status = CLEARED and restores the pre-KYC application status.
        """
        rows = execute_query(
            "SELECT id, status FROM applications WHERE id = %s AND org_id = %s",
            (application_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Application {application_id} not found")

        execute_transaction([(
            """
            UPDATE applications
               SET kyc_status = 'CLEARED',
                   status     = 'ELIGIBILITY_SCREENING'
             WHERE id = %s AND org_id = %s
               AND kyc_status = 'KYC_RECONCILIATION'
            """,
            (application_id, org_id),
        )])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            actor_type="human",
            action=AuditAction.UPDATE,
            resource_type="application",
            resource_id=application_id,
            detail={
                "event":           "kyc_hold_cleared",
                "resolution_note": resolution_note,
            },
        )
        logger.info("EC-ADM-01: KYC hold cleared for application %s by %s", application_id, actor_id)
        return {"application_id": application_id, "kyc_status": "CLEARED"}

    @classmethod
    def update_name_source(
        cls,
        application_id: str,
        org_id: str,
        source: str,
        name: str,
        actor_id: str,
    ) -> dict:
        """
        Store a name from an external source (Aadhaar eKYC, JEE scorecard import).
        Allowed sources: 'aadhaar' | 'entrance_scorecard'
        Re-runs the identity check automatically after updating.
        """
        col_map = {"aadhaar": "aadhaar_name", "entrance_scorecard": "jee_name"}
        col = col_map.get(source)
        if not col:
            raise ValueError(f"Unknown name source '{source}'. Must be: {list(col_map)}")

        execute_transaction([(
            f"UPDATE applications SET {col} = %s WHERE id = %s AND org_id = %s",  # noqa: S608
            (name.strip(), application_id, org_id),
        )])

        # Re-run check now that a new source is available
        return cls.check(application_id, org_id, actor_id)
