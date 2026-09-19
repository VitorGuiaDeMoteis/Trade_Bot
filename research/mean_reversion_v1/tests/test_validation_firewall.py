import pytest

from research.mean_reversion_v1.historical import DiagnosticFirewallError, verify_validation_access


def test_validation_requires_valid_dev():
    with pytest.raises(DiagnosticFirewallError):
        verify_validation_access(None)

    with pytest.raises(DiagnosticFirewallError):
        verify_validation_access({"status": "INVALID_FOR_RESEARCH"})

    with pytest.raises(DiagnosticFirewallError):
        verify_validation_access({"status": "RUNNING"})

    # Should pass
    verify_validation_access({"status": "COMPLETED_VALID"})
