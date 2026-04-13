from __future__ import annotations

"""
WiFi Attendance Router — E05-WiFi

Manages WiFi-proximity attendance sessions:
  1. Faculty starts a session (POST /attendance/wifi/start)
  2. Students self-verify by hitting the endpoint from the same network (POST /attendance/wifi/verify)
  3. Faculty polls the live roster (GET /attendance/wifi/sessions/{id})
  4. Faculty ends the session — absent students are auto-marked (POST /attendance/wifi/sessions/{id}/end)

IP proximity check: student's public IP must match faculty's public IP recorded at session start.
This requires both devices to be on the same NAT gateway (campus WiFi hotspot).

Feature flag: academics.offline_attendance_pwa (controls whether the desktop app button is shown in UI,
but the API itself is always available for authorized faculty).
"""

from server.core.rbac import Permission, require_permission  # noqa: E402

import logging  # noqa: E402
import secrets  # noqa: E402

from fastapi import APIRouter, HTTPException, Request, status  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from server.core.audit import AuditAction, AuditLedger  # noqa: E402
from server.core.domain_events import DomainEventBus  # noqa: E402
from server.db_service import execute_query, execute_transaction  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/attendance/wifi", tags=["WiFi Attendance"])


# ── Pydantic models ──────────────────────────────────────────────────────────


class StartSessionRequest(BaseModel):
    course_id: str
    ssid: str
    wifi_password: str
    duration_minutes: int = 15


class VerifyRequest(BaseModel):
    session_token: str
    """The 8-character token displayed on the faculty's screen. Student enters this."""


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    """Extract public IP from request. Respects X-Forwarded-For for reverse-proxy deployments."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _get_faculty_course(tenant_id: str, course_id: str, faculty_id: str) -> dict:
    rows = execute_query(
        """
        SELECT c.id, c.code, c.name, c.faculty_id
        FROM courses c
        WHERE c.id = $1 AND c.tenant_id = $2 AND c.faculty_id = $3
        """,
        (course_id, tenant_id, faculty_id),
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Course not found or you are not the assigned faculty",
        )
    return dict(rows[0])


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/start", status_code=status.HTTP_201_CREATED)
@require_permission(Permission.ACADEMICS_MANAGE)
def start_wifi_session(
    body: StartSessionRequest,
    request: Request,
):
    """
    Faculty starts a WiFi attendance session.
    Returns the session_id, session_token (8-char), and duration.
    """
    tenant_id = str(getattr(request.state, "tenant_id", "default"))
    faculty_id = str(getattr(request.state, "user_id", "anonymous"))

    course = _get_faculty_course(tenant_id, body.course_id, faculty_id)
    faculty_ip = _get_client_ip(request)

    # Generate a short, memorable session token
    session_token = secrets.token_hex(4).upper()  # e.g. "A3F9B2C1"

    execute_transaction(
        [
            (
                """
        INSERT INTO attendance_wifi_sessions
            (tenant_id, course_id, faculty_id, session_token, ssid, wifi_password,
             faculty_public_ip, duration_minutes)
        VALUES ($1,$2,$3,$4,$5,$6,$7::inet,$8)
        """,
                (
                    tenant_id,
                    body.course_id,
                    faculty_id,
                    session_token,
                    body.ssid,
                    body.wifi_password,
                    faculty_ip,
                    body.duration_minutes,
                ),
            )
        ]
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id="system",
        actor_role="system",
        entity_type="start_wifi_session",
        entity_id="",
        tenant_id=tenant_id,
        metadata={"source": "start_wifi_session"},
    )

    row = execute_query(
        """
        SELECT id, session_token, ssid, wifi_password, duration_minutes, started_at
        FROM attendance_wifi_sessions
        WHERE session_token=$1 AND tenant_id=$2
        ORDER BY started_at DESC LIMIT 1
        """,
        (session_token, tenant_id),
    )
    session = dict(row[0])

    logger.info(
        "wifi_session_started course=%s faculty=%s token=%s ip=%s",
        body.course_id,
        faculty_id,
        session_token,
        faculty_ip,
    )
    return {
        "session_id": str(session["id"]),
        "session_token": session["session_token"],
        "ssid": session["ssid"],
        "wifi_password": session["wifi_password"],
        "duration_minutes": session["duration_minutes"],
        "started_at": session["started_at"].isoformat(),
        "course_code": course["code"],
        "course_name": course["name"],
    }


@router.get("/sessions/{session_id}")
@require_permission(Permission.ACADEMICS_READ)
def get_session_status(
    session_id: str,
    request: Request,
):
    """
    Poll for live session status + verified student roster.
    Called every 3 seconds by the desktop app's LiveRoster component.
    """
    tenant_id = str(getattr(request.state, "tenant_id", "default"))

    rows = execute_query(
        """
        SELECT s.id, s.status, s.duration_minutes, s.started_at, s.ended_at,
               s.student_count, s.present_count, s.absent_count,
               c.code AS course_code, c.name AS course_name
        FROM attendance_wifi_sessions s
        JOIN courses c ON c.id = s.course_id
        WHERE s.id=$1 AND s.tenant_id=$2
        """,
        (session_id, tenant_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Session not found")

    session = dict(rows[0])

    # Live roster: all enrolled students + their verification status
    roster_rows = execute_query(
        """
        SELECT
            st.id AS student_id,
            u.full_name,
            st.roll_number,
            v.status AS verification_status,
            v.verified_at,
            v.ip_matched
        FROM course_enrollments ce
        JOIN students st ON st.id = ce.student_id
        JOIN users u ON u.id = st.user_id
        LEFT JOIN attendance_wifi_verifications v
            ON v.student_id = st.id AND v.session_id = $1
        WHERE ce.course_id = (
            SELECT course_id FROM attendance_wifi_sessions WHERE id=$1
        )
        AND ce.status = 'ACTIVE'
        ORDER BY st.roll_number
        """,
        (session_id,),
    )

    return {
        "session_id": session_id,
        "status": session["status"],
        "course_code": session["course_code"],
        "course_name": session["course_name"],
        "duration_minutes": session["duration_minutes"],
        "started_at": session["started_at"].isoformat(),
        "ended_at": session["ended_at"].isoformat() if session["ended_at"] else None,
        "present_count": session["present_count"],
        "absent_count": session["absent_count"],
        "student_count": session["student_count"],
        "roster": [
            {
                "student_id": str(r["student_id"]),
                "full_name": r["full_name"],
                "roll_number": r["roll_number"],
                "status": r["verification_status"] or "PENDING",
                "verified_at": r["verified_at"].isoformat()
                if r["verified_at"]
                else None,
                "ip_matched": r["ip_matched"],
            }
            for r in roster_rows
        ],
    }


@router.post("/verify", status_code=status.HTTP_200_OK)
@require_permission(Permission.STUDENT_READ)
def verify_student_presence(
    body: VerifyRequest,
    request: Request,
):
    """
    Student self-verification endpoint.
    Student enters the session_token displayed on faculty's screen.
    Backend checks: is this student's public IP the same as the faculty's IP?
    If yes → PRESENT. If no → IP_MISMATCH (manual review required).
    """
    tenant_id = str(getattr(request.state, "tenant_id", "default"))
    student_id = str(getattr(request.state, "user_id", "anonymous"))
    student_ip = _get_client_ip(request)

    # Find the active session by token
    session_rows = execute_query(
        """
        SELECT id, faculty_public_ip, course_id, status
        FROM attendance_wifi_sessions
        WHERE session_token=$1 AND tenant_id=$2 AND status='ACTIVE'
        """,
        (body.session_token, tenant_id),
    )
    if not session_rows:
        raise HTTPException(
            status_code=404, detail="Session not found or already ended"
        )

    session = dict(session_rows[0])
    session_id = str(session["id"])

    # Check for duplicate verification
    existing = execute_query(
        "SELECT id FROM attendance_wifi_verifications WHERE session_id=$1 AND student_id=$2",
        (session_id, student_id),
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already verified for this session")

    # IP proximity check
    faculty_ip = str(session["faculty_public_ip"])
    ip_matched = student_ip == faculty_ip
    verif_status = "PRESENT" if ip_matched else "IP_MISMATCH"

    execute_transaction(
        [
            (
                """
        INSERT INTO attendance_wifi_verifications
            (session_id, student_id, tenant_id, student_public_ip, ip_matched, status, verified_at)
        VALUES ($1,$2,$3,$4::inet,$5,$6,NOW())
        """,
                (
                    session_id,
                    student_id,
                    tenant_id,
                    student_ip,
                    ip_matched,
                    verif_status,
                ),
            )
        ]
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id="system",
        actor_role="system",
        entity_type="student_presence",
        entity_id="",
        tenant_id=tenant_id,
        metadata={"source": "verify_student_presence"},
    )

    # Update session present_count
    if ip_matched:
        execute_transaction(
            [
                (
                    "UPDATE attendance_wifi_sessions SET present_count=present_count+1 WHERE id=$1",
                    (session_id,),
                )
            ]
        )

    logger.info(
        "wifi_verify student=%s session=%s ip_matched=%s status=%s",
        student_id,
        session_id,
        ip_matched,
        verif_status,
    )
    return {
        "status": verif_status,
        "ip_matched": ip_matched,
        "message": "Marked PRESENT"
        if ip_matched
        else "IP mismatch — faculty can manually override",
    }


@router.post("/sessions/{session_id}/end", status_code=status.HTTP_200_OK)
@require_permission(Permission.ACADEMICS_MANAGE)
def end_wifi_session(
    session_id: str,
    request: Request,
):
    """
    Faculty ends the WiFi session.
    All enrolled students who never verified → auto-marked ABSENT in attendance_records.
    Fires domain event attendance.wifi_session_ended.
    """
    tenant_id = str(getattr(request.state, "tenant_id", "default"))
    faculty_id = str(getattr(request.state, "user_id", "anonymous"))

    rows = execute_query(
        """
        SELECT s.id, s.course_id, s.faculty_id, s.status, s.present_count,
               c.code AS course_code, c.name AS course_name
        FROM attendance_wifi_sessions s
        JOIN courses c ON c.id = s.course_id
        WHERE s.id=$1 AND s.tenant_id=$2 AND s.status='ACTIVE'
        """,
        (session_id, tenant_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Active session not found")

    session = dict(rows[0])
    if str(session["faculty_id"]) != faculty_id:
        raise HTTPException(status_code=403, detail="Only the session owner can end it")

    course_id = str(session["course_id"])

    # Get enrolled students who didn't verify (→ ABSENT)
    unverified = execute_query(
        """
        SELECT st.id AS student_id, u.full_name
        FROM course_enrollments ce
        JOIN students st ON st.id = ce.student_id
        JOIN users u ON u.id = st.user_id
        WHERE ce.course_id=$1 AND ce.status='ACTIVE'
          AND st.id NOT IN (
              SELECT student_id FROM attendance_wifi_verifications WHERE session_id=$2
          )
        """,
        (course_id, session_id),
    )

    absent_count = len(unverified)

    # Close the session
    execute_transaction(
        [
            (
                """
        UPDATE attendance_wifi_sessions
        SET status='ENDED', ended_at=NOW(), absent_count=$1
        WHERE id=$2
        """,
                (absent_count, session_id),
            )
        ]
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id="system",
        actor_role="system",
        entity_type="end_wifi_session",
        entity_id="",
        tenant_id=tenant_id,
        metadata={"source": "end_wifi_session"},
    )

    # Insert ABSENT records for unverified students
    for student in unverified:
        execute_transaction(
            [
                (
                    """
            INSERT INTO attendance_wifi_verifications
                (session_id, student_id, tenant_id, ip_matched, status, verified_at)
            VALUES ($1,$2,$3,FALSE,'ABSENT',NOW())
            ON CONFLICT (session_id, student_id) DO NOTHING
            """,
                    (session_id, str(student["student_id"]), tenant_id),
                )
            ]
        )

    DomainEventBus.publish(
        "attendance.wifi_session_ended",
        {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "course_id": course_id,
            "course_code": session["course_code"],
            "faculty_id": faculty_id,
            "present_count": session["present_count"],
            "absent_count": absent_count,
        },
    )

    logger.info(
        "wifi_session_ended session=%s present=%s absent=%s",
        session_id,
        session["present_count"],
        absent_count,
    )
    return {
        "session_id": session_id,
        "status": "ENDED",
        "present_count": session["present_count"],
        "absent_count": absent_count,
    }
