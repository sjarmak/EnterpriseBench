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
# Kept on the NEGATION axis only (F2): "cannot parse", "skips parsing",
# "failing to parse" are natural rewordings of the historical falsehood. The
# PARSE-VERB axis is deliberately NOT broadened past "pars" — see
# _denies_oldobject_parsing for why "check"/"read"/"inspect" are out.
_NEGATION = re.compile(
    r"\b(not|never|cannot|can'?t|without|fails?|failing|failed"
    r"|ignores?|ignored|skips?|skipped|skipping|omits?|omitted"
    r"|neglects?|neglected|disregards?|disregarded)\b|n't"
)

# References to request.OldObject. Two forms: the collapsed identifier
# ("oldobject", after dotted-identifier collapse — may be glued to a preceding
# word like "request" and followed by ".Raw"->"raw", so no boundaries), OR the
# spaced English phrase ("old object", boundary-anchored so lookalikes such as
# "manifold object", "old objective", "threshold object" do NOT match) (F4).
_OLDOBJECT = re.compile(r"oldobject|\bold\s+objects?\b")

# The parse verb, boundary-anchored so "sparse"/"sparsely" do not leak in next
# to the widened negation vocabulary.
_PARSE = re.compile(r"\bpars")

# Causal-accuracy qualifier. Its presence anywhere in the SENTENCE marks the
# accurate mechanism ("the fallback is unreachable / never reached because
# Object.Raw is populated / non-empty"), not the blanket falsehood. This is the
# real behb8 distinction: the truthful finding always names why the fallback
# does not fire ("... because Object.Raw is populated"); the falsehood
# ("OldObject is not parsed", full stop) does not.
_QUALIFIER = re.compile(r"\b(fallback|unreachable|reached|populated|non[-\s]?empty)\b")


def _collapse(text: str) -> str:
    """Normalise and collapse dotted identifiers.

    Dotted identifiers (request.OldObject, r.Store.Get, Object.Raw) are collapsed
    so the dots inside a symbol name are not mistaken for boundaries — only real
    punctuation separates units.
    """
    return re.sub(r"\.(?=\w)", "", _norm(text))


def _sentences(text: str) -> list[str]:
    """Coarse split for the mechanism shield — sentence terminators only."""
    return re.split(r"[.;\n]", _collapse(text))


def _clauses(sentence: str) -> list[str]:
    """Fine split within a sentence for denial-token co-occurrence."""
    return re.split(r"[,:—–]", sentence)


def _denies_oldobject_parsing(text: str) -> bool:
    """True if the prose blankly claims request.OldObject is not parsed.

    A tripwire, NOT a proof. Deciding whether prose semantically denies that
    OldObject is parsed is a classification task a regex cannot cover in full;
    this guard pins the known-falsehood *shape* and is intentionally scoped so
    it never blocks a correct edit. The real guarantee that the shipped key
    stays accurate is the POSITIVE-contract test
    ``test_expected_solution_states_the_real_control_flow`` (plus human review);
    this negative tripwire is the belt, not the suspenders.

    Two granularities, biased to avoid false-positives (blocking a correct edit
    has no backstop; missing a reworded falsehood is caught by the positive
    contract above):

    * Denial detection is CLAUSE-scoped: a clause names OldObject (``oldobject``
      collapsed, or spaced ``old object``), contains the parse verb ``pars``,
      and carries a negation. Order-independent — catches the verb-first
      historical falsehood ("does NOT parse request.OldObject"), the
      subject-first form ("request.OldObject is not parsed"), and negation
      rewordings ("never parses", "cannot parse", "skips parsing", "failing to
      parse").
    * The mechanism shield is SENTENCE-scoped: if the sentence containing that
      clause names the accuracy mechanism (``_QUALIFIER``) anywhere, the prose
      is the accurate finding, not a denial. The accurate framing always names
      *why* the fallback does not fire ("... because Object.Raw is populated",
      "the fallback is never reached"), and that phrase may sit in an adjacent
      clause ("Because Object.Raw is populated, request.OldObject is never
      parsed") — so the shield must reach across the whole sentence, not just
      the denial clause.

    Deliberately NOT covered (accepted, per ZFC / no-silent-caps — a heuristic
    must not pretend to be exhaustive):

    * Verb-axis rewordings that avoid ``pars`` ("does not inspect/read/check
      request.OldObject", "ignores request.OldObject"). Broadening the verb set
      to catch these was rejected: "check" collides with the answer key's own
      accurate idiom ("the source tier is never checked"), turning the guard
      against a correct edit — the worse failure direction.
    * A falsehood split across two SENTENCES, or within one sentence so OldObject
      and the parse verb never share a clause (appositive comma).
    * A blanket denial that crams an unrelated mechanism word into its own
      sentence ("OldObject is never parsed in any path and the table stays
      populated") — the sentence-scoped shield exonerates it. Requiring the
      shield to reach across clauses (to allow the accurate cause-first framing)
      is what admits this; the reverse scoping would instead false-positive on
      correct prose, which is the worse trade.
    * An adversarially fabricated qualifier ("OldObject is never parsed, fallback
      notwithstanding").

    If CI ever gains model access, replace this with an LLM judge.
    """
    for sentence in _sentences(text):
        if _QUALIFIER.search(sentence):
            continue
        for clause in _clauses(sentence):
            if (
                _OLDOBJECT.search(clause)
                and _PARSE.search(clause)
                and _NEGATION.search(clause)
            ):
                return True
    return False


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
        # verb-first / subject-first historical falsehood
        "It does NOT parse request.OldObject, so the source tier is never checked.",
        "request.OldObject is not parsed on UPDATE.",
        "The webhook never parses request.OldObject.",
        "It fails to parse request.OldObject.",
        "Authorization proceeds without parsing request.OldObject.",
        # F2: negation-axis rewordings that keep the parse verb
        "It cannot parse request.OldObject.",
        "The handler skips parsing request.OldObject.",
        "Failing to parse request.OldObject, it checks only the new tier.",
        # F4: spaced "old object" paraphrase (not the collapsed identifier)
        "The webhook does not parse the old object at all.",
        # A blanket denial is NOT exonerated by a mechanism word sitting in a
        # SEPARATE sentence — the shield is sentence-scoped, so it does not reach
        # across the period.
        "request.OldObject is never parsed. The table stays populated.",
    ],
)
def test_guard_catches_the_falsehood_in_any_wording(denial: str) -> None:
    """Pin the guard itself: every phrasing of the historical falsehood — verb-
    first, subject-first, and reworded negations (F2), plus the spaced-phrase
    paraphrase (F4) — must be detected, so the guard cannot silently degrade to
    catching only the original sentences."""
    assert _denies_oldobject_parsing(denial), (
        f"guard failed to flag a request.OldObject-not-parsed denial: {denial!r}"
    )


@pytest.mark.parametrize(
    "accurate",
    [
        # original two-clause framing
        "The OldObject fallback is never reached — only the new tier is parsed.",
        "request.OldObject is referenced as a fallback; only Object.Raw is parsed on UPDATE.",
        # F0: a single accurate clause that names the mechanism ("because
        # Object.Raw is populated") — the qualifier keeps it out of the guard.
        "On UPDATE, request.OldObject.Raw is never parsed because Object.Raw is populated.",
        # F5: conjunction-joined accurate prose in one clause — "fallback"/
        # "never reached" mark the accurate mechanism.
        "the OldObject fallback is never reached and only the new tier is parsed",
        # Cause-first accurate framing: the mechanism ("Object.Raw is populated")
        # sits in a DIFFERENT clause than the denial, so a clause-scoped shield
        # would wrongly flag it — the shield must reach across the sentence.
        "Because Object.Raw is populated, request.OldObject is never parsed on UPDATE.",
        # The accurate "old tier is never checked" idiom must not trip the guard
        # even with request.OldObject in the same sentence (verb axis is 'pars'
        # only, so "checked" is not a parse verb).
        "request.OldObject is referenced, but the old tier is never checked on UPDATE.",
        # Accurate fallback description whose negation scopes to Object.Raw.
        "When Object.Raw cannot be parsed, request.OldObject provides the bytes.",
    ],
)
def test_guard_allows_the_accurate_framing(accurate: str) -> None:
    """The correct analysis always names the mechanism (fallback / populated /
    unreachable / never reached); the guard must not mistake it for a denial.
    This pins the original two-clause framing, the confirmed false-positives
    F0/F5 that the mechanism shield fixes, and the cause-first phrasing where the
    mechanism precedes the denial — the regression this bead is about (a
    false-positive blocks a correct edit with no backstop)."""
    assert not _denies_oldobject_parsing(accurate), (
        f"guard false-positived on accurate prose: {accurate!r}"
    )


@pytest.mark.parametrize(
    "lookalike",
    [
        "the manifold object is never parsed",
        "the old objective standard is never parsed",
        "a threshold object is not parsed",
        "household objects are never parsed",
    ],
)
def test_guard_ignores_oldobject_lookalikes(lookalike: str) -> None:
    """The OldObject match is boundary-anchored: prose that merely contains a
    word ending in "old" next to an "object"-prefixed word (manifold, threshold,
    household, "old objective") does not name request.OldObject and must never be
    flagged, even alongside a negated parse verb."""
    assert not _denies_oldobject_parsing(lookalike), (
        f"guard false-positived on an OldObject lookalike: {lookalike!r}"
    )


@pytest.mark.parametrize(
    "evasion",
    [
        # Verb-axis rewording that avoids "pars" — broadening the verb set to
        # catch this was rejected (it collides with the accurate "never checked"
        # idiom); see _denies_oldobject_parsing.__doc__.
        "The webhook ignores request.OldObject entirely.",
        "It does not inspect request.OldObject on UPDATE.",
        "The handler never reads request.OldObject.",
        # Falsehood split across two SENTENCES so OldObject and the parse verb
        # never share a clause.
        "request.OldObject is present. That field is not parsed.",
        # Within-sentence appositive comma (F1): the comma fragments the clause,
        # so OldObject and the parse verb never co-occur in one clause.
        "request.OldObject, the delete-time field, is not parsed.",
        # A blanket denial that crams an unrelated mechanism word into its own
        # sentence: the sentence-scoped shield exonerates it (the price of
        # letting the accurate cause-first framing through — the safer trade,
        # since the reverse over-fires on correct prose).
        "request.OldObject is never parsed in any code path and the table stays populated.",
    ],
)
def test_documented_evasions_are_accepted_gaps(evasion: str) -> None:
    """Pin the guard's DELIBERATE limits loudly (no-silent-caps / ZFC): these
    reworded denials evade on purpose because closing them robustly is a
    semantic-classification task a regex cannot do without over-firing on
    correct prose. This test documents the boundary, not an aspiration — the
    positive-contract test is the real accuracy guarantee. If CI ever gains
    model access (LLM judge) and the guard is broadened, update this test."""
    assert not _denies_oldobject_parsing(evasion), (
        f"a documented-gap evasion is now caught: {evasion!r} — if this is an "
        f"intentional improvement, move it into the 'denial' parametrize and "
        f"update the guard docstring."
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
