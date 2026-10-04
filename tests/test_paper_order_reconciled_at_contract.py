"""The ALPACA_PAPER order list must never publish a NULL `last_reconciled_at`.

Paper observation showed `latest_orders[*].last_reconciled_at: null` on every
ALPACA_PAPER order. AGENT_STATE.md carried that as a live backlog item for four
cycles ("observation path reports NULL ... find the SECOND constructor") plus a
separate SIMULATOR audit candidate. This cycle verified all three backlog
candidates against the code and they are FALSE PREMISES:

- there is exactly ONE production `PaperOrder(` KEYWORD constructor
  (`services/api/broker_routes.py`), and it already passes `last_reconciled_at`.
  The other production sites construct by `model_validate` over `paper_orders`
  columns (`paper_queries.portfolio`, `decisions_routes`); they cannot source
  the stamp because the migration moved the column to `broker_orders`, and that
  is correct for REPLAY -- see the checklist test below;
- `broker_orders.last_reconciled_at` is NOT NULL in the model AND in its
  creating migration, so the value can never be absent on that path;
- the NULLs came from the FROZEN RUNTIME, which runs an older commit that
  predates the column being set -- not from a defect on HEAD.

Those findings were recorded only in prose and cost repeated re-derivation. The
class of bug they share is the one `test_broker_snapshot_not_null_contract.py`
already pins for snapshots: a read-site assumption about a NOT NULL column,
verified by GREP and recorded in a Markdown file, that can drift silently.
Pin the order-side half of that contract executably.

Two failure modes this prevents, both silent at the time they land:

1. someone relaxes `broker_orders.last_reconciled_at` to nullable (or reads it
   through an outer join that can miss the row) while the route still forwards
   it verbatim -> the ALPACA_PAPER order list republishes the NULL symptom and
   Mission Control shows orders that can never have been reconciled;
2. someone adds a second production `PaperOrder(` constructor and forgets the
   field -- the contract types it `datetime | None = None`, so the omission is
   legal Python that publishes NULL with no error.

Pure unit tests: no Postgres, no broker, no DB mutation, no migration run.
"""

import re
from pathlib import Path

from packages.contracts.paper import PaperOrder
from services.api import broker_routes
from services.api.models import broker_orders, paper_orders, paper_runs

REPO_ROOT = Path(__file__).resolve().parents[1]
BROKER_ORDERS_MIGRATION = (
    REPO_ROOT / "infrastructure/docker/migrations/versions/b990f1234567_m7_broker_orders.py"
)

# `paper_orders` is the table whose rows both Paper modes read; `broker_orders`
# is the ALPACA_PAPER-only extension holding the reconciliation stamp. The
# route inner-joins them, which is what makes the NOT NULL stamp reachable.
EXPECTED_ORDER_STAMP_COLUMN = "last_reconciled_at"


def _broker_routes_source() -> str:
    return Path(broker_routes.__file__).read_text(encoding="utf-8")


def test_broker_orders_last_reconciled_at_is_not_null_in_model_metadata() -> None:
    """The assumption the ALPACA_PAPER route's verbatim forward rests on."""
    column = broker_orders.c[EXPECTED_ORDER_STAMP_COLUMN]

    assert column.nullable is False


def test_broker_orders_last_reconciled_at_is_not_null_in_its_migration() -> None:
    """Guard the migration, not just the metadata.

    The route forwards a DATABASE column, so metadata agreeing with a migration
    that had relaxed it would prove nothing. Reading the declaration needs no
    migration run.
    """
    source = BROKER_ORDERS_MIGRATION.read_text(encoding="utf-8")

    assert EXPECTED_ORDER_STAMP_COLUMN in source, "reconciliation stamp vanished from broker_orders"

    declaration = next(
        line
        for line in source.splitlines()
        if EXPECTED_ORDER_STAMP_COLUMN in line and "Column" in line
    )
    assert "nullable=False" in declaration, (
        "broker_orders.last_reconciled_at is no longer NOT NULL, but the route "
        "still forwards it verbatim into PaperOrder.last_reconciled_at -- the "
        "ALPACA_PAPER order list can republish the NULL symptom recorded in "
        "AGENT_STATE.md without any error being raised"
    )


def test_defaulted_fields_are_exactly_what_the_migration_moved_off_paper_orders() -> None:
    """Enumerate, executably, everything a constructor may legally omit.

    `PaperOrder` has FIVE defaulted fields, not one: `filled_quantity` plus the
    four columns migration `b990f1234567` dropped from `paper_orders` when it
    created `broker_orders` (`broker_order_id`, `client_order_id`,
    `broker_status`, `last_reconciled_at`). Deriving the expected set FROM the
    migration rather than hardcoding it keeps the checklist honest: add a
    defaulted reconciliation-shaped field and this fails until someone decides
    whether a new constructor must supply it, instead of the omission
    publishing NULL with no error.

    Those same four columns explain why the REPLAY read sites
    (`paper_queries.portfolio`, `decisions_routes`) legitimately publish
    `last_reconciled_at: null`: they select `paper_orders` alone, which no
    longer has the column to source. That is by design -- REPLAY reconciles
    locally and hardcodes `reconciled=True` -- and is NOT the ALPACA_PAPER
    defect, which is what the checks above pin.
    """
    upgrade = BROKER_ORDERS_MIGRATION.read_text(encoding="utf-8").split("def downgrade")[0]
    dropped = {
        match.group(1)
        for match in re.finditer(r'op\.drop_column\(\s*"paper_orders",\s*"(\w+)"', upgrade)
    }
    defaulted = {
        name for name, field in PaperOrder.model_fields.items() if not field.is_required()
    }

    assert dropped, "the migration no longer documents what it moved off paper_orders"
    assert EXPECTED_ORDER_STAMP_COLUMN in dropped, (
        "b990f1234567 no longer lists last_reconciled_at among the paper_orders "
        "columns it moved to broker_orders; this file's checklist is now "
        "describing a layout that does not exist"
    )
    assert defaulted - {"filled_quantity"} == dropped


def test_alpaca_paper_route_forwards_the_stamp() -> None:
    """The single production constructor must actually pass the stamp.

    Guards against a refactor that keeps reading the joined row but stops
    forwarding it, which is indistinguishable from the missing column without
    this check.
    """
    assert f"{EXPECTED_ORDER_STAMP_COLUMN}=o[" in _broker_routes_source(), (
        "the ALPACA_PAPER order constructor no longer forwards "
        f"{EXPECTED_ORDER_STAMP_COLUMN}; PaperOrder defaults it to None"
    )


def test_reconciliation_stamp_cannot_be_lost_by_the_join() -> None:
    """The join must stay INNER on `broker_orders`.

    The route selects `broker_orders` joined to `paper_orders` and forwards the
    stamp from the broker row. An outer join in the wrong direction would let a
    row through with the stamp absent -- reproducing the NULL symptom while
    both columns stayed NOT NULL, which is why the metadata checks above alone
    are not sufficient.
    """
    source = _broker_routes_source()

    assert "broker_orders.join(" in source, "the broker/paper order join disappeared"
    assert "outerjoin" not in source, (
        "an outer join can surface an order whose broker row is absent, leaving "
        f"{EXPECTED_ORDER_STAMP_COLUMN} unsourced"
    )


def test_paper_runs_status_cannot_express_a_degraded_run() -> None:
    """Why the REPLAY path may hardcode `reconciled=True` after reconciling.

    `paper_queries.portfolio()` sets `reconciled = True` unconditionally once
    `store.reconcile()` returns and never sets `degraded`. That is only sound
    while `paper_runs.status` cannot carry a degraded value: the ALPACA_PAPER
    route derives both flags from the snapshot status precisely because a
    DEGRADED/STALE run must not publish `reconciled: true`. If a future
    migration widens this CHECK constraint, REPLAY would start publishing an
    unearned `reconciled` and this test is what says so.

    The `mode` half of the same constraint is pinned by the page-literal test in
    `test_paper_page_mode.py`; this one owns the `status` half.
    """
    constraint = next(
        c for c in paper_runs.constraints if getattr(c, "name", None) == "ck_paper_run_mode"
    )
    sqltext = str(getattr(constraint, "sqltext", ""))

    assert sqltext, (
        "ck_paper_run_mode is not a CHECK constraint any more -- this test can "
        "no longer read the run status domain"
    )

    for status in ("READY", "RUNNING", "COMPLETED"):
        assert status in sqltext, f"{status} left the paper_runs status domain"

    assert "DEGRADED" not in sqltext
    assert "STALE" not in sqltext


def test_paper_orders_table_has_no_stamp_column_of_its_own() -> None:
    """One definition per concept: the stamp lives on `broker_orders` only.

    `b990f1234567` dropped `paper_orders.last_reconciled_at` when it created
    `broker_orders`. Re-adding it would give the same timestamp two homes, and
    a route that read the wrong one would silently diverge again.
    """
    assert EXPECTED_ORDER_STAMP_COLUMN not in paper_orders.c