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


# The falsehood's SHAPE: a negation that attaches to the parse verb — a negation
# form followed (within two words) by a "pars" verb. This is deliberately
# tighter than "any negation anywhere in the clause + any 'pars' anywhere": the
# negation must bind to the parsing, so accurate prose where the negation scopes
# to a different word ("parsed WITHOUT error", "parsed only when Object.Raw is
# NOT present", "parsed when Object.Raw CANNOT be decoded") is NOT a denial.
# Covers not/never/cannot/can't/does-not/is-not parse(s|d), fails|failing to
# parse, without|skips|omits|ignores|neglects|disregards parsing, and n't parse.
_NEGPARSE = re.compile(
    r"(?:\b(?:not|never|cannot|can'?t|without|fails?|failing|failed"
    r"|ignores?|ignored|skips?|skipped|skipping|omits?|omitted"
    r"|neglects?|neglected|disregards?|disregarded)\b|n't)"
    r"(?:\s+\w+){0,2}?\s+pars"
)

# request.OldObject, as the camelCase identifier only. _collapse turns an
# intra-identifier dot into a SPACE (not nothing), so "request.OldObject" ->
# "request oldobject" and the anchored token matches — while a lookalike whose
# owner merely ends in "old" ("Threshold.Object" -> "threshold object",
# "Household.Object", "manifold.Object.Raw") does NOT collapse into "oldobject".
# The spaced English phrase "old object" is deliberately NOT matched (a
# documented gap) — matching it false-positived on accurate prose ("the old
# object's tier is never parsed").
_OLDOBJECT = re.compile(r"\boldobject\b")

# Causal-accuracy qualifier. Its presence anywhere in the SENTENCE marks the
# accurate mechanism ("the fallback is unreachable / never reached because
# Object.Raw is populated / non-empty"), not the blanket falsehood. This is the
# real behb8 distinction: the truthful finding always names why the fallback
# does not fire ("... because Object.Raw is populated"); the falsehood
# ("OldObject is not parsed", full stop) does not.
_QUALIFIER = re.compile(r"\b(fallback|unreachable|reached|populated|non[-\s]?empty)\b")


def _collapse(text: str) -> str:
    """Normalise and collapse intra-identifier dots to a space.

    Dotted identifiers (request.OldObject, r.Store.Get, Object.Raw) have their
    internal dots replaced by a SPACE so the symbol is not split on the dot, yet
    "request.OldObject" becomes two whitespace-separated tokens ("request
    oldobject") rather than one glued run ("requestoldobject"). The space is
    load-bearing: it lets ``\\boldobject\\b`` distinguish the real identifier
    from a lookalike like "Threshold.Object" ("threshold object"). A
    sentence-terminating dot (followed by a space, not a word char) is left
    intact so it still separates sentences.
    """
    return re.sub(r"\.(?=\w)", " ", _norm(text))


def _sentences(text: str) -> list[str]:
    """Coarse split for the mechanism shield — sentence terminators only."""
    return re.split(r"[.;!?\n]", _collapse(text))


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

    * Denial detection is CLAUSE-scoped: a clause names OldObject
      (``\\boldobject\\b`` after intra-identifier dots collapse to spaces) AND
      carries a ``_NEGPARSE`` match — a negation that attaches to the parse verb.
      Order-independent: catches the verb-first historical falsehood ("does NOT
      parse request.OldObject"), the subject-first form ("request.OldObject is
      not parsed"), and negation rewordings ("never parses", "cannot parse",
      "skips parsing", "failing to parse"). Requiring the negation to bind to the
      parse verb (not merely co-occur in the clause) is what keeps accurate prose
      whose negation scopes elsewhere ("parsed without error", "parsed only when
      Object.Raw is not present") from tripping the guard.
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

    * Verb-axis rewordings that avoid the ``pars`` verb ("does not inspect / read
      / check request.OldObject", "ignores request.OldObject", "OldObject.Parse()
      is never invoked"). Broadening the verb set to catch these was rejected:
      "check" collides with the answer key's own accurate idiom ("the source tier
      is never checked"), turning the guard against a correct edit — the worse
      failure direction.
    * The spaced English phrase "old object" (vs the "OldObject" identifier).
      Matching it false-positived on accurate prose ("the old object's tier is
      never parsed").
    * A falsehood split across two SENTENCES, or within one sentence so OldObject
      and the negated parse verb never share a clause (appositive comma).
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
            if _OLDOBJECT.search(clause) and _NEGPARSE.search(clause):
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
        # A blanket denial is NOT exonerated by a mechanism word sitting in a
        # SEPARATE sentence — the shield is sentence-scoped, so it does not reach
        # across the period.
        "request.OldObject is never parsed. The table stays populated.",
        # ...nor across a "!"/"?" terminator (those end a sentence too, so an
        # unrelated qualifier before them cannot shield the following denial).
        "Object.Raw is never populated! request.OldObject is not parsed.",
        "Is the fallback reached? request.OldObject is not parsed on UPDATE.",
    ],
)
def test_guard_catches_the_falsehood_in_any_wording(denial: str) -> None:
    """Pin the guard itself: every phrasing of the historical falsehood — verb-
    first, subject-first, and reworded negations (F2) — must be detected, so the
    guard cannot silently degrade to catching only the original sentences,
    including across "!"/"?" sentence terminators."""
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
        # Negation that binds to a NON-parse word: OldObject IS parsed here, the
        # negation scopes to "error" / "present" / "decoded". Requiring the
        # negation to attach to the parse verb keeps these accurate statements out
        # of the guard.
        "request.OldObject is parsed without error on DELETE.",
        "request.OldObject.Raw is parsed only when Object.Raw is not present.",
        "request.OldObject is parsed when Object.Raw cannot be decoded.",
    ],
)
def test_guard_allows_the_accurate_framing(accurate: str) -> None:
    """The correct analysis either names the mechanism (fallback / populated /
    unreachable / never reached) or negates something other than the parsing; the
    guard must not mistake it for a denial. Pins the original two-clause framing,
    the confirmed false-positives F0/F5 that the mechanism shield fixes, the
    cause-first phrasing where the mechanism precedes the denial, and prose whose
    negation binds to a non-parse word — the regression this bead is about (a
    false-positive blocks a correct edit with no backstop)."""
    assert not _denies_oldobject_parsing(accurate), (
        f"guard false-positived on accurate prose: {accurate!r}"
    )


@pytest.mark.parametrize(
    "lookalike",
    [
        # spaced English words that merely end in "old" next to "object..."
        "the manifold object is never parsed",
        "the old objective standard is never parsed",
        "a threshold object is not parsed",
        "household objects are never parsed",
        # dotted symbols whose owner ends in "old": these must NOT collapse into
        # the "oldobject" token (the reason _collapse turns the intra-identifier
        # dot into a space rather than deleting it).
        "Threshold.Object is never parsed on UPDATE.",
        "Household.Object is not parsed.",
        "manifold.Object.Raw is never parsed.",
        "Scaffold.Object is not parsed at all.",
    ],
)
def test_guard_ignores_oldobject_lookalikes(lookalike: str) -> None:
    """The OldObject match is anchored to the ``oldobject`` identifier token.
    Prose that merely contains a word ending in "old" next to an "object"-prefixed
    word — spaced ("manifold object", "old objective") OR dotted
    ("Threshold.Object", which collapses to "threshold object", not
    "thresholdobject") — does not name request.OldObject and must never be
    flagged, even alongside a negated parse verb."""
    assert not _denies_oldobject_parsing(lookalike), (
        f"guard false-positived on an OldObject lookalike: {lookalike!r}"
    )


@pytest.mark.parametrize(
    "evasion",
    [
        # Verb-axis rewording that avoids the "pars" verb — broadening the verb
        # set to catch these was rejected (it collides with the accurate "never
        # checked" idiom); see _denies_oldobject_parsing.__doc__.
        "The webhook ignores request.OldObject entirely.",
        "It does not inspect request.OldObject on UPDATE.",
        "The handler never reads request.OldObject.",
        # Method-call phrasing where the negation binds to "invoked", not to a
        # "pars" verb ("...Parse() is never invoked"): same verb-axis gap.
        "request.OldObject.Parse() is never invoked.",
        # Spaced English "old object" (vs the "OldObject" identifier) — matching
        # it false-positived on accurate prose, so it is deliberately a gap.
        "The webhook does not parse the old object at all.",
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
