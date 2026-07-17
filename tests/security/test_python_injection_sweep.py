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
``open('${HARNESS_VAR}')`` and cannot see what the body does with the bytes.

Some classes are deliberately out of scope, each verified absent from the corpus
today — so this is a documentation note, not a live hole; fold each in when a real
script needs it:

* Python-level code-exec of file contents (``exec(open('${REPORT}').read())``)
  passes the structural shape check above — a different class, and no ``exec`` /
  ``eval`` appears in any check script.
* an interpreter reached through a shell var (``PY=python3`` then ``$PY -c "…"``)
  is not recognised as a Python call — ``$VAR -c`` = 0 hits.
* a body piped into the interpreter (``cat … | python3``) is neither a ``-c``
  string nor a heredoc — ``| python`` = 0 hits.
* runtime word-splitting via a *non-``$IFS``* whitespace-valued expansion: a script
  that sets ``SP=' '`` and writes ``python3$SP-c …`` would split at runtime but is
  read as one bare word here. ``$IFS``/``${IFS}`` — the canonical, fixed-name,
  no-setup form — IS modelled (``_ifs_len``); ``$SP`` requires attacker-side setup
  and is 0 hits. A ``declare -n`` nameref aliasing a harness var writes through an
  indirection this static scan cannot resolve; its presence collapses the allowlist
  to empty (``_OPAQUE_WRITE``) rather than being silently trusted.

Performance note: the heredoc arms use a non-greedy DOTALL body capture whose
worst case is superlinear in the count of *unterminated* heredoc openers within one
file (a typo'd terminator). Check scripts are small, so the whole >500-script sweep
stays well under a second; a ``"<<" not in`` fast-path skips the scan for
heredoc-free scripts, and a hard body bound is tracked as follow-up EnterpriseBench-b5mmv.

Superseded eventually by rmz1x (migrate these blobs onto
``eb_verify.scorers.file_extraction``); until then this is the backstop.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
BENCHMARKS = ROOT / "benchmarks"

# A heredoc-fed Python invocation. ``python[0-9.]*`` tolerates ``python3.11`` etc.,
# then ANY run of argv tokens (``(?:[ \t]+[^\s<]+)*`` — each token stops before the
# ``<`` of ``<<``) may sit between the interpreter and ``<<``. This is load-bearing:
# the dominant corpus form is ``python3 - "$REPORT" "$GT_DIR" <<DELIM`` (a ``-``
# stdin script plus positional args), and a prior spelling that required ``<<`` to
# follow the interpreter directly matched 0 of 27 corpus heredoc scripts — a dead
# arm that let a future author copy that idiom with an UNQUOTED delimiter and
# interpolate agent data undetected. Only an *unquoted* delimiter triggers bash
# expansion inside the body; ``<<'DELIM'`` / ``<<"DELIM"`` are literal (safe) and
# skipped via the captured quote group.
#
# The terminator must be the *entire* line — the delimiter alone (for ``<<-``,
# preceded only by tabs), then end-of-line or end-of-file. Bash ends a heredoc only
# on a line equal to the delimiter; trailing text after it (even one space) does NOT
# terminate. Two decoy shapes exploited an over-loose terminator:
#   * a tab-INDENTED delimiter on a plain ``<<DELIM`` — ``(?P<dash>-)?`` records the
#     form and ``(?(dash)\t*|)`` allows leading tabs only for the dash form.
#   * a delimiter followed by TRAILING text (``PYEOF=1``, ``PYEOF )``) — the prior
#     ``(?P=delim)\b`` matched on the word boundary alone, so any non-word char after
#     the delimiter looked like a terminator; ``(?:\r?\n|\Z)`` now requires nothing
#     between the delimiter and the line end.
# Either decoy truncated the scanned body early while bash read the full body past
# it, hiding an injection after the decoy. Being stricter than bash here can only
# over-scan (fail-closed), never miss a real terminator.
_HEREDOC = re.compile(
    r"""python[0-9.]*(?:[ \t]+[^\s<]+)*[ \t]*<<(?P<dash>-)?[ \t]*"""
    r"""(?P<q>['"]?)(?P<delim>\w+)(?P=q)[^\n]*\r?\n"""
    r"""(?P<body>.*?)\r?\n(?(dash)\t*|)(?P=delim)(?:\r?\n|\Z)""",
    re.DOTALL,
)

# Any command's heredoc (not just python's), used only to blank heredoc *bodies*
# before the ``-c`` scan below — a body is content the script author wrote, and a
# ``python3 -c "…$x…"`` example line quoted inside a *safe* (quoted-delimiter)
# heredoc body must not be mistaken for a live ``-c`` invocation. Same column-rules
# conditional as ``_HEREDOC``.
_ANY_HEREDOC = re.compile(
    r"""<<(?P<dash>-)?[ \t]*(?P<q>['"]?)(?P<delim>\w+)(?P=q)[^\n]*\r?\n"""
    r"""(?P<body>.*?)\r?\n(?(dash)\t*|)(?P=delim)(?:\r?\n|\Z)""",
    re.DOTALL,
)


def _strip_heredoc_bodies(script_text: str) -> str:
    """Blank each *quoted*-delimiter heredoc body, keeping line structure.

    Only ``<<'DELIM'`` / ``<<"DELIM"`` bodies are blanked: bash does NOT expand them,
    so a ``python3 -c "…$x…"`` example line quoted inside one is inert text, not a
    live invocation, and must not be mistaken for one by the ``-c`` scanner. An
    *unquoted*-delimiter body IS bash-expanded, so it is left in place — a
    ``$(python3 -c "…$AGENT…")`` command substitution inside e.g. a ``cat <<A`` body
    genuinely runs and must be scanned by ``_c_bodies`` (blanking it hid exactly that
    injection). ``_HEREDOC`` separately scans unquoted heredoc bodies destined for
    python itself.

    The ``"<<" not in`` short-circuit skips the DOTALL regex entirely for the many
    scripts with no heredoc. The regex's non-greedy body capture is worst-case
    superlinear in the count of *unterminated* openers within a single file (a
    typo'd terminator); check scripts are small so this stays sub-millisecond in
    practice, and a hard bound is tracked as a follow-up (see module docstring)."""
    if "<<" not in script_text:
        return script_text

    def _blank(m: re.Match[str]) -> str:
        if m.group("q"):  # quoted delimiter → literal (unexpanded) body, safe to blank
            return "<<" + m.group("delim") + "\n"
        return m.group(0)  # unquoted delimiter → bash-expanded, keep for the -c scan

    return _ANY_HEREDOC.sub(_blank, script_text)


# ``python[0-9.]*`` as a *whole* word (the interpreter), so ``pythonic`` or a path
# ending ``…/python3x`` is not mistaken for it.
_PYTHON_WORD = re.compile(r"python[0-9.]*\Z")

# ``$IFS`` / ``${IFS}`` (not ``$IFSFOO``). Bash word-splits on the *value* of
# ``$IFS`` (whitespace by default), so ``python3${IFS}-c${IFS}"$X"`` runs as three
# argv words at runtime despite holding no literal space. The word walkers below
# treat it as an inter-word boundary; otherwise the whole construct is swallowed as
# one bare word, ``python[0-9.]*`` never matches it, and the ``-c`` injection is
# unscanned. Other whitespace-valued expansions (a script-defined ``SP=' '`` used as
# ``$SP``) stay a disclosed out-of-scope gap — ``$IFS`` is the canonical, fixed-name
# trick and the only one that needs no attacker-side setup.
_IFS = re.compile(r"\$(?:\{IFS\}|IFS(?![A-Za-z0-9_]))")


def _ifs_len(text: str, i: int) -> int:
    """Length of an unquoted ``$IFS``/``${IFS}`` token at ``text[i]``, else ``0``."""
    m = _IFS.match(text, i)
    return m.end() - i if m else 0


def _skip_quote(text: str, i: int) -> int | None:
    """If ``text[i]`` opens a quote/substitution/escape, return the index just past
    it; else ``None``. Consuming these whole is what keeps their inner spaces and
    metacharacters from being read as word boundaries."""
    n = len(text)
    c = text[i]
    if c == "\\":
        return min(i + 2, n)
    if c == "'":
        j = text.find("'", i + 1)
        return (j + 1) if j >= 0 else n
    if text.startswith("$'", i):  # ANSI-C quoting: C escapes, but no var expansion
        j = i + 2
        while j < n:
            if text[j] == "\\":
                j += 2
            elif text[j] == "'":
                return j + 1
            else:
                j += 1
        return n
    if c == '"':
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
            elif text[j] == '"':
                return j + 1
            elif text.startswith("$(", j) or text[j] == "`":
                # bash re-parses a ``$(...)``/backtick inside double quotes, so a ``"``
                # within it does NOT close the outer string; skip the whole substitution
                # (its interior is recursed for nested ``-c`` bodies elsewhere).
                nxt = _skip_quote(text, j)
                j = nxt if nxt is not None else n
            else:
                j += 1
        return n
    if c == "`":
        j = text.find("`", i + 1)
        return (j + 1) if j >= 0 else n
    if text.startswith("$(", i):
        depth, j = 1, i + 2
        while j < n and depth:
            cj = text[j]
            if cj == "\\":
                j += 2
                continue
            # bash re-parses quoting independently inside ``$(...)``; skip a nested
            # quote / substitution WHOLE so a ``)`` (or ``(``) sitting inside it does
            # not move the depth counter. Counting bare parens alone let
            # ``$(f ')' )`` close early, desyncing the word walk so a following
            # ``-c "…$AGENT…"`` invocation went unscanned entirely.
            if cj in "'\"`" or text.startswith(("$(", "$'"), j):
                nxt = _skip_quote(text, j)
                j = nxt if nxt is not None else n
                continue
            if cj == "(":
                depth += 1
            elif cj == ")":
                depth -= 1
            j += 1
        return j
    return None


_WORD_END = frozenset(" \t\n;&|<>()")


def _word_end(text: str, i: int, stop_at_ifs: bool = True) -> int:
    """The index just past the quote-aware shell word starting at ``text[i]``.

    A word ends at the first ``_WORD_END`` char that is not inside a quote /
    ``$(...)`` / backtick (those are consumed whole by ``_skip_quote`` so their
    inner spaces and metacharacters are not read as boundaries). Shared by every
    word-walker below so the boundary rule lives in exactly one place.

    ``stop_at_ifs`` ends the word at an unquoted ``$IFS``/``${IFS}`` — correct for a
    COMMAND word (bash word-splits on ``$IFS`` at runtime). It must be ``False`` for
    an assignment RHS: assignments do NOT word-split, so ``VAR=${WORKSPACE}${IFS}$X``
    is one value whose ``$X`` tail must stay in the RHS to be seen as non-harness."""
    n = len(text)
    j = i
    while j < n and text[j] not in _WORD_END:
        if stop_at_ifs and j > i and _ifs_len(text, j):
            break  # ``$IFS`` word-splits a COMMAND at runtime: a boundary
        nxt = _skip_quote(text, j)
        j = nxt if nxt is not None else j + 1
    return j


def _word_expanding(text: str, i: int) -> str:
    """The *expanding* text of the shell word starting at ``text[i]``.

    A word ends at the first unquoted whitespace or command metacharacter. Its
    expanding text is the concatenation of every segment bash would expand —
    unquoted runs (incl. bare ``$VAR``), double-quoted contents, ``$(...)`` and
    backticks (all kept raw so ``_live_expansions`` flags the ``$``/backtick; the
    inert ``"`` delimiters do not introduce false expansions) — with single-quoted
    and ``$'...'`` segments dropped (bash performs no expansion in them).
    Backslashes are preserved so backslash-parity in ``_live_expansions`` still
    holds. Adjacent concatenation (``"a"$V'b'"c"``) is one word, so a bare ``$VAR``
    glued after a closing quote is captured rather than left unscanned."""
    n = len(text)
    out: list[str] = []
    while i < n:
        c = text[i]
        if c in _WORD_END:
            break
        if c == "'":  # single-quoted: dropped (no expansion)
            j = text.find("'", i + 1)
            i = (j + 1) if j >= 0 else n
        elif text.startswith("$'", i):  # ANSI-C: dropped (no var expansion)
            nxt = _skip_quote(text, i)
            i = nxt if nxt is not None else n
        elif c == '"' or c == "`" or text.startswith("$(", i):
            # double-quote / backtick / ``$(...)``: keep RAW, including the
            # delimiters. Slicing the interior invited an off-by-one that dropped
            # the final char of an *unterminated* ``"…`` (``_skip_quote`` returns
            # ``n`` there, not closing-quote+1); the delimiter chars are inert for
            # ``$``/backtick detection, so keeping them whole is both correct and
            # simpler.
            nxt = _skip_quote(text, i)
            end = nxt if nxt is not None else n
            out.append(text[i:end])
            i = end
        elif c == "\\":
            out.append(text[i : i + 2])
            i += 2
        else:  # bare char, incl. a live ``$`` beginning ``$VAR``/``${VAR}``
            out.append(c)
            i += 1
    return "".join(out)


def _c_bodies(script_text: str) -> list[str]:
    """Every expanding Python body passed as a ``python … -c`` argument, INCLUDING
    invocations nested in a command substitution (``VAR=$(python3 -c "…")`` — 16
    corpus scripts do exactly this) at any depth. Strips quoted-heredoc bodies first
    (so a ``-c`` example inside a safe heredoc is not rescanned)."""
    return _scan_commands(_strip_heredoc_bodies(script_text))


def _scan_commands(text: str) -> list[str]:
    """Scan a COMMAND context for ``python … -c`` bodies.

    Words are walked quote-aware. On an interpreter word, forward tokens up to the
    next command separator are the invocation: flag tokens (and any argument, quoted
    or not) are skipped until ``-c``, whose argument word — separate, or glued as
    ``-c"…"`` — is the body (so a quoted flag value ``-W "ignore::X"`` no longer hides
    it). A ``$(...)``/backtick command substitution EXECUTES, so its interior is a
    nested command context and is recursed into; a standalone double-quoted word is
    not a command line, but any ``$(...)`` embedded in it still runs, so it is scanned
    for those (``_scan_dquote``). Single-quoted / ``$'…'`` words are inert and skipped."""
    n = len(text)
    bodies: list[str] = []
    i = 0
    while i < n:
        c = text[i]
        if c in _WORD_END:  # inter-word / separator run
            i += 1
            continue
        if ilen := _ifs_len(text, i):  # ``$IFS`` acts as whitespace between words
            i += ilen
            continue
        if text.startswith("$(", i) or c == "`":  # command substitution → recurse
            end = _skip_quote(text, i)
            end = end if end is not None else n
            bodies += _scan_commands(_delimited_interior(text, i, end))
            i = end
            continue
        if c == '"':  # double-quoted word: scan only for embedded command subs
            end = _skip_quote(text, i)
            end = end if end is not None else n
            bodies += _scan_dquote(_delimited_interior(text, i, end))
            i = end
            continue
        nxt = _skip_quote(text, i)
        if nxt is not None:  # single-quoted / ``$'…'`` — inert, skip whole
            i = nxt
            continue
        j = _word_end(text, i)  # a bare word
        if _PYTHON_WORD.match(text, i, j):
            resume, body = _consume_c_invocation(text, j)
            i = resume
            if body is not None:
                bodies.append(body)
        else:
            # A non-interpreter bare word may still EMBED a command substitution
            # (``VAR=$(python3 -c "…")`` — the dominant corpus shape), which
            # ``_word_end`` consumed whole; scan the word for those.
            bodies += _scan_dquote(text[i:j])
            i = j
    return bodies


def _delimited_interior(text: str, i: int, end: int) -> str:
    """The interior of the ``$(…)`` / `` `…` `` / ``"…"`` opened at ``text[i]`` and
    closed just before ``end`` (``_skip_quote``'s return). Drops the opener (``$(``,
    `` ` ``, or ``"``) and, when the closer is present, the trailing delimiter."""
    start = i + 2 if text.startswith("$(", i) else i + 1
    closer = ")" if text.startswith("$(", i) else text[i]
    stop = end - 1 if end > start and text[end - 1 : end] == closer else end
    return text[start:stop]


def _scan_dquote(interior: str) -> list[str]:
    """A double-quoted string is not a command line, but any ``$(...)`` / backtick it
    embeds still executes — recurse into those (and only those) for nested ``-c``
    bodies. A bare ``python3 -c …`` sitting in double-quoted *text* is inert and must
    NOT be read as an invocation (``echo "run python3 -c $X"`` prints, not runs)."""
    n = len(interior)
    bodies: list[str] = []
    i = 0
    while i < n:
        if interior.startswith("$(", i) or interior[i] == "`":
            end = _skip_quote(interior, i)
            end = end if end is not None else n
            bodies += _scan_commands(_delimited_interior(interior, i, end))
            i = end
        elif interior[i] == "\\":
            i += 2
        else:
            i += 1
    return bodies


def _consume_c_invocation(text: str, start: int) -> tuple[int, str | None]:
    """From ``start`` (just past an interpreter word), find this command's ``-c``
    argument. Returns ``(resume_index, body_or_None)`` — the body is the expanding
    text of the ``-c`` argument if one is present, else ``None``."""
    n = len(text)
    k = start
    while k < n:
        c = text[k]
        if c in ";&|\n()":  # command boundary — no ``-c`` in this command
            return k, None
        if c in " \t<>":  # inter-word whitespace or a redirection operator — skip
            k += 1
            continue
        if ilen := _ifs_len(text, k):  # ``$IFS`` word-splits: inter-word whitespace
            k += ilen
            continue
        nxt = _skip_quote(text, k)
        if nxt is not None:  # a quoted token (e.g. a flag value) — skip it
            k = nxt
            continue
        j = _word_end(text, k)  # bare token
        tok = text[k:j]
        if tok == "-c":  # body is the next word
            m = j
            while m < n:  # skip whitespace and ``$IFS`` between ``-c`` and its arg
                if text[m] in " \t":
                    m += 1
                elif il := _ifs_len(text, m):
                    m += il
                else:
                    break
            if m < n and text[m] not in ";&|\n()<>":
                return j, _word_expanding(text, m)
            return j, None
        if tok.startswith("-c"):  # glued: ``-c"…"`` / ``-cCODE``
            return j, _word_expanding(text, k + 2)
        k = j
    return k, None


def _live_expansions(body: str) -> Iterator[tuple[int, str]]:
    """Yield ``(position, char)`` for each *live* bash expansion (``$`` or backtick).

    A ``$`` or backtick is live iff preceded by an **even** number of backslashes
    (zero counts): ``\\$`` is escaped (odd), ``\\\\$`` expands (even, the ``\\\\``
    is one literal backslash and the ``$`` is live). A single-char ``(?<!\\)``
    lookbehind gets the even-run case wrong and silently under-scans; counting the
    run in Python is the correct, readable fix. Backticks are command substitution
    and follow the same rule — always violations (no allowlisted open() shape).
    """
    for pos, char in enumerate(body):
        if char not in "$`":
            continue
        backslashes = 0
        cursor = pos - 1
        while cursor >= 0 and body[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            yield pos, char


# The (optional) simple var name immediately after a ``$`` — used only to test the
# open() carve-out. ``$(...)`` / ``${!V}`` yield no name and are always violations.
# The leading ``\{?`` lets ``${VAR}`` match past the brace; only ``group(1)`` is read,
# so no trailing ``\}?`` is needed to consume the closing brace.
_VARNAME = re.compile(r"\{?(\w+)")

# The interpolation site is the argument of ``open(`` (any whitespace / opening
# quote may sit between). Anchored at end-of-prefix, so distance does not matter.
_OPEN_ARG = re.compile(r"""open\(\s*['"]?$""")

# A ``name=`` / ``name[subscript]=`` / ``name+=`` write, matched BROADLY over the
# raw (continuation-joined) script — deliberately NOT anchored to a command start.
# The prior name-then-``=`` anchor was fail-*open*: any write spelling it did not
# enumerate (``NAME[0]=``, a second space-joined ``A=1 B=2`` assignment, or the
# literal ``NAME=`` inside an ``eval "NAME=…"`` string) left the harness seed
# untouched and trusted. A broad raw scan instead SEES all of those — the ``[0]``
# subscript sits between name and ``=`` (captured, and any subscript write is
# non-clean by construction), a co-located assignment is just another match, and
# an ``eval``-smuggled assignment appears verbatim in the text. Over-matching a
# ``NAME=`` inside a comment or a no-space Python body assignment only over-*taints*
# a name — the fail-closed direction, and harmless unless that name is a harness
# var actually interpolated into ``open()`` (verified absent in the corpus sweep).
_WRITE = re.compile(r"\b(\w+)(\[[^\]]*\])?(\+?=)")

# Builtins that WRITE a variable without a ``name=`` shape, matched as command words
# ANYWHERE (``.finditer`` over the whole script), NOT anchored to a recognised
# command start. ``read``/``mapfile``/``readarray`` take stdin/agent data into their
# targets; ``printf -v NAME`` writes ``NAME``; ``for NAME in`` / ``select`` bind
# ``NAME``. A prior version anchored these at a fragment start with an *enumerated*
# lead (``while``/``if``/``do``/``{``…); every lead it forgot — a ``case`` arm
# (``*) read WS``), a function body (``f() { read WS; }``), ``coproc`` — hid the write
# and left the harness seed trusted. Un-anchoring drops the enumeration entirely: the
# builtin is found wherever it sits. Over-matching the word inside a comment or a
# Python body only over-taints (fail-closed), harmless unless it hits a var actually
# used in an ``open()`` carve-out (verified 0 offenders across the corpus sweep).
_READ = re.compile(r"\b(?:read|mapfile|readarray)\b([^\n;&|]*)")
_PRINTF_V = re.compile(r"\bprintf\b(?:\s+-\w+)*\s+-v\s*(\w+)")
_FOR = re.compile(r"\b(?:for|select)\s+(\w+)\s+in\b")
# Bash parameter-expansion assignment forms ``${NAME:=val}`` / ``${NAME=val}`` write
# NAME as a side effect (``:-`` / ``:+`` / ``:?`` do NOT assign, so ``:?=`` requires
# the ``=``). Invisible to the ``name=``-shaped ``_WRITE``; recorded as a non-clean
# write so a harness var defaulted to agent data is not left trusted.
_DEFAULT_ASSIGN = re.compile(r"\$\{(\w+):?=")

# Constructs whose write EFFECT this single-file static scan cannot resolve, so their
# mere presence collapses the allowlist to empty (see ``_harness_path_vars``) rather
# than risk trusting a var they silently reassigned: ``eval`` / ``coproc`` (run a
# constructed or re-parsed command), a ``-n`` nameref (writes through an alias), and
# ``source``/``.`` (the write lives in ANOTHER file). All are absent from the corpus,
# so the sweep stays green; a future script using one forgoes the ``open()`` carve-out
# and must route paths via ``os.environ``. ``$IFS`` is deliberately NOT here — it is
# normalised to a space for builtin detection (see ``_var_writes``), so an
# ``$IFS``-glued write is SEEN rather than collapsed on.
_OPAQUE_WRITE = re.compile(
    r"\beval\b|\bcoproc\b"
    r"|\b(?:declare|local|typeset|readonly)\s+-\w*n"
    r"|(?:^|[;&|])[ \t]*(?:source|\.)[ \t]+\S",
    re.MULTILINE,
)

# A *fully* harness-rooted assignment RHS, in TWO anchored alternatives so a value
# that lost its closing quote — or carries a ``$AGENT`` tail — fails closed:
#
#   * double-quoted — opens ``"``, the harness root, then ONLY literal path chars
#     (no ``$`` expansion, ``$(...)``/backtick, or another ``"``), then a REQUIRED
#     closing ``"`` at end. ``REPORT="${WORKSPACE}/x|$AGENT"`` — a ``|`` inside the
#     quotes — has its ``$AGENT`` tail in the RHS word, which the ``[^$`"]`` body
#     rejects, so this alternative fails and the var is tainted.
#   * bare (unquoted) — the harness root then literal path chars with no
#     whitespace, quote, or expansion, to end.
#
# The root is ``${WORKSPACE}``/``${TASK_DIR}`` (braced) or bare ``$WORKSPACE`` (not
# ``$WORKSPACEFOO``). Anchoring the END is load-bearing: prefix-only matching judged
# ``"${WORKSPACE}/$(jq .p answer.json)"`` harness-safe and let its agent-controlled
# tail flow into ``open()``. Anything the anchors cannot fully account for — a
# default-value expansion ``${WORKSPACE:-…}``, a single-quoted RHS — fails closed.
_ROOT = r"\$(?:\{(?:WORKSPACE|TASK_DIR)\}|(?:WORKSPACE|TASK_DIR)(?![A-Za-z0-9_]))"
_HARNESS_RHS = re.compile(
    rf'^"{_ROOT}[^$`"]*"$'  # double-quoted: closing quote required
    rf'|^{_ROOT}[^$`"\s]*$'  # bare: no whitespace / quote / expansion
)


def _var_writes(script_text: str) -> dict[str, list[bool]]:
    """Map each written var name to a list of ``is_clean`` flags, one per write.

    A write is *clean* iff it is a plain (un-subscripted) ``name=<harness-rooted-
    literal-path>`` assignment. Append (``+=``), any subscript write, ``read`` /
    ``mapfile`` / ``printf -v`` / ``for``-binding, ``${NAME:=…}`` default-assignment,
    and any RHS the ``_HARNESS_RHS`` anchor cannot fully vet are non-clean. The caller
    trusts a var only when *every* recorded write is clean, so a broad-scan false
    write can only over-taint.
    """
    writes: dict[str, list[bool]] = defaultdict(list)
    # bash removes a backslash-newline before tokenizing, so a continued
    # ``VAR=<root>\<newline><agent-tail>`` is really one assignment; join first, else
    # only the clean-looking first physical line is seen and the var is trusted.
    joined = script_text.replace("\\\n", "")
    # Assignment writes — broad, so subscript / space-joined / eval-embedded writes are
    # all seen. Cleanliness needs the RHS word, walked quote-aware from the ``=`` with
    # ``stop_at_ifs=False``: an assignment RHS does NOT word-split, so a
    # ``VAR=${WORKSPACE}${IFS}$AGENT`` tail must stay in the RHS to be seen as
    # non-harness (normalising ``$IFS`` here would truncate the RHS and wrongly clean it).
    for mo in _WRITE.finditer(joined):
        name, subscript, op = mo.group(1), mo.group(2), mo.group(3)
        rhs = joined[mo.end() : _word_end(joined, mo.end(), stop_at_ifs=False)]
        clean = op == "=" and subscript is None and bool(_HARNESS_RHS.match(rhs))
        writes[name].append(clean)
    # ``${NAME:=…}`` / ``${NAME=…}`` default-assignment writes — never a clean path.
    for mo in _DEFAULT_ASSIGN.finditer(joined):
        writes[mo.group(1)].append(False)
    # Write builtins (read / mapfile / readarray / printf -v / for / select), found as
    # command words ANYWHERE. Run on ``$IFS``-normalised text so an ``$IFS``-glued write
    # (``read${IFS}-r${IFS}WS``) word-splits into visible tokens — unlike an assignment
    # RHS, a COMMAND does word-split, so revealing more here is correct AND fail-closed.
    ntext = _IFS.sub(" ", joined)
    for mo in _READ.finditer(ntext):
        for token in mo.group(1).split():
            if not token.startswith("-") and token.isidentifier():
                writes[token].append(False)
    for mo in _PRINTF_V.finditer(ntext):
        writes[mo.group(1)].append(False)
    for mo in _FOR.finditer(ntext):
        writes[mo.group(1)].append(False)
    return writes


def _harness_path_vars(script_text: str) -> set[str]:
    """Vars safe to interpolate into ``open(...)`` — every write is harness-rooted.

    ``WORKSPACE``/``TASK_DIR`` seed the set (they arrive from the harness env), but a
    non-harness write to *any* name — including those two — removes it, so an
    agent-influenced value routed through a harness-named var is not allowlisted.
    Fail-closed: a var is trusted only if it has writes and *all* of them are clean,
    or it is an unwritten seed; and if the script uses an opaque-write construct
    (``eval`` / ``coproc`` / ``-n`` nameref / ``source`` / ``.``) the whole allowlist
    collapses to empty.
    """
    if _OPAQUE_WRITE.search(script_text):
        return set()
    safe = {"WORKSPACE", "TASK_DIR"}
    for var, cleans in _var_writes(script_text).items():
        if all(cleans):  # every write clean (a var with no writes never appears here)
            safe.add(var)
        else:
            safe.discard(var)
    return safe


def _expanded_bodies(script_text: str) -> list[str]:
    """Every Python body bash performs expansion on before Python parses it:

    * each ``python … -c`` argument, extracted quote-aware by ``_c_bodies`` (heredoc
      bodies stripped first, so a ``-c`` example line quoted inside a safe heredoc is
      not rescanned);
    * each *unquoted*-delimiter heredoc body (``<<PYEOF`` — bash expands;
      ``<<'PYEOF'`` is literal and skipped via the captured quote group).
    """
    bodies = _c_bodies(script_text)
    if "<<" in script_text:  # skip the DOTALL heredoc scan when there is no heredoc
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
                name_match = _VARNAME.match(body, pos + 1)
                var = name_match.group(1) if name_match else None
                if var in harness and _OPEN_ARG.search(body, 0, pos):
                    continue
            line_start = body.rfind("\n", 0, pos) + 1
            line_end = body.find("\n", pos)
            line = body[line_start : line_end if line_end != -1 else None].strip()
            token = f"${var}" if var else ("`…`" if char == "`" else "$(…)")
            sites.append(f"{token}: {line[:60]!r}")
    return sites


# The full check-script corpus, discovered once (the tree is walked at import, not
# per test). ``test_scripts_discovered`` guards against a broken glob silently
# yielding zero scripts, which would make the sweep vacuously green.
_SCRIPTS = sorted(BENCHMARKS.rglob("checks/*.sh"))


@pytest.mark.security
def test_scripts_discovered() -> None:
    """A broken glob returning zero scripts would make the sweep vacuously green."""
    assert len(_SCRIPTS) > 400, (
        f"expected the full benchmarks check-script corpus, found {len(_SCRIPTS)} — "
        "the glob is broken or the tree moved; the sweep would false-pass."
    )


# Corpus scripts that feed Python through a heredoc — discovered with a LOOSER
# opener than ``_HEREDOC`` (``[^\n]*`` between interpreter and ``<<``, vs the
# precise argv-token run) so that if ``_HEREDOC`` is too strict this list still
# finds them and the coverage test below fails.
_PY_HEREDOC_SCRIPTS = [
    s for s in _SCRIPTS if re.search(r"python[0-9.]*[^\n]*<<-?\s*['\"]?\w", s.read_text())
]


@pytest.mark.security
def test_heredoc_arm_matches_corpus_heredocs() -> None:
    """The heredoc arm must actually match the corpus's python-heredoc scripts.

    A prior spelling required ``<<`` to follow the interpreter directly and so
    matched 0 of the 27 real ``python3 - "$REPORT" … <<DELIM`` scripts — a silently
    dead arm. Had a future author copied that idiom with an *unquoted* delimiter and
    interpolated agent data, the body would go unscanned while the sweep stayed
    green. This asserts the arm stays live against the real corpus shape, which the
    in-file meta-tests (synthetic bodies) alone did not.
    """
    assert _PY_HEREDOC_SCRIPTS, "no python-heredoc scripts found — this guard is vacuous"
    unmatched = [
        str(s.relative_to(ROOT))
        for s in _PY_HEREDOC_SCRIPTS
        if not _HEREDOC.search(s.read_text())
    ]
    assert not unmatched, (
        "the heredoc detector arm does not match these real python-heredoc scripts, "
        f"so their bodies would never be scanned for injection:\n{unmatched}"
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
        for script in _SCRIPTS
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
    # Corpus-shaped heredoc: argv tokens (``- "$REPORT" "$GT_DIR"``) sit between the
    # interpreter and ``<<``. The DOMINANT corpus spelling; a prior arm that required
    # ``<<`` to follow the interpreter directly matched 0 of 27 and silently disabled
    # heredoc scanning. Unquoted delimiter here → the body is expanded and injected.
    "corpus-shaped heredoc (argv before <<)": (
        'python3 - "$REPORT" "$GT_DIR" <<PYEOF\nx = "$AGENT_FILES"\nPYEOF'
    ),
    # S6: an indented decoy terminator. A plain ``<<PYEOF`` (no dash) ends ONLY at a
    # column-0 ``PYEOF``; a tab-indented ``PYEOF`` is body text. Matching it as the
    # terminator (the prior ``[ \t]*(?P=delim)``) truncated the scanned body before
    # the injection while bash read the whole body.
    "indented decoy heredoc terminator": (
        "python3 <<PYEOF\nharmless = 1\n\tPYEOF\nx = '''$AGENT_FILES'''\nPYEOF"
    ),
    # S1: a read behind an env-assignment prefix. ``_ASSIGN`` used to claim ``IFS``
    # and ``continue`` past the ``read``, leaving WORKSPACE trusted.
    "allowlist bypass: env-prefixed read into WORKSPACE": (
        "IFS= read -r WORKSPACE < answer.json\n"
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # S2: a ``|`` inside the quoted RHS split the fragment, dropping the ``$AGENT``
    # tail; the surviving ``REPORT="${WORKSPACE}/x`` lost its closing quote and was
    # judged clean. The quote-must-close anchor now taints it.
    "allowlist bypass: separator inside quoted RHS": (
        'REPORT="${WORKSPACE}/x|$AGENT"\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    # S3: a for-loop binds the harness var to each word of an agent-influenced list.
    "allowlist bypass: for-loop-bound WORKSPACE": (
        "for WORKSPACE in $AGENT_FILES; do :; done\n"
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Array-subscript assignment: ``[0]`` sits between name and ``=`` so a
    # name-then-``=`` anchor never saw the write; the broad ``_WRITE`` scan does, and
    # any subscript write is non-clean by construction. ``${WORKSPACE}`` returns the
    # reassigned index-0 value at bash runtime.
    "allowlist bypass: array-subscript reassign": (
        'WORKSPACE[0]="$(cat answer.json)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # eval-smuggled assignment: the literal ``WORKSPACE=`` is present in the eval
    # string (caught by the broad scan) AND ``eval`` collapses the allowlist to empty.
    "allowlist bypass: eval-wrapped reassign": (
        'eval "WORKSPACE=\\"$(cat answer.json)\\""\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Two space-joined assignments in one simple command — both persist in bash (no
    # command follows). A first-``name=``-only scan recorded TMP and missed WORKSPACE.
    "allowlist bypass: space-joined WORKSPACE reassign": (
        'TMP=x WORKSPACE="$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # A ``printf -v`` substring inside an unrelated assignment's RHS must not let the
    # real reassignment escape recording (the old ``continue`` skipped ``_ASSIGN``).
    "allowlist bypass: printf-v substring hides reassign": (
        'WORKSPACE="$(id)# printf -v Y foo"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
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
    # No space between ``-c`` and the opening quote. ``-c\s+"`` (mandatory space)
    # skipped the whole body unscanned; ``-c\s*"`` catches it.
    "no-space -c\"...\" bare code": (
        'AGENT_SCORE="x"\npython3 -c"\nresult = $AGENT_SCORE\n"'
    ),
    # A sibling reassignment joined by ``;``/``&&`` onto another command. The broad
    # ``_WRITE`` scan surfaces the ``WORKSPACE=`` write regardless of what precedes it.
    "allowlist bypass: ;-joined WORKSPACE reassignment": (
        'TMP=x; WORKSPACE="$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: &&-joined WORKSPACE reassignment": (
        'true && WORKSPACE="$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Non-``name=`` write spellings. A ``name=``-only scanner never un-trusted the
    # seed; ``_var_writes`` models read / declare / += / printf -v as writes.
    "allowlist bypass: read into WORKSPACE": (
        'read WORKSPACE < answer.json\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: declare-reassigned WORKSPACE": (
        'declare WORKSPACE="$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: += appended WORKSPACE": (
        'WORKSPACE+="$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: printf -v into WORKSPACE": (
        'printf -v WORKSPACE "%s" "$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Backslash line-continuation: the real RHS is both physical lines concatenated.
    # Scanning only line 1 saw a clean-looking prefix; joining continuations first
    # taints the whole assignment.
    "allowlist bypass: continuation-split RHS": (
        'WORKSPACE="${WORKSPACE}"\\\n'
        '"$(id)"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # A (Phase-4 review): a decoy terminator with TRAILING text. Bash ends a heredoc
    # only on a line equal to the delimiter; ``PYEOF=1`` is body text, not a
    # terminator. The prior ``(?P=delim)\b`` matched the word boundary alone and
    # truncated the scanned body before the injection — the trailing-side twin of the
    # (already fixed) S6 leading-indent decoy. Present on the corpus-dominant shape.
    "trailing-text decoy heredoc terminator": (
        'python3 - "$REPORT" <<PYEOF\nharmless = 1\nPYEOF=1\n'
        'x = "$AGENT_FILES"\nPYEOF'
    ),
    "trailing-text decoy terminator (plain <<)": (
        "python3 <<PYEOF\nharmless = 1\nPYEOF )\nx = '''$AGENT_FILES'''\nPYEOF"
    ),
    # B (Phase-4 review): a ``read``/``for`` write hidden behind a compound-command
    # keyword. An anchored ``^…`` scan with an enumerated lead missed these; the
    # un-anchored builtin search finds the write wherever it sits.
    "allowlist bypass: while-read into WORKSPACE": (
        'while read -r WORKSPACE; do break; done < answer.json\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: if-read into WORKSPACE": (
        'if read -r WORKSPACE < answer.json; then :; fi\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: do-for-bound TASK_DIR": (
        'for x in a; do for TASK_DIR in $AGENT_FILES; do :; done; done\n'
        "python3 -c \"\nwith open('${TASK_DIR}') as f:\n    pass\n\""
    ),
    # C (Phase-4 review): a ``)`` inside a quoted argument to a ``$(...)`` flag value
    # before ``-c``. Counting bare parens closed the substitution early, desyncing the
    # word walk so ``-c`` was never found and the whole invocation went unscanned.
    "nested-quote paren in $() flag hides -c": (
        "python3 -W $(f ')' )'y' -c \"\nresult = $AGENT_SCORE\n\""
    ),
    # D (Phase-4 review): ``$IFS`` glued onto the interpreter. Bash word-splits on the
    # value of ``$IFS`` at runtime, so this is three argv words; a literal-whitespace-
    # only tokeniser swallowed the whole construct and never recognised ``python3``.
    "IFS-glued interpreter and -c": 'python3${IFS}-c${IFS}"result = $AGENT_SCORE"',
    # F (Phase-4 review): ``${WORKSPACE:=…}`` default-assignment. Not a ``name=`` shape
    # so ``_WRITE`` missed it, leaving WORKSPACE trusted; ``_DEFAULT_ASSIGN`` records
    # it as a non-clean write.
    "allowlist bypass: default-assign reassigns WORKSPACE": (
        ': "${WORKSPACE:=$(cat answer.json)}"\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Re-review round 2: the same read/for-write class hidden behind leads an
    # enumerated ``_CMD_LEAD`` would have to list one by one — a ``case`` arm, a
    # function body, ``coproc``. The un-anchored builtin search catches all of them.
    "allowlist bypass: case-arm-hidden read into WORKSPACE": (
        'case "$X" in\n  *) read -r WORKSPACE < answer.json ;;\nesac\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: function-body-hidden read into WORKSPACE": (
        'f() { read -r WORKSPACE < answer.json; }\nf\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    "allowlist bypass: coproc-hidden read into WORKSPACE": (
        'coproc read -r WORKSPACE < answer.json\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Re-review round 2: ``$IFS`` glued into a ``read`` — modeled on the ``-c``
    # extraction side, but the taint side split on literal whitespace only until the
    # ``$IFS``-normalisation of the builtin scan was added.
    "allowlist bypass: IFS-glued read into WORKSPACE": (
        'read${IFS}-r${IFS}WORKSPACE < answer.json\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Re-review round 2: ``eval``/nameref collapse the allowlist; ``coproc`` and
    # ``source``/``.`` write through a channel this single-file scan cannot resolve, so
    # they collapse it too. ``source`` reassigns WORKSPACE from another file.
    "allowlist bypass: source-hidden reassign (opaque collapse)": (
        'source ./agent_supplied.sh\n'
        "python3 -c \"\nwith open('${WORKSPACE}') as f:\n    pass\n\""
    ),
    # Re-review round 2: an unquoted ``cat`` heredoc whose body contains a live
    # ``$(python3 -c "…$AGENT…")`` command substitution. Blanking ALL heredoc bodies
    # before the ``-c`` scan hid it; only QUOTED-delimiter bodies are blanked now.
    "cmd-subst -c inside an unquoted cat heredoc": (
        'AGENT_FILES="$(cat answer.json)"\ncat <<A\n$(python3 -c "x=$AGENT_FILES")\nA'
    ),
    # A ``python … -c`` nested in a command substitution runs at runtime. This is the
    # DOMINANT corpus shape (``GT=$(python3 -c "…")`` — 16 scripts); the prior scan
    # skipped every ``$(...)`` whole, never looking inside for a nested invocation.
    "cmd-subst -c in a bare assignment RHS": 'V=$(python3 -c "x=$AGENT_FILES")\n',
    "backtick -c command substitution": 'V=`python3 -c "x=$AGENT_FILES"`\n',
    "cmd-subst -c nested in double quotes": 'echo "$(python3 -c "x=$AGENT_FILES")"\n',
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
    # The real corpus shape: argv (``- "$REPORT"``) before a QUOTED delimiter → no
    # expansion. The argv-tolerant opener must still respect the quote and not flag
    # the body, or every one of the 27 corpus heredoc scripts turns red.
    "corpus-shaped quoted heredoc (argv, no expansion)": (
        "python3 - \"$REPORT\" <<'PYEOF'\n"
        "with open(sys.argv[1]) as f:\n    x = '$AGENT_FILES'\nPYEOF"
    ),
    # escaped \$ is passed through literally by bash — not expanded.
    "escaped-dollar literal": 'python3 -c "\nx = \'\\$AGENT_FILES\'\n"',
    # ``export`` prefix on the real shape (platform_engineering uses this) — the
    # fail-closed rewrite must not over-taint a legitimately clean assignment.
    "export-prefixed harness path into open()": (
        'export REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    # A clean assignment sharing its line with an unrelated command via ``;``. Frag-
    # splitting must still see REPORT's assignment as clean, not swallow or taint it.
    "separator-joined clean assignment": (
        'cd /tmp; REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    # C-guard: the nested-quote ``$()`` fix must still RECOGNISE a clean invocation
    # whose flag value contains a parenthesised, quoted ``$(...)`` — recognition intact
    # (so the body IS scanned) and the harness carve-out holds (so it is not flagged).
    "balanced $() flag value, clean harness body": (
        'REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        'python3 -W "$(echo \'ignore)\')" -c "\nwith open(\'${REPORT}\') as f:\n    pass\n"'
    ),
    # D-guard: ``$IFS`` between ``-c`` and a CLEAN harness body — the interpreter is
    # recognised through the split and the carve-out still applies (no false flag).
    "IFS-separated clean harness body": (
        'REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        'python3${IFS}-c${IFS}"with open(\'${REPORT}\') as f: pass"'
    ),
    # F-guard: the NON-assigning default-VALUE form ``${REPORT:-…}`` (``:-``, not
    # ``:=``) must NOT be read as a write — ``_DEFAULT_ASSIGN``'s ``:?=`` requires the
    # ``=`` — so REPORT stays clean and its ``open()`` use is not flagged.
    "default-value ${:-} is not a write": (
        'REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        ': "${REPORT:-/tmp/fallback}"\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    # Round-2 guard: the un-anchored ``for`` scan must not over-taint the harness var.
    # This is the REAL corpus shape (4 of the 6 carve-out scripts loop like this): a
    # ``for`` binds a NON-harness loop var while REPORT stays cleanly harness-rooted.
    "for-loop over non-harness var, clean harness body": (
        'REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        'for f in a b c; do :; done\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    # Round-2 guard: an un-anchored ``read`` into a NON-harness var leaves the harness
    # var trusted — tainting is per-target, not blanket.
    "read into non-harness var, clean harness body": (
        'REPORT="${WORKSPACE}/agent_output/answer.json"\n'
        'read -r LINE < /etc/hostname\n'
        "python3 -c \"\nwith open('${REPORT}') as f:\n    pass\n\""
    ),
    # Round-2 guard: the REAL corpus command-substitution shape (16 check_error_source
    # scripts). The ``$(python3 -c "…")`` body is now scanned (not skipped), and it
    # reads paths via ``os.environ`` with no shell ``$`` interpolation → not flagged.
    "cmd-subst body reading only os.environ": (
        'GT_FILES=$(python3 -c "\n'
        "import os\nfor f in open(os.environ['GT_FILE']):\n    print(f)\n\")\n"
    ),
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
