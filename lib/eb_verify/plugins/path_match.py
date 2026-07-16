"""
path_match — a PRECISION layer over the canonical file-matching scorer.

Shared primitive for scoring an agent's *claimed* source-file list against a
*required* (ground-truth) file set. Fixes EnterpriseBench-6py4v: the recall-only
substring pattern (``found = sum(1 for gt in required if any(gt in claimed ...))``)
let a guess/listing shotgun score 1.00 without reading the repo — over-listing
was free.

This module does NOT reimplement path matching. Matching (segment/component
alignment, citation-suffix stripping, and — critically — per-answer credit
assignment so one ambiguous basename cannot claim several required files) lives
in :mod:`eb_verify.scorers.file_extraction` and is reused verbatim via
:func:`~eb_verify.scorers.file_extraction.score_answer` and
:func:`~eb_verify.scorers.file_extraction.components`. An earlier version rolled
its own segment matcher and regressed the ambiguous-basename defect that
``file_extraction`` already solved; reuse is the fix.

What this module ADDS on top of that matcher — the decided precision policy:
  1. Shape-validate + dedup the claimed list first (reject embedded
     whitespace/newline, oversize, absurd separator count). This is the one
     defense ``file_extraction`` lacks: it kills the find-dump-as-one-string and
     the free-text notes blob (each is a single whitespace-laden entry, dropped
     before matching). Callers must ALSO byte-cap the raw answer upstream.
  2. score = found / max(len(required), len(effective_claimed)). Precision-
     aware: padding true positives with junk lowers the score, so the guess
     shotgun and the full-tree listing both fall below the 0.5 pass threshold.
     Claimed paths that match a *sufficient* (GT-blessed supporting) file but no
     required file are neutral — excluded from the denominator so a thorough,
     correct answer is not punished for citing evidence the ground truth blesses.

``found`` comes from ``score_answer``, which caps recall at 1.0 and never lets a
single vague guess be credited to more than one required file. A malformed
*required* (non-empty but no usable path strings) raises rather than silently
scoring 1.0 — a grader must fail loud, not mask its own broken ground truth.
"""

from __future__ import annotations

from eb_verify.scorers.file_extraction import components, score_answer, _matches_parts

MAX_PATH_LEN = 512
# A real source path is not 40 directories deep; anything past this is a blob
# masquerading as a path (or a hostile input trying to look path-shaped).
MAX_SEGMENTS = 40


def is_plausible_path(entry: object) -> bool:
    """True iff *entry* is a single, plausibly-real path string.

    Rejects non-strings, empty/blank, oversize, any embedded whitespace
    (space/tab/newline/CR/formfeed/vtab — the marker of a blob or listing), and
    absurd separator counts. This is the blob defense the underlying matcher
    does not have.
    """
    if not isinstance(entry, str):
        return False
    stripped = entry.strip()
    if not stripped or len(stripped) > MAX_PATH_LEN:
        return False
    if any(ch.isspace() for ch in stripped):
        return False
    if stripped.count("/") > MAX_SEGMENTS:
        return False
    return True


def valid_claimed_paths(claimed: object) -> list[str]:
    """Filter *claimed* to plausible single paths — stripped, de-duplicated,
    order-preserving. Non-list input yields an empty list."""
    seen: set[str] = set()
    out: list[str] = []
    for entry in claimed if isinstance(claimed, list) else []:
        if not is_plausible_path(entry):
            continue
        stripped = entry.strip()
        if stripped in seen:
            continue
        seen.add(stripped)
        out.append(stripped)
    return out


def _clean_targets(targets: object) -> list[str]:
    """Stripped, non-empty string entries from a target list (required/sufficient)."""
    return [
        t.strip()
        for t in (targets if isinstance(targets, list) else [])
        if isinstance(t, str) and t.strip()
    ]


def path_match_score(
    claimed: object,
    required: object,
    sufficient: object = None,
) -> float:
    """Precision-aware score in [0, 1] for *claimed* paths vs *required* paths.

    *claimed*, *required*, *sufficient* are lists of path strings (non-str
    entries are ignored). *sufficient* names GT-blessed supporting files: a
    claimed path matching one of them (and no required file) is neutral —
    excluded from the precision denominator so thoroughness is not punished.

    Empty *required* -> 1.0 (nothing to identify). Non-empty *required* that
    contains no usable path string -> ValueError (malformed ground truth must
    fail loud). Non-empty *required* with no valid claimed paths -> 0.0.
    """
    req = _clean_targets(required)
    if not req:
        if isinstance(required, list) and len(required) > 0:
            raise ValueError(
                "required contains entries but none are usable path strings; "
                "extract .path from dict entries before scoring"
            )
        return 1.0

    valid = valid_claimed_paths(claimed)
    if not valid:
        return 0.0

    # Correct recall matching (per-answer credit, citation-strip, code-path
    # component alignment) is delegated to the canonical scorer.
    matched, _ambiguous = score_answer(req, valid)
    found = len(matched)

    req_parts = [components(r) for r in req]
    suf_parts = [components(s) for s in _clean_targets(sufficient)]

    # Precision denominator: every valid claimed path counts, EXCEPT one that
    # matches only a sufficient (GT-blessed) file and no required file.
    effective = 0
    for claim in valid:
        claim_parts = components(claim)
        neutral = not any(
            _matches_parts(rp, claim_parts) for rp in req_parts
        ) and any(_matches_parts(sp, claim_parts) for sp in suf_parts)
        if not neutral:
            effective += 1

    denom = max(len(req), effective)
    return found / denom
