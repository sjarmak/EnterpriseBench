"""Tests for configs/sg_indexing_list.json structure and generation script."""

import glob
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

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
        # Only the fields the generator guarantees for every entry.
        # Enrichment fields (_language/_loc_estimate/_tier) are hint-based
        # and validated separately in TestRepoEnrichment when present.
        required_fields = {
            "sg_name",
            "github_repo",
            "commit",
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
    """Validate LOC estimates, language, and tier classification.

    Enrichment fields are hint-based: the generator only emits them for
    repos present in its LANGUAGE_HINTS/LOC_HINTS tables. Entries without
    hints legitimately lack them, so these tests validate the fields when
    present rather than requiring them on every entry.
    """

    def test_language_valid_when_present(self, index_data: dict) -> None:
        # Floor guard: if LANGUAGE_HINTS drifts out of sync with github_repo
        # values, every entry loses _language and the loop below becomes
        # vacuous — require at least one enriched entry.
        assert any(
            "_language" in r for r in index_data["repos"]
        ), "No repo has _language — LANGUAGE_HINTS out of sync with index"
        for repo in index_data["repos"]:
            if "_language" in repo:
                lang = repo["_language"]
                assert (
                    isinstance(lang, str) and len(lang) > 0
                ), f"Repo {repo['sg_name']} has empty/null _language"

    def test_loc_estimate_positive_when_present(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            if "_loc_estimate" in repo:
                loc = repo["_loc_estimate"]
                assert (
                    isinstance(loc, int) and loc > 0
                ), f"Repo {repo['sg_name']} has invalid _loc_estimate: {loc}"

    def test_tier_paired_with_loc_estimate(self, index_data: dict) -> None:
        """The generator emits _tier and _loc_estimate together, never alone."""
        for repo in index_data["repos"]:
            assert ("_tier" in repo) == (
                "_loc_estimate" in repo
            ), f"Repo {repo['sg_name']} has _tier/_loc_estimate unpaired"

    def test_tier_matches_loc_range(self, index_data: dict) -> None:
        for repo in index_data["repos"]:
            if "_tier" not in repo:
                continue
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
        """Enriched repos must span all tiers (catches enrichment being
        dropped wholesale or collapsing to one tier)."""
        tiers = {r["_tier"] for r in index_data["repos"] if "_tier" in r}
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


@pytest.fixture(scope="module")
def generated_index(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the generator once, writing to a temp path (never the checked-in
    file), and return the parsed output."""
    out_path = tmp_path_factory.mktemp("sg_index") / "sg_indexing_list.json"
    result = subprocess.run(
        [sys.executable, GENERATE_SCRIPT, "--output", str(out_path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert out_path.exists(), "Generator did not write to the --output path"
    with open(out_path) as f:
        return json.load(f)


# Suites present in the checked-in index that the generator cannot produce
# (fa876ae backfill: their tasks have no configs/sg_mirrors/ files). Extending
# the backfill means adding the new suite here — the reverse-containment test
# below will fail loudly until you do, which is the point.
HAND_BACKFILLED_SUITES = {"customer_escalation", "platform_engineering"}


class TestGenerationScript:
    """Verify the generation script produces output consistent with the
    checked-in index.

    The checked-in file may carry hand-backfilled suites on top of what the
    generator produces (HAND_BACKFILLED_SUITES above), so suite comparison
    allows those exceptions. The contract is containment in BOTH directions:
    everything the generator produces must appear in the checked-in file, and
    everything checked-in (minus the known backfill) must be reproduced by
    the generator — a one-way subset check would pass vacuously if the
    generator silently dropped most of its output.
    """

    def test_generated_output_is_structurally_valid(
        self, generated_index: dict
    ) -> None:
        required = {
            "_description",
            "_generated",
            "_total_unique_repos",
            "_total_mirror_files",
            "suites",
            "repos",
        }
        assert required.issubset(set(generated_index.keys()))
        assert generated_index["_total_unique_repos"] == len(generated_index["repos"])
        assert len(generated_index["repos"]) > 0

    def test_generated_repos_all_present_in_checked_in(
        self, generated_index: dict, index_data: dict
    ) -> None:
        """Every generator-produced repo must exist in the checked-in index
        with the same source repo and pinned commit, AND every checked-in
        repo must be reproduced by the generator. Catches a stale checked-in
        index (new mirror file not reflected), silent rev drift, and a
        generator regression that silently drops repos (a one-way subset
        check passes vacuously on undercounts). No repos are hand-backfilled
        today; if that changes, add a HAND_BACKFILLED_REPOS allowlist
        mirroring the suites one."""
        checked_in = {r["sg_name"]: r for r in index_data["repos"]}
        problems = []
        for repo in generated_index["repos"]:
            name = repo["sg_name"]
            existing = checked_in.get(name)
            if existing is None:
                problems.append(f"{name}: missing from checked-in index")
                continue
            for field in ("github_repo", "commit"):
                if repo[field] != existing[field]:
                    problems.append(
                        f"{name}: {field} differs "
                        f"(generated={repo[field]!r}, "
                        f"checked-in={existing[field]!r})"
                    )
        generated_names = {r["sg_name"] for r in generated_index["repos"]}
        for name in checked_in.keys() - generated_names:
            problems.append(f"{name}: checked-in but not produced by generator")
        assert not problems, (
            "Checked-in index is stale or diverged; regenerate with "
            "scripts/generate_sg_index.py and re-apply manual entries:\n"
            + "\n".join(problems)
        )

    def test_generated_suites_match_checked_in_modulo_backfill(
        self, generated_index: dict, index_data: dict
    ) -> None:
        generated = set(generated_index["suites"])
        checked_in = set(index_data["suites"])
        assert generated, "Generator produced zero suites"
        missing = generated - checked_in
        assert not missing, f"Generator suites missing from checked-in: {missing}"
        dropped = checked_in - HAND_BACKFILLED_SUITES - generated
        assert not dropped, (
            f"Generator no longer produces checked-in suites {dropped} "
            "(not in the HAND_BACKFILLED_SUITES allowlist)"
        )

    def test_generator_does_not_modify_checked_in_index(self, tmp_path: Path) -> None:
        """Regression test: the test suite's generator invocation must never
        touch configs/sg_indexing_list.json (it used to clobber it)."""

        def digest() -> str:
            with open(INDEX_PATH, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()

        before = digest()
        result = subprocess.run(
            [
                sys.executable,
                GENERATE_SCRIPT,
                "--output",
                str(tmp_path / "out.json"),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert digest() == before, (
            "Generator modified configs/sg_indexing_list.json despite "
            "--output pointing elsewhere"
        )
