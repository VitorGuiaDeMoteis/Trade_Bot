"""Hermetic fake model. Image contains no repository package, tools, credentials or SDK."""

import json
import sys
from pathlib import Path

prompt = Path("/opt/observer/prompt.txt").read_text()
snapshot = json.loads(sys.stdin.buffer.read(65537))
assert snapshot["schema_version"] == "1.0" and "observador" in prompt
print(
    json.dumps(
        {
            "schema_version": "1.0",
            "regime": {"label": "UNCERTAIN", "confidence": 0.0, "evidence": []},
            "risk_flags": [],
            "observations": ["Provider isolado determinístico. Sem inferência de mercado."],
        }
    )
)
