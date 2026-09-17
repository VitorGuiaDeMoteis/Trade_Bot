from decimal import Decimal
from uuid import uuid4
from sqlalchemy import text
from services.api.database import create_database_engine
from services.api.config import Settings
from services.api.models import paper_orders

def test_fractional_persistence():
    engine = create_database_engine(Settings())
    order_id = str(uuid4())
    run_id = str(uuid4())
    signal_id = str(uuid4())
    decision_id = str(uuid4())
    
    qty = Decimal("0.0302312345")
    
    with engine.begin() as conn:
        conn.execute(text("SET session_replication_role = replica;"))
        
        conn.execute(text("""
            INSERT INTO paper_orders (order_id, run_id, signal_id, risk_decision_id, symbol, side, quantity, filled_quantity, status, requested_at, idempotency_key, reason)
            VALUES (:order_id, :run_id, :signal_id, :decision_id, 'AAPL', 'BUY', :qty, :qty, 'FILLED', now(), :order_id, 'test')
        """), {
            "order_id": order_id, "run_id": run_id, "signal_id": signal_id,
            "decision_id": decision_id, "qty": qty
        })
        
        row = conn.execute(text("SELECT quantity FROM paper_orders WHERE order_id = :order_id"), {"order_id": order_id}).scalar()
        
        conn.execute(text("SET session_replication_role = DEFAULT;"))
        # We can rollback to keep DB clean
        conn.execute(text("ROLLBACK;"))
        
        assert row == qty, f"Expected {qty}, got {row}"

def test_fractional_downgrade_blocked():
    from alembic.config import Config
    from alembic import command
    engine = create_database_engine(Settings())
    order_id = str(uuid4())
    run_id = str(uuid4())
    signal_id = str(uuid4())
    decision_id = str(uuid4())
    
    qty = Decimal("0.0302312345")
    
    # Pre-upgrade to head if not already
    config = Config("alembic.ini")
    command.upgrade(config, "head")

    with engine.begin() as conn:
        conn.execute(text("SET session_replication_role = replica;"))
        conn.execute(text("""
            INSERT INTO paper_orders (order_id, run_id, signal_id, risk_decision_id, symbol, side, quantity, filled_quantity, status, requested_at, idempotency_key, reason)
            VALUES (:order_id, :run_id, :signal_id, :decision_id, 'AAPL', 'BUY', :qty, :qty, 'FILLED', now(), :order_id, 'test')
        """), {
            "order_id": order_id, "run_id": run_id, "signal_id": signal_id,
            "decision_id": decision_id, "qty": qty
        })
        conn.execute(text("SET session_replication_role = DEFAULT;"))

    try:
        import pytest
        with pytest.raises(Exception) as excinfo:
            command.downgrade(config, "db6f20ef0e19") # Try to downgrade the fractional migration
        
        error_msg = str(excinfo.value).lower()
        assert "constraint" in error_msg or "fractional" in error_msg or "paper_data_present" in error_msg, f"Unexpected error: {error_msg}"

            
        with engine.begin() as conn:
            # Dado original não deve ser truncado
            row = conn.execute(text("SELECT quantity FROM paper_orders WHERE order_id = :order_id"), {"order_id": order_id}).scalar()
            assert row == qty
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM paper_orders WHERE order_id = :order_id"), {"order_id": order_id})
