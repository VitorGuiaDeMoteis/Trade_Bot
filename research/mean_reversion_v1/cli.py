import json
from pathlib import Path

import typer

from research.mean_reversion_v1.manifest import PROTOCOL_VERSION, get_git_info, get_source_tree_hash

app = typer.Typer(no_args_is_help=True, help="Mean Reversion V1.2 research-only CLI")


@app.command()
def status() -> None:
    root = Path.cwd().resolve()
    manifest_path = root / ".artifacts" / "research" / "mean_reversion_v1" / "dev_manifest.json"

    dev_status = "NOT_RUN"
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text())
            dev_status = m.get("status", "INVALID_FOR_RESEARCH")

            print(f"DEV: {dev_status}")
            print(f"git_head: {m.get('git_head')}")
            print(f"source_tree_hash: {m.get('source_tree_hash')}")
            print(f"protocol_version: {m.get('protocol_version')}")
            return
        except Exception:
            dev_status = "INVALID_FOR_RESEARCH"

    # If not run, show current
    try:
        git_info = get_git_info(root)
        print(f"DEV: {dev_status}")
        print(f"git_head: {git_info['git_head']}")
        print(f"source_tree_hash: {get_source_tree_hash(root)}")
        print(f"protocol_version: {PROTOCOL_VERSION}")
    except Exception:
        print(f"DEV: {dev_status}")
        print("Cannot determine git/source state.")


@app.command()
def fetch() -> None:
    print("Fetching data (placeholder)")


@app.command()
def dev() -> None:
    print("Running DEV (placeholder)")


@app.command()
def validation() -> None:
    print("Running VALIDATION (placeholder)")


@app.command()
def diagnostic() -> None:
    from research.mean_reversion_v1.historical import (
        DiagnosticFirewallError,
        verify_historical_diagnostic_access,
    )

    try:
        # In a real run, this would load the seal, check if it's valid, check if DEV/VAL passed.
        # But we don't have the full state logic, so we raise the error
        verify_historical_diagnostic_access(False, False, False)
    except DiagnosticFirewallError as e:
        print(f"Firewall active: {e}")


@app.command()
def seal() -> None:
    print("Creating seal (placeholder)")


@app.command()
def verify_seal() -> None:
    print("Verifying seal (placeholder)")


if __name__ == "__main__":
    app()
