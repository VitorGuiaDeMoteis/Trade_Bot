from services.api.database import create_database_engine
from services.api.config import Settings
from sqlalchemy import text
import json
e = create_database_engine(Settings())
with e.connect() as c:
    res = c.execute(text("SELECT provider, latency_ms, status, validated_output FROM observer_analysis_runs ORDER BY created_at DESC LIMIT 5")).fetchall()
    for r in res:
        print(f"Provider: {r[0]}, Latency: {r[1]}, Status: {r[2]}")
        print(json.dumps(r[3], indent=2))
