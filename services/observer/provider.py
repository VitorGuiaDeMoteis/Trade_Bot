"""Only trusted fake code executes in-process. Real model adapters must use isolation."""

from dataclasses import dataclass
from typing import Protocol

from packages.contracts.observer import canonical


@dataclass(frozen=True)
class Identity:
    provider: str
    model: str
    model_version: str
    image_digest: str | None = None


class ModelProvider(Protocol):
    identity: Identity

    async def generate(self, snapshot: bytes, prompt: str) -> bytes: ...


class FakeProvider:
    identity = Identity("fake", "deterministic-observer", "1")

    async def generate(self, snapshot: bytes, prompt: str) -> bytes:
        return canonical(
            {
                "schema_version": "1.0",
                "regime": {"label": "UNCERTAIN", "confidence": 0.0, "evidence": []},
                "risk_flags": [],
                "observations": ["Resposta determinística de teste. Sem inferência de mercado."],
            }
        )
