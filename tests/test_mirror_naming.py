"""Tests for scripts/infra/mirror_naming.py.

Single source of truth for the sg-evals mirror-naming formula, extracted
because it had drifted into 5 independent copies (EnterpriseBench-k9po).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "infra"))

from mirror_naming import GITHUB_REPO_NAME_RE, derive_mirror_name  # noqa: E402


class TestDeriveMirrorName:
    def test_tag_rev_used_as_is(self) -> None:
        assert (
            derive_mirror_name("github.com/ansible/ansible", "v2.16.0")
            == "sg-evals/ansible--v2.16.0"
        )

    def test_hash_rev_truncated_to_eight_chars(self) -> None:
        assert (
            derive_mirror_name(
                "github.com/zulip/zulip", "38053e9c7cc59b5e3f7c26af49fc1bb57acf0b86"
            )
            == "sg-evals/zulip--38053e9c"
        )

    def test_org_dropped_not_just_scheme(self) -> None:
        """The whole point of this bug: only the repo name survives, not org/repo."""
        assert (
            derive_mirror_name("github.com/FasterXML/jackson-databind", "v1.0.0")
            == "sg-evals/jackson-databind--v1.0.0"
        )

    def test_strips_scheme_and_git_suffix(self) -> None:
        assert (
            derive_mirror_name("https://github.com/ansible/ansible.git", "v2.16.0")
            == "sg-evals/ansible--v2.16.0"
        )

    def test_ref_suffix_slash_replaced_with_underscore(self) -> None:
        assert (
            derive_mirror_name("github.com/apache/gecko-dev", "releases/gecko-1.2")
            == "sg-evals/gecko-dev--releases_gecko-1.2"
        )

    def test_full_sha_truncates_even_when_mirror_file_stored_it_full(self) -> None:
        """Regression: configs/sg_mirrors/support-map-libreoffice-formula-007.json
        stored the full 40-char SHA in mirror_id, but the real GitHub mirror
        (verified via `gh repo view`) uses the 8-char truncated form."""
        assert (
            derive_mirror_name(
                "github.com/LibreOffice/core",
                "61f8fb648ecf9a20ee8abec0e8d3fad3e666db5e",
            )
            == "sg-evals/core--61f8fb64"
        )

    def test_p6ms_corrected_mirrors_match_real_github_names(self) -> None:
        """Regression (EnterpriseBench-p6ms): these 4 were previously malformed
        as sg-evals/sg-evals/* or dropped their rev. Verified live against the
        sg-evals GitHub org."""
        cases = [
            (
                "github.com/containerd/containerd",
                "v1.7.24",
                "sg-evals/containerd--v1.7.24",
            ),
            (
                "github.com/prometheus/alertmanager",
                "v0.26.0",
                "sg-evals/alertmanager--v0.26.0",
            ),
            (
                "github.com/dandydeveloper/charts",
                "redis-ha-4.26.6",
                "sg-evals/charts--redis-ha-4.26.6",
            ),
            (
                "github.com/kubernetes-sigs/knftables",
                "v0.0.17",
                "sg-evals/knftables--v0.0.17",
            ),
        ]
        for github_repo, rev, expected in cases:
            assert derive_mirror_name(github_repo, rev) == expected

    def test_k9po_corrected_stale_tilde_mirrors_match_real_github_names(self) -> None:
        """Regression (EnterpriseBench-k9po): these 5 mirror files pinned
        unresolved `<sha>~1` revs, which produce unrepresentable GitHub names.
        Fixed to the resolved SHA from configs/runs/mirror_creation_manifest.json;
        verified live against the sg-evals GitHub org."""
        cases = [
            (
                "github.com/bitnami/charts",
                "130ffd163382dffd5762034291203a3ac2792fba",
                "sg-evals/charts--130ffd16",
            ),
            (
                "github.com/bitnami/charts",
                "478a81c9e91d2c2cf867e70aeea81e10cbcab9ce",
                "sg-evals/charts--478a81c9",
            ),
            (
                "github.com/projectcalico/calico",
                "70ebb8c4fd8cd32233afce241f013d484b4bb860",
                "sg-evals/calico--70ebb8c4",
            ),
            (
                "github.com/keycloak/keycloak",
                "c8428c040a896696d9d0e99b37df509e59c6c7a4",
                "sg-evals/keycloak--c8428c04",
            ),
            (
                "github.com/keycloak/keycloak",
                "6fd372cbe60dff025c30da9d69da00f74097b1b9",
                "sg-evals/keycloak--6fd372cb",
            ),
        ]
        for github_repo, rev, expected in cases:
            assert derive_mirror_name(github_repo, rev) == expected


class TestGithubRepoNameRegex:
    """Non-tautological invariant: a name derive_mirror_name() produces must
    actually be a legal GitHub repo name, or the "fix" just bakes in a new
    unrepresentable name (as the stale `~1` revs did before correction)."""

    def test_valid_names_match(self) -> None:
        assert GITHUB_REPO_NAME_RE.match("ansible--v2.16.0")
        assert GITHUB_REPO_NAME_RE.match("zulip--38053e9c")
        assert GITHUB_REPO_NAME_RE.match("charts--redis-ha-4.26.6")

    def test_tilde_notation_does_not_match(self) -> None:
        """The exact defect this bead fixes: unresolved `<sha>~1` revs
        produce a `~` in the name, which GitHub rejects."""
        assert not GITHUB_REPO_NAME_RE.match("charts--36231~1")
