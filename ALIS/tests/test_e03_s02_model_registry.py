"""
E03-S02 Verification Test: Local LLM Runtime Integration

Tests:
1. Import integrity — all new symbols importable
2. ModelRegistry unit logic — register, get_active, hot-swap
3. AIGateway signature accepts capability parameter
4. DB schema — the DDL string exists in init_db
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} — {detail}")


# =========================================================================
# TEST 1: Import Integrity
# =========================================================================
print("\n=== TEST 1: Import Integrity ===")

try:
    from server.core.model_registry import (
        ModelRegistry,
        ModelCapability,
        ModelStatus,
        LLMModelRead,
        LLMModelRegister,
        ResolvedModel,
    )
    check("model_registry imports", True)
except ImportError as e:
    check("model_registry imports", False, str(e))

try:
    from server.core.ai_gateway import AIGateway, AIGatewayContext
    check("ai_gateway imports", True)
except ImportError as e:
    check("ai_gateway imports", False, str(e))

# =========================================================================
# TEST 2: ModelCapability enum values
# =========================================================================
print("\n=== TEST 2: ModelCapability Enum ===")
check("Infer exists", ModelCapability.INFER.value == "Infer")
check("Score exists", ModelCapability.SCORE.value == "Score")
check("Plan exists", ModelCapability.PLAN.value == "Plan")
check("Execute exists", ModelCapability.EXECUTE.value == "Execute")

# =========================================================================
# TEST 3: Pydantic schemas
# =========================================================================
print("\n=== TEST 3: Pydantic Schemas ===")

try:
    reg = LLMModelRegister(
        name="qwen",
        version="1.5-q8",
        capability=ModelCapability.INFER,
        is_active=True,
    )
    check("LLMModelRegister valid", reg.name == "qwen")
except Exception as e:
    check("LLMModelRegister valid", False, str(e))

try:
    LLMModelRegister(name="", version="1.0", capability=ModelCapability.INFER)
    check("LLMModelRegister rejects empty name", False, "Should have raised")
except Exception:
    check("LLMModelRegister rejects empty name", True)

# =========================================================================
# TEST 4: ResolvedModel + ollama tag
# =========================================================================
print("\n=== TEST 4: ResolvedModel ===")
tag = ModelRegistry._format_ollama_tag("qwen", "1.5-q8")
check("ollama_tag format", tag == "qwen:1.5-q8", f"got '{tag}'")

rm = ResolvedModel(
    id="test-id",
    name="qwen",
    version="1.5-q8",
    capability="Infer",
    ollama_model_tag="qwen:1.5-q8",
    config={"temperature": 0.0},
)
check("ResolvedModel construction", rm.ollama_model_tag == "qwen:1.5-q8")

# =========================================================================
# TEST 5: AIGateway.get_llm accepts capability param
# =========================================================================
print("\n=== TEST 5: AIGateway.get_llm Signature ===")
import inspect

sig = inspect.signature(AIGateway.get_llm)
params = list(sig.parameters.keys())
check("capability in get_llm params", "capability" in params, f"params: {params}")
check("model_name still available", "model_name" in params)

# =========================================================================
# TEST 6: DB schema DDL present
# =========================================================================
print("\n=== TEST 6: DB Schema DDL ===")
db_service_path = os.path.join(
    os.path.dirname(__file__), "..", "server", "db_service.py"
)
with open(db_service_path, "r") as f:
    db_src = f.read()

check("llm_model_registry table DDL", "llm_model_registry" in db_src)
check("uq_llm_model_active_capability index", "uq_llm_model_active_capability" in db_src)
check("seed-qwen-infer seed row", "seed-qwen-infer" in db_src)
check("RLS policy present", "tenant_isolation_llm_models" in db_src)

# =========================================================================
# TEST 7: No cloud imports
# =========================================================================
print("\n=== TEST 7: No Cloud Imports ===")
model_reg_path = os.path.join(
    os.path.dirname(__file__), "..", "server", "core", "model_registry.py"
)
with open(model_reg_path, "r") as f:
    mr_src = f.read()

check("No openai import", "openai" not in mr_src)
check("No anthropic import", "anthropic" not in mr_src)

# =========================================================================
# SUMMARY
# =========================================================================
print(f"\n{'='*50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL} checks")
print(f"{'='*50}")

sys.exit(0 if FAIL == 0 else 1)
