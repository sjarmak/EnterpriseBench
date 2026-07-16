"""Tests for the path_match precision-aware file-matching primitive.

Guards EnterpriseBench-6py4v: the required_files pattern was recall-only, so a
guess/listing shotgun scored 1.00 without reading the repo. Each documented
bypass must now score < 0.5 (the checkpoint pass threshold), while a genuine
targeted answer still scores 1.0.

Bypasses reproduced here against the two ground-truth files from
ansible-galaxy-tar-regression-prove-001:
  R = ["lib/ansible/galaxy/collection/__init__.py",
       "lib/ansible/galaxy/collection/concrete_artifact_manager.py"]
"""

from __future__ import annotations

import pytest

from eb_verify.plugins.path_match import (
    is_plausible_path,
    path_match_score,
    valid_claimed_paths,
)


R = [
    "lib/ansible/galaxy/collection/__init__.py",
    "lib/ansible/galaxy/collection/concrete_artifact_manager.py",
]


# -- is_plausible_path -------------------------------------------------------


class TestIsPlausiblePath:
    def test_accepts_a_normal_path(self):
        assert is_plausible_path("lib/ansible/galaxy/collection/__init__.py")

    def test_accepts_a_bare_filename(self):
        assert is_plausible_path("concrete_artifact_manager.py")

    def test_rejects_embedded_space(self):
        assert not is_plausible_path("lib/a/__init__.py lib/b/manager.py")

    def test_rejects_newline(self):
        assert not is_plausible_path("lib/a/__init__.py\nlib/b/manager.py")

    def test_rejects_tab(self):
        assert not is_plausible_path("lib/a.py\tlib/b.py")

    def test_rejects_empty_and_blank(self):
        assert not is_plausible_path("")
        assert not is_plausible_path("   ")

    def test_rejects_oversize(self):
        assert not is_plausible_path("a/" * 400 + "x.py")  # > 512 chars

    def test_rejects_absurd_separator_count(self):
        assert not is_plausible_path("/".join(["x"] * 60))

    def test_rejects_non_string(self):
        assert not is_plausible_path(None)
        assert not is_plausible_path(123)


# -- valid_claimed_paths -----------------------------------------------------


class TestValidClaimedPaths:
    def test_strips_and_dedups_order_preserving(self):
        claimed = [" a/b.py ", "a/b.py", "c/d.py"]
        assert valid_claimed_paths(claimed) == ["a/b.py", "c/d.py"]

    def test_drops_blob_entries(self):
        claimed = ["a/b.py", "junk with spaces", "c/d.py"]
        assert valid_claimed_paths(claimed) == ["a/b.py", "c/d.py"]

    def test_non_list_returns_empty(self):
        assert valid_claimed_paths("a/b.py") == []
        assert valid_claimed_paths(None) == []


# -- path_match_score: genuine answers (negative controls) -------------------


class TestGenuineAnswers:
    def test_exact_targeted_answer_scores_1(self):
        assert path_match_score(list(R), R) == 1.0

    def test_repo_relative_suffix_matches_symmetrically(self):
        # Agent gives repo-relative paths (workspace-stripped); still 1.0.
        claimed = [
            "galaxy/collection/__init__.py",
            "galaxy/collection/concrete_artifact_manager.py",
        ]
        assert path_match_score(claimed, R) == 1.0

    def test_bare_basename_matches(self):
        claimed = ["__init__.py", "concrete_artifact_manager.py"]
        # Both bare filenames are segment-suffix matches; clean 2/2.
        assert path_match_score(claimed, R) == 1.0

    def test_small_over_listing_still_passes(self):
        claimed = R + ["lib/ansible/galaxy/collection/galaxy_api.py"]
        # 2 found / max(2, 3) = 0.667 — small over-listing tolerated.
        assert path_match_score(claimed, R) == pytest.approx(2 / 3)
        assert path_match_score(claimed, R) >= 0.5


# -- path_match_score: the documented bypasses (must score < 0.5) ------------


class TestBypassesKilled:
    def test_guess_shotgun_fails(self):
        # 24 brute-forced plausible paths for 2 GT -> 2/24 = 0.083.
        stems = [
            "lib/ansible/galaxy/collection",
            "lib/ansible/galaxy",
            "lib/ansible/utils",
        ]
        leaves = [
            "__init__.py",
            "concrete_artifact_manager.py",
            "galaxy_api.py",
            "gpg.py",
            "collection.py",
            "role.py",
            "api.py",
            "token.py",
        ]
        shotgun = [f"{s}/{leaf}" for s in stems for leaf in leaves]  # 24 paths
        assert len(shotgun) == 24
        score = path_match_score(shotgun, R)
        assert score == pytest.approx(2 / 24)
        assert score < 0.5

    def test_find_dump_as_one_string_fails(self):
        # A `find` listing submitted as ONE path string (newlines) -> dropped.
        blob = "\n".join(
            [
                "lib/ansible/galaxy/collection/__init__.py",
                "lib/ansible/galaxy/collection/concrete_artifact_manager.py",
                "lib/ansible/module_utils/basic.py",
            ]
        )
        assert path_match_score([blob], R) == 0.0

    def test_find_dump_as_many_entries_fails(self):
        # The stronger exploit: 1567 real paths as separate entries. Precision
        # denominator crushes it: 2 / max(2, 1567).
        big = [f"lib/ansible/module_utils/f{i}.py" for i in range(1565)] + R
        score = path_match_score(big, R)
        assert score == pytest.approx(2 / 1567)
        assert score < 0.5

    def test_concat_without_space_fails(self):
        # Both GT paths concatenated with no separator -> one entry, valid
        # shape, but segment-alignment finds neither.
        concat = R[0] + R[1]
        assert path_match_score([concat], R) == 0.0

    def test_free_text_blob_fails(self):
        # A notes blob mentioning both substrings is one whitespace-laden entry.
        blob = (
            "random notes lib/ansible/galaxy/collection/__init__.py more notes "
            "lib/ansible/galaxy/collection/concrete_artifact_manager.py end"
        )
        assert path_match_score([blob], R) == 0.0


# -- path_match_score: located citations (path:line / #Lnnn / ::sym) ---------


class TestLocatorSuffixes:
    def test_colon_line_still_matches(self):
        claimed = [
            "lib/ansible/galaxy/collection/__init__.py:42",
            "lib/ansible/galaxy/collection/concrete_artifact_manager.py:100",
        ]
        assert path_match_score(claimed, R) == 1.0

    def test_github_hash_line_still_matches(self):
        # GitHub / Sourcegraph blob anchors (#L120, #L120-L140).
        claimed = [R[0] + "#L42", R[1] + "#L120-L140"]
        assert path_match_score(claimed, R) == 1.0

    def test_line_and_column_still_matches(self):
        # rustc / ripgrep --vimgrep style path:line:col.
        claimed = [R[0] + ":42:5", R[1] + ":100:12"]
        assert path_match_score(claimed, R) == 1.0

    def test_locator_only_stripped_from_last_segment(self):
        # A colon-number inside a directory name is not a trailing locator.
        assert path_match_score(["a/b:1/c.py"], ["a/b:1/c.py"]) == 1.0


# -- path_match_score: sufficient (GT-blessed) files are neutral --------------


class TestSufficientFilesNeutral:
    SUF = ["src/flask/app.py"]
    REQ = ["src/flask/blueprints.py", "src/flask/sansio/scaffold.py"]

    def test_citing_sufficient_file_is_not_penalised(self):
        # Both required + one sufficient file: sufficient is excluded from the
        # denominator, so a thorough correct answer stays at 1.0.
        claimed = self.REQ + ["src/flask/app.py"]
        assert path_match_score(claimed, self.REQ, sufficient=self.SUF) == 1.0

    def test_sufficient_does_not_rescue_a_shotgun(self):
        # Unblessed junk still penalises; sufficient only exempts blessed files.
        claimed = self.REQ + ["src/flask/app.py", "x/y.py", "x/z.py"]
        # effective = 2 required + 2 junk = 4 (app.py dropped); 2/4 = 0.5.
        assert path_match_score(claimed, self.REQ, sufficient=self.SUF) == pytest.approx(0.5)

    def test_sufficient_not_required_to_be_found(self):
        # Citing only the required files (not the sufficient) still scores 1.0.
        assert path_match_score(self.REQ, self.REQ, sufficient=self.SUF) == 1.0

    def test_path_matching_both_required_and_sufficient_counts_as_found(self):
        # Degenerate overlap: a path in both lists is found, not neutralised.
        assert path_match_score(["a/b.py"], ["a/b.py"], sufficient=["a/b.py"]) == 1.0


# -- path_match_score: ambiguous basename must NOT claim several required -----


class TestAmbiguousBasenameNotCredited:
    # Regression guard: a single vague basename shared by multiple required
    # files must not be credited to all of them (would let one no-repo-read
    # guess score 1.0). Real GTs in this repo have colliding basenames.
    DUAL = ["hyper/Cargo.toml", "tokio/tokio/Cargo.toml"]
    TRI = ["tonic/tonic/Cargo.toml", "hyper/Cargo.toml", "tokio/tokio/Cargo.toml"]

    def test_lone_ambiguous_basename_scores_zero(self):
        assert path_match_score(["Cargo.toml"], self.DUAL) == 0.0

    def test_lone_ambiguous_basename_zero_tri(self):
        assert path_match_score(["Cargo.toml"], self.TRI) == 0.0

    def test_distinct_repo_qualified_paths_score_full(self):
        assert path_match_score(list(self.DUAL), self.DUAL) == 1.0

    def test_ambiguous_client_py_across_repos(self):
        req = ["httpx/httpx/_client.py", "httpcore/httpcore/_client.py"]
        assert path_match_score(["_client.py"], req) == 0.0


# -- path_match_score: accepted partial credit (HIGH-3, not a bypass) ---------


class TestAcceptedPartialCredit:
    def test_slash_joined_two_paths_scores_partial_not_full(self):
        # "path1/path2" segment-aligns to path2 only -> 1 of 2 -> 0.5. This is
        # the same partial credit an honest one-of-two answer earns, so it is
        # accepted behavior, not a full-credit bypass.
        joined = R[0] + "/" + R[1]
        score = path_match_score([joined], R)
        assert score == pytest.approx(0.5)
        assert score < 1.0


# -- path_match_score: edge cases --------------------------------------------


class TestEdges:
    def test_empty_required_is_full_credit(self):
        assert path_match_score(["anything.py"], []) == 1.0

    def test_empty_claimed_with_required_is_zero(self):
        assert path_match_score([], R) == 0.0

    def test_both_empty_is_full_credit_no_zero_division(self):
        # required empty short-circuits before the denominator -> no ZeroDivision.
        assert path_match_score([], []) == 1.0

    def test_malformed_required_raises(self):
        # required must be pre-extracted to str. A non-empty list of dicts is
        # malformed GT -> fail loud, never silently score 1.0.
        with pytest.raises(ValueError):
            path_match_score(list(R), [{"path": R[0]}])

    def test_partial_recall(self):
        claimed = [R[0]]  # only one of two
        assert path_match_score(claimed, R) == pytest.approx(0.5)

    def test_substring_only_does_not_match(self):
        # Old recall bug: gt in claimed. "collection/__init__.py" is a substring
        # of a longer unrelated segment but NOT segment-aligned -> no match.
        claimed = ["lib/other/xcollection/y__init__.py"]
        assert path_match_score(claimed, [R[0]]) == 0.0
