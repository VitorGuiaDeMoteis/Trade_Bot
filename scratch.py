with open("services/api/live_paper_runtime.py", encoding="utf-8") as f:
    text = f.read()

# Fix __init__
text = text.replace(
    "def __init__(self, broker: ExternalBroker, engine, symbol: str):",
    "def __init__(self, broker: ExternalBroker, engine, symbols: list[str]):",
)
text = text.replace("self.symbol = symbol", "self.symbols = symbols")

# Fix _process_pending symbols property error
# Wait, I already changed it to loop over self.symbols, but earlier I restored the file!
# If I restored it, it's currently back to using self.symbol and the OLD _process_pending!!
# Let's completely rewrite it again cleanly.
