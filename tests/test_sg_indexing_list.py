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

sys.path.insert(0, os.path.join(ROOT, "scripts", "infra"))
from mirror_naming import GITHUB_REPO_NAME_RE, derive_mirror_name  # noqa: E402


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

    def test_no_malformed_sg_names(self, index_data: dict) -> None:
        """Regression (EnterpriseBench-p6ms): four 2026-04-03 mirror files
        embedded the sg-evals/ prefix inside mirror_id (yielding
        sg-evals/sg-evals/* garbage) and one archived-task placeholder
        produced sg-evals/unknown/repo--HEAD. Neither shape may reappear."""
        bad = [
            r["sg_name"]
            for r in index_data["repos"]
            if r["sg_name"].startswith("sg-evals/sg-evals/")
            or r["sg_name"].startswith("sg-evals/unknown/")
        ]
        assert not bad, f"Malformed sg_name entries in index: {bad}"

    def test_sg_name_has_exactly_one_path_segment_after_prefix(
        self, index_data: dict
    ) -> None:
        """Regression (EnterpriseBench-k9po): the index's sg_name convention
        was sg-evals/{org}/{repo}--{rev} for all 133 entries, embedding the
        org — but real sg-evals mirrors drop the org (sg-evals/{repo}--{rev}).
        General shape check, not just the two specific garbage patterns
        test_no_malformed_sg_names already knew about."""
        bad = [
            r["sg_name"]
            for r in index_data["repos"]
            if r["sg_name"].removeprefix("sg-evals/").count("/") != 0
        ]
        assert not bad, f"sg_name embeds extra path segments (org?): {bad}"

    def test_sg_name_matches_derivation(self, index_data: dict) -> None:
        """Positive check: sg_name must equal what derive_mirror_name()
        computes from github_repo + commit — the actual convention
        create_sg_mirrors.py uses when creating mirrors on GitHub."""
        for repo in index_data["repos"]:
            expected = derive_mirror_name(repo["github_repo"], repo["commit"])
            assert (
                repo["sg_name"] == expected
            ), f"{repo['sg_name']} does not match derived name {expected}"

    def test_sg_name_suffix_is_a_legal_github_repo_name(self, index_data: dict) -> None:
        """Non-tautological companion to test_sg_name_matches_derivation:
        re-deriving from a bad input (e.g. an unresolved `<sha>~1` rev) would
        still round-trip green against itself. This instead checks the
        result is an actually creatable GitHub repo name — the same
        validation create_sg_mirrors.py applies before creating a mirror
        (EnterpriseBench-k9po: 5 mirror files pinned unresolved `~1` revs,
        which produce a `~` here and must fail this check)."""
        bad = [
            r["sg_name"]
            for r in index_data["repos"]
            if not GITHUB_REPO_NAME_RE.match(r["sg_name"].removeprefix("sg-evals/"))
        ]
        assert not bad, f"sg_name is not a legal GitHub repo name: {bad}"

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

    def test_every_repo_is_enriched(self, index_data: dict) -> None:
        """Every repo in the index must carry _language/_loc_estimate/_tier.
        The generator's hint tables claim full coverage ("Every repo in the
        index must have an entry here"); this makes the claim enforceable.
        Adding a mirror for a new repo requires adding LANGUAGE_HINTS and
        LOC_HINTS entries in scripts/generate_sg_index.py."""
        unenriched = [
            r["sg_name"]
            for r in index_data["repos"]
            if not {"_language", "_loc_estimate", "_tier"} <= set(r.keys())
        ]
        assert not unenriched, (
            "Repos missing enrichment (add LANGUAGE_HINTS/LOC_HINTS entries "
            f"in scripts/generate_sg_index.py): {unenriched}"
        )

    def test_corrected_mirror_repos_present_and_enriched(
        self, index_data: dict
    ) -> None:
        """Regression (EnterpriseBench-p6ms): the four repaired mirror_ids
        must appear under their canonical sg-evals/{repo}--{rev} names
        (org dropped, per EnterpriseBench-k9po) with enrichment fields."""
        expected = {
            "sg-evals/containerd--v1.7.24",
            "sg-evals/alertmanager--v0.26.0",
            "sg-evals/charts--redis-ha-4.26.6",
            "sg-evals/knftables--v0.0.17",
        }
        by_name = {r["sg_name"]: r for r in index_data["repos"]}
        missing = expected - set(by_name)
        assert not missing, f"Corrected mirror repos missing from index: {missing}"
        for name in expected:
            fields = {"_language", "_loc_estimate", "_tier"} - set(by_name[name])
            assert not fields, f"{name} missing enrichment fields: {fields}"

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
                sg_name = derive_mirror_name(m["repo"], m["rev"])
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


# Suites whose entries were hand-backfilled (fa876ae) from task sets that are
# not reproducible from this branch's benchmarks tree. The generator carries
# them over verbatim from the checked-in index; import its constant directly
# so the test set cannot drift from the script's (a hand-copied duplicate
# would silently stop exercising content equality for a drifted suite).
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from generate_sg_index import (  # noqa: E402
    BACKFILLED_SUITES as CARRIED_BACKFILL_SUITES,
)


class TestGenerationScript:
    """Verify the generation script produces output consistent with the
    checked-in index.

    The generator derives most content from configs/sg_mirrors/ and carries
    the CARRIED_BACKFILL_SUITES over from the checked-in index verbatim, so
    generate -> write reproduces the full checked-in file. The contract is
    containment in BOTH directions: everything the generator produces must
    appear in the checked-in file, and everything checked-in must be
    reproduced by the generator — a one-way subset check would pass vacuously
    if the generator silently dropped most of its output.
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

    def test_generated_suites_match_checked_in(
        self, generated_index: dict, index_data: dict
    ) -> None:
        generated = set(generated_index["suites"])
        checked_in = set(index_data["suites"])
        assert generated, "Generator produced zero suites"
        assert generated == checked_in, (
            "Generated suite set diverged from checked-in: "
            f"only-generated={generated - checked_in}, "
            f"only-checked-in={checked_in - generated}"
        )

    def test_carried_backfill_suites_survive_regeneration(
        self, generated_index: dict, index_data: dict
    ) -> None:
        """The fa876ae backfilled suites must be carried over by the
        generator with content identical to the checked-in index — any
        delta means the carry-over silently mutated hand-curated data."""
        for suite in sorted(CARRIED_BACKFILL_SUITES):
            assert (
                suite in generated_index["suites"]
            ), f"Backfilled suite '{suite}' missing from generated output"
            assert generated_index["suites"][suite] == index_data["suites"][suite], (
                f"Backfilled suite '{suite}' content changed across "
                "regeneration (carry-over must be verbatim)"
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
