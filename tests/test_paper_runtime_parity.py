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

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from scripts import paper_runtime_parity as parity
from scripts.paper_runtime_parity import (
    AHEAD,
    BEHIND,
    DIVERGED,
    EXPLAINED_BY_LAG,
    KNOWN_FIXES,
    LIVE_ON_RUNTIME,
    OBSERVATION_ERROR,
    OBSERVATION_INCOMPLETE,
    OBSERVATION_MISSING,
    OBSERVATION_OK,
    OBSERVATION_UNREADABLE,
    SYNC,
    UNKNOWN,
    UNKNOWN_FIX,
    ObservationHealth,
    ParityReport,
    build_report,
    main,
    read_observation,
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


def _use_git(monkeypatch: pytest.MonkeyPatch, git: Any) -> None:
    """Force `main()` to build its report through an injected `git` callable.

    `build_report` binds `subprocess_run_git` as a default argument at import
    time, so patching the module attribute never reaches it -- and `RUNTIME` /
    `BRANCH` are placeholder paths that no real `git` could ever resolve.  Wrap
    the function instead, which is the only seam `main` actually goes through.

    Every test that drives `main` MUST come through here.  A test that forgets
    silently runs the REAL git against `C:/frozen/...`, and then passes for the
    wrong reason: the placeholder path already fails, so the assertion is
    satisfied by the environment instead of by the failure being injected.
    """
    real_build_report = parity.build_report

    def build_with_git(runtime: Path, branch: Path, **kwargs: Any) -> ParityReport:
        return real_build_report(runtime, branch, git=git, **kwargs)

    monkeypatch.setattr(parity, "build_report", build_with_git)


def _use_fake_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point `main()` at an in-sync fake repository."""
    _use_git(monkeypatch, fake_git({RUNTIME: RUNTIME_HEAD, BRANCH: RUNTIME_HEAD}))


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


# --- Observation health -----------------------------------------------------
#
# Git parity cannot see the observation at all.  When the observer's probe fails
# it replaces paper-latest.json with a stub carrying `observer_error` and NO
# `paper` block; a git-only gate renders that exactly like a healthy runtime.
# These tests pin the classification so the gate stays fail-closed.


def _write_observation(tmp_path: Path, payload: object) -> Path:
    target = tmp_path / "paper-latest.json"
    target.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )
    return target


def test_observer_error_stub_is_never_usable(tmp_path: Path) -> None:
    """The live shape today: the observer failed and wrote a bare stub.

    Classifying this as anything but unusable would let a cycle report "no
    anomalies" from a file that observed nothing.
    """
    path = _write_observation(
        tmp_path,
        {
            "observed_at": "2026-10-04T07:08:01Z",
            "observer_error": "TimeoutError",
            "observer_message": "HTTP connection timed out",
        },
    )

    observation = read_observation(path)

    assert observation.status == OBSERVATION_ERROR
    assert observation.usable is False
    detail = observation.detail or ""
    assert "TimeoutError" in detail
    assert "HTTP connection timed out" in detail
    assert observation.observed_at == "2026-10-04T07:08:01Z"


def test_observation_with_paper_payload_is_usable(tmp_path: Path) -> None:
    path = _write_observation(
        tmp_path,
        {
            "observed_at": "2026-10-04T07:07:57Z",
            "health": {"status": "degraded", "database": "ok"},
            "paper": {"paused": False, "positions": []},
        },
    )

    observation = read_observation(path)

    assert observation.status == OBSERVATION_OK
    assert observation.usable is True
    assert observation.observed_at == "2026-10-04T07:07:57Z"


def test_observation_without_paper_payload_is_incomplete(tmp_path: Path) -> None:
    """The observer claimed success but withheld the payload.

    Distinct from an observer error on purpose: git sees both identically, and
    a reader who knows only "the observer broke" would go looking for the wrong
    bug.
    """
    path = _write_observation(
        tmp_path, {"observed_at": "2026-10-04T07:07:57Z", "health": {"status": "ok"}}
    )

    assert read_observation(path).status == OBSERVATION_INCOMPLETE
    assert read_observation(path).usable is False


@pytest.mark.parametrize(
    ("filename", "payload", "expected"),
    [
        ("paper-latest.json", "{ not json", OBSERVATION_UNREADABLE),
        ("paper-latest.json", "[]", OBSERVATION_UNREADABLE),
    ],
)
def test_malformed_observation_is_unreadable_not_ok(
    tmp_path: Path, filename: str, payload: str, expected: str
) -> None:
    path = tmp_path / filename
    path.write_text(payload, encoding="utf-8")

    observation = read_observation(path)

    assert observation.status == expected
    assert observation.usable is False


def test_missing_observation_file_is_missing_not_ok(tmp_path: Path) -> None:
    observation = read_observation(tmp_path / "absent.json")

    assert observation.status == OBSERVATION_MISSING
    assert observation.usable is False


def test_report_without_observation_refuses_to_call_the_runtime_healthy() -> None:
    """Absence of evidence is not evidence of health.

    The default is a report built with no observation, so no test can silently
    depend on the real .agent-runtime file -- and no caller can mistake a
    skipped check for a clean runtime.
    """
    report = _behind_report()

    assert report.observation is None
    assert report.observation_usable is False
    assert "not examined" in report.render()


def test_unusable_observation_is_rendered_before_the_lag_notes() -> None:
    """Ordering matters: lag advice is meaningless without runtime evidence.

    A reader who cannot see the runtime has no anomaly list to interpret, so
    "EXPLAINED BY RUNTIME LAG" printed first reads as if the runtime was
    actually examined.
    """
    report = _behind_report()
    report = replace(
        report,
        observation=ObservationHealth(
            path="paper-latest.json",
            status=OBSERVATION_ERROR,
            detail="TimeoutError: HTTP connection timed out",
            observed_at="2026-10-04T07:08:01Z",
        ),
    )

    rendered = report.render()

    assert report.observation_usable is False
    assert rendered.index("observation :") < rendered.index("EXPLAINED BY RUNTIME LAG")
    assert "TimeoutError" in rendered
    assert "NO paper payload" in rendered


def test_usable_observation_renders_a_bare_ok(tmp_path: Path) -> None:
    report = replace(
        _behind_report(),
        observation=read_observation(
            _write_observation(
                tmp_path,
                {"observed_at": "2026-10-04T07:07:57Z", "paper": {"paused": False}},
            )
        ),
    )

    rendered = report.render()

    assert report.observation_usable is True
    assert "observation : ok (2026-10-04T07:07:57Z)" in rendered
    assert "NO paper payload" not in rendered


def test_json_report_carries_the_observation_verdict(tmp_path: Path) -> None:
    """The JSON form must not lose the verdict; agents read it, not the text."""
    report = replace(
        _behind_report(),
        observation=read_observation(
            _write_observation(
                tmp_path, {"observed_at": "t", "observer_error": "TimeoutError"}
            )
        ),
    )

    payload = report.to_dict()
    observation = payload["observation"]
    assert isinstance(observation, dict)

    assert payload["observation_usable"] is False
    assert observation["status"] == OBSERVATION_ERROR
    json.dumps(payload)  # the report stays serialisable


def test_main_reports_an_unusable_observation_instead_of_exiting_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: a stub observation must be visible in the printed gate.

    Runtime parity here is in-sync, so without the observation verdict the exit
    code would be 0 -- indistinguishable from a genuinely healthy runtime.
    """
    observation = _write_observation(
        tmp_path, {"observed_at": "t", "observer_error": "TimeoutError"}
    )
    _use_fake_git(monkeypatch)

    code = main(
        [
            "--json",
            "--observation",
            str(observation),
            "--runtime",
            str(RUNTIME),
            "--branch",
            str(BRANCH),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["observation_usable"] is False
    assert payload["observation"]["status"] == OBSERVATION_ERROR
    assert payload["status"] == SYNC
    assert code == 0  # git parity is clean; the observation warning carries the nuance


def test_main_can_skip_the_observation_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = _write_observation(
        tmp_path, {"observed_at": "t", "observer_error": "TimeoutError"}
    )
    assert observation.exists()
    _use_fake_git(monkeypatch)

    main(
        [
            "--json",
            "--skip-observation",
            "--runtime",
            str(RUNTIME),
            "--branch",
            str(BRANCH),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["observation"] is None
    assert payload["observation_usable"] is False


def test_an_unknown_runtime_still_renders_the_observation_verdict(
    tmp_path: Path,
) -> None:
    """Text output must not drop the observation line when parity is unknown.

    The early return in `render` is the only path that skips the anomaly notes,
    so it is also the easiest place to silently lose the reason the observation
    cannot be trusted.
    """
    observation_path = _write_observation(
        tmp_path, {"observed_at": "t", "observer_error": "TimeoutError"}
    )
    report = build_report(
        RUNTIME,
        BRANCH,
        git=fake_git(
            {RUNTIME: RUNTIME_HEAD, BRANCH: BRANCH_HEAD}, failing={BRANCH}
        ),
        observation_path=observation_path,
    )
    assert report.status == UNKNOWN

    rendered = report.render()
    assert OBSERVATION_ERROR in rendered
    assert "TimeoutError" in rendered


def test_an_unusable_runtime_still_prints_the_observation_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead runtime must not take the observation verdict down with it.

    On Windows a missing worktree makes `git` raise OSError from
    `subprocess.run(cwd=...)` rather than exit non-zero, so a narrow
    `except RuntimeError` turned an unreadable runtime into a traceback and the
    cycle learned nothing at all.
    """
    observation = _write_observation(
        tmp_path, {"observed_at": "t", "observer_error": "TimeoutError"}
    )

    def unusable_runtime_git(args: Any, cwd: Path | None = None) -> Any:
        raise NotADirectoryError(267, "boom")

    _use_git(monkeypatch, unusable_runtime_git)

    code = main(
        [
            "--json",
            "--observation",
            str(observation),
            "--runtime",
            str(RUNTIME),
            "--branch",
            str(BRANCH),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == UNKNOWN
    # The injected error must be the one reported: without this the test also
    # passes when the REAL git fails on the placeholder path, which would leave
    # the OSError branch of build_report completely unexercised.
    assert "boom" in str(payload["error"])
    assert payload["observation"]["status"] == OBSERVATION_ERROR
    assert payload["observation_usable"] is False
    assert code == 2
