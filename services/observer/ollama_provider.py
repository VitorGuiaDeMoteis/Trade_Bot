import json
import httpx
from datetime import datetime
from services.observer.provider import Identity, ModelProvider

class OllamaProvider(ModelProvider):
    def __init__(self, model: str = "qwen2.5-coder:7b", base_url: str = "http://127.0.0.1:11434") -> None:
        self.identity = Identity("ollama", model, "latest")
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def generate(self, snapshot: bytes, prompt: str) -> bytes:
        # prompt and snapshot usually combined?
        # Let's check how the M5 engine sends it.
        # usually snapshot + "\n" + prompt.
        content = snapshot.decode("utf-8") + "\n\n" + prompt
        
        request_data = {
            "model": self.identity.model,
            "prompt": content,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0
            }
        }
        try:
            resp = await self.client.post(f"{self.base_url}/api/generate", json=request_data)
            resp.raise_for_status()
            data = resp.json()
            return data["response"].encode("utf-8")
        except httpx.TimeoutException:
            raise TimeoutError("ollama_timeout")
        except Exception as e:
            raise RuntimeError(f"ollama_error: {e}")
            
    async def close(self):
        await self.client.aclose()
