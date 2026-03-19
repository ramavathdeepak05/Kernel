"""E14 — Regulatory Event Handlers

Subscribes to all domain events that carry regulatory metric data.
Each handler updates exactly one or two metric rows in regulatory_metrics.
No cross-module reads — all data comes from the event payload.

Event subscriptions (from architecture.md §15, E14 subscriber list):
  StudentEnrolled          → naac.criterion_1.total_enrollment
                             naac.criterion_1.student_faculty_ratio (enrollment side)
  StudentCancelled         → naac.criterion_1.attrition_count
  ResultPublished          → naac.criterion_2.pass_percentage
                             naac.criterion_2.sgpa_avg
  ScholarshipDisbursed     → naac.criterion_5.students_receiving_aid_count
  EmployeeJoined           → naac.criterion_2.faculty_phd_count (if qualification=PhD)
                             naac.criterion_2.faculty_total_count
  AppraisalSubmitted       → naac.criterion_3.research_publications_count
  LibraryCatalogueUpdated  → naac.criterion_4.library_holdings_count
  GrievanceClosed          → naac.criterion_6.grievance_resolved_count
  TrainingCompleted        → naac.criterion_3.fdp_count
  OfferReceived            → naac.criterion_5.placement_count (for NIRF GO parameter)

Reference: ALIS-skills/references/architecture.md §15
"""

import logging
from typing import Any, Dict

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(event: Dict[str, Any]) -> str:
    return str(event.get("org_id", ""))


def _payload(event: Dict[str, Any]) -> Dict[str, Any]:
    return event.get("payload", {})


def _event_id(event: Dict[str, Any]) -> str:
    return str(event.get("id", ""))


def _event_type(event: Dict[str, Any]) -> str:
    return str(event.get("event_type", ""))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def on_student_enrolled(event: Dict[str, Any]) -> None:
    """naac.criterion_1.total_enrollment ++"""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        breakdown = {
            "program": payload.get("program"),
            "category": payload.get("category"),
            "gender": payload.get("gender"),
            "batch": payload.get("batch"),
        }
        RegulatoryMetricsService.increment(
            org_id=org_id,
            metric_key="naac.criterion_1.total_enrollment",
            delta=1.0,
            framework="NAAC",
            source_event=_event_type(event),
            source_event_id=_event_id(event),
        )
        logger.debug("E14: enrollment metric incremented for org %s", org_id)
    except Exception as exc:
        logger.error("E14: on_student_enrolled failed: %s", exc, exc_info=True)


def on_student_cancelled(event: Dict[str, Any]) -> None:
    """naac.criterion_1.attrition_count ++"""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        RegulatoryMetricsService.increment(
            org_id=org_id,
            metric_key="naac.criterion_1.attrition_count",
            delta=1.0,
            framework="NAAC",
            source_event=_event_type(event),
            source_event_id=_event_id(event),
        )
    except Exception as exc:
        logger.error("E14: on_student_cancelled failed: %s", exc, exc_info=True)


def on_result_published(event: Dict[str, Any]) -> None:
    """naac.criterion_2.pass_percentage and sgpa_avg (rolling snapshot)."""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        pass_pct = payload.get("pass_percentage")
        sgpa_avg = payload.get("sgpa_avg")
        if pass_pct is not None:
            RegulatoryMetricsService.record(
                org_id=org_id,
                metric_key="naac.criterion_2.pass_percentage",
                metric_value=float(pass_pct),
                framework="NAAC",
                breakdown={"semester": payload.get("semester"), "batch": payload.get("batch")},
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
        if sgpa_avg is not None:
            RegulatoryMetricsService.record(
                org_id=org_id,
                metric_key="naac.criterion_2.sgpa_avg",
                metric_value=float(sgpa_avg),
                framework="NAAC",
                breakdown={"semester": payload.get("semester"), "batch": payload.get("batch")},
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
        # Also update NIRF TLR pass percentage
        if pass_pct is not None:
            RegulatoryMetricsService.record(
                org_id=org_id,
                metric_key="nirf.tlr.pass_percentage",
                metric_value=float(pass_pct),
                framework="NIRF",
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
    except Exception as exc:
        logger.error("E14: on_result_published failed: %s", exc, exc_info=True)


def on_scholarship_disbursed(event: Dict[str, Any]) -> None:
    """naac.criterion_5.students_receiving_aid_count ++"""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        RegulatoryMetricsService.increment(
            org_id=org_id,
            metric_key="naac.criterion_5.students_receiving_aid_count",
            delta=1.0,
            framework="NAAC",
            source_event=_event_type(event),
            source_event_id=_event_id(event),
        )
        # NIRF — % students receiving financial aid
        RegulatoryMetricsService.increment(
            org_id=org_id,
            metric_key="nirf.go.students_receiving_financial_aid",
            delta=1.0,
            framework="NIRF",
            source_event=_event_type(event),
            source_event_id=_event_id(event),
        )
    except Exception as exc:
        logger.error("E14: on_scholarship_disbursed failed: %s", exc, exc_info=True)


def on_employee_joined(event: Dict[str, Any]) -> None:
    """naac.criterion_2.faculty_total_count ++ and phd count if qualified."""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        emp_type = payload.get("employment_type", "")
        qualification = payload.get("highest_qualification", "")

        if emp_type in ("FACULTY", "TEACHING"):
            RegulatoryMetricsService.increment(
                org_id=org_id,
                metric_key="naac.criterion_2.faculty_total_count",
                delta=1.0,
                framework="NAAC",
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
            if qualification.upper() in ("PHD", "PH.D", "DOCTORATE"):
                RegulatoryMetricsService.increment(
                    org_id=org_id,
                    metric_key="naac.criterion_2.faculty_phd_count",
                    delta=1.0,
                    framework="NAAC",
                    source_event=_event_type(event),
                    source_event_id=_event_id(event),
                )
    except Exception as exc:
        logger.error("E14: on_employee_joined failed: %s", exc, exc_info=True)


def on_appraisal_submitted(event: Dict[str, Any]) -> None:
    """naac.criterion_3.research_publications_count += publications in this appraisal."""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        publications = int(payload.get("publications_count", 0))
        if publications > 0:
            RegulatoryMetricsService.increment(
                org_id=org_id,
                metric_key="naac.criterion_3.research_publications_count",
                delta=float(publications),
                framework="NAAC",
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
    except Exception as exc:
        logger.error("E14: on_appraisal_submitted failed: %s", exc, exc_info=True)


def on_library_catalogue_updated(event: Dict[str, Any]) -> None:
    """naac.criterion_4.library_holdings_count = total holdings (absolute, not delta)."""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        total_holdings = payload.get("total_holdings")
        if total_holdings is not None:
            RegulatoryMetricsService.record(
                org_id=org_id,
                metric_key="naac.criterion_4.library_holdings_count",
                metric_value=float(total_holdings),
                framework="NAAC",
                breakdown={
                    "books": payload.get("books_count"),
                    "journals": payload.get("journals_count"),
                    "e_resources": payload.get("e_resources_count"),
                },
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
    except Exception as exc:
        logger.error("E14: on_library_catalogue_updated failed: %s", exc, exc_info=True)


def on_grievance_closed(event: Dict[str, Any]) -> None:
    """naac.criterion_6.grievance_resolved_count ++"""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        RegulatoryMetricsService.increment(
            org_id=org_id,
            metric_key="naac.criterion_6.grievance_resolved_count",
            delta=1.0,
            framework="NAAC",
            source_event=_event_type(event),
            source_event_id=_event_id(event),
        )
    except Exception as exc:
        logger.error("E14: on_grievance_closed failed: %s", exc, exc_info=True)


def on_training_completed(event: Dict[str, Any]) -> None:
    """naac.criterion_3.fdp_count ++"""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        training_type = payload.get("training_type", "")
        if training_type.upper() in ("FDP", "FACULTY_DEVELOPMENT", "UGC_MANDATORY"):
            RegulatoryMetricsService.increment(
                org_id=org_id,
                metric_key="naac.criterion_3.fdp_count",
                delta=1.0,
                framework="NAAC",
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
    except Exception as exc:
        logger.error("E14: on_training_completed failed: %s", exc, exc_info=True)


def on_offer_received(event: Dict[str, Any]) -> None:
    """naac.criterion_5.placement_count ++ and nirf.go.placement_count ++"""
    from .metrics_service import RegulatoryMetricsService
    org_id = _org(event)
    if not org_id:
        return
    try:
        payload = _payload(event)
        offer_type = payload.get("offer_type", "PLACEMENT")
        if offer_type in ("PLACEMENT", "INTERNSHIP_TO_PPO"):
            RegulatoryMetricsService.increment(
                org_id=org_id,
                metric_key="naac.criterion_5.placement_count",
                delta=1.0,
                framework="NAAC",
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
            RegulatoryMetricsService.increment(
                org_id=org_id,
                metric_key="nirf.go.placement_count",
                delta=1.0,
                framework="NIRF",
                source_event=_event_type(event),
                source_event_id=_event_id(event),
            )
    except Exception as exc:
        logger.error("E14: on_offer_received failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_all() -> None:
    """Register all E14 domain event subscriptions."""
    DomainEventBus.subscribe("StudentEnrolled",          on_student_enrolled)
    DomainEventBus.subscribe("StudentCancelled",         on_student_cancelled)
    DomainEventBus.subscribe("ResultPublished",          on_result_published)
    DomainEventBus.subscribe("ScholarshipDisbursed",     on_scholarship_disbursed)
    DomainEventBus.subscribe("EmployeeJoined",           on_employee_joined)
    DomainEventBus.subscribe("AppraisalSubmitted",       on_appraisal_submitted)
    DomainEventBus.subscribe("LibraryCatalogueUpdated",  on_library_catalogue_updated)
    DomainEventBus.subscribe("GrievanceClosed",          on_grievance_closed)
    DomainEventBus.subscribe("TrainingCompleted",        on_training_completed)
    DomainEventBus.subscribe("OfferReceived",            on_offer_received)
    logger.info("E14 Regulatory event handlers registered (10 subscriptions)")
