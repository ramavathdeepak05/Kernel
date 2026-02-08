
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from server.core.exceptions import (
    GlobalLockViolationError,
    PermissionDeniedError,
    BusinessRuleViolation
)
from server.core.error_handlers import register_exception_handlers

# Mock App
app = FastAPI()
register_exception_handlers(app)

@app.get("/trigger/lock")
def trigger_lock():
    raise GlobalLockViolationError(
        violations=["DUES_PENDING", "ATTENDANCE_SHORT"],
        details={"student_id": "ST123"}
    )

@app.get("/trigger/auth")
def trigger_auth():
    raise PermissionDeniedError(
        message="User does not have required role",
        details={"required": "admin", "actual": "student"}
    )

@app.get("/trigger/rule")
def trigger_rule():
    raise BusinessRuleViolation(
        message="Age cannot be less than 18"
    )

client = TestClient(app)

def test_global_lock_error():
    response = client.get("/trigger/lock")
    assert response.status_code == 423
    data = response.json()
    assert data["status"] == "error"
    assert data["code"] == "ERR_LAYER4_LOCK"
    assert "DUES_PENDING" in data["message"]
    assert data["details"]["student_id"] == "ST123"
    print("\n[PASS] Global Lock Error Test")

def test_permission_error():
    response = client.get("/trigger/auth")
    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"
    assert data["code"] == "ERR_LAYER5_ACCESS"
    print("\n[PASS] Permission Error Test")

def test_business_rule_error():
    response = client.get("/trigger/rule")
    assert response.status_code == 422
    data = response.json()
    assert data["status"] == "error"
    assert data["code"] == "ERR_LAYER2_RULE"
    print("\n[PASS] Business Rule Error Test")

if __name__ == "__main__":
    test_global_lock_error()
    test_permission_error()
    test_business_rule_error()
