"""Explicit development operations: python -m scripts.paper replay|status|pause|resume|reset."""

import argparse
import json

from sqlalchemy.exc import SQLAlchemyError

from services.api.config import Settings
from services.api.database import check_database, create_database_engine
from services.api.paper_queries import portfolio
from services.api.paper_store import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulação LOCAL; nenhum acesso a corretora.")
    parser.add_argument(
        "command", choices=["replay", "status", "reconcile", "pause", "resume", "reset"]
    )
    parser.add_argument("--confirm")
    args = parser.parse_args()
    settings = Settings()
    engine = create_database_engine(settings)
    try:
        if check_database(engine) != "up":
            raise ValueError("database_or_schema_unavailable")
        store = PaperStore(engine, settings)
        if args.command == "reset":
            if args.confirm != "RESET_PAPER_LOCAL":
                parser.error("reset requires --confirm RESET_PAPER_LOCAL; old run remains archived")
            store.initialize(reset=True)
        elif args.command in {"pause", "resume"}:
            store.set_paused(args.command == "pause")
        elif args.command == "replay":
            store.replay()
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c, c.begin():
            result = portfolio(c, store)
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    except (SQLAlchemyError, ValueError) as error:
        # SQL exceptions may contain credentials; only domain codes may be exposed.
        message = str(error) if isinstance(error, ValueError) else "database_unavailable"
        parser.exit(1, f"Paper local interrompido: {message}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
