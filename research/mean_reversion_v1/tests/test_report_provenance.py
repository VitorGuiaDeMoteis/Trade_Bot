import pytest


def validate_report_provenance(report: dict, manifest: dict):
    if report.get("git_head") != manifest.get("git_head"):
        raise ValueError("Report git_head must match manifest git_head")
    if report.get("source_tree_hash") != manifest.get("source_tree_hash"):
        raise ValueError("Report source_tree_hash must match manifest source_tree_hash")
    if report.get("run_manifest_hash") != manifest.get("run_manifest_hash"):
        raise ValueError("Report run_manifest_hash must match manifest run_manifest_hash")


def test_report_provenance_mismatch():
    manifest = {"git_head": "123", "source_tree_hash": "abc", "run_manifest_hash": "def"}

    with pytest.raises(ValueError):
        validate_report_provenance(
            {"git_head": "456", "source_tree_hash": "abc", "run_manifest_hash": "def"}, manifest
        )

    with pytest.raises(ValueError):
        validate_report_provenance(
            {"git_head": "123", "source_tree_hash": "xyz", "run_manifest_hash": "def"}, manifest
        )

    validate_report_provenance(
        {"git_head": "123", "source_tree_hash": "abc", "run_manifest_hash": "def"}, manifest
    )
