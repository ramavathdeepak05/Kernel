"""ALIS Load Test — Locust scenarios

Targets:
  Normal load: 200 concurrent users, p95 < 500ms, error < 0.5%
  Result day:  2000 concurrent users, p95 < 2s, error < 1%

Run:
  locust -f infra/loadtest/locustfile.py --host http://localhost:8000
  locust -f infra/loadtest/locustfile.py --users 200 --spawn-rate 20 --run-time 2m --headless
"""

from locust import HttpUser, task, between, events
import json, random, string

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _random_suffix():
    return ''.join(random.choices(string.ascii_lowercase, k=6))


class ALISBaseUser(HttpUser):
    """Base class: handles login + auth token storage."""
    abstract = True
    token: str = ""
    org_id: str = ""

    def on_start(self):
        """Login and store JWT token."""
        resp = self.client.post("/api/v1/auth/login", json={
            "email": self.login_email,
            "password": self.login_password,
        })
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("access_token", "")
            self.org_id = data.get("org_id", "")
        else:
            self.token = ""

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}


# ---------------------------------------------------------------------------
# Registrar user — administrative read-heavy operations
# ---------------------------------------------------------------------------

class RegistrarUser(ALISBaseUser):
    """Simulates a registrar doing dashboard reads and student lookups."""
    wait_time = between(1, 3)
    login_email = "registrar@test.alis.local"
    login_password = "TestPass123!"

    @task(3)
    def dashboard_pipeline_summary(self):
        with self.client.get(
            "/api/v1/admissions/pipeline-summary",
            headers=self.auth_headers(),
            catch_response=True,
            name="/admissions/pipeline-summary"
        ) as resp:
            if resp.status_code not in (200, 401, 404):
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(2)
    def list_students(self):
        with self.client.get(
            "/api/v1/admissions/students?limit=20",
            headers=self.auth_headers(),
            catch_response=True,
            name="/admissions/students"
        ) as resp:
            if resp.status_code not in (200, 401, 404):
                resp.failure(f"Unexpected {resp.status_code}")

    @task(2)
    def list_pending_approvals(self):
        self.client.get(
            "/api/v1/approvals/pending",
            headers=self.auth_headers(),
            name="/approvals/pending"
        )

    @task(1)
    def finance_reports(self):
        self.client.get(
            "/api/v1/finance/reports/collection",
            headers=self.auth_headers(),
            name="/finance/reports/collection"
        )

    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health")


# ---------------------------------------------------------------------------
# Student user — result-day read burst
# ---------------------------------------------------------------------------

class StudentUser(ALISBaseUser):
    """Simulates students checking grades on result day."""
    wait_time = between(0.5, 2)
    login_email = "student@test.alis.local"
    login_password = "TestPass123!"

    @task(5)
    def check_results(self):
        with self.client.get(
            "/api/v1/examinations/results",
            headers=self.auth_headers(),
            catch_response=True,
            name="/examinations/results"
        ) as resp:
            if resp.status_code not in (200, 401, 404):
                resp.failure(f"Unexpected {resp.status_code}")

    @task(3)
    def check_attendance(self):
        self.client.get(
            "/api/v1/academics/attendance/my",
            headers=self.auth_headers(),
            name="/academics/attendance/my"
        )

    @task(2)
    def check_dues(self):
        self.client.get(
            "/api/v1/finance/invoices/my",
            headers=self.auth_headers(),
            name="/finance/invoices/my"
        )

    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health")


# ---------------------------------------------------------------------------
# Faculty user — grade entry and attendance marking
# ---------------------------------------------------------------------------

class FacultyUser(ALISBaseUser):
    """Simulates faculty entering attendance and marks."""
    wait_time = between(2, 5)
    login_email = "faculty@test.alis.local"
    login_password = "TestPass123!"

    @task(3)
    def view_course_list(self):
        self.client.get(
            "/api/v1/academics/courses/my",
            headers=self.auth_headers(),
            name="/academics/courses/my"
        )

    @task(2)
    def view_pending_assessments(self):
        self.client.get(
            "/api/v1/academics/assessments/pending",
            headers=self.auth_headers(),
            name="/academics/assessments/pending"
        )

    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health")


# ---------------------------------------------------------------------------
# Event hooks — summary reporting
# ---------------------------------------------------------------------------

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    stats = environment.stats
    total = stats.total
    print(f"\n=== ALIS Load Test Summary ===")
    print(f"Total requests:    {total.num_requests}")
    print(f"Failures:          {total.num_failures}")
    print(f"Failure rate:      {total.fail_ratio * 100:.2f}%")
    print(f"Median latency:    {total.median_response_time}ms")
    print(f"p95 latency:       {total.get_response_time_percentile(0.95)}ms")
    print(f"p99 latency:       {total.get_response_time_percentile(0.99)}ms")
    print(f"RPS:               {total.current_rps:.1f}")
    pass
