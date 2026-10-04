"""The Paper review gate compares an observation against the branch under review.

That comparison is unsound unless the frozen runtime is actually running that
branch: the runtime worktree is pinned to its own commit and never
fast-forwards.  A field populated only on this branch legitimately reads `null`
in an observation, and a reviewer who cannot tell the two cases apart either
files a phantom defect or -- worse -- "fixes" already-correct code.

These tests pin the classification logic.  `git` is faked throughout, so no
repository, runtime or database is touched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.paper_runtime_parity import (
    AHEAD,
    BEHIND,
    DIVERGED,
    SYNC,
    UNKNOWN,
    ParityReport,
    build_report,
    main,
)

RUNTIME = Path("C:/frozen/runtime")
BRANCH = Path("C:/frozen/branch")
RUNTIME_HEAD = "1" * 40
BRANCH_HEAD = "2" * 40


def _proc(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=""
    )


def fake_git(
    heads: dict[Path, str],
    *,
    ancestors: set[tuple[str, str]] | None = None,
    logs: dict[str, str] | None = None,
    failing: set[Path] | None = None,
) -> Any:
    """A `git` stand-in driven by the command argv.

    `ancestors` holds (candidate, descendant) pairs that answer merge-base
    --is-ancestor with exit 0; everything else answers 1. `logs` keys are
    "<older>..<newer>" ranges.
    """
    ancestors = ancestors or set()
    logs = logs or {}
    failing = failing or set()

    def run(args: Any, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        argv = list(args)
        if argv[:2] == ["rev-parse", "HEAD"]:
            if cwd in failing:
                return _proc("fatal: not a git repository\n", 128)
            return _proc(f"{heads.get(cwd or Path(), '')}\n")
        if argv[:2] == ["merge-base", "--is-ancestor"]:
            return _proc(returncode=0 if (argv[2], argv[3]) in ancestors else 1)
        if argv[0] == "log":
            return _proc(logs.get(argv[-1], ""))
        raise AssertionError(f"unexpected git invocation: {argv}")

    return run


def test_same_commit_is_in_sync() -> None:
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git({RUNTIME: RUNTIME_HEAD, BRANCH: RUNTIME_HEAD}),
    )
    assert report.status == SYNC
    assert report.in_sync
    assert not report.observations_may_lag
    assert report.commits_only_on_branch == ()
    assert report.commits_only_on_runtime == ()


def test_runtime_ancestor_reports_behind_and_flags_lag() -> None:
    """The live case: the runtime predates this branch, so nulls are expected."""
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git(
            {RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD},
            ancestors={(RUNTIME_HEAD, BRANCH_HEAD)},
            logs={f"{RUNTIME_HEAD}..{BRANCH_HEAD}": "abc1234 fix(api): stamp reconciled\n"},
        ),
    )
    assert report.status == BEHIND
    assert not report.in_sync
    assert report.observations_may_lag
    assert report.commits_only_on_branch == ("abc1234 fix(api): stamp reconciled",)
    assert report.commits_only_on_runtime == ()
    assert "check parity" in report.render()


def test_branch_ancestor_reports_runtime_ahead() -> None:
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git(
            {RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD},
            ancestors={(BRANCH_HEAD, RUNTIME_HEAD)},
            logs={f"{BRANCH_HEAD}..{RUNTIME_HEAD}": "def5678 chore: runtime side\n"},
        ),
    )
    assert report.status == AHEAD
    assert report.commits_only_on_runtime == ("def5678 chore: runtime side",)
    # An ahead runtime cannot explain a null field, so no lag is claimed.
    assert not report.observations_may_lag


def test_neither_ancestor_reports_diverged_and_flags_lag() -> None:
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git({RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD}),
    )
    assert report.status == DIVERGED
    assert report.observations_may_lag
    assert "diverged" in report.render()


def test_unreadable_runtime_is_unknown_not_an_exception() -> None:
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git({RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD}, failing={RUNTIME}),
    )
    assert report.status == UNKNOWN
    assert report.error
    assert not report.observations_may_lag
    assert "unknown" in report.render()


def test_short_rev_parse_output_is_treated_as_failure() -> None:
    """A truncated/absent HEAD must not be mistaken for a commit id."""
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git({RUNTIME: "not-a-sha", BRANCH: BRANCH_HEAD}),
    )
    assert report.status == UNKNOWN
    assert report.error


def test_ancestry_probes_run_in_a_repository_not_the_caller_cwd() -> None:
    """merge-base/log must be given the repo, or they resolve against the CWD.

    A `cwd=None` probe inherits the process working directory; invoked from
    outside a checkout every probe exits 128 and the report claims `diverged`
    -- fabricated deployment drift on a perfectly healthy branch.
    """
    seen: list[Path | None] = []
    heads_by_cwd: dict[Path, str] = {RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD}

    def recording_git(
        args: Any, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        if list(args)[:2] == ["rev-parse", "HEAD"]:
            return _proc(f"{heads_by_cwd.get(cwd or Path(), '')}\n")
        seen.append(cwd)
        if list(args)[:2] == ["merge-base", "--is-ancestor"]:
            return _proc(returncode=0 if list(args)[2] == RUNTIME_HEAD else 1)
        if list(args)[0] == "log":
            return _proc("")
        raise AssertionError(f"unexpected git invocation: {args}")

    report = build_report(RUNTIME, BRANCH, git=recording_git)

    assert seen, "no ancestry probe ran"
    assert set(seen) == {BRANCH}, f"probe ran outside the branch repo: {seen}"
    assert report.status == BEHIND


@pytest.mark.parametrize(
    ("status", "expected"),
    [(UNKNOWN, 2), (BEHIND, 1), (DIVERGED, 1), (AHEAD, 1), (SYNC, 0)],
)
def test_main_exit_codes(status: str, expected: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero means 'not in sync', so a caller can gate on it."""
    report = ParityReport(
        runtime_path=str(RUNTIME),
        runtime_head=RUNTIME_HEAD,
        branch_head=BRANCH_HEAD,
        status=status,
    )
    monkeypatch.setattr("scripts.paper_runtime_parity.build_report", lambda *a, **k: report)
    assert main([]) == expected


def test_json_output_is_serialisable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = ParityReport(
        runtime_path=str(RUNTIME),
        runtime_head=RUNTIME_HEAD,
        branch_head=BRANCH_HEAD,
        status=BEHIND,
        commits_only_on_branch=("abc1234 fix(api): stamp reconciled",),
    )
    monkeypatch.setattr("scripts.paper_runtime_parity.build_report", lambda *a, **k: report)
    main(["--json"])
    payload = capsys.readouterr().out
    assert '"status": "runtime-behind"' in payload
    assert '"observations_may_lag": true' in payload
