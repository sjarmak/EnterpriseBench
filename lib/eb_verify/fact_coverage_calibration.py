"""
Calibration experiment for fact_coverage's TF-IDF char-ngram default embedder.

Labeled set: paraphrase pairs (same code-fact stated differently — SHOULD
match) and near-miss pairs (different symbol / different repo / negation /
right entities, wrong relation — should NOT match). Sweeps the match
threshold and reports precision/recall/F1 per threshold plus the best-F1
operating point. Run:

    PYTHONPATH=lib python3 -m eb_verify.fact_coverage_calibration
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eb_verify.fact_coverage import TfidfCharNgramEmbedder


@dataclass(frozen=True)
class LabeledPair:
    a: str
    b: str
    should_match: bool
    kind: str  # paraphrase | different-symbol | different-repo | negation | wrong-relation


PARAPHRASE_PAIRS = [
    LabeledPair(
        "httpx delegates connection pooling to httpcore",
        "connection pool management in httpx is handled by the httpcore library",
        True, "paraphrase"),
    LabeledPair(
        "requests.Session persists cookies across requests via a RequestsCookieJar",
        "a Session object in requests keeps cookies between calls using RequestsCookieJar",
        True, "paraphrase"),
    LabeledPair(
        "Flask's url_for builds URLs from endpoint names registered on a blueprint",
        "url_for in Flask generates a URL for an endpoint name defined in a blueprint",
        True, "paraphrase"),
    LabeledPair(
        "celery workers acknowledge tasks late when acks_late is enabled",
        "enabling acks_late makes the celery worker ack the task after it finishes executing",
        True, "paraphrase"),
    LabeledPair(
        "SQLAlchemy's sessionmaker returns a factory that creates Session objects",
        "sessionmaker in SQLAlchemy is a factory producing new Session instances",
        True, "paraphrase"),
    LabeledPair(
        "gunicorn forks worker processes from a master arbiter process",
        "the gunicorn arbiter master process spawns its workers by forking",
        True, "paraphrase"),
    LabeledPair(
        "pydantic v2 validates models using the rust pydantic-core library",
        "model validation in pydantic v2 is implemented in pydantic-core, which is written in rust",
        True, "paraphrase"),
    LabeledPair(
        "urllib3's Retry class re-attempts idempotent HTTP requests after connection failures",
        "the retry machinery in urllib3 retries idempotent requests on connection errors",
        True, "paraphrase"),
    LabeledPair(
        "django QuerySets are lazy and only hit the database when iterated",
        "the django ORM lazily evaluates a QuerySet until iteration forces a database query",
        True, "paraphrase"),
    LabeledPair(
        "the kubelet reports node status to the kubernetes API server every 10 seconds",
        "kubernetes node status updates are posted by the kubelet to the API server at 10 second intervals",
        True, "paraphrase"),
    LabeledPair(
        "terraform stores resource state in terraform.tfstate by default",
        "by default terraform persists the state of managed resources to the terraform.tfstate file",
        True, "paraphrase"),
    LabeledPair(
        "grafana loads dashboard provisioning configs from the provisioning/dashboards directory",
        "dashboards are provisioned in grafana via config files under provisioning/dashboards",
        True, "paraphrase"),
]

NEAR_MISS_PAIRS = [
    LabeledPair(
        "httpx delegates connection pooling to httpcore",
        "httpx delegates HTTP/2 framing to the h2 package",
        False, "different-symbol"),
    LabeledPair(
        "the connection pool in httpcore is thread-safe",
        "the connection pool in httpcore is not thread-safe",
        False, "negation"),
    LabeledPair(
        "httpx depends on httpcore for its transport layer",
        "httpcore depends on httpx for its transport layer",
        False, "wrong-relation"),
    LabeledPair(
        "requests.Session persists cookies across requests",
        "aiohttp.ClientSession persists cookies across requests",
        False, "different-repo"),
    LabeledPair(
        "Flask's url_for builds URLs from endpoint names registered on a blueprint",
        "Flask's send_file streams a file from disk to the client",
        False, "different-symbol"),
    LabeledPair(
        "gunicorn forks worker processes from a master arbiter process",
        "uvicorn runs its workers inside a single event loop process",
        False, "different-repo"),
    LabeledPair(
        "SQLAlchemy's sessionmaker returns a factory that creates Session objects",
        "SQLAlchemy's create_engine returns an Engine bound to a database URL",
        False, "different-symbol"),
    LabeledPair(
        "pydantic v2 validates models using the rust pydantic-core library",
        "pydantic v1 validates models in pure python without pydantic-core",
        False, "negation"),
    LabeledPair(
        "the kubelet reports node status to the kubernetes API server every 10 seconds",
        "the kube-scheduler assigns pods to nodes based on their resource requests",
        False, "different-symbol"),
    LabeledPair(
        "terraform stores resource state in terraform.tfstate by default",
        "terraform stores provider plugins under the .terraform/providers directory",
        False, "different-symbol"),
    LabeledPair(
        "django QuerySets are lazy and only hit the database when iterated",
        "django templates are rendered eagerly when the response is built",
        False, "different-symbol"),
    LabeledPair(
        "urllib3's Retry class re-attempts idempotent HTTP requests after connection failures",
        "urllib3 raises MaxRetryError once its retries are exhausted",
        False, "wrong-relation"),
]

ALL_PAIRS: list[LabeledPair] = PARAPHRASE_PAIRS + NEAR_MISS_PAIRS


def pair_similarities(pairs: list[LabeledPair] | None = None) -> list[tuple[LabeledPair, float]]:
    """Cosine similarity per labeled pair, embedded in one shared vector space."""
    pairs = ALL_PAIRS if pairs is None else pairs
    if not pairs:
        raise ValueError("pairs must be non-empty")
    texts = [t for p in pairs for t in (p.a, p.b)]
    emb = TfidfCharNgramEmbedder().embed(texts)
    return [
        (p, float(np.dot(emb[2 * i], emb[2 * i + 1])))
        for i, p in enumerate(pairs)
    ]


def sweep(thresholds: list[float] | None = None) -> tuple[list[dict], dict]:
    """Sweep thresholds; return (rows, best_row) with precision/recall/F1."""
    if thresholds is None:
        thresholds = [round(0.05 * i, 2) for i in range(1, 20)]  # 0.05..0.95
    sims = pair_similarities()
    rows = []
    for t in thresholds:
        tp = sum(1 for p, s in sims if p.should_match and s >= t)
        fp = sum(1 for p, s in sims if not p.should_match and s >= t)
        fn = sum(1 for p, s in sims if p.should_match and s < t)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        rows.append({"threshold": t, "tp": tp, "fp": fp, "fn": fn,
                     "precision": prec, "recall": rec, "f1": f1})
    best = max(rows, key=lambda r: (r["f1"], r["threshold"]))
    return rows, best


def main() -> None:
    sims = pair_similarities()
    print(f"{len(ALL_PAIRS)} labeled pairs "
          f"({sum(p.should_match for p in ALL_PAIRS)} match / "
          f"{sum(not p.should_match for p in ALL_PAIRS)} no-match)\n")

    print("per-pair similarities:")
    for p, s in sorted(sims, key=lambda x: -x[1]):
        label = "MATCH " if p.should_match else "nomatch"
        print(f"  {s:.3f}  {label}  [{p.kind}]  {p.a[:52]!r} vs {p.b[:52]!r}")

    rows, best = sweep()
    print("\nthreshold sweep:")
    print(f"  {'thr':>5} {'tp':>3} {'fp':>3} {'fn':>3} {'prec':>6} {'rec':>6} {'f1':>6}")
    for r in rows:
        marker = "  <-- best" if r is best else ""
        print(f"  {r['threshold']:>5.2f} {r['tp']:>3} {r['fp']:>3} {r['fn']:>3} "
              f"{r['precision']:>6.3f} {r['recall']:>6.3f} {r['f1']:>6.3f}{marker}")
    print(f"\nbest F1 = {best['f1']:.3f} at threshold {best['threshold']:.2f}")
    if best["f1"] < 0.75:
        print("VERDICT: TF-IDF char-ngram default is NOT sufficient (F1 < 0.75); "
              "a real embedding model is needed.")
    else:
        print("VERDICT: TF-IDF char-ngram default clears the F1 >= 0.75 bar on this set.")


if __name__ == "__main__":
    main()
