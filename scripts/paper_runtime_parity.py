"""Read-only parity report between the frozen Paper runtime and this branch.

The autonomous Paper review gate compares `.agent-runtime/paper-latest.json`
against this working tree.  That comparison is only meaningful if the frozen
runtime is actually running the code being reviewed: the runtime is a separate
worktree pinned to its own commit and it NEVER fast-forwards during autonomous
development.  A field that is populated on this branch can legitimately read as
null in an observation simply because the deployed checkout predates the fix.

Two questions are answered.  First, how far behind the runtime is.  Second, for
each KNOWN_FIX, whether the runtime actually contains that commit -- which turns
"is this observation anomaly a live defect or runtime lag?" into a lookup
instead of a fresh investigation every cycle.

This module answers that question with `git` alone.  It is strictly read-only:
it runs `rev-parse`, `merge-base` and `log` against the runtime worktree and
writes nothing anywhere.  It never opens the database, never contacts the
broker, and never mutates the frozen worktree.

Usage:
    python -m scripts.paper_runtime_parity
    python -m scripts.paper_runtime_parity --runtime C:/path/to/runtime --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# The frozen Alpaca Paper runtime worktree. Overridable via --runtime.
DEFAULT_RUNTIME = Path(
    "C:/Users/vitor/OneDrive/Documentos/ChatGPT/TradingBot-runtime"
)

# Where the review gate is expected to find observations.
DEFAULT_OBSERVATION = Path(
    "C:/Users/vitor/OneDrive/Documentos/ChatGPT/TradingBot-agent/.agent-runtime/paper-latest.json"
)

SYNC = "in-sync"
BEHIND = "runtime-behind"
AHEAD = "runtime-ahead"
DIVERGED = "diverged"
UNKNOWN = "unknown"

#: A known symptom is `explained-by-runtime-lag` when the runtime does not
#: contain the fix and `live-on-runtime` when it does.  `unknown-fix` means the
#: commit is not even in this branch's history, so no verdict is possible -- a
#: typo'd sha must never yield a confident "explained" answer.
EXPLAINED_BY_LAG = "explained-by-runtime-lag"
LIVE_ON_RUNTIME = "live-on-runtime"
UNKNOWN_FIX = "unknown-fix"

#: A run_git returns a CompletedProcess; tests substitute their own callable so
#: no real repository is required to exercise the classification logic.
RunGit = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class KnownFix:
    """A commit that corrected a defect the review gate can still observe.

    `symptom` is phrased the way the anomaly appears in the observation, so a
    cycle reading the report can match it without re-deriving the cause.
    """

    commit: str
    symptom: str


#: Defects already corrected on this branch whose symptom persists in every
#: observation while the frozen runtime stays behind.  Each entry is a claim the
#: report VERIFIES, never assumes: `commit` must be reachable from the branch
#: HEAD, otherwise it is reported as `unknown-fix`.
KNOWN_FIXES: tuple[KnownFix, ...] = (
    KnownFix(
        commit="5ee4f29",
        symptom=(
            "latest_orders[*].requested_at advances every reconcile cycle while "
            "latest_orders[*].last_reconciled_at is null"
        ),
    ),
    # `get_broker_portfolio` published the PaperPortfolio count defaults (0)
    # next to populated order/fill lists. An unreported symptom is worse than an
    # unreported FIX: the report is what stops the next cycle from re-deriving it.
    KnownFix(
        commit="7252052",
        symptom=(
            "paper.orders_count_reported=0 while paper.orders_count_actual>0 "
            "(same for fills_count_reported vs fills_count_actual)"
        ),
    ),
    # `/health` read the worker's EXECUTION gate, which `reconcile_once` closes
    # for a moment of every 3s cycle, so a healthy runtime published
    # status=degraded (HTTP 503). It is the single most frequent anomaly in the
    # observation history -- 670 of 1138 samples carry it -- and it looks like a
    # live fault unless a reader knows the runtime predates `health_ready()`.
    KnownFix(
        commit="b6b2802",
        symptom=(
            "health.status=degraded while paper.degraded=false, paper.paused=false "
            "and paper.reconciled=true (the /health execution-gate flap)"
        ),
    ),
)


@dataclass(frozen=True)
class FixProvenance:
    """Where a known fix sits relative to the branch and the runtime."""

    commit: str
    symptom: str
    in_branch: bool
    in_runtime: bool

    @property
    def state(self) -> str:
        if not self.in_branch:
            return UNKNOWN_FIX
        return LIVE_ON_RUNTIME if self.in_runtime else EXPLAINED_BY_LAG

    def to_dict(self) -> dict[str, object]:
        return {
            "commit": self.commit,
            "symptom": self.symptom,
            "in_branch": self.in_branch,
            "in_runtime": self.in_runtime,
            "state": self.state,
        }


def subprocess_run_git(
    args: Sequence[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command. Never raises for a non-zero exit."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _rev_parse(git: RunGit, path: Path) -> str:
    result = git(["rev-parse", "HEAD"], path)
    head = result.stdout.strip()
    if result.returncode != 0 or len(head) != 40:
        detail = (result.stderr or result.stdout).strip().splitlines()
        reason = detail[0] if detail else f"git exited {result.returncode}"
        raise RuntimeError(reason)
    return head


def _is_ancestor(git: RunGit, candidate: str, descendant: str, repo: Path) -> bool:
    """True when `candidate` is reachable from `descendant`.

    `repo` must be passed explicitly: `merge-base` resolves both revisions
    against the REPOSITORY it runs in, so with no cwd it inherits the caller's
    working directory.  Run from outside a checkout, every probe exits 128 and
    the classification silently degrades to `diverged` -- a fabricated
    "deployment drift" verdict for a healthy branch.
    """
    return (
        git(["merge-base", "--is-ancestor", candidate, descendant], repo).returncode == 0
    )


def _ahead_commits(git: RunGit, older: str, newer: str, repo: Path) -> tuple[str, ...]:
    result = git(["log", "--format=%h %s", f"{older}..{newer}"], repo)
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line.strip())


@dataclass(frozen=True)
class ParityReport:
    """The runtime checkout's commit relative to this branch's HEAD.

    `status` is the field to act on:

    - ``in-sync``    the runtime runs exactly this commit.
    - ``runtime-behind`` the runtime is a strict ancestor; the branch holds
      commits the runtime has never run.  Observations may legitimately omit
      anything those commits introduced.
    - ``runtime-ahead``  the runtime is ahead of this branch; the branch is
      stale relative to what is deployed.
    - ``diverged``    neither commit contains the other: the histories split,
      which is deployment drift and needs a human decision.
    - ``unknown``     the runtime could not be read; nothing was concluded.
    """

    runtime_path: str
    runtime_head: str | None
    branch_head: str | None
    status: str
    commits_only_on_branch: tuple[str, ...] = ()
    commits_only_on_runtime: tuple[str, ...] = ()
    error: str | None = None
    fixes: tuple[FixProvenance, ...] = ()

    @property
    def in_sync(self) -> bool:
        return self.status == SYNC

    @property
    def observations_may_lag(self) -> bool:
        """True when a null field in an observation may be runtime lag.

        This is the whole point of the report: a `null` that only this branch
        populates is expected under `runtime-behind`, so it must not be filed
        as a defect on this branch without checking parity first.
        """
        return self.status in (BEHIND, DIVERGED)

    @property
    def anomalies_explained_by_lag(self) -> tuple[str, ...]:
        """Symptoms a reviewer can stop investigating, and why.

        Each entry names a commit that IS in the branch and is NOT in the
        runtime, so the anomaly belongs to the deployed checkout, not to this
        code.  A symptom whose fix IS in the runtime is deliberately absent:
        then the runtime is running the fix and the anomaly is still live.
        """
        return tuple(f.symptom for f in self.fixes if f.state == EXPLAINED_BY_LAG)

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_path": self.runtime_path,
            "runtime_head": self.runtime_head,
            "branch_head": self.branch_head,
            "status": self.status,
            "in_sync": self.in_sync,
            "observations_may_lag": self.observations_may_lag,
            "commits_only_on_branch": list(self.commits_only_on_branch),
            "commits_only_on_runtime": list(self.commits_only_on_runtime),
            "fixes": [f.to_dict() for f in self.fixes],
            "anomalies_explained_by_lag": list(self.anomalies_explained_by_lag),
            "error": self.error,
        }

    def render(self) -> str:
        if self.status == UNKNOWN:
            return f"runtime parity unknown ({self.runtime_path}): {self.error}"
        lines = [
            f"runtime : {self.runtime_path}",
            f"  runtime HEAD : {self.runtime_head}",
            f"  branch  HEAD : {self.branch_head}",
            f"  status       : {self.status}",
        ]
        if self.commits_only_on_branch:
            lines.append(f"  {len(self.commits_only_on_branch)} commit(s) on this branch only:")
            lines.extend(f"    {c}" for c in self.commits_only_on_branch)
        if self.commits_only_on_runtime:
            lines.append(f"  {len(self.commits_only_on_runtime)} commit(s) on the runtime only:")
            lines.extend(f"    {c}" for c in self.commits_only_on_runtime)
        for fix in self.fixes:
            lines.append(f"  fix {fix.commit}: {fix.state}")
            lines.append(f"    {fix.symptom}")
        if self.anomalies_explained_by_lag:
            lines.append(
                "  EXPLAINED BY RUNTIME LAG: do not file these as defects on this"
                " branch; the runtime never ran the fix."
            )
        if self.observations_may_lag:
            lines.append(
                "  NOTE: a field this branch populates may read null in an "
                "observation; check parity before filing it as a defect."
            )
        return "\n".join(lines)


def build_report(
    runtime_path: Path = DEFAULT_RUNTIME,
    branch_path: Path | None = None,
    *,
    git: RunGit = subprocess_run_git,
) -> ParityReport:
    """Classify the frozen runtime against this branch. Read-only.

    Any failure to read the runtime yields an `unknown` report rather than an
    exception, so the review gate can print the report unconditionally.
    """
    branch = branch_path if branch_path is not None else Path(__file__).resolve().parents[1]
    try:
        runtime_head = _rev_parse(git, runtime_path)
        branch_head = _rev_parse(git, branch)
    except RuntimeError as exc:
        return ParityReport(
            runtime_path=str(runtime_path),
            runtime_head=None,
            branch_head=None,
            status=UNKNOWN,
            error=str(exc),
        )

    if runtime_head == branch_head:
        status = SYNC
    elif _is_ancestor(git, runtime_head, branch_head, branch):
        status = BEHIND
    elif _is_ancestor(git, branch_head, runtime_head, branch):
        status = AHEAD
    else:
        status = DIVERGED

    branch_only = _ahead_commits(git, runtime_head, branch_head, branch)
    runtime_only = _ahead_commits(git, branch_head, runtime_head, branch)
    if status in (SYNC, UNKNOWN):
        branch_only, runtime_only = (), ()

    # Provenance is computed only after both revisions resolved, and both
    # ancestry probes run against `branch` so they resolve in this repository
    # rather than in whatever cwd the caller happened to be in.
    fixes = tuple(
        FixProvenance(
            commit=known.commit,
            symptom=known.symptom,
            in_branch=_is_ancestor(git, known.commit, branch_head, branch),
            in_runtime=_is_ancestor(git, known.commit, runtime_head, branch),
        )
        for known in KNOWN_FIXES
    )

    return ParityReport(
        runtime_path=str(runtime_path),
        runtime_head=runtime_head,
        branch_head=branch_head,
        status=status,
        commits_only_on_branch=branch_only,
        commits_only_on_runtime=runtime_only,
        fixes=fixes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--branch", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)

    report = build_report(args.runtime, args.branch)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.render())

    if report.status == UNKNOWN:
        return 2
    return 0 if report.in_sync else 1


if __name__ == "__main__":
    sys.exit(main())
