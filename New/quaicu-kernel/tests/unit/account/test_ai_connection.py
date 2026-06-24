"""AI-gateway BYO connection storage on the account engine — encrypt round-trip + masking."""

from __future__ import annotations

from core.account import AccountEngine, AccountStore
from core.entitlements import EntitlementStore


def _engine(pepper: str = "pepper-xyz") -> AccountEngine:
    return AccountEngine(AccountStore(), EntitlementStore(), pepper=pepper)


def test_set_get_roundtrip_decrypts_key():
    eng = _engine()
    acct, _ = eng.signup(email="a@b.io", name="Acme")
    eng.set_ai_connection(
        acct.tenant_id, provider="openai", base_url="https://api.openai.com/v1/",
        api_key="sk-secret-123", default_model="gpt-4o",
    )
    conn = eng.get_ai_connection(acct.tenant_id)
    assert conn is not None
    assert conn.api_key == "sk-secret-123"          # decrypted
    assert conn.base_url == "https://api.openai.com/v1"  # trailing slash stripped
    assert conn.default_model == "gpt-4o"


def test_status_is_masked_and_never_leaks_key():
    eng = _engine()
    acct, _ = eng.signup(email="a@b.io", name="Acme")
    eng.set_ai_connection(acct.tenant_id, provider="openai", base_url="https://x/v1", api_key="sk-abcd1234")
    status = eng.ai_connection_status(acct.tenant_id)
    assert status["connected"] is True
    assert status["key_hint"].endswith("1234")
    assert "sk-abcd1234" not in str(status)


def test_vertex_roundtrips_project_location_and_masks_sa_json():
    eng = _engine()
    acct, _ = eng.signup(email="a@b.io", name="Acme")
    sa = '{"client_email": "svc@proj.iam", "type": "service_account", "private_key": "SECRET"}'
    eng.set_ai_connection(
        acct.tenant_id, provider="vertex", base_url="", api_key=sa,
        default_model="google/gemini-2.0-flash-001", project="proj", location="us-central1",
    )
    conn = eng.get_ai_connection(acct.tenant_id)
    assert conn.provider == "vertex" and conn.project == "proj" and conn.location == "us-central1"
    assert conn.api_key == sa  # SA JSON decrypts back for the outbound call
    status = eng.ai_connection_status(acct.tenant_id)
    assert status["project"] == "proj" and status["location"] == "us-central1"
    assert "SECRET" not in str(status)  # the SA JSON (private key) never leaks in status


def test_bedrock_roundtrips_aws_fields_and_masks_secret():
    eng = _engine()
    acct, _ = eng.signup(email="a@b.io", name="Acme")
    eng.set_ai_connection(
        acct.tenant_id, provider="bedrock", base_url="", api_key="aws-secret-xyz",
        default_model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        location="us-east-1", aws_access_key_id="AKIAEXAMPLE",
    )
    conn = eng.get_ai_connection(acct.tenant_id)
    assert conn.provider == "bedrock" and conn.location == "us-east-1"
    assert conn.aws_access_key_id == "AKIAEXAMPLE"
    assert conn.api_key == "aws-secret-xyz"  # secret decrypts for the call
    status = eng.ai_connection_status(acct.tenant_id)
    assert status["aws_access_key_id"] == "AKIAEXAMPLE" and status["location"] == "us-east-1"
    assert "aws-secret-xyz" not in str(status)  # the secret access key never leaks


def test_unset_connection_is_none():
    eng = _engine()
    acct, _ = eng.signup(email="a@b.io", name="Acme")
    assert eng.get_ai_connection(acct.tenant_id) is None
    assert eng.ai_connection_status(acct.tenant_id) is None


def test_clear_removes_connection():
    eng = _engine()
    acct, _ = eng.signup(email="a@b.io", name="Acme")
    eng.set_ai_connection(acct.tenant_id, provider="openai", base_url="https://x/v1", api_key="sk-1")
    assert eng.clear_ai_connection(acct.tenant_id) is True
    assert eng.get_ai_connection(acct.tenant_id) is None
    assert eng.clear_ai_connection(acct.tenant_id) is False  # idempotent


def test_key_not_decryptable_under_a_different_pepper():
    """The at-rest key is bound to the server pepper — a different pepper cannot read it."""
    store = AccountStore()
    eng_a = AccountEngine(store, EntitlementStore(), pepper="pepper-a")
    acct, _ = eng_a.signup(email="a@b.io", name="Acme")
    eng_a.set_ai_connection(acct.tenant_id, provider="openai", base_url="https://x/v1", api_key="sk-secret")

    eng_b = AccountEngine(store, EntitlementStore(), pepper="pepper-b")
    try:
        eng_b.get_ai_connection(acct.tenant_id)
        raised = False
    except ValueError:
        raised = True
    assert raised
