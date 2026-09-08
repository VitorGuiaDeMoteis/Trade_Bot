
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

# Assuming alembic.ini is in the root and we are running tests from root.
ALEMBIC_INI_PATH = "alembic.ini"

# Using clean_db_for_migrations from conftest.py

def get_schema_summary(engine):
    inspector = sa.inspect(engine)
    summary = {}
    for table_name in sorted(inspector.get_table_names()):
        table_info = {"columns": {}, "unique_constraints": [], "check_constraints": [], "foreign_keys": []}
        for col in sorted(inspector.get_columns(table_name), key=lambda x: x["name"]):
            table_info["columns"][col["name"]] = str(col["type"])
        
        for uq in sorted(inspector.get_unique_constraints(table_name), key=lambda x: x["name"] if x["name"] else ""):
            table_info["unique_constraints"].append((uq["name"], tuple(sorted(uq["column_names"]))))
            
        for ck in sorted(inspector.get_check_constraints(table_name), key=lambda x: x["name"] if x["name"] else ""):
            table_info["check_constraints"].append(ck["name"])
            
        for fk in sorted(inspector.get_foreign_keys(table_name), key=lambda x: x["name"] if x["name"] else ""):
            table_info["foreign_keys"].append((fk["name"], tuple(sorted(fk["constrained_columns"]))))
            
        summary[table_name] = table_info
    return summary

def run_alembic(target="head"):
    alembic_cfg = Config(ALEMBIC_INI_PATH)
    command.upgrade(alembic_cfg, target)

def test_migration_fresh(clean_db_for_migrations):
    run_alembic("head")
    summary = get_schema_summary(clean_db_for_migrations)
    assert "live_paper_control" in summary
    assert summary["broker_orders"]["columns"]["requested_qty"].startswith("BIGINT")

def test_migration_historical_to_head(clean_db_for_migrations):
    # 1. Migrate to 002ad
    run_alembic("002ad6ee70d8")
    
    # 2. Migrate to head
    run_alembic("head")
    summary_historical = get_schema_summary(clean_db_for_migrations)
    
    # Compare with fresh
    with clean_db_for_migrations.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    run_alembic("head")
    summary_fresh = get_schema_summary(clean_db_for_migrations)
    
    assert summary_historical == summary_fresh

def test_migration_mutated_to_head(clean_db_for_migrations):
    # 1. Migrate to 002ad
    run_alembic("002ad6ee70d8")
    
    # 2. Manually mutate DB to simulate the old 002ad state
    with clean_db_for_migrations.begin() as conn:
        conn.execute(sa.text('''
            ALTER TABLE live_paper_control ALTER COLUMN control_id TYPE BIGINT;
            ALTER TABLE broker_orders ALTER COLUMN requested_qty TYPE BIGINT;
            ALTER TABLE broker_orders ALTER COLUMN filled_qty TYPE BIGINT;
            ALTER TABLE broker_fills ALTER COLUMN qty TYPE BIGINT;
        '''))
        conn.execute(sa.text('''
            ALTER TABLE broker_orders ADD CONSTRAINT uq_broker_order_risk_decision UNIQUE (risk_decision_id);
            ALTER TABLE broker_orders ADD CONSTRAINT ck_broker_orders_side CHECK (side IN ('BUY', 'SELL'));
            ALTER TABLE broker_orders ADD CONSTRAINT ck_broker_orders_timeframe CHECK (timeframe = '15m');
        '''))
        # Emulate the new constraint being already there (though 002ad already adds it, it's just an example of what might have happened)
        # Actually 002ad historical already dropped ck_candles_hour and added ck_candles_timeframe_duration
        # So we don't need to do it here again.

    # 3. Migrate to head
    run_alembic("head")
    summary_mutated = get_schema_summary(clean_db_for_migrations)
    
    # Compare with fresh
    with clean_db_for_migrations.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    run_alembic("head")
    summary_fresh = get_schema_summary(clean_db_for_migrations)
    
    assert summary_mutated == summary_fresh
