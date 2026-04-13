"""
EC-HR-02 — Publication Discovery Service

Weekly scanning of ORCID and Scopus for faculty publications.
Discovered publications are stored as DRAFT entries requiring faculty confirmation
(Accept button → liability transfer to the faculty member).

Flow:
1. Beat task runs weekly: scan ORCID API for each faculty's ORCID iD
2. New publications matched → stored as UNVERIFIED
3. Faculty reviews → Accept (VERIFIED) or Reject (REJECTED)
4. VERIFIED publications feed into API score, CAS eligibility, NAAC/NIRF metrics

Integration:
- ORCID Public API: https://pub.orcid.org/v3.0/{orcid-id}/works
- Scopus Search API: https://api.elsevier.com/content/search/scopus
- Google Scholar (future): via serpapi or similar

Security:
- ORCID iD stored per faculty in staff_profiles
- API keys for Scopus stored in Vault KV
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx
from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class PublicationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"  # Discovered by scraper, pending faculty review
    VERIFIED = "VERIFIED"  # Faculty accepted (liability transferred)
    REJECTED = "REJECTED"  # Faculty rejected (false match)
    DUPLICATE = "DUPLICATE"  # Already in system


class PublicationDiscoveryService:
    """
    Discovers faculty publications from ORCID and Scopus APIs.
    Stores as UNVERIFIED until faculty confirms (Accept/Reject).
    """

    ORCID_API_BASE = "https://pub.orcid.org/v3.0"

    @classmethod
    async def discover_from_orcid(
        cls, org_id: str, staff_id: str, orcid_id: str
    ) -> list[dict[str, Any]]:
        """Fetch publications from ORCID Public API for a faculty member."""
        discovered = []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{cls.ORCID_API_BASE}/{orcid_id}/works",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code != 200:
                    logger.warning(
                        "ORCID API returned %d for %s", resp.status_code, orcid_id
                    )
                    return []

                data = resp.json()
                groups = data.get("group", [])

                for group in groups:
                    summaries = group.get("work-summary", [])
                    if not summaries:
                        continue
                    summary = summaries[0]  # Take first summary per group

                    title_obj = summary.get("title", {}).get("title", {})
                    title = (
                        title_obj.get("value", "")
                        if isinstance(title_obj, dict)
                        else str(title_obj)
                    )
                    pub_year = (
                        summary.get("publication-date", {})
                        .get("year", {})
                        .get("value", "")
                    )
                    journal = (
                        summary.get("journal-title", {}).get("value", "")
                        if summary.get("journal-title")
                        else ""
                    )
                    doi = ""
                    for eid in summary.get("external-ids", {}).get("external-id", []):
                        if eid.get("external-id-type") == "doi":
                            doi = eid.get("external-id-value", "")
                            break

                    if not title:
                        continue

                    # Check if already exists
                    existing = execute_query(
                        "SELECT id FROM faculty_publications "
                        "WHERE staff_id = %s AND org_id = %s AND (doi = %s OR title = %s)",
                        (staff_id, org_id, doi, title),
                        tenant_id=org_id,
                    )
                    if existing:
                        continue

                    pub_id = str(uuid4())
                    execute_transaction(
                        [
                            (
                                """
                            INSERT INTO faculty_publications
                                (id, org_id, staff_id, title, journal, year, doi,
                                 source, status, discovered_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ORCID', %s, NOW())
                            """,
                                (
                                    pub_id,
                                    org_id,
                                    staff_id,
                                    title,
                                    journal,
                                    pub_year,
                                    doi,
                                    PublicationStatus.UNVERIFIED.value,
                                ),
                            )
                        ],
                        tenant_id=org_id,
                    )

                    discovered.append(
                        {
                            "id": pub_id,
                            "title": title,
                            "journal": journal,
                            "year": pub_year,
                            "doi": doi,
                            "source": "ORCID",
                            "status": PublicationStatus.UNVERIFIED.value,
                        }
                    )

        except Exception as exc:
            logger.error("ORCID discovery failed for %s: %s", orcid_id, exc)

        return discovered

    @classmethod
    async def discover_from_scopus(
        cls,
        org_id: str,
        staff_id: str,
        author_name: str,
        scopus_api_key: str,
    ) -> list[dict[str, Any]]:
        """Fetch publications from Scopus Search API."""
        discovered = []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://api.elsevier.com/content/search/scopus",
                    params={
                        "query": f"AUTHOR-NAME({author_name})",
                        "count": 25,
                        "sort": "-coverDate",
                    },
                    headers={
                        "X-ELS-APIKey": scopus_api_key,
                        "Accept": "application/json",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Scopus API returned %d", resp.status_code)
                    return []

                results = resp.json().get("search-results", {}).get("entry", [])
                for entry in results:
                    title = entry.get("dc:title", "")
                    journal = entry.get("prism:publicationName", "")
                    year = (
                        entry.get("prism:coverDate", "")[:4]
                        if entry.get("prism:coverDate")
                        else ""
                    )
                    doi = entry.get("prism:doi", "")
                    citations = int(entry.get("citedby-count", 0))

                    if not title:
                        continue

                    existing = execute_query(
                        "SELECT id FROM faculty_publications "
                        "WHERE staff_id = %s AND org_id = %s AND (doi = %s OR title = %s)",
                        (staff_id, org_id, doi, title),
                        tenant_id=org_id,
                    )
                    if existing:
                        continue

                    pub_id = str(uuid4())
                    execute_transaction(
                        [
                            (
                                """
                            INSERT INTO faculty_publications
                                (id, org_id, staff_id, title, journal, year, doi,
                                 citation_count, source, status, discovered_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'SCOPUS', %s, NOW())
                            """,
                                (
                                    pub_id,
                                    org_id,
                                    staff_id,
                                    title,
                                    journal,
                                    year,
                                    doi,
                                    citations,
                                    PublicationStatus.UNVERIFIED.value,
                                ),
                            )
                        ],
                        tenant_id=org_id,
                    )

                    discovered.append(
                        {
                            "id": pub_id,
                            "title": title,
                            "journal": journal,
                            "year": year,
                            "doi": doi,
                            "citations": citations,
                            "source": "SCOPUS",
                            "status": PublicationStatus.UNVERIFIED.value,
                        }
                    )

        except Exception as exc:
            logger.error("Scopus discovery failed for %s: %s", author_name, exc)

        return discovered

    @classmethod
    def verify_publication(
        cls, org_id: str, pub_id: str, decision: str, actor_id: str
    ) -> dict[str, Any]:
        """Faculty accepts or rejects a discovered publication."""
        if decision not in ("VERIFIED", "REJECTED"):
            raise ValueError("Decision must be VERIFIED or REJECTED")

        execute_transaction(
            [
                (
                    "UPDATE faculty_publications SET status = %s, verified_by = %s, verified_at = NOW() "
                    "WHERE id = %s AND org_id = %s AND status = %s",
                    (
                        decision,
                        actor_id,
                        pub_id,
                        org_id,
                        PublicationStatus.UNVERIFIED.value,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="faculty",
            entity_type="faculty_publication",
            entity_id=pub_id,
            tenant_id=org_id,
            metadata={"decision": decision, "event": "publication_verification"},
        )
        return {"id": pub_id, "status": decision}

    @classmethod
    def get_faculty_publications(
        cls, org_id: str, staff_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        if status:
            rows = execute_query(
                "SELECT * FROM faculty_publications WHERE staff_id = %s AND org_id = %s AND status = %s "
                "ORDER BY year DESC, discovered_at DESC",
                (staff_id, org_id, status),
                tenant_id=org_id,
            )
        else:
            rows = execute_query(
                "SELECT * FROM faculty_publications WHERE staff_id = %s AND org_id = %s "
                "ORDER BY year DESC, discovered_at DESC",
                (staff_id, org_id),
                tenant_id=org_id,
            )
        return [dict(r) for r in rows]

    @classmethod
    async def run_weekly_scan(cls, org_id: str) -> dict[str, Any]:
        """Beat task: scan all faculty ORCID iDs for new publications."""
        staff = execute_query(
            "SELECT id, name, orcid_id FROM staff_profiles "
            "WHERE org_id = %s AND status = 'ACTIVE' AND orcid_id IS NOT NULL AND orcid_id != ''",
            (org_id,),
            tenant_id=org_id,
        )
        total_discovered = 0
        for s in staff:
            pubs = await cls.discover_from_orcid(org_id, str(s["id"]), s["orcid_id"])
            total_discovered += len(pubs)
            if pubs:
                logger.info(
                    "Discovered %d new publications for %s", len(pubs), s["name"]
                )

        return {
            "staff_scanned": len(staff),
            "publications_discovered": total_discovered,
        }
