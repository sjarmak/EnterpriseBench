"""Answer-key fidelity for security_operations/rbac-audit-001.

The webhook_authorization checkpoint used to assert the webhook "does NOT parse
request.OldObject", and its evaluation_criteria demanded the agent "explain that
request.OldObject is not parsed". That is false against the pinned source
(projectcalico/calico@70ebb8c4, webhooks/pkg/rbac/rbac.go authorize()):

    // In some cases (e.g., DELETE), the object may be in
    // the OldObject field instead of the Object field, so we check both.
    raw := ar.Request.Object.Raw
    if len(raw) == 0 {
        raw = ar.Request.OldObject.Raw
    }

The webhook DOES reference request.OldObject, as a fallback when Object.Raw is
empty. The real defect is that on UPDATE, Object.Raw is populated, so the
fallback is never reached and only the NEW object's tier is authorized. An agent
that read the code and reported this correctly ("the OldObject fallback exists
but is unreachable on UPDATE") failed the criterion as written — the key
penalised the correct analysis (EnterpriseBench-behb8).

These regressions pin the corrected answer key so the falsehood cannot creep
back: the blanket "OldObject is not parsed" claim must stay gone, and the
accurate fallback-unreachable-on-UPDATE framing must stay present.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASK_DIR = REPO_ROOT / "benchmarks" / "security_operations" / "rbac-audit-001"
SOLUTION = TASK_DIR / "expected_solution.json"


def _norm(text: str) -> str:
    """Lowercase and collapse whitespace so wording variants compare equal."""
    return re.sub(r"\s+", " ", text).strip().lower()


# Negation forms that, next to a parse verb, deny that OldObject is parsed.
_NEGATION = re.compile(r"\b(not|never|fails?|without)\b|n't")


def _clauses(text: str) -> list[str]:
    """Split into single clauses for co-occurrence tests.

    Dotted identifiers (request.OldObject, r.Store.Get) are collapsed first so
    the dots inside a symbol name are not mistaken for clause boundaries — only
    real punctuation (sentence period, comma, semicolon, colon, em/en dash,
    newline) separates clauses.
    """
    joined = re.sub(r"\.(?=\w)", "", _norm(text))
    return re.split(r"[.,;:—–\n]", joined)


def _denies_oldobject_parsing(text: str) -> bool:
    """True if any single clause claims request.OldObject is not parsed.

    Order-independent: catches both the verb-first historical falsehood ("does
    NOT parse request.OldObject") and the subject-first form ("request.OldObject
    is not parsed"), plus rewordings ("never parses OldObject", "fails to parse
    OldObject"). Clause-scoped on purpose: the accurate two-clause framing
    ("OldObject fallback is never reached — only the new tier is parsed") keeps
    "oldobject" and the parse verb in separate clauses, so it is not a denial.
    A falsehood deliberately split across two sentences would slip through; that
    is an accepted tradeoff for keeping the accurate prose from false-positiving.
    """
    return any(
        "oldobject" in clause and "pars" in clause and _NEGATION.search(clause)
        for clause in _clauses(text)
    )


@pytest.fixture(scope="module")
def checkpoints() -> dict:
    return json.loads(SOLUTION.read_text())["checkpoints"]


@pytest.fixture(scope="module")
def webhook_checkpoint(checkpoints: dict) -> dict:
    return checkpoints["webhook_authorization"]


@pytest.fixture(scope="module")
def apiserver_checkpoint(checkpoints: dict) -> dict:
    return checkpoints["apiserver_authorization"]


def test_expected_solution_drops_the_oldobject_not_parsed_falsehood(
    webhook_checkpoint: dict,
) -> None:
    """The webhook DOES reference request.OldObject; the key must not deny it."""
    assert not _denies_oldobject_parsing(webhook_checkpoint["expected_solution"]), (
        "webhook_authorization.expected_solution still claims request.OldObject "
        "is not parsed, contradicting the pinned source where it is a fallback path."
    )


def test_criteria_drop_the_oldobject_not_parsed_falsehood(
    webhook_checkpoint: dict,
) -> None:
    for crit in webhook_checkpoint["evaluation_criteria"]:
        assert not _denies_oldobject_parsing(crit), (
            f"evaluation criterion still demands the false 'request.OldObject is "
            f"not parsed' finding: {crit!r}"
        )


@pytest.mark.parametrize(
    "denial",
    [
        "It does NOT parse request.OldObject, so the source tier is never checked.",
        "request.OldObject is not parsed on UPDATE.",
        "The webhook never parses request.OldObject.",
        "It fails to parse request.OldObject.",
        "Authorization proceeds without parsing request.OldObject.",
    ],
)
def test_guard_catches_the_falsehood_in_any_wording(denial: str) -> None:
    """Pin the guard itself: every phrasing of the historical falsehood — verb-
    first, subject-first, and reworded negations — must be detected, so the
    guard cannot silently degrade to catching only the two original sentences."""
    assert _denies_oldobject_parsing(denial), (
        f"guard failed to flag a request.OldObject-not-parsed denial: {denial!r}"
    )


@pytest.mark.parametrize(
    "accurate",
    [
        "The OldObject fallback is never reached — only the new tier is parsed.",
        "request.OldObject is referenced as a fallback; only Object.Raw is parsed on UPDATE.",
    ],
)
def test_guard_allows_the_accurate_two_clause_framing(accurate: str) -> None:
    """The correct analysis keeps OldObject and the parse verb in separate
    clauses; the guard must not mistake it for a denial (the regression this
    whole bead fixes)."""
    assert not _denies_oldobject_parsing(accurate), (
        f"guard false-positived on accurate prose: {accurate!r}"
    )


def test_expected_solution_states_the_real_control_flow(
    webhook_checkpoint: dict,
) -> None:
    """Accurate framing: Object.Raw drives authz; the OldObject fallback exists
    but is unreachable on UPDATE, so only the new tier is checked."""
    prose = _norm(webhook_checkpoint["expected_solution"])
    assert "object.raw" in prose, (
        "expected_solution should name the real symbol request.Object.Raw."
    )
    assert "fallback" in prose, (
        "expected_solution should describe the OldObject fallback path."
    )
    # The load-bearing insight: the fallback does not fire on UPDATE.
    assert any(
        marker in prose
        for marker in ("unreachable", "never reached", "not reached", "populated", "non-empty")
    ), (
        "expected_solution should explain the OldObject fallback is unreachable "
        "on UPDATE because Object.Raw is populated."
    )


def test_apiserver_solution_names_observable_control_flow(
    apiserver_checkpoint: dict,
) -> None:
    """The apiserver checkpoint should rest on symbols an agent can observe in
    the source, not the single fix-prescriptive objInfo.UpdatedObject() token.

    Verified against the pinned source (projectcalico/calico@70ebb8c4,
    apiserver/pkg/registry/projectcalico/{globalpolicy,networkpolicy}/storage.go
    Update()): r.Store.Get() fetches the OLD object, names.TierOrDefault(
    obj.Spec.Tier) derives its tier, and r.authorizer.AuthorizeTierOperation()
    authorizes only that tier; objInfo is forwarded to r.Store.Update() without
    objInfo.UpdatedObject() ever being called.
    """
    prose = _norm(apiserver_checkpoint["expected_solution"])
    for symbol in ("r.store.get", "names.tierordefault", "authorizetieroperation"):
        assert symbol in prose, (
            f"apiserver_authorization.expected_solution should name the "
            f"observable symbol {symbol!r} so the checkpoint rests on source "
            f"evidence, not the lone objInfo.UpdatedObject() fix token."
        )
    # The load-bearing insight must survive the enrichment.
    assert "updatedobject" in prose, (
        "apiserver_authorization.expected_solution must keep the "
        "objInfo.UpdatedObject()-not-called insight."
    )


def test_answer_key_is_valid_json_with_all_checkpoints(checkpoints: dict) -> None:
    """Guard against a malformed edit dropping a checkpoint."""
    expected = {
        "identify_policy_types",
        "apiserver_authorization",
        "webhook_authorization",
        "bypass_and_remediation",
    }
    assert set(checkpoints) == expected, (
        f"checkpoint set drifted: {sorted(checkpoints)}"
    )
    for name, cp in checkpoints.items():
        assert cp["expected_solution"].strip(), f"{name} has empty expected_solution"
        assert cp["evaluation_criteria"], f"{name} has no evaluation_criteria"
