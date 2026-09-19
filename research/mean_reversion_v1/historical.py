class DiagnosticFirewallError(Exception):
    pass


def verify_historical_diagnostic_access(
    seal_valid: bool, dev_passed: bool, val_passed: bool
) -> None:
    if not seal_valid:
        raise DiagnosticFirewallError("Valid seal required for historical diagnostic.")
    if not (dev_passed and val_passed):
        raise DiagnosticFirewallError("DEV and VALIDATION must complete successfully.")
