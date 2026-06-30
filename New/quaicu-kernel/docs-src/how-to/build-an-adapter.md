# Build an Adapter

The kernel uses hexagonal architecture, every external dependency is accessed through a Port interface. Adding a new model provider, storage backend, or signing service means writing one adapter file. Zero core changes.

## The hexagonal rule

Core imports zero concrete libraries. Adapters import the concrete library and implement the port.

```
core/ports/inference.py     ← the interface (never changes)
adapters/inference/ollama.py ← implements InferencePort (the only place Ollama is imported)
```

## Example: Implementing InferencePort

```python
# adapters/inference/my_provider.py
from core.ports.inference import InferencePort, ModelRef, ModelResponse

class MyProviderAdapter(InferencePort):
    def __init__(self, api_key: str, base_url: str):
        self._client = MyProviderClient(api_key=api_key, base_url=base_url)

    async def generate(
        self,
        model: ModelRef,
        prompt: str,
        *,
        tenant_id: str,
        max_tokens: int = 2048,
    ) -> ModelResponse:
        raw = await self._client.complete(
            model=model.name,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        return ModelResponse(
            text=raw.text,
            model=model,
            prompt_tokens=raw.usage.prompt_tokens,
            completion_tokens=raw.usage.completion_tokens,
        )
```

## Wire it in `kernel.toml`

```toml
[inference]
adapter = "my_provider"
api_key = "${MY_PROVIDER_API_KEY}"
base_url = "https://api.myprovider.com/v1"
```

## Available ports

| Port | File | Purpose |
|------|------|---------|
| `InferencePort` | `core/ports/inference.py` | LLM generation |
| `StoragePort` | `core/ports/storage.py` | Database access |
| `IdentityPort` | `core/ports/identity.py` | Actor resolution |
| `WorkflowPort` | `core/ports/workflow.py` | Durable execution |
| `HITLPort` | `core/ports/hitl.py` | Human approval routing |
| `ConsentPort` | `core/ports/consent.py` | Consent verification |
| `EventBusPort` | `core/ports/events.py` | Event emission |
