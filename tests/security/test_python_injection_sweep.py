"""Repo-wide catch-all for the shell-into-Python injection class (EnterpriseBench-b0fuq).

The two sibling modules each leave a hole this one closes:

* ``test_check_error_source_forgery.py`` (qvpzt) globs ONLY
  ``customer_escalation/*/checks/check_error_source.sh`` + the archived mirror, so a
  new vulnerable ``check_root_cause.sh`` — or a ``check_error_source.sh`` under
  ``technical_debt/`` — matches nothing.
* ``test_check_scripts_injection.py`` (0rv.23) pins a hardcoded 37-entry
  ``TARGET_FILES`` list, so it covers zero future files by construction.

Both also test the ``'''`` *spelling* rather than the *class*.

The vector, precisely: a check script runs ``python3 -c "<body>"`` (bash *double*-
quoted, so bash performs expansion before Python parses the body) or a heredoc
with an *unquoted* delimiter (``python3 <<PYEOF`` — same expansion). If any
shell-expanded, agent-influenceable value lands in that Python source, the agent
can inject Python and forge a passing verifier score. The original qvpzt vector
was ``agent_files = '''$AGENT_FILES'''`` with a quote-breakout, but the *class* is
wider than that one spelling — all of these are the same forge-the-verdict
primitive via a different shell metacharacter, and this sweep flags every one:

* ``'$V'`` / ``"$V"`` / ``'''$V'''`` / escaped ``\\"$V\\"`` — quote-breakout literals
* ``result = $V`` — a bare expansion used directly as Python source
* ``'''$(cat "$WORKSPACE/…/answer.json")'''`` — command substitution embedding
  the full agent-controlled file *contents* as source
* ``${!V}`` — indirect expansion

so the rule is deliberately blunt: **any unescaped ``$`` expansion inside an
expanded Python body is a violation**, with exactly one carve-out.

Carve-out (allowlist): a *harness-derived path var* interpolated as the argument
of ``open(...)`` — e.g. ``with open('${REPORT}') as f:``. There the *path* is
harness-controlled and the agent's bytes are read as data via ``json.load``, never
as source. Six scripts do this today and are safe. The allowlist is dataflow-
aware, not name-based: a var counts as harness-derived only if **every** assignment
to it in the script is rooted at ``${WORKSPACE}``/``${TASK_DIR}``. A single
non-harness assignment (``REPORT="$(jq -r .p "$REPORT")"``) — or reassigning
``WORKSPACE`` itself to agent-influenced content — taints the name and it is no
longer allowlisted, closing the "smuggle agent data through a harness-named var"
bypass.

Deliberately fail-closed, and narrower than "any safe harness-var use": a harness
var interpolated anywhere *other* than an ``open()`` argument (e.g. into a
``print`` string) is still flagged. Refactor such a script to pass the value via
``os.environ`` — the same safe pattern the qvpzt fix template uses — rather than
widening this carve-out. The carve-out is structural only: it matches the *shape*
``open('${HARNESS_VAR}')`` and cannot see what the body does with the bytes, so an
``exec(open('${REPORT}').read())`` would pass the shape check — Python-level
code-exec of file contents is a different class, out of this shell-into-Python
guard's scope (and absent from the corpus: no ``exec``/``eval`` in any check script).

Two *invocation-recognition* gaps are known fail-open, deliberately out of scope
until a real script needs them (both verified absent from the corpus today, so
this stays a documentation note rather than a live hole): an interpreter reached
through a shell var (``PY=python3`` then ``$PY -c "…"``) is not recognised as a
Python call, and a body piped into the interpreter (``cat … | python3``) is
neither a ``-c`` string nor a heredoc. A new script using either spelling would
slip the sweep; fold recognition in then. The corpus greps are
``$VAR -c`` = 0 hits and ``| python`` = 0 hits.

Superseded eventually by rmz1x (migrate these blobs onto
``eb_verify.plugins.file_extraction``); until then this is the backstop.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
BENCHMARKS = ROOT / "benchmarks"

# A bash *double*-quoted ``python3 -c "..."`` body. ``(?:[^"\\]|\\.)*`` consumes
# escaped ``\"`` and ``\\`` in matched pairs, so the body terminates on the first
# genuinely-unescaped ``"`` regardless of backslash-run parity — a single
# ``(?<!\\)"`` lookbehind would drop the whole body (scan nothing, silently) when
# an even backslash run precedes the real closing quote. ``python[0-9.]*`` tolerates
# ``python3.11`` etc. Interpreter flags before ``-c`` are tolerated
# (``(?!-c\b)-\w+(?:\s+[^\s"]+)?`` — a flag token, optionally with its own arg such
# as ``-W ignore``), as is any whitespace run (multiple spaces / tabs / newlines),
# so ``python3 -W ignore -c`` and double-space spellings are still scanned rather
# than silently skipped. A *single*-quoted ``-c '...'`` body performs no expansion
# and is intentionally not matched.
_PY_BODY = re.compile(
    r'python[0-9.]*\s+(?:(?!-c\b)-\w+(?:\s+[^\s"]+)?\s+)*-c\s+"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)

# A heredoc-fed Python invocation: ``python3 [-] <<[-]DELIM ... DELIM``. Only an
# *unquoted* delimiter triggers bash expansion inside the body; ``<<'DELIM'`` /
# ``<<"DELIM"`` are literal (safe) and skipped via the captured quote group.
_HEREDOC = re.compile(
    r"""python[0-9.]* *-? *<<-?\s*(?P<q>['"]?)(?P<delim>\w+)(?P=q)\r?\n"""
    r"""(?P<body>.*?)\r?\n[ \t]*(?P=delim)\b""",
    re.DOTALL,
)

# A ``$`` or backtick candidate — every one is a *potential* live expansion; parity
# of the preceding backslash run decides whether bash actually expands it (see
# ``_live_expansions``). Backticks are command substitution and count alongside ``$``.
_EXPANSION_CHAR = re.compile(r"[$`]")


def _live_expansions(body: str) -> Iterator[tuple[int, str]]:
    """Yield ``(position, char)`` for each *live* bash expansion in ``body``.

    A ``$`` or backtick is live iff preceded by an **even** number of backslashes
    (zero counts): ``\\$`` is escaped (odd), ``\\\\$`` expands (even, the ``\\\\``
    is one literal backslash and the ``$`` is live). A single-char ``(?<!\\)``
    lookbehind gets the even-run case wrong and silently under-scans; counting the
    run in Python is the correct, readable fix. Backticks follow the same rule and
    are always violations (command substitution has no allowlisted open() shape).
    """
    for match in _EXPANSION_CHAR.finditer(body):
        pos = match.start()
        backslashes = 0
        cursor = pos - 1
        while cursor >= 0 and body[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            yield pos, body[pos]


# The (optional) simple var name immediately after a ``$`` — used only to test the
# open() carve-out. ``$(...)`` / ``${!V}`` yield no name and are always violations.
# The leading ``\{?`` lets ``${VAR}`` match past the brace; only ``group(1)`` is read,
# so no trailing ``\}?`` is needed to consume the closing brace.
_VARNAME = re.compile(r"\{?(\w+)")

# The interpolation site is the argument of ``open(`` (any whitespace / opening
# quote may sit between). Anchored at end-of-prefix, so distance does not matter.
_OPEN_ARG = re.compile(r"""open\(\s*['"]?$""")

# A bash assignment at ANY indentation. Column-0-only (``^`` without ``[ \t]*``)
# missed a reassignment nested in an ``if``/``for``/function block — the exact
# ``  WORKSPACE=$(id)`` smuggle the allowlist must taint. Python-body lines survive
# unscathed: Python spells assignment with spaces (``x = ...``), which ``\w+=`` does
# not match, so only real shell ``name=value`` assignments are considered.
_ASSIGN = re.compile(r"^[ \t]*(?:export\s+)?(\w+)=(.*)$", re.MULTILINE)

# A *fully* harness-rooted assignment RHS: the ``$WORKSPACE``/``$TASK_DIR`` root
# (braced or bare, not ``$WORKSPACEFOO``) followed to end-of-string by ONLY literal
# path characters — no further ``$`` expansion, ``$(...)``/backtick command
# substitution, or concatenation onto agent-influenced content. Anchoring the END
# (``[^$`]*$``) is load-bearing: ``.match`` alone anchored only the prefix, so
# ``"${WORKSPACE}/$(jq .p answer.json)"`` was judged harness-safe and its
# agent-controlled tail flowed into ``open()``. Anything the pattern cannot fully
# account for fails closed (the var is not allowlisted).
_HARNESS_RHS = re.compile(
    r"""^"?\$(?:\{(?:WORKSPACE|TASK_DIR)\}|(?:WORKSPACE|TASK_DIR)(?![A-Za-z0-9_]))"""
    r"""[^$`]*$"""
)


def _harness_path_vars(script_text: str) -> set[str]:
    """Vars safe to interpolate into ``open(...)`` — every assignment is harness-rooted.

    ``WORKSPACE``/``TASK_DIR`` seed the set (they arrive from the harness env), but a
    non-harness assignment to *any* name — including those two — removes it, so an
    agent-influenced value routed through a harness-named var is not allowlisted.
    """
    safe = {"WORKSPACE", "TASK_DIR"}
    assignments: dict[str, list[str]] = defaultdict(list)
    for match in _ASSIGN.finditer(script_text):
        assignments[match.group(1)].append(match.group(2).strip())
    for var, rhs_values in assignments.items():
        if all(_HARNESS_RHS.match(rhs) for rhs in rhs_values):
            safe.add(var)
        else:
            safe.discard(var)
    return safe


def _expanded_bodies(script_text: str) -> list[str]:
    """Every Python body bash will perform expansion on: double-quoted ``-c`` bodies
    (``\\"`` normalised to ``"`` as the interpreter sees it) plus unquoted heredocs."""
    bodies = [m.group(1).replace('\\"', '"') for m in _PY_BODY.finditer(script_text)]
    bodies += [
        m.group("body")
        for m in _HEREDOC.finditer(script_text)
        if m.group("q") == ""  # unquoted delimiter → bash expands
    ]
    return bodies


def _injection_sites(script_text: str) -> list[str]:
    """Describe each shell expansion into an expanded Python body. Empty == clean.

    Every unescaped ``$`` is a violation EXCEPT a harness-derived path var used as an
    ``open(...)`` argument (read as data, never as source).
    """
    harness = _harness_path_vars(script_text)
    sites: list[str] = []
    for body in _expanded_bodies(script_text):
        for pos, char in _live_expansions(body):
            var = None
            if char == "$":
                name_match = _VARNAME.match(body[pos + 1 :])
                var = name_match.group(1) if name_match else None
                if var in harness and _OPEN_ARG.search(body[:pos]):
                    continue
            line_start = body.rfind("\n", 0, pos) + 1
            line_end = body.find("\n", pos)
            line = body[line_start : line_end if line_end != -1 else None].strip()
            token = f"${var}" if var else ("`…`" if char == "`" else "$(…)")
            sites.append(f"{token}: {line[:60]!r}")
    return sites


def _check_scripts() -> list[Path]:
    return sorted(BENCHMARKS.rglob("checks/*.sh"))


@pytest.mark.security
def test_scripts_discovered() -> None:
    """A broken glob returning zero scripts would make the sweep vacuously green."""
    scripts = _check_scripts()
    assert len(scripts) > 400, (
        f"expected the full benchmarks check-script corpus, found {len(scripts)} — "
        "the glob is broken or the tree moved; the sweep would false-pass."
    )


@pytest.mark.security
def test_no_python_injection_repo_wide() -> None:
    """No check script anywhere expands a shell value into a Python body.

    One assertion over the whole corpus (~500+ scripts, sub-second): the forge-the-
    verdict class from qvpzt / 0rv.23, but not tied to a filename, a directory, or
    the ``'''`` spelling. Every offender is reported at once.
    """
    offenders = {
        str(script.relative_to(ROOT)): sites
        for script in _check_scripts()
        if (sites := _injection_sites(script.read_text()))
    }
    assert not offenders, (
        "check scripts expand a shell value into a Python body (shell-into-Python "
        "injection — the forgeable-verdict class from qvpzt / 0rv.23), reachable "
        f"anywhere in the corpus:\n{offenders}"
    )


# Bodies the detector MUST flag — one per distinct vector reviewers surfaced.
# ``$AGENT*`` stands in for an agent-influenced value; the harness-rooted preamble
# is included where an allowlist-bypass is being exercised.
_VULNERABLE = {
    "triple-single (original qvpzt)": 'python3 -c "\nx = \'\'\'$AGENT_FILES\'\'\'\n"',
    "single-quote literal": 'python3 -c "\nx = \'$AGENT_FILES\'\n"',
    "escaped double-quote literal": 'python3 -c "\nx = \\"$AGENT_FILES\\"\n"',
    "bare expansion as code": 'python3 -c "\nresult = $AGENT_SCORE\n"',
    "command substitution": (
        'python3 -c "\nx = \'\'\'$(cat \\"$WORKSPACE/answer.json\\")\'\'\'\n"'
    ),
    "backtick command substitution": (
        "python3 -c \"\nx = '''`cat answer.json`'''\n\""
    ),
    "flag before -c (python3 -W ignore -c)": (
        'python3 -W ignore -c "\nx = \'$AGENT_FILES\'\n"'
    ),
    "even backslash run keeps $ live": (
        'python3 -c "\nx = \'\\\\$AGENT_FILES\'\n"'
    ),
    "unquoted heredoc body": "python3 <<PYEOF\nx = '''$AGENT_FILES'''\nPYEOF",
    "allowlist bypass: reassigned harness var": (
        'REPORT="${WORKSPACE}/answer.json"\n'
        'REPORT="$(jq -r .path "$REPORT")"\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    # BLOCKING-1: harness root then a command-substitution TAIL on the SAME
    # assignment. Prefix-only anchoring judged this safe; full-RHS anchoring taints it.
    "allowlist bypass: harness root + command-subst tail": (
        'REPORT="${WORKSPACE}/$(jq -r .path answer.json)"\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    "allowlist bypass: reassigned WORKSPACE": (
        'WORKSPACE="$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # BLOCKING-2: reassignment INDENTED inside a control block. Column-0-only
    # scanning left the harness var in the safe set; ``^[ \t]*`` taints it.
    "allowlist bypass: indented WORKSPACE reassignment": (
        'if true; then\n'
        '    WORKSPACE="$(id)"\n'
        'fi\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
}

# Bodies the detector MUST NOT flag.
_SAFE = {
    "harness path into open() (REPORT)": (
        'REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    "harness path into open(), spaced/newline": (
        'GT="${TASK_DIR}/ground_truth.json"\n'
        "python3 -c \"\nwith open(\n    '${GT}') as f:\n    pass\n\""
    ),
    # bash single-quoted -c body: bash does NOT expand, so no vector.
    "single-quoted -c body (no expansion)": (
        "python3 -c '\nagent_files = \"\"\"$AGENT_FILES\"\"\"\n'"
    ),
    # quoted heredoc delimiter: bash does NOT expand the body.
    "quoted heredoc delimiter (no expansion)": (
        "python3 <<'PYEOF'\nagent_files = '''$AGENT_FILES'''\nPYEOF"
    ),
    # escaped \$ is passed through literally by bash — not expanded.
    "escaped-dollar literal": 'python3 -c "\nx = \'\\$AGENT_FILES\'\n"',
}


@pytest.mark.security
@pytest.mark.parametrize("label,script", _VULNERABLE.items(), ids=list(_VULNERABLE))
def test_detector_catches_known_vectors(label: str, script: str) -> None:
    """The detector matches the class, not one spelling — proves non-vacuous."""
    assert _injection_sites(script), f"detector missed the {label} vector"


@pytest.mark.security
@pytest.mark.parametrize("label,script", _SAFE.items(), ids=list(_SAFE))
def test_detector_allows_safe_patterns(label: str, script: str) -> None:
    """Harness-path open() and non-expanding bodies must not be flagged."""
    assert not _injection_sites(script), (
        f"detector false-flagged the safe {label} pattern: {_injection_sites(script)}"
    )
