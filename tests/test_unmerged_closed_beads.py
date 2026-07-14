"""Tests for scripts/infra/check_unmerged_closed_beads.py."""

import json
import os
import pathlib
import subprocess
import sys

import pytest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "infra"
SCRIPT = SCRIPT_DIR / "check_unmerged_closed_beads.py"

sys.path.insert(0, str(SCRIPT_DIR))
import check_unmerged_closed_beads as reaper  # noqa: E402
from check_unmerged_closed_beads import (  # noqa: E402
    Bead,
    BranchState,
    bead_id_for_branch,
    collect_states,
    count_unlanded_commits,
    fetch_beads,
    find_violations,
    format_report,
    list_work_branches,
    parse_beads,
)


def _state(
    bead_id: str, status: str, unlanded: int, no_merge: bool = False
) -> BranchState:
    return BranchState(
        branch=f"work/{bead_id}",
        bead_id=bead_id,
        status=status,
        unlanded_commits=unlanded,
        no_merge=no_merge,
    )


class TestFindViolations:
    def test_closed_and_unlanded_is_a_violation(self) -> None:
        violations = find_violations([_state("EB-a", "closed", 3)])
        assert [(v.bead_id, v.unlanded_commits) for v in violations] == [("EB-a", 3)]

    def test_closed_and_landed_is_clean(self) -> None:
        assert find_violations([_state("EB-a", "closed", 0)]) == []

    def test_open_and_unlanded_is_clean(self) -> None:
        """Open beads are work in progress, not stranded work."""
        assert find_violations([_state("EB-a", "open", 5)]) == []

    def test_blocked_and_unlanded_is_clean(self) -> None:
        assert find_violations([_state("EB-a", "blocked", 5)]) == []

    def test_unknown_bead_is_not_a_violation(self) -> None:
        """A branch with no bead in the store cannot be a close-without-merge."""
        assert find_violations([_state("EB-gone", "", 4)]) == []

    def test_no_merge_label_exempts_a_closed_unlanded_bead(self) -> None:
        """A bead closed as superseded or rejected owes main nothing."""
        assert find_violations([_state("EB-a", "closed", 2, no_merge=True)]) == []

    def test_no_merge_label_does_not_exempt_an_unlabelled_sibling(self) -> None:
        states = [
            _state("EB-abandoned", "closed", 2, no_merge=True),
            _state("EB-stranded", "closed", 2),
        ]
        assert [v.bead_id for v in find_violations(states)] == ["EB-stranded"]

    def test_violations_sorted_by_unlanded_commits_descending(self) -> None:
        states = [
            _state("EB-a", "closed", 2),
            _state("EB-b", "closed", 9),
            _state("EB-c", "closed", 5),
        ]
        assert [v.bead_id for v in find_violations(states)] == ["EB-b", "EB-c", "EB-a"]

    def test_mixed_set_reports_only_the_closed_unlanded_ones(self) -> None:
        states = [
            _state("EB-open", "open", 7),
            _state("EB-closed-clean", "closed", 0),
            _state("EB-closed-dirty", "closed", 2),
            _state("EB-unknown", "", 1),
        ]
        assert [v.bead_id for v in find_violations(states)] == ["EB-closed-dirty"]


class TestBeadIdForBranch:
    def test_strips_the_prefix(self) -> None:
        assert bead_id_for_branch("work/EnterpriseBench-2hum", "work/") == (
            "EnterpriseBench-2hum"
        )

    def test_keeps_dotted_bead_ids_intact(self) -> None:
        assert bead_id_for_branch("work/EnterpriseBench-jn73.2.7", "work/") == (
            "EnterpriseBench-jn73.2.7"
        )

    def test_rejects_a_branch_outside_the_prefix(self) -> None:
        with pytest.raises(ValueError, match="does not start with"):
            bead_id_for_branch("fix/EnterpriseBench-2hum", "work/")


class TestParseBeads:
    def test_reads_status_and_the_no_merge_label(self) -> None:
        payload = json.dumps(
            [
                {"id": "EB-a", "status": "closed", "labels": ["no-merge", "rig:eb"]},
                {"id": "EB-b", "status": "open", "labels": []},
                {"id": "EB-c", "status": "closed"},
            ]
        )
        assert parse_beads(payload) == {
            "EB-a": Bead(status="closed", no_merge=True),
            "EB-b": Bead(status="open", no_merge=False),
            "EB-c": Bead(status="closed", no_merge=False),
        }

    def test_empty_list_is_an_empty_map(self) -> None:
        assert parse_beads("[]") == {}

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(RuntimeError, match="invalid JSON"):
            parse_beads("not json")

    def test_non_list_payload_raises(self) -> None:
        with pytest.raises(RuntimeError, match="expected a list"):
            parse_beads('{"id": "EB-a"}')

    def test_missing_status_raises_rather_than_dropping_the_bead(self) -> None:
        """Silently losing a status would report the branch clean."""
        with pytest.raises(RuntimeError, match="missing a string id or status"):
            parse_beads('[{"id": "EB-a"}]')

    def test_non_list_labels_raises(self) -> None:
        with pytest.raises(RuntimeError, match="non-list labels"):
            parse_beads('[{"id": "EB-a", "status": "closed", "labels": "no-merge"}]')


@pytest.fixture
def git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real git repo with a main branch and three work/ branches.

    work/EB-landed   — merged into main (0 unlanded)
    work/EB-stranded — 2 commits never merged
    work/EB-picked   — 1 commit cherry-picked onto main (0 unlanded by patch-id)
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def commit(name: str, body: str) -> None:
        (repo / name).write_text(body)
        git("add", name)
        git("commit", "-qm", f"add {name}")

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    commit("base.txt", "base\n")

    git("checkout", "-q", "-b", "work/EB-landed")
    commit("landed.txt", "landed\n")
    git("checkout", "-q", "main")
    git("merge", "-q", "--ff-only", "work/EB-landed")

    git("checkout", "-q", "-b", "work/EB-stranded", "main")
    commit("stranded-1.txt", "one\n")
    commit("stranded-2.txt", "two\n")

    git("checkout", "-q", "-b", "work/EB-picked", "main")
    commit("picked.txt", "picked\n")
    picked_sha = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    git("cherry-pick", picked_sha)

    return repo


class TestGitEdges:
    def test_lists_only_work_branches(self, git_repo: pathlib.Path) -> None:
        subprocess.run(
            ["git", "branch", "unrelated"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )
        assert list_work_branches("work/", git_repo) == [
            "work/EB-landed",
            "work/EB-picked",
            "work/EB-stranded",
        ]

    def test_stranded_branch_has_unlanded_commits(self, git_repo: pathlib.Path) -> None:
        assert count_unlanded_commits("work/EB-stranded", "main", git_repo) == 2

    def test_merged_branch_has_none(self, git_repo: pathlib.Path) -> None:
        assert count_unlanded_commits("work/EB-landed", "main", git_repo) == 0

    def test_cherry_picked_branch_counts_as_landed(
        self, git_repo: pathlib.Path
    ) -> None:
        """The commit SHA differs but the patch is on main — that is landed."""
        assert count_unlanded_commits("work/EB-picked", "main", git_repo) == 0

    def test_missing_integration_ref_raises(self, git_repo: pathlib.Path) -> None:
        with pytest.raises(RuntimeError, match="git cherry failed"):
            count_unlanded_commits("work/EB-stranded", "no-such-ref", git_repo)


def _write_fake_bd(bin_dir: pathlib.Path, beads: list[dict] | None, exit_code: int = 0):
    """Put a fake `bd` on PATH that echoes a canned --json payload."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    payload = "" if beads is None else json.dumps(beads)
    bd = bin_dir / "bd"
    bd.write_text("#!/bin/sh\n" f"printf '%s' '{payload}'\n" f"exit {exit_code}\n")
    bd.chmod(0o755)
    return bin_dir


class TestFetchBeads:
    def test_no_ids_does_not_shell_out(self, git_repo: pathlib.Path) -> None:
        assert fetch_beads([], git_repo) == {}

    def test_reads_the_bd_payload(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path, monkeypatch
    ) -> None:
        bin_dir = _write_fake_bd(
            tmp_path / "bin", [{"id": "EB-a", "status": "closed", "labels": []}]
        )
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        assert fetch_beads(["EB-a"], git_repo) == {
            "EB-a": Bead(status="closed", no_merge=False)
        }

    def test_bd_failure_raises_rather_than_reporting_clean(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path, monkeypatch
    ) -> None:
        bin_dir = _write_fake_bd(tmp_path / "bin", None, exit_code=1)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        with pytest.raises(RuntimeError, match="bd list failed"):
            fetch_beads(["EB-a"], git_repo)

    def test_missing_bd_binary_raises(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        with pytest.raises(OSError):
            fetch_beads(["EB-a"], git_repo)


class TestCollectStates:
    def test_wires_branches_beads_and_commit_counts_together(
        self, git_repo: pathlib.Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            reaper,
            "fetch_beads",
            lambda bead_ids, cwd: {
                "EB-landed": Bead(status="closed", no_merge=False),
                "EB-stranded": Bead(status="closed", no_merge=False),
                # EB-picked deliberately absent from the store
            },
        )

        states = collect_states("work/", "main", git_repo)

        assert states == [
            BranchState("work/EB-landed", "EB-landed", "closed", 0, False),
            BranchState("work/EB-picked", "EB-picked", "", 0, False),
            BranchState("work/EB-stranded", "EB-stranded", "closed", 2, False),
        ]


def _run_cli(
    git_repo: pathlib.Path, bin_dir: pathlib.Path, *args: str
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(git_repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestCLI:
    """The exit-code contract is the whole interface: 0 clean, 1 violation, 2 error."""

    def test_violation_exits_1_and_names_the_bead(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        bin_dir = _write_fake_bd(
            tmp_path / "bin",
            [
                {"id": "EB-landed", "status": "closed", "labels": []},
                {"id": "EB-picked", "status": "closed", "labels": []},
                {"id": "EB-stranded", "status": "closed", "labels": []},
            ],
        )
        result = _run_cli(git_repo, bin_dir)

        assert result.returncode == 1
        assert "EB-stranded" in result.stdout
        assert "EB-landed" not in result.stdout

    def test_no_merge_label_exits_0(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        bin_dir = _write_fake_bd(
            tmp_path / "bin",
            [
                {"id": "EB-landed", "status": "closed", "labels": []},
                {"id": "EB-picked", "status": "closed", "labels": []},
                {"id": "EB-stranded", "status": "closed", "labels": ["no-merge"]},
            ],
        )
        result = _run_cli(git_repo, bin_dir)

        assert result.returncode == 0
        assert "No closed bead has unlanded commits" in result.stdout

    def test_open_beads_exit_0(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        bin_dir = _write_fake_bd(
            tmp_path / "bin",
            [
                {"id": "EB-landed", "status": "open", "labels": []},
                {"id": "EB-picked", "status": "open", "labels": []},
                {"id": "EB-stranded", "status": "open", "labels": []},
            ],
        )
        assert _run_cli(git_repo, bin_dir).returncode == 0

    def test_bd_failure_exits_2_not_1(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        """An infra failure must not masquerade as a violation, or as clean."""
        bin_dir = _write_fake_bd(tmp_path / "bin", None, exit_code=1)
        result = _run_cli(git_repo, bin_dir)

        assert result.returncode == 2
        assert "ERROR" in result.stderr

    def test_malformed_bd_json_exits_2(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        bd = bin_dir / "bd"
        bd.write_text("#!/bin/sh\nprintf 'garbage'\n")
        bd.chmod(0o755)
        result = _run_cli(git_repo, bin_dir)

        assert result.returncode == 2
        assert "ERROR" in result.stderr

    def test_missing_integration_ref_exits_2(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        bin_dir = _write_fake_bd(
            tmp_path / "bin", [{"id": "EB-stranded", "status": "closed", "labels": []}]
        )
        result = _run_cli(git_repo, bin_dir, "--integration-ref", "no-such-ref")

        assert result.returncode == 2
        assert "ERROR" in result.stderr

    def test_json_output_shape(
        self, git_repo: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        bin_dir = _write_fake_bd(
            tmp_path / "bin",
            [
                {"id": "EB-landed", "status": "closed", "labels": []},
                {"id": "EB-picked", "status": "closed", "labels": []},
                {"id": "EB-stranded", "status": "closed", "labels": []},
            ],
        )
        result = _run_cli(git_repo, bin_dir, "--json")
        payload = json.loads(result.stdout)

        assert result.returncode == 1
        assert payload["integration_ref"] == "main"
        assert payload["branches_checked"] == 3
        assert payload["violation_count"] == 1
        assert payload["violations"] == [
            {
                "branch": "work/EB-stranded",
                "bead_id": "EB-stranded",
                "unlanded_commits": 2,
            }
        ]
        assert len(payload["branches"]) == 3


class TestFormatReport:
    def test_clean_report_names_the_branches_it_checked(self) -> None:
        states = [_state("EB-a", "closed", 0), _state("EB-b", "open", 3)]
        report = format_report(states, find_violations(states))
        assert "No closed bead has unlanded commits" in report
        assert "2 work branches" in report

    def test_violation_report_names_the_bead_and_the_commit_count(self) -> None:
        states = [_state("EB-a", "closed", 2)]
        report = format_report(states, find_violations(states))
        assert "EB-a" in report
        assert "work/EB-a" in report
        assert "2 unlanded commit" in report

    def test_violation_report_points_at_the_no_merge_escape_hatch(self) -> None:
        states = [_state("EB-a", "closed", 2)]
        report = format_report(states, find_violations(states))
        assert "--add-label no-merge" in report

    def test_no_branches_is_reported_distinctly_from_no_violations(self) -> None:
        """0 branches checked is not the same guarantee as 0 violations across N."""
        assert format_report([], []) == "No work branches found."
