import sys
import asyncio
from scripts.night_lab import main
sys.argv = ["night_lab.py", "--dataset", "services/replay/data/spy-history.json", "--model", "qwen3:4b"]
if __name__ == "__main__":
    asyncio.run(main())
