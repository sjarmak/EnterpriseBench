"""Tests for configs/sg_indexing_list.json structure and generation script."""

import json
import glob
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(ROOT, "configs", "sg_indexing_list.json")
MIRRORS_DIR = os.path.join(ROOT, "configs", "sg_mirrors")
GENERATE_SCRIPT = os.path.join(ROOT, "scripts", "generate_sg_index.py")


@pytest.fixture(scope="module")
def index_data() -> dict:
    with open(INDEX_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def mirror_files() -> list[dict]:
    results = []
    for path in sorted(glob.glob(os.path.join(MIRRORS_DIR, "*.json"))):
        with open(path) as f:
            results.append(json.load(f))
    return results


class TestIndexStructure:
    """Validate the top-level structure of sg_indexing_list.json."""

    def test_has_required_top_level_keys(self, index_data: dict) -> None:
        required = {
            "_description",
            "_generated",
            "_total_unique_repos",
            "_total_mirror_files",
            "suites",
            "repos",
        }
        assert required.issubset(set(index_data.keys()))

    def test_total_unique_repos_matches_repos_list(self, index_data: dict) -> None:
        assert index_data["_total_unique_repos"] == len(index_data["repos"])

    def test_repos_is_nonempty_list(self, index_data: dict) -> None:
        assert isinstance(index_data["repos"], list)
        assert len(index_data["repos"]) > 0

    def test_suites_is_dict(self, index_data: dict) -> None:
        assert isinstance(index_data["suites"], dict)


class TestRepoEntries:
    """Validate individual repo entries."""

    def test_every_repo_has_required_fields(self, index_data: dict) -> None:
        required_fields = {
            "sg_name",
            "github_repo",
            "commit",
            "_language",
            "_loc_estimate",
            "_tier",
            "_indexed",
            "_task_count",
        }
        for repo in index_data["repos"]:
            missing = required_fields - set(repo.keys())
            assert (
                not missing
            ), f"Repo {repo.get('sg_name', '?')} missing fields: {missing}"

    def test_sg_name_starts_with_prefix(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            assert repo["sg_name"].startswith(
                "sg-evals/"
            ), f"sg_name must start with 'sg-evals/': {repo['sg_name']}"

    def test_task_count_is_positive(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            assert (
                repo["_task_count"] >= 1
            ), f"Repo {repo['sg_name']} has task_count < 1"

    def test_indexed_is_boolean(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            assert isinstance(
                repo["_indexed"], bool
            ), f"Repo {repo['sg_name']} _indexed is not bool"

    def test_no_duplicate_sg_names(self, index_data: dict) -> None:
        names = [r["sg_name"] for r in index_data["repos"]]
        assert len(names) == len(set(names)), "Duplicate sg_name entries found"

    def test_repos_sorted_by_sg_name(self, index_data: dict) -> None:
        names = [r["sg_name"] for r in index_data["repos"]]
        assert names == sorted(names), "Repos not sorted by sg_name"


class TestRepoEnrichment:
    """Validate LOC estimates, language, and tier classification."""

    def test_language_populated(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            lang = repo.get("_language")
            assert (
                lang and isinstance(lang, str) and len(lang) > 0
            ), f"Repo {repo['sg_name']} has empty/null _language"

    def test_loc_estimate_positive(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            loc = repo.get("_loc_estimate")
            assert (
                isinstance(loc, int) and loc > 0
            ), f"Repo {repo['sg_name']} has invalid _loc_estimate: {loc}"

    def test_tier_valid(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            tier = repo.get("_tier")
            assert tier in {
                "A",
                "B",
                "C",
            }, f"Repo {repo['sg_name']} has invalid _tier: {tier}"

    def test_tier_matches_loc_range(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            loc = repo["_loc_estimate"]
            tier = repo["_tier"]
            if loc > 500_000:
                expected = "A"
            elif loc >= 100_000:
                expected = "B"
            else:
                expected = "C"
            assert tier == expected, (
                f"Repo {repo['sg_name']}: tier {tier} does not match "
                f"LOC {loc} (expected {expected})"
            )

    def test_tier_distribution_reasonable(self, index_data: dict) -> None:
        """Ensure we have repos across all tiers (not all one tier)."""
        tiers = {repo["_tier"] for repo in index_data["repos"]}
        assert tiers == {"A", "B", "C"}, f"Expected all tiers A/B/C, got {tiers}"


class TestSuiteSummaries:
    """Validate per-suite summary entries."""

    def test_suite_has_required_fields(self, index_data: dict) -> None:
        required = {"_status", "_indexed_count", "_repo_count", "_task_count"}
        for name, suite in index_data["suites"].items():
            missing = required - set(suite.keys())
            assert not missing, f"Suite '{name}' missing fields: {missing}"

    def test_suite_repo_counts_positive(self, index_data: dict) -> None:
        for name, suite in index_data["suites"].items():
            assert suite["_repo_count"] > 0, f"Suite '{name}' has 0 repos"


class TestMirrorCoverage:
    """Ensure every mirror file is represented in the index."""

    def test_all_mirror_repos_in_index(
        self, index_data: dict, mirror_files: list[dict]
    ) -> None:
        index_sg_names = {r["sg_name"] for r in index_data["repos"]}
        missing = []
        for mf in mirror_files:
            for m in mf.get("mirrors", []):
                sg_name = f"sg-evals/{m['mirror_id']}"
                if sg_name not in index_sg_names:
                    missing.append(sg_name)
        assert not missing, f"Mirror repos missing from index: {missing}"

    def test_total_mirror_files_matches(
        self, index_data: dict, mirror_files: list[dict]
    ) -> None:
        assert index_data["_total_mirror_files"] == len(mirror_files)


class TestCrossReferences:
    """Validate cross-reference fields."""

    def test_suites_field_is_sorted(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            if "_suites" in repo:
                assert repo["_suites"] == sorted(
                    repo["_suites"]
                ), f"Repo {repo['sg_name']} _suites not sorted"


class TestGenerationScript:
    """Verify the generation script produces consistent output."""

    def test_script_runs_without_error(self) -> None:
        result = subprocess.run(
            [sys.executable, GENERATE_SCRIPT],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

    def test_script_output_matches_checked_in(self, index_data: dict) -> None:
        """Re-generate and verify it matches what's on disk."""
        result = subprocess.run(
            [sys.executable, GENERATE_SCRIPT],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        with open(INDEX_PATH) as f:
            regenerated = json.load(f)

        # Compare everything except _generated date
        index_copy = {k: v for k, v in index_data.items() if k != "_generated"}
        regen_copy = {k: v for k, v in regenerated.items() if k != "_generated"}
        assert (
            index_copy == regen_copy
        ), "Regenerated index differs from checked-in version"
