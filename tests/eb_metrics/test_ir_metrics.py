"""Tests for the ported CSB retrieval-quality metrics (eb_metrics.ir_metrics).

These lock the port's fidelity to CodeScaleBench ``ir_metrics.py`` — in
particular the empty-set asymmetry, the ``precision@k`` fixed-``k``
denominator, and the multi-repo path normalization that lets
``repo::path`` ground truth match ``/workspace/<repo>/...`` retrieved paths.
"""

from __future__ import annotations

import math

import pytest

from eb_metrics.ir_metrics import (
    compute_ir_scores,
    context_efficiency,
    f1_at_k,
    file_level_recall,
    mean_average_precision,
    mrr,
    ndcg_at_k,
    normalize_path,
    precision_at_k,
    recall_at_k,
)


# ---------------------------------------------------------------------------
# normalize_path — multi-repo path canonicalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("kubernetes::pkg/kubelet/prober/worker.go", "pkg/kubelet/prober/worker.go"),
        ("/workspace/kubernetes/pkg/kubelet/prober/worker.go", "pkg/kubelet/prober/worker.go"),
        ("workspace/grafana/public/app/x.ts", "public/app/x.ts"),
        ("chromium--2d05e315/third_party/blink/x.cc", "third_party/blink/x.cc"),
        ("a/pkg/server/main.go", "pkg/server/main.go"),
        ("b/lib/util.py", "lib/util.py"),
        ("  /Src/Main.PY  ", "src/main.py"),  # strip + lowercase
    ],
)
def test_normalize_path_canonicalizes(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


def test_normalize_keeps_code_dir_lead() -> None:
    # 'src' is in the _CODE_DIRS allowlist, so it is NOT stripped as a repo name.
    assert normalize_path("src/server/handler.go") == "src/server/handler.go"


def test_normalize_strips_non_code_dir_lead() -> None:
    # 'kubernetes' is not a code dir → the leading repo segment is stripped.
    assert normalize_path("kubernetes/pkg/kubelet/x.go") == "pkg/kubelet/x.go"


def test_normalize_matches_when_repo_relative_leads_with_code_dir() -> None:
    # When the repo-relative path leads with a _CODE_DIRS segment (kept, not
    # stripped), a repo::path GT and a /workspace/<repo>/ retrieved path
    # canonicalize to the SAME value → they match.
    gt = normalize_path("kubernetes::pkg/kubelet/prober/worker.go")
    ret = normalize_path("/workspace/kubernetes/pkg/kubelet/prober/worker.go")
    assert gt == ret == "pkg/kubelet/prober/worker.go"


def test_normalize_known_limitation_non_code_dir_lead() -> None:
    """Inherited CSB limitation: repos whose relative paths lead with a
    non-code dir (grafana → ``public/``) do NOT round-trip symmetrically.

    ``repo::`` GT drops the ``::`` then over-strips ``public``; the
    ``/workspace/<repo>/`` retrieved path strips only the repo. The single
    leading-segment strip leaves them one level apart. Ported verbatim from
    CSB ``_normalize`` — pinned here so the fragility is visible, not a
    silent recall undercount. (Improving this is a flagged follow-up.)
    """
    gt = normalize_path("grafana::public/app/plugins/datasource/jaeger/x.ts")
    ret = normalize_path("/workspace/grafana/public/app/plugins/datasource/jaeger/x.ts")
    assert gt == "app/plugins/datasource/jaeger/x.ts"
    assert ret == "public/app/plugins/datasource/jaeger/x.ts"
    assert gt != ret  # the documented mismatch


# ---------------------------------------------------------------------------
# Core @k metrics — formulas and denominators
# ---------------------------------------------------------------------------


def test_precision_at_k_divides_by_k_not_len() -> None:
    # 3 retrieved, all relevant, k=10 → 3/10, NOT 3/3.
    retrieved = ["a.py", "b.py", "c.py"]
    relevant = {"a.py", "b.py", "c.py"}
    assert precision_at_k(retrieved, relevant, 10) == 0.3
    assert precision_at_k(retrieved, relevant, 3) == 1.0


def test_recall_at_k_is_found_over_relevant() -> None:
    retrieved = ["a.py", "x.py"]
    relevant = {"a.py", "b.py"}
    assert recall_at_k(retrieved, relevant, 5) == 0.5


def test_f1_at_k_harmonic_mean() -> None:
    retrieved = ["a.py", "x.py"]
    relevant = {"a.py", "b.py"}
    p = precision_at_k(retrieved, relevant, 2)  # 1/2
    r = recall_at_k(retrieved, relevant, 2)  # 1/2
    assert f1_at_k(retrieved, relevant, 2) == pytest.approx(2 * p * r / (p + r))


def test_mrr_reciprocal_rank_of_first_hit() -> None:
    assert mrr(["x.py", "y.py", "a.go"], {"a.go"}) == pytest.approx(1 / 3)
    assert mrr(["a.go"], {"a.go"}) == 1.0
    assert mrr(["x.py"], {"a.go"}) == 0.0


def test_ndcg_perfect_and_partial() -> None:
    relevant = {"a.py", "b.py"}
    # Both relevant items first → perfect nDCG.
    assert ndcg_at_k(["a.py", "b.py"], relevant, 2) == pytest.approx(1.0)
    # One relevant at rank 2 only.
    dcg = 1.0 / math.log2(3)
    idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
    assert ndcg_at_k(["x.py", "a.py"], relevant, 2) == pytest.approx(dcg / idcg)


def test_map_single_query_average_precision() -> None:
    # hits at ranks 1 and 3 of 2 relevant → (1/1 + 2/3) / 2.
    retrieved = ["a.py", "x.py", "b.py"]
    relevant = {"a.py", "b.py"}
    assert mean_average_precision(retrieved, relevant) == pytest.approx((1.0 + 2 / 3) / 2)


# ---------------------------------------------------------------------------
# Empty-set asymmetry — must be preserved verbatim from CSB
# ---------------------------------------------------------------------------


def test_empty_relevant_set_asymmetry() -> None:
    retrieved = ["a.py"]
    empty: set[str] = set()
    # recall-family → 1.0 (nothing to miss); precision/nDCG → 0.0.
    assert recall_at_k(retrieved, empty, 5) == 1.0
    assert file_level_recall(retrieved, empty) == 1.0
    assert mean_average_precision(retrieved, empty) == 1.0
    assert precision_at_k(retrieved, empty, 5) == 0.0
    assert ndcg_at_k(retrieved, empty, 5) == 0.0


def test_empty_retrieved_set() -> None:
    relevant = {"a.py"}
    assert recall_at_k([], relevant, 5) == 0.0
    assert precision_at_k([], relevant, 5) == 0.0
    assert file_level_recall([], relevant) == 0.0
    assert context_efficiency([], relevant) == 0.0
    assert mrr([], relevant) == 0.0


def test_zero_intersection() -> None:
    assert file_level_recall(["x.py"], {"a.py"}) == 0.0
    assert context_efficiency(["x.py"], {"a.py"}) == 0.0
    assert f1_at_k(["x.py"], {"a.py"}, 5) == 0.0


# ---------------------------------------------------------------------------
# compute_ir_scores — end-to-end, realistic multi-repo
# ---------------------------------------------------------------------------


def test_compute_ir_scores_multi_repo_match() -> None:
    gt = [
        "kubernetes::pkg/kubelet/prober/worker.go",
        "kubernetes::pkg/kubelet/prober/worker_test.go",
    ]
    retrieved = [
        "/workspace/kubernetes/pkg/kubelet/prober/worker.go",
        "/workspace/kubernetes/README.md",
    ]
    s = compute_ir_scores(retrieved, gt, "err-prov-04", "baseline")

    assert s.n_ground_truth == 2
    assert s.n_retrieved == 2
    assert s.n_overlap == 1
    assert s.file_recall == 0.5
    assert s.context_efficiency == 0.5
    assert s.recall[10] == 0.5
    assert s.precision[10] == 0.1  # 1 hit / k=10
    # Everything rounded to 4 dp and dict-keyed by the default k set.
    assert set(s.precision) == {1, 3, 5, 10}


def test_compute_ir_scores_dedup_ground_truth_by_normalized_form() -> None:
    # Two GT entries that normalize to the same path collapse in the set.
    gt = ["kubernetes::pkg/a.go", "/workspace/kubernetes/pkg/a.go"]
    s = compute_ir_scores(["pkg/a.go"], gt, "t", "c")
    assert s.n_ground_truth == 1
    assert s.file_recall == 1.0


def test_compute_ir_scores_to_dict_roundtrip() -> None:
    s = compute_ir_scores(["a.py"], ["a.py"], "t", "c")
    d = s.to_dict()
    assert d["file_recall"] == 1.0
    assert d["n_overlap"] == 1
    assert set(d["recall"]) == {1, 3, 5, 10}
