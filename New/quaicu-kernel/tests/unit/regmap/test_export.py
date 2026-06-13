"""Unit tests for the WS-F regulator ledger-proof export + its independent verifier."""

from __future__ import annotations

import pytest

from core.ledger.engine import TrustLedger
from core.regmap.export import build_ledger_proof_bundle, verify_ledger_proof_bundle
from core.types import (
    Action,
    ActionId,
    ActionState,
    Actor,
    ActorId,
    Decision,
    EvaluationResult,
    IdempotencyKey,
    TenantId,
)

TENANT = TenantId("ciro-bank")


def _action(n: int) -> Action:
    return Action(
        id=ActionId(f"act-{n}"),
        type="loan.approve",
        payload={"amount": n},
        actor=Actor(id=ActorId("alice"), tenant=TENANT, roles=("role:maker",)),
        tenant=TENANT,
        idempotency_key=IdempotencyKey(f"idem-{n}"),
        state=ActionState.SEALING,
    )


async def _ledger_with(n: int) -> TrustLedger:
    ledger = TrustLedger()
    for i in range(n):
        await ledger.seal(
            action=_action(i),
            evaluation=EvaluationResult(decision=Decision.ALLOW, policy_versions=("v1.0",)),
            recorded_result={},
        )
    return ledger


def _export(ledger: TrustLedger, **kwargs) -> dict:
    entries = ledger.get_entries(TENANT)
    entries_with_paths = [(e, ledger.get_inclusion_proof(TENANT, e.ledger_seq)[1]) for e in entries]
    bundle = build_ledger_proof_bundle(
        tenant_id=str(TENANT),
        window_start=entries[0].sealed_at,
        window_end=entries[-1].sealed_at,
        entries_with_paths=entries_with_paths,
        sth=ledger.get_signed_tree_head(TENANT),
        public_key_pem=ledger._signer.public_key_pem,  # type: ignore[attr-defined]
        regulation_refs=["rbi.ifrs9.staging"],
        policy_versions=["v1.0"],
        **kwargs,
    )
    return bundle.to_dict()


# ── Happy path ──────────────────────────────────────────────────────────────────


async def test_export_verifies_clean():
    ledger = await _ledger_with(5)
    bundle = _export(ledger)
    ok, errors = verify_ledger_proof_bundle(bundle)
    assert ok, errors
    assert len(bundle["inclusion_proofs"]) == 5
    assert bundle["evidence"]["verifiable"] is True
    assert bundle["evidence"]["manifest"]["action_count"] == 5


async def test_single_entry_export_verifies():
    ledger = await _ledger_with(1)
    ok, errors = verify_ledger_proof_bundle(_export(ledger))
    assert ok, errors


# ── Tamper detection ─────────────────────────────────────────────────────────────


async def test_tampered_leaf_fails_verification():
    ledger = await _ledger_with(4)
    bundle = _export(ledger)
    # Flip a byte in one leaf hash — the recomputed root no longer matches the signed root.
    bad = bundle["inclusion_proofs"][1]["leaf_hash_hex"]
    bundle["inclusion_proofs"][1]["leaf_hash_hex"] = ("f" if bad[0] != "f" else "0") + bad[1:]
    ok, errors = verify_ledger_proof_bundle(bundle)
    assert not ok
    assert any("does not match the signed root" in e for e in errors)


async def test_tampered_signature_fails_verification():
    ledger = await _ledger_with(3)
    bundle = _export(ledger)
    sig = bundle["signed_tree_head"]["signature_hex"]
    bundle["signed_tree_head"]["signature_hex"] = ("0" if sig[0] != "0" else "1") + sig[1:]
    ok, errors = verify_ledger_proof_bundle(bundle)
    assert not ok
    assert any("signature does not verify" in e for e in errors)


async def test_tampered_root_fails_verification():
    ledger = await _ledger_with(3)
    bundle = _export(ledger)
    root = bundle["signed_tree_head"]["root_hash_hex"]
    bundle["signed_tree_head"]["root_hash_hex"] = ("0" if root[0] != "0" else "1") + root[1:]
    ok, _ = verify_ledger_proof_bundle(bundle)
    assert not ok  # both the proofs and the signature now disagree with the altered root


async def test_missing_public_key_is_unverifiable():
    ledger = await _ledger_with(2)
    bundle = _export(ledger)
    bundle["signed_tree_head"]["public_key_pem"] = None
    ok, errors = verify_ledger_proof_bundle(bundle)
    assert not ok
    assert any("public key" in e for e in errors)


async def test_malformed_bundle_fails_gracefully():
    ok, errors = verify_ledger_proof_bundle({"nonsense": True})
    assert not ok
    assert errors
