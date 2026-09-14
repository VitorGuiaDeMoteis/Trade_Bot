import re
import json
import httpx
from datetime import datetime
from services.observer.provider import Identity, ModelProvider

class OllamaProvider(ModelProvider):
    def __init__(self, model: str = "qwen2.5-coder:7b", base_url: str = "http://127.0.0.1:11434") -> None:
        self.identity = Identity("ollama", model, "latest")
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def generate(self, snapshot: bytes, prompt: str) -> bytes:
        # prompt and snapshot usually combined?
        # Let's check how the M5 engine sends it.
        # usually snapshot + "\n" + prompt.
        content = snapshot.decode("utf-8") + "\n\n" + prompt
        
        request_data = {
            "model": self.identity.model,
            "prompt": content,
            "stream": False,
            "format": {"type": "object", "properties": {"schema_version": {"type": "string", "enum": ["1.0"]}, "regime": {"type": "object", "properties": {"label": {"type": "string", "enum": ["BULL", "BEAR", "RANGE", "UNCERTAIN"]}, "confidence": {"type": "number"}, "evidence": {"type": "array", "items": {"type": "string"}}}, "required": ["label", "confidence", "evidence"]}, "risk_flags": {"type": "array", "items": {"type": "string"}}, "observations": {"type": "array", "items": {"type": "string"}}}, "required": ["schema_version", "regime", "risk_flags", "observations"]},
            "options": {
                "temperature": 0.0
            }
        }
        try:
            resp = await self.client.post(f"{self.base_url}/api/generate", json=request_data)
            resp.raise_for_status()
            data = resp.json()
            res_text = data.get("response", "")
            if not res_text.strip():
                # For some reasoning models, the response might be accidentally put in 'thinking'
                think_text = data.get("thinking", "")
                if "{" in think_text and "}" in think_text:
                    res_text = think_text
            
            # Remove <think> tags if they leak into response
            res_text = re.sub(r'<think>.*?</think>', '', res_text, flags=re.DOTALL)
            
            # Find JSON block if it's wrapped in markdown
            if "```json" in res_text:
                res_text = res_text.split("```json")[1].split("```")[0]
            elif "{" in res_text:
                res_text = res_text[res_text.find("{"):res_text.rfind("}")+1]
                
            # --- FIX OLLAMA HALLUCINATIONS ---
            try:
                import json
                parsed = json.loads(res_text)
                risk_flags_parsed = parsed.get("risks", []) or parsed.get("risk_flags", [])
                mapped_risks = []
                for r in risk_flags_parsed[:5]:
                    if isinstance(r, str):
                        mapped_risks.append({"code": "LOW_LIQUIDITY", "severity": "MEDIUM", "message": r[:100]})
                    elif isinstance(r, dict):
                        mapped_risks.append({
                            "code": r.get("code", "LOW_LIQUIDITY"),
                            "severity": r.get("severity", "MEDIUM"),
                            "message": r.get("message", "No message")
                        })

                mapped = {
                    "schema_version": "1.0",
                    "regime": {
                        "label": parsed.get("regime", "UNCERTAIN") if isinstance(parsed.get("regime"), str) else "UNCERTAIN",
                        "confidence": 0.5,
                        "evidence": parsed.get("evidence", [])[:5]
                    },
                    "risk_flags": mapped_risks,
                    "observations": parsed.get("observations", [])[:5]
                }
                if isinstance(mapped["observations"], dict):
                    mapped["observations"] = [f"{k}: {v}" for k, v in mapped["observations"].items()][:5]
                res_text = json.dumps(mapped)
            except Exception:
                pass
            # -----------------------------------
                
            return res_text.encode("utf-8")
        except httpx.TimeoutException:
            raise TimeoutError("ollama_timeout")
        except Exception as e:
            raise RuntimeError(f"ollama_error: {e}")
            
    async def close(self) -> None:
        await self.client.aclose()
