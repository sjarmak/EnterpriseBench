"""Redaction boundary for operator-facing failure text.

Every invalidity channel — a session that died, a verifier that never reached a
verdict, a judge that raised — carries a ``detail`` built from text this harness
does not author: an agent's exception, a verifier's stderr, an HTTP error body.
That text fans out to three sinks that each keep it verbatim: ``chain_result``
JSON (persisted, and aggregated across runs), stdout via ``ChainResult.summary``,
and ``logger.error``.

The harness runs agents with ``ANTHROPIC_API_KEY`` in their environment, so an
exception embedding a response body or an env dump arrives at those sinks with a
live credential in it. ``run_task`` already treats agent secrets as a real threat
when it hands them over in an env-file rather than in ps-visible argv; this
module is the same control on the failure path, which had none.

Redaction changes when a credential shape changes, not when a scoring rule does,
so it lives here rather than in ``scorer_guard`` — and ``session`` can scrub its
own error text without importing the scorer trust boundary to do it.
"""

from __future__ import annotations

import re

# Hard cap on any single string a failure channel carries. A verifier that
# streams megabytes to stderr, or an exception carrying a whole response body,
# must not flood chain_result.json or an operator's terminal.
MAX_DETAIL_CHARS = 2000

_TRUNCATION_NOTE = "... [truncated]"

_REDACTED = "[REDACTED]"

# The secret shapes destroyed before any failure text is persisted or logged.
#
# A denylist can never be complete, so this one is deliberately biased toward
# over-redaction: it names the credentials this harness actually handles
# (Anthropic keys, bearer tokens, AWS access-key ids) plus the generic
# ``NAME=value`` / ``"name": value`` shape an env dump, a shell trace, or a JSON
# error body prints them in. Over-redacting an operator's debug string costs a
# little context; under-redacting one publishes a live key.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9_-]+"), _REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*"), f"Bearer {_REDACTED}"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), _REDACTED),
    # The NAME survives so an operator still learns WHICH credential reached the
    # failure path; only its value is destroyed. Any name ENDING in a sensitive
    # word matches, so ``ANTHROPIC_API_KEY`` is covered without enumerating it.
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_.-]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD))"
            r'(["\']?\s*[=:]\s*["\']?)[^\s"\',;}]+'
        ),
        rf"\1\2{_REDACTED}",
    ),
)


def redact(text: str) -> str:
    """Destroy every known secret shape in ``text``.

    Idempotent: no pattern matches its own replacement, so text that has already
    been through here passes back out unchanged.
    """
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def bound(text: str) -> str:
    """Cap ``text`` at :data:`MAX_DETAIL_CHARS`, marking that it was cut.

    The note fits INSIDE the cap rather than being appended past it, so the
    output is never longer than the cap and re-bounding an already-bounded
    string is a no-op. Both matter: this runs at more than one channel boundary,
    and a string may cross two of them before it reaches a sink.
    """
    if len(text) <= MAX_DETAIL_CHARS:
        return text
    return text[: MAX_DETAIL_CHARS - len(_TRUNCATION_NOTE)] + _TRUNCATION_NOTE


def safe_detail(value: object) -> str:
    """The one way failure text becomes safe to persist, print, and log.

    Redaction runs BEFORE bounding, not after: a cut can leave a fragment that
    the patterns no longer recognise. ``AKIA`` + 16 chars sliced mid-key stops
    matching its own pattern and would sail through as plaintext.

    Takes ``object`` because callers hand it exceptions directly — the value is
    only ever rendered as text, so it is coerced here rather than at each call.
    """
    return bound(redact(str(value)))
