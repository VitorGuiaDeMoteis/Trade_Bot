import typer

app = typer.Typer(no_args_is_help=True, help="Mean Reversion V1.2 research-only CLI")


@app.command()
def status() -> None:
    print("Mean Reversion V1.2 CLI status: OK")


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
