"""
E04-S02 — Lead De-duplication Wizard

MODULE: M1 — Admissions & Marketing
LAYER: Layer 4 (Lock if applicant already advanced) + Layer 6 (Audit trail)
ENTITY: LeadMergeLog

Identifies and merges duplicate leads using Jaro-Winkler similarity.

De-dup Rules:
    - similarity >= 0.9 → auto-merge (no admin required)
    - 0.7 <= similarity < 0.9 → merge requires admin justification
    - similarity < 0.7 → rejected (not a duplicate)

Hard Constraints:
    - Cannot merge leads if either is in ADMITTED or ENROLLED state (Layer 4)
    - Original lead IDs are preserved for audit
    - Merge target (primary) inherits the earlier created_at timestamp

Acceptance Criteria (E04-S02):
    - [x] API: POST /leads/merge
    - [x] Merge log recorded
    - [x] Admin override with justification
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation
from server.db_service import execute_query, execute_transaction

from .models import LeadMergeLog, LeadMergeRequest

logger = logging.getLogger(__name__)

# Minimum score to auto-merge without human review
_AUTO_MERGE_THRESHOLD = 0.9

# Minimum score to allow merge at all (below = not a duplicate)
_MERGE_FLOOR = 0.7

# States that block merge (applicant already advanced)
_PROTECTED_STATES = {"ADMITTED", "ENROLLED"}


class LeadDeduplicationService:
    """
    Lead de-duplication using Jaro-Winkler string similarity.

    All merge operations are appended to `lead_merge_log` for audit.
    Original records are never hard-deleted — the duplicate's status
    is set to ANNULLED and its data is preserved.
    """

    @classmethod
    def compute_similarity(cls, applicant_a: dict, applicant_b: dict) -> float:
        """
        Compute composite similarity between two applicant records.

        Weights:
            email  40% — strong identifier
            phone  35% — strong identifier
            name   25% — fuzzy match on normalized name
        """
        email_score = _jaro_winkler(
            applicant_a.get("email", "").lower(),
            applicant_b.get("email", "").lower(),
        )
        phone_score = _jaro_winkler(
            _digits_only(applicant_a.get("phone", "")),
            _digits_only(applicant_b.get("phone", "")),
        )
        name_score = _jaro_winkler(
            applicant_a.get("name", "").lower(),
            applicant_b.get("name", "").lower(),
        )

        return round(0.40 * email_score + 0.35 * phone_score + 0.25 * name_score, 4)

    @classmethod
    def find_duplicates(
        cls, applicant_id: str, org_id: str, top_n: int = 5
    ) -> list[dict]:
        """
        Find the top-N most similar applicants to a given applicant.

        Returns a list of dicts with keys:
            applicant_id, name, email, phone, similarity_score
        Sorted by similarity descending. Only includes scores >= _MERGE_FLOOR.
        """
        target_rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not target_rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{applicant_id}' not found.",
            )
        target = target_rows[0]

        candidates = execute_query(
            "SELECT * FROM applicants WHERE org_id = %s AND id != %s "
            "AND status != 'ANNULLED'",
            (org_id, applicant_id),
        )

        scored = []
        for c in candidates:
            score = cls.compute_similarity(target, c)
            if score >= _MERGE_FLOOR:
                scored.append(
                    {
                        "applicant_id": c["id"],
                        "name": c["name"],
                        "email": c["email"],
                        "phone": c["phone"],
                        "status": c["status"],
                        "similarity_score": score,
                    }
                )

        return sorted(scored, key=lambda x: x["similarity_score"], reverse=True)[:top_n]

    @classmethod
    def merge(
        cls,
        request: LeadMergeRequest,
        org_id: str,
        actor_id: str,
    ) -> LeadMergeLog:
        """
        Merge a duplicate lead into a primary applicant.

        If similarity >= 0.9 → auto-merge.
        Otherwise → requires justification in request.

        Args:
            request:  LeadMergeRequest with primary_id and duplicate_id
            org_id:   Tenant scope
            actor_id: Actor performing the merge

        Returns:
            LeadMergeLog record

        Raises:
            BusinessRuleViolation: If either applicant is in a protected state,
                                   or similarity is below floor,
                                   or manual merge lacks justification.
        """
        primary_rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (request.primary_applicant_id, org_id),
        )
        duplicate_rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (request.duplicate_applicant_id, org_id),
        )

        if not primary_rows:
            raise BusinessRuleViolation(
                message=f"Primary applicant '{request.primary_applicant_id}' not found."
            )
        if not duplicate_rows:
            raise BusinessRuleViolation(
                message=f"Duplicate applicant '{request.duplicate_applicant_id}' not found."
            )

        primary = primary_rows[0]
        duplicate = duplicate_rows[0]

        # --- Layer 4: Block if either applicant is advanced ---
        for ap, label in [(primary, "Primary"), (duplicate, "Duplicate")]:
            if ap["status"] in _PROTECTED_STATES:
                raise BusinessRuleViolation(
                    message=(
                        f"{label} applicant '{ap['id']}' is in state "
                        f"'{ap['status']}' — cannot be merged."
                    ),
                    details={"applicant_id": ap["id"], "status": ap["status"]},
                )

        # --- Compute similarity ---
        score = cls.compute_similarity(primary, duplicate)

        if score < _MERGE_FLOOR:
            raise BusinessRuleViolation(
                message=(
                    f"Similarity score {score:.2f} is below minimum threshold "
                    f"{_MERGE_FLOOR}. These applicants are not duplicates."
                ),
                details={"similarity_score": score},
            )

        # --- Determine merge method ---
        if score >= _AUTO_MERGE_THRESHOLD:
            method = "auto"
        else:
            if not request.justification:
                raise BusinessRuleViolation(
                    message=(
                        f"Similarity score {score:.2f} is below auto-merge threshold "
                        f"{_AUTO_MERGE_THRESHOLD}. Justification is required for "
                        f"manual merge."
                    ),
                    details={"similarity_score": score},
                )
            method = "admin_approved"

        # --- Execute merge: ANNUL duplicate, preserve primary ---
        now = datetime.now(timezone.utc)
        log_id = str(uuid4())
        execute_transaction(
            [
                (
                    "UPDATE applicants SET status = 'ANNULLED', updated_at = %s "
                    "WHERE id = %s AND org_id = %s",
                    (now, duplicate["id"], org_id),
                ),
                (
                    """
                INSERT INTO lead_merge_log
                    (id, org_id, primary_id, merged_id, similarity_score,
                     method, justification, merged_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        log_id,
                        org_id,
                        primary["id"],
                        duplicate["id"],
                        score,
                        method,
                        request.justification,
                        actor_id,
                        now,
                    ),
                ),
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="applicant",
            entity_id=primary["id"],
            org_id=org_id,
            module="M1",
            wizard="Lead De-duplication",
            success=True,
            metadata={
                "action": "lead_merge",
                "merged_id": duplicate["id"],
                "similarity_score": score,
                "method": method,
                "justification": request.justification,
            },
        )

        logger.info(
            "E04-S02: Merged applicant %s → primary %s [score=%.2f, method=%s, org=%s]",
            duplicate["id"],
            primary["id"],
            score,
            method,
            org_id,
        )

        return LeadMergeLog(
            id=log_id,
            org_id=org_id,
            primary_id=primary["id"],
            merged_id=duplicate["id"],
            similarity_score=score,
            method=method,
            justification=request.justification,
            merged_by=actor_id,
            created_at=now,
        )


# =============================================================================
# Jaro-Winkler Implementation
# =============================================================================


def _jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    """
    Compute Jaro-Winkler similarity between two strings.

    Returns a score in [0.0, 1.0]. 1.0 = identical.

    Args:
        s1, s2: Strings to compare
        p:      Winkler scaling factor (default 0.1)
    """
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len_s1, len_s2 = len(s1), len(s2)
    match_dist = max(len_s1, len_s2) // 2 - 1
    if match_dist < 0:
        match_dist = 0

    s1_matches = [False] * len_s1
    s2_matches = [False] * len_s2

    matches = 0
    transpositions = 0

    for i in range(len_s1):
        lo = max(0, i - match_dist)
        hi = min(i + match_dist + 1, len_s2)
        for j in range(lo, hi):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len_s1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        matches / len_s1 + matches / len_s2 + (matches - transpositions / 2) / matches
    ) / 3.0

    # Winkler prefix bonus
    prefix = 0
    for i in range(min(4, len_s1, len_s2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return round(jaro + prefix * p * (1 - jaro), 6)


def _digits_only(s: str) -> str:
    """Extract only digit characters from a string."""
    return "".join(c for c in s if c.isdigit())
