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
    EXPLAINED_BY_LAG,
    KNOWN_FIXES,
    LIVE_ON_RUNTIME,
    SYNC,
    UNKNOWN,
    UNKNOWN_FIX,
    ParityReport,
    build_report,
    main,
    subprocess_run_git,
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


def _behind_report(*, also_on_runtime: set[str] | None = None) -> ParityReport:
    """A runtime that is a strict ancestor of the branch.

    EVERY known fix is an ancestor of the BRANCH (they are all branch commits);
    `also_on_runtime` decides per sha whether the runtime has it too.  Anchoring
    only the first entry would let a new fix read as `unknown-fix` by accident
    and quietly stop being reported.
    """
    ancestors = {(RUNTIME_HEAD, BRANCH_HEAD)}
    ancestors |= {(fix.commit, BRANCH_HEAD) for fix in KNOWN_FIXES}
    ancestors |= {(sha, RUNTIME_HEAD) for sha in (also_on_runtime or set())}
    return build_report(
        RUNTIME,
        BRANCH,
        git=fake_git({RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD}, ancestors=ancestors),
    )


def test_fix_missing_from_runtime_is_reported_as_runtime_lag() -> None:
    """The point of the section: a stale runtime gets an explicit verdict.

    Without this, every cycle re-investigates a symptom whose fix is already
    merged here and simply never deployed.
    """
    report = _behind_report()

    provenance = report.fixes[0]
    assert provenance.state == EXPLAINED_BY_LAG
    assert provenance.symptom in report.anomalies_explained_by_lag
    rendered = report.render()
    assert provenance.commit in rendered
    assert "EXPLAINED BY RUNTIME LAG" in rendered


def test_fix_present_on_runtime_is_not_called_runtime_lag() -> None:
    """When the runtime HAS the fix, the symptom is live and must be reported.

    The inverse error is the dangerous one: calling a live defect "explained"
    would suppress the investigation that finds it.
    """
    report = _behind_report(also_on_runtime={fix.commit for fix in KNOWN_FIXES})

    assert report.fixes[0].state == LIVE_ON_RUNTIME
    assert report.anomalies_explained_by_lag == ()
    assert "EXPLAINED BY RUNTIME LAG" not in report.render()


def test_every_known_fix_is_classified_independently() -> None:
    """Each entry must be judged by its OWN ancestry, not the registry's first.

    The runtime here has the first fix but NOT the count fix, so the count
    symptom is excused while the first entry's is not.  Classification that
    collapsed across entries would either excuse a live defect or re-open a
    settled one.

    Membership is asserted per entry rather than against the whole tuple: an
    equality check over the full collection fails the next time a fix is
    appended, which teaches the next cycle to "fix" the fixture instead of
    extending the registry.
    """
    count_fix = next(f for f in KNOWN_FIXES if f.commit == "7252052")
    report = _behind_report(also_on_runtime={KNOWN_FIXES[0].commit})

    states = {provenance.commit: provenance.state for provenance in report.fixes}
    assert states[KNOWN_FIXES[0].commit] == LIVE_ON_RUNTIME
    assert states[count_fix.commit] == EXPLAINED_BY_LAG
    excused = report.anomalies_explained_by_lag
    assert count_fix.symptom in excused
    assert KNOWN_FIXES[0].symptom not in excused
    # Every excused symptom belongs to a fix the runtime genuinely lacks, and
    # every such fix is excused: no entry is dropped from the report.
    assert set(excused) == {
        f.symptom for f in report.fixes if f.state == EXPLAINED_BY_LAG
    }
    assert set(excused) == {f.symptom for f in KNOWN_FIXES if f.commit != KNOWN_FIXES[0].commit}


def test_count_symptom_is_registered_against_its_own_fix() -> None:
    """The reported-vs-actual count gap must name the commit that fixed it.

    This anomaly sits in EVERY observation while the runtime is undeployed; an
    unregistered symptom costs a future cycle the whole re-derivation.
    """
    symptom = next(f.symptom for f in KNOWN_FIXES if f.commit == "7252052")
    assert "orders_count_reported" in symptom
    assert "orders_count_actual" in symptom

    report = _behind_report()
    provenance = next(f for f in report.fixes if f.commit == "7252052")
    assert provenance.state == EXPLAINED_BY_LAG
    assert symptom in report.anomalies_explained_by_lag
    assert symptom in report.render()


def test_health_flap_symptom_is_registered_against_its_own_fix() -> None:
    """The /health flap must name the commit that fixed it.

    `health.status=degraded` beside `paper.degraded=false, reconciled=true` is
    the most frequent anomaly in the observation history (670 of 1138 samples)
    and reads exactly like a live fault.  `health_ready()` (b6b2802) fixed it on
    this branch and the frozen runtime never ran that commit, so an unregistered
    symptom costs every future cycle the whole re-derivation.
    """
    symptom = next(f.symptom for f in KNOWN_FIXES if f.commit == "b6b2802")
    assert "health.status=degraded" in symptom
    assert "paper.degraded=false" in symptom
    assert "paper.reconciled=true" in symptom

    report = _behind_report()
    provenance = next(f for f in report.fixes if f.commit == "b6b2802")
    assert provenance.state == EXPLAINED_BY_LAG
    assert symptom in report.anomalies_explained_by_lag
    assert symptom in report.render()


def test_every_registered_fix_is_a_real_commit_on_this_branch() -> None:
    """Every registered sha must resolve in THIS repository.

    A typo or a rebase-orphaned sha makes `in_branch` False, which downgrades the
    entry to `unknown-fix`: the report then explains NOTHING for that symptom and
    the next cycle re-derives it from scratch -- the exact failure this module
    exists to prevent. Read-only: merge-base only.
    """
    repo = Path(__file__).resolve().parents[1]

    for fix in KNOWN_FIXES:
        probe = subprocess_run_git(
            ["merge-base", "--is-ancestor", fix.commit, "HEAD"], repo
        )
        assert probe.returncode == 0, (
            f"{fix.commit} is not an ancestor of HEAD; it would classify as "
            f"{UNKNOWN_FIX} and stop explaining its symptom"
        )


def test_fix_absent_from_branch_history_is_unknown_not_explained() -> None:
    """An unresolvable sha yields no verdict, never a reassuring one."""
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git(
            {RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD},
            ancestors={(RUNTIME_HEAD, BRANCH_HEAD)},
        ),
    )

    assert report.status == BEHIND
    assert report.fixes[0].state == UNKNOWN_FIX
    assert report.anomalies_explained_by_lag == ()


def test_unreadable_runtime_reports_no_fix_provenance() -> None:
    """Nothing was read, so nothing is claimed -- not even an explanation."""
    report = build_report(RUNTIME, BRANCH, git=fake_git({RUNTIME: "abc"}))

    assert report.status == UNKNOWN
    assert report.fixes == ()
    assert report.anomalies_explained_by_lag == ()
