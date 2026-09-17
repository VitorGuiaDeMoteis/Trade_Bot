"""Compatibility entry point for the canonical Paper V1 preflight."""

import asyncio
import json

from scripts.paper_ops import run_preflight

if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_preflight(False)), indent=2, default=str))
