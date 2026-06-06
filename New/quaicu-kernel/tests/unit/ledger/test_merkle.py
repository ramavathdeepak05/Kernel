"""Unit tests for the RFC 6962 Merkle tree implementation (core/ledger/merkle.py).

Each test targets a specific cryptographic invariant. Failures here are specification violations,
not just implementation bugs.
"""

from __future__ import annotations

import hashlib

from core.ledger.merkle import (
    MerkleTree,
    compute_root,
    internal_hash,
    leaf_hash,
)


# ── Helper ────────────────────────────────────────────────────────────────────


def _build_tree(n: int) -> MerkleTree:
    """Build a MerkleTree with `n` distinct entries."""
    t = MerkleTree()
    for i in range(n):
        t.append(f"entry-{i}".encode())
    return t


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_leaf_hash_uses_0x00_domain_separator() -> None:
    data = b"x"
    expected = hashlib.sha256(b"\x00" + data).digest()
    assert leaf_hash(data) == expected


def test_internal_hash_uses_0x01_domain_separator() -> None:
    a = b"a" * 32
    b_ = b"b" * 32
    expected = hashlib.sha256(b"\x01" + a + b_).digest()
    assert internal_hash(a, b_) == expected


def test_empty_tree_root() -> None:
    t = MerkleTree()
    expected = hashlib.sha256(b"").digest()
    assert t.root() == expected


def test_single_leaf_root() -> None:
    entry = b"hello"
    t = MerkleTree()
    _, lh = t.append(entry)
    assert lh == leaf_hash(entry)
    assert t.root() == lh  # single-leaf MTH == the leaf hash itself


def test_single_leaf_inclusion_proof_is_empty() -> None:
    t = MerkleTree()
    t.append(b"only")
    proof = t.inclusion_proof(0)
    assert proof == []


def test_two_leaves_root() -> None:
    t = MerkleTree()
    _, lh0 = t.append(b"leaf0")
    _, lh1 = t.append(b"leaf1")
    expected = hashlib.sha256(b"\x01" + lh0 + lh1).digest()
    assert t.root() == expected


def test_inclusion_proof_verifies_for_all_leaves() -> None:
    for n in range(1, 9):
        t = _build_tree(n)
        root = t.root()
        for i in range(n):
            lh = t._leaves[i]
            proof = t.inclusion_proof(i)
            assert t.verify_inclusion(i, lh, proof, root), (
                f"inclusion proof failed for leaf {i} in tree of size {n}"
            )


def test_consistency_proof_verifies() -> None:
    t = _build_tree(8)
    old_leaves = list(t._leaves[:4])
    old_root = compute_root(old_leaves)
    new_root = t.root()
    proof = t.consistency_proof(4)
    assert t.verify_consistency(4, old_root, 8, new_root, proof)


def test_consistency_proof_detects_tamper() -> None:
    t = _build_tree(8)
    old_leaves = list(t._leaves[:4])
    old_root = compute_root(old_leaves)

    # Tamper: replace leaf 2 with a different hash.
    t._leaves[2] = hashlib.sha256(b"tampered").digest()
    new_root = t.root()
    proof = t.consistency_proof(4)

    # The original old_root no longer matches the tampered tree.
    assert not t.verify_consistency(4, old_root, 8, new_root, proof)


def test_append_only_grows_monotonically() -> None:
    t = MerkleTree()
    for i in range(5):
        assert t.size == i
        t.append(f"e{i}".encode())
    assert t.size == 5


def test_verify_inclusion_wrong_root_fails() -> None:
    t = _build_tree(4)
    lh = t._leaves[0]
    proof = t.inclusion_proof(0)
    bad_root = b"\xff" * 32
    assert not t.verify_inclusion(0, lh, proof, bad_root)


def test_verify_inclusion_wrong_leaf_fails() -> None:
    t = _build_tree(4)
    good_root = t.root()
    proof = t.inclusion_proof(0)
    bad_leaf = b"\x00" * 32
    assert not t.verify_inclusion(0, bad_leaf, proof, good_root)
