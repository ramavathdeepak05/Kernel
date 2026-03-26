"""
ALIS Load Test — Locust
=======================

Simulates peak admissions-day traffic: 500 concurrent users, mixed
read-heavy and write operations.

Usage:
    # Headless (CI / pipeline):
    locust -f tests/load/locustfile.py \
           --headless -u 500 -r 50 \
           --run-time 120s \
           --host http://localhost:8000

    # Interactive browser UI:
    locust -f tests/load/locustfile.py --host http://localhost:8000

    # Against staging:
    ALIS_HOST=https://api.staging.alis.edu \
    ALIS_TENANT=woxsen \
    ALIS_USER=loadtest@woxsen.edu.in \
    ALIS_PASS=LoadTest@1234 \
    locust -f tests/load/locustfile.py --headless -u 200 -r 20 --run-time 60s

Target SLO:
    p95 response time < 2000 ms
    Error rate < 1%
    500 concurrent users sustained for 120 seconds

Environment variables:
    ALIS_HOST     — base URL (default: http://localhost:8000)
    ALIS_TENANT   — tenant slug (default: demo)
    ALIS_USER     — login email (default: admin@demo.edu)
    ALIS_PASS     — password (default: Admin@1234)
"""
from __future__ import annotations

import json
import os
import random
import string
import time
import uuid
from typing import Optional

from locust import HttpUser, between, events, task
from locust.runners import MasterRunner

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TENANT = os.getenv("ALIS_TENANT", "demo")
USER   = os.getenv("ALIS_USER",   "admin@demo.edu")
PASS   = os.getenv("ALIS_PASS",   "Admin@1234")

PROGRAMS    = ["B.Tech CSE", "MBA", "B.Com", "M.Tech", "B.Sc Maths", "BBA"]
CHANNELS    = ["WEBSITE", "DIRECT", "REFERRAL", "SOCIAL_MEDIA"]
LEAD_STATUS = ["NEW", "CONTACTED", "INTERESTED"]


def _rand_email() -> str:
    return f"load_{uuid.uuid4().hex[:8]}@test.invalid"


def _rand_phone() -> str:
    return f"9{random.randint(100000000, 999999999)}"


# ---------------------------------------------------------------------------
# Shared token store (populated once per worker on start)
# ---------------------------------------------------------------------------

_auth_tokens: dict[str, str] = {}  # tenant_id → bearer token


def _get_token(client) -> Optional[str]:
    if TENANT not in _auth_tokens:
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": USER, "password": PASS, "tenant_id": TENANT},
            name="/auth/login [setup]",
        )
        if resp.status_code == 200:
            _auth_tokens[TENANT] = resp.json().get("token", "")
    return _auth_tokens.get(TENANT)


# ---------------------------------------------------------------------------
# User: read-heavy staff (70% of load)
# ---------------------------------------------------------------------------

class StaffReadUser(HttpUser):
    """
    Simulates a logged-in staff member navigating dashboards — mostly GETs.
    Weight 7: represents 70% of all simulated users.
    """
    weight = 7
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.token = _get_token(self.client)
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(4)
    def read_admissions_overview(self):
        self.client.get(
            "/api/v1/admissions/leads",
            headers=self.headers,
            name="/admissions/leads [list]",
            params={"limit": 20, "offset": 0},
        )

    @task(3)
    def read_finance_overview(self):
        self.client.get(
            "/api/v1/finance/invoices/summary",
            headers=self.headers,
            name="/finance/invoices/summary",
        )

    @task(3)
    def read_academics_courses(self):
        self.client.get(
            "/api/v1/academics/courses",
            headers=self.headers,
            name="/academics/courses [list]",
            params={"limit": 10},
        )

    @task(2)
    def read_hr_staff(self):
        self.client.get(
            "/api/v1/hr/staff",
            headers=self.headers,
            name="/hr/staff [list]",
            params={"limit": 20},
        )

    @task(2)
    def read_student_services_hostel(self):
        self.client.get(
            "/api/v1/students/hostel/occupancy",
            headers=self.headers,
            name="/students/hostel/occupancy",
        )

    @task(2)
    def read_reporting_dashboard(self):
        self.client.get(
            "/api/v1/reporting/dashboard",
            headers=self.headers,
            name="/reporting/dashboard",
        )

    @task(1)
    def read_health(self):
        self.client.get("/health", name="/health")

    @task(1)
    def read_notifications(self):
        self.client.get(
            "/api/v1/communication/notifications",
            headers=self.headers,
            name="/communication/notifications",
            params={"limit": 10, "unread_only": "true"},
        )


# ---------------------------------------------------------------------------
# User: admissions officer (20% of load) — creates leads + reads applications
# ---------------------------------------------------------------------------

class AdmissionsUser(HttpUser):
    """
    Simulates an admissions officer: creates leads, advances applications,
    reads merit lists.  Represents peak admissions workload.
    """
    weight = 2
    wait_time = between(1.0, 3.0)

    def on_start(self):
        self.token = _get_token(self.client)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        } if self.token else {}
        self._created_lead_ids: list[str] = []

    @task(3)
    def create_lead(self):
        payload = {
            "name": f"Load Test {uuid.uuid4().hex[:6]}",
            "email": _rand_email(),
            "phone": _rand_phone(),
            "intended_program": random.choice(PROGRAMS),
            "source_channel": random.choice(CHANNELS),
        }
        resp = self.client.post(
            "/api/v1/admissions/leads",
            json=payload,
            headers=self.headers,
            name="/admissions/leads [create]",
        )
        if resp.status_code in (200, 201):
            lead_id = resp.json().get("id") or resp.json().get("lead_id")
            if lead_id:
                self._created_lead_ids.append(lead_id)

    @task(2)
    def update_lead_status(self):
        if not self._created_lead_ids:
            return
        lead_id = random.choice(self._created_lead_ids)
        self.client.patch(
            f"/api/v1/admissions/leads/{lead_id}",
            json={"status": random.choice(LEAD_STATUS)},
            headers=self.headers,
            name="/admissions/leads/:id [update status]",
        )

    @task(2)
    def list_applications(self):
        self.client.get(
            "/api/v1/admissions/applications",
            headers=self.headers,
            name="/admissions/applications [list]",
            params={"limit": 10},
        )

    @task(1)
    def get_merit_list(self):
        self.client.get(
            "/api/v1/admissions/merit-list",
            headers=self.headers,
            name="/admissions/merit-list",
            params={"program": random.choice(PROGRAMS), "year": "2025-26"},
        )

    @task(1)
    def read_seat_matrix(self):
        self.client.get(
            "/api/v1/admissions/seat-matrix",
            headers=self.headers,
            name="/admissions/seat-matrix",
        )


# ---------------------------------------------------------------------------
# User: finance officer (10% of load) — reads invoices + records payments
# ---------------------------------------------------------------------------

class FinanceUser(HttpUser):
    """
    Simulates a finance officer: reads fee summaries, default-risk list,
    and posts payment reconciliations.
    """
    weight = 1
    wait_time = between(2.0, 5.0)

    def on_start(self):
        self.token = _get_token(self.client)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        } if self.token else {}

    @task(3)
    def read_pending_waivers(self):
        self.client.get(
            "/api/v1/finance/waivers",
            headers=self.headers,
            name="/finance/waivers [list]",
            params={"status": "PENDING"},
        )

    @task(2)
    def read_default_risk(self):
        self.client.get(
            "/api/v1/finance/default-risk",
            headers=self.headers,
            name="/finance/default-risk",
            params={"academic_year": "2024-25"},
        )

    @task(2)
    def read_collection_report(self):
        self.client.get(
            "/api/v1/finance/collection-report",
            headers=self.headers,
            name="/finance/collection-report",
            params={"academic_year": "2024-25"},
        )

    @task(1)
    def read_scholarships(self):
        self.client.get(
            "/api/v1/finance/scholarships",
            headers=self.headers,
            name="/finance/scholarships",
        )


# ---------------------------------------------------------------------------
# Event hooks — print SLO verdict after test run
# ---------------------------------------------------------------------------

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    stats = environment.stats
    total = stats.total
    if total.num_requests == 0:
        return
    p95 = total.get_response_time_percentile(0.95)
    err_rate = total.fail_ratio * 100
    print("\n" + "═" * 60)
    print("  ALIS LOAD TEST — SLO VERDICT")
    print("═" * 60)
    print(f"  Total requests : {total.num_requests:,}")
    print(f"  Total failures : {total.num_failures:,}")
    print(f"  Error rate     : {err_rate:.2f}%  (SLO: < 1%)")
    print(f"  p95 response   : {p95:.0f} ms  (SLO: < 2000 ms)")
    print(f"  RPS            : {total.total_rps:.1f}")
    slo_ok = (p95 < 2000) and (err_rate < 1.0)
    print(f"\n  {'✅ SLO PASSED' if slo_ok else '❌ SLO FAILED'}")
    print("═" * 60 + "\n")
    if not slo_ok and isinstance(environment.runner, MasterRunner):
        environment.process_exit_code = 1
