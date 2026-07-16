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

# Answer fields that carry claimed source-file paths, unioned. Matches
# run_task.py's advertised output schema (source_files + code_paths are both
# offered to the agent). ``error_source.files`` is unioned separately below.
# Deliberately excludes ``citations`` (a distinct evidence-span artifact, see
# EnterpriseBench-fsb4d). Single-sourced here so the answer plugin and the shell
# check scripts share one extractor instead of respelling the field list.
_CLAIMED_PATH_FIELDS = ("source_files", "files", "code_paths")


def extract_claimed_paths(data: object) -> list[str]:
    """Pull the agent's claimed source-file paths from answer data as a
    STRUCTURED list — never by flattening free text.

    Unions the ``source_files``/``files``/``code_paths`` fields plus
    ``error_source.files``; each entry may be a str or a dict with a
    ``path``/``file`` key. Free-text flattening is deliberately not used: it is
    the over-permissive path that let any mention anywhere count
    (EnterpriseBench-6py4v).
    """
    if not isinstance(data, dict):
        return []
    raw: list = []
    for field in _CLAIMED_PATH_FIELDS:
        value = data.get(field)
        if isinstance(value, list):
            raw.extend(value)
    error_source = data.get("error_source")
    if isinstance(error_source, dict) and isinstance(error_source.get("files"), list):
        raw.extend(error_source["files"])

    paths: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            resolved: object = entry
        elif isinstance(entry, dict):
            resolved = entry.get("path", entry.get("file", ""))
        else:
            resolved = ""
        if isinstance(resolved, str) and resolved.strip():
            paths.append(resolved.strip())
    return paths


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

    # Precision denominator: every valid claimed path counts, EXCEPT one that
    # matches only a sufficient (GT-blessed) file and no required file. With no
    # sufficient files there is nothing to exclude, so every claim counts and the
    # per-claim matching (and the req_parts precompute it needs) is skipped.
    suf_parts = [components(s) for s in _clean_targets(sufficient)]
    if not suf_parts:
        effective = len(valid)
    else:
        req_parts = [components(r) for r in req]
        effective = 0
        for claim in valid:
            claim_parts = components(claim)
            matches_sufficient = any(_matches_parts(sp, claim_parts) for sp in suf_parts)
            if not matches_sufficient or any(_matches_parts(rp, claim_parts) for rp in req_parts):
                effective += 1

    denom = max(len(req), effective)
    return found / denom
