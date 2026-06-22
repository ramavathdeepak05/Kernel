"""Starter policy packs — ready-made CEL rule sets shipped under ``docs/policy-packs/``.

Each pack is a directory with a ``policies.toml`` of ``[[policy.seed]]`` entries (the same format
the kernel seeds at boot). The console lets a tenant *import* a pack: every entry is registered as a
DRAFT policy the tenant then backtests + activates through the normal lifecycle — so adopting a
regulatory baseline is two clicks instead of hand-authoring CEL.

The packs ship as repo files (the runtime image bundles the tree), so this module discovers them at
the documented path. Display metadata (human name + regulation) lives in ``_META``; a pack directory
without an entry still works, falling back to its directory name.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

# core/policy/packs.py → parents[2] is the package root (alongside docs/).
PACKS_DIR = Path(__file__).resolve().parents[2] / "docs" / "policy-packs"

# pack id (directory name) → (display name, regulation, one-line description)
_META: dict[str, tuple[str, str, str]] = {
    "dpdp": (
        "India DPDP Act 2023",
        "Digital Personal Data Protection Act, 2023",
        "Consent, purpose-limitation, erasure, and cross-border transfer controls for personal data.",
    ),
    "eu-ai-act": (
        "EU AI Act",
        "Regulation (EU) 2024/1689",
        "Prohibited-practice, high-risk human-oversight, and AI transparency/disclosure controls.",
    ),
}


@dataclass(frozen=True)
class PackPolicy:
    id: str
    governs: str
    condition: str
    decision: str
    approvers: tuple[str, ...]
    regulatory_refs: tuple[str, ...]


@dataclass(frozen=True)
class PolicyPack:
    id: str
    name: str
    regulation: str
    description: str
    policies: tuple[PackPolicy, ...]

    @property
    def action_types(self) -> tuple[str, ...]:
        """Distinct ``governs`` action types, in first-seen order."""
        seen: list[str] = []
        for p in self.policies:
            if p.governs not in seen:
                seen.append(p.governs)
        return tuple(seen)


def _load_dir(pack_id: str, path: Path) -> PolicyPack | None:
    toml_path = path / "policies.toml"
    if not toml_path.is_file():
        return None
    cfg = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    seeds = cfg.get("policy", {}).get("seed", [])
    policies = tuple(
        PackPolicy(
            id=str(s["id"]),
            governs=str(s["governs"]),
            condition=str(s["condition"]),
            decision=str(s["decision"]),
            approvers=tuple(str(a) for a in (s.get("approvers") or [])),
            regulatory_refs=tuple(str(r) for r in (s.get("regulatory_refs") or [])),
        )
        for s in seeds
        if "id" in s and "governs" in s and "condition" in s and "decision" in s
    )
    if not policies:
        return None
    name, regulation, description = _META.get(pack_id, (pack_id, "", ""))
    return PolicyPack(
        id=pack_id, name=name, regulation=regulation, description=description, policies=policies
    )


def list_packs() -> list[PolicyPack]:
    """All packs discovered under ``PACKS_DIR``, sorted by id. Empty if the dir is absent."""
    if not PACKS_DIR.is_dir():
        return []
    packs: list[PolicyPack] = []
    for child in sorted(PACKS_DIR.iterdir()):
        if child.is_dir():
            pack = _load_dir(child.name, child)
            if pack is not None:
                packs.append(pack)
    return packs


def get_pack(pack_id: str) -> PolicyPack | None:
    """Load a single pack by id (directory name), or None if absent/empty."""
    path = PACKS_DIR / pack_id
    if not path.is_dir():
        return None
    return _load_dir(pack_id, path)
