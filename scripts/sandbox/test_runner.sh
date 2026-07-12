#!/usr/bin/env bash
# test_runner.sh — Cross-repo test runner for EnterpriseBench tasks.
# Executes checkpoint verifiers and produces structured JSON output.
#
# Usage: /workspace/test.sh [checkpoint_name]
#
# Output: JSON object with per-checkpoint results and aggregate score.
# Exit code: 0 if all checkpoints pass, 1 otherwise.
set -uo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
VERIFIER_DIR="$WORKSPACE/.verifiers"
# Scoring closes $WORKSPACE to everyone but root (the grader must not be able to
# plant an artifact for a later checkpoint), so the orchestrator redirects this
# file to a scorer-writable path. The default stays put for standalone runs.
RESULTS_FILE="${EB_RESULTS_FILE:-$WORKSPACE/.results.json}"

# --- helpers ---

json_escape() {
    # Escape a string for safe JSON embedding (all RFC 7159 control chars)
    printf '%s' "$1" \
      | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g; s/\r/\\r/g; s/\x0c/\\f/g; s/\x08/\\b/g' \
      | tr '\n' ' '
}

now_ms() {
    date +%s%3N 2>/dev/null || date +%s000
}

# Discover repos in /workspace/ (directories with .git)
discover_repos() {
    local repos=()
    for dir in "$WORKSPACE"/*/; do
        [ -d "$dir/.git" ] && repos+=("$(basename "$dir")")
    done
    printf '%s\n' "${repos[@]}"
}

# Sentinel that declares a verifier-harness failure rather than an agent
# failure. Mirrors eb_verify.scorer_guard.INFRA_SENTINEL — the scorer trust
# boundary greps for this string, so the two must stay in lockstep.
INFRA_SENTINEL="VERIFIER_INFRA_ERROR"

# Preamble sourced (via BASH_ENV) by every verifier shell.
#
# Bash calls command_not_found_handle for ANY command it cannot find, in ANY
# context — including inside `if python3 ... 2>/dev/null`, where the verifier's
# own control flow would otherwise swallow the failure and go on to print a
# perfectly well-formed 0.0. The handler records the name to EB_INFRA_LOG, a
# side channel the verifier cannot redirect away, which is what makes a missing
# interpreter unswallowable. Returning 127 reproduces bash's native exit status
# for an unfindable command, so `set -e` and every exit-code test behave exactly
# as they did before the handler existed.
INFRA_PREAMBLE=$(mktemp)
trap 'rm -f "$INFRA_PREAMBLE"' EXIT
cat >"$INFRA_PREAMBLE" <<'PREAMBLE'
command_not_found_handle() {
    printf '%s\n' "$1" >>"${EB_INFRA_LOG:-/dev/null}"
    printf '%s: command not found\n' "$1" >&2
    return 127
}
PREAMBLE

# Run a single verifier, capture JSON output and exit code.
# Returns: sets VERIFIER_EXIT, VERIFIER_JSON, VERIFIER_DURATION_MS, VERIFIER_RAN
#
# A verifier that never ran must never be scored. Absence of a verdict is not a
# verdict of 0.0 (nor of 1.0) — so this function NEVER fabricates a score from
# an exit code. It attests, per checkpoint, whether the verifier actually
# produced a verdict (VERIFIER_RAN); the scorer trust boundary refuses to score
# any checkpoint that did not.
run_verifier() {
    local verifier_path="$1"
    local timeout_sec="${2:-120}"
    local start end

    start=$(now_ms)

    # Run with timeout; capture stdout (expected JSON), stderr for diagnostics
    local raw_stdout raw_stderr
    raw_stderr=$(mktemp)

    # Capture exit code before || true to avoid masking real failures
    local raw_stdout_file infra_log
    raw_stdout_file=$(mktemp)
    infra_log=$(mktemp)

    # Pass the workspace explicitly as $1: several checks resolve
    # WORKSPACE="${1:-.}", which shadows the exported env var. Scoring runs from
    # a cwd outside the workspace (the agent must not control the checks'
    # sys.path[0]), so the "." fallback would silently zero every such check.
    if command -v timeout >/dev/null 2>&1; then
        BASH_ENV="$INFRA_PREAMBLE" EB_INFRA_LOG="$infra_log" \
            timeout "$timeout_sec" bash "$verifier_path" "$WORKSPACE" >"$raw_stdout_file" 2>"$raw_stderr"
        VERIFIER_EXIT=$?
    else
        BASH_ENV="$INFRA_PREAMBLE" EB_INFRA_LOG="$infra_log" \
            bash "$verifier_path" "$WORKSPACE" >"$raw_stdout_file" 2>"$raw_stderr"
        VERIFIER_EXIT=$?
    fi

    raw_stdout=$(cat "$raw_stdout_file")
    rm -f "$raw_stdout_file"

    # Dedupe with awk, not `sort -u`: this runs in whatever minimal image the
    # task ships, and a detector that itself depends on a possibly-absent
    # command would fail exactly when it is needed most. awk is already a hard
    # dependency of this script (weighted-score math below).
    local missing_cmds
    missing_cmds=$(awk '!seen[$0]++ { printf "%s%s", (c++ ? " " : ""), $0 }' "$infra_log" 2>/dev/null)
    rm -f "$infra_log"

    end=$(now_ms)
    VERIFIER_DURATION_MS=$(( end - start ))
    VERIFIER_RAN="true"

    local infra_detail=""
    if [ -n "$missing_cmds" ]; then
        # Checked ahead of the timeout below: a command that does not exist is an
        # infra failure whether or not the verifier also ran out the clock.
        #
        # Fires even when the verifier redirected the failure to /dev/null and
        # carried on to print a legitimate-looking score — that printed score is
        # a fiction and is discarded here.
        infra_detail="$INFRA_SENTINEL: verifier shelled a command that does not exist: $missing_cmds"
    elif [ "$VERIFIER_EXIT" -eq 124 ]; then
        # Timeout: the verifier DID run, it just did not finish. Left as a scored
        # 0.0 — unchanged from before — because a hang is as often the subject
        # code's fault as the harness's, and reclassifying it is a separate
        # judgement call from "the verifier never ran".
        VERIFIER_JSON="{\"score\": 0.0, \"passed\": false, \"detail\": \"Timed out after ${timeout_sec}s\"}"
        rm -f "$raw_stderr"
        return
    elif [ "$VERIFIER_EXIT" -eq 127 ]; then
        # Belt and braces: covers a not-found command raised by something other
        # than the handler (e.g. a non-bash interpreter in the chain).
        infra_detail="$INFRA_SENTINEL: verifier exited 127 (command not found)"
    elif ! printf '%s' "$raw_stdout" | grep -q '^{'; then
        # No JSON on stdout means the verifier died before reaching its verdict.
        # Previously this was fabricated into a score from the exit code alone:
        # nonzero became a false 0.0 (under-credit) and — worse — zero became a
        # free 1.0 (over-credit) for a verifier that printed nothing at all.
        local stderr_content
        stderr_content=$(cat "$raw_stderr" 2>/dev/null || true)
        infra_detail="$INFRA_SENTINEL: verifier produced no JSON verdict (exit $VERIFIER_EXIT): ${stderr_content:-no output}"
    fi

    if [ -n "$infra_detail" ]; then
        VERIFIER_RAN="false"
        VERIFIER_JSON="{\"score\": 0.0, \"passed\": false, \"verifier_ran\": false, \"detail\": \"$(json_escape "$infra_detail")\"}"
    else
        VERIFIER_JSON="$raw_stdout"
    fi

    rm -f "$raw_stderr"
}

# --- single checkpoint mode ---

if [ -n "${1:-}" ]; then
    CHECKPOINT="$1"
    # Validate checkpoint name (alphanumeric, hyphens, underscores only)
    if [[ "$CHECKPOINT" =~ [^a-zA-Z0-9_-] ]]; then
        printf '{"score": 0.0, "passed": false, "detail": "Invalid checkpoint name"}\n'
        exit 1
    fi
    VERIFIER="$VERIFIER_DIR/${CHECKPOINT}.sh"
    if [ ! -f "$VERIFIER" ]; then
        printf '{"score": 0.0, "passed": false, "detail": "No verifier found for checkpoint: %s"}\n' "$CHECKPOINT"
        exit 1
    fi
    run_verifier "$VERIFIER" 120
    printf '%s\n' "$VERIFIER_JSON"
    exit "$VERIFIER_EXIT"
fi

# --- full run: all checkpoints ---

echo "=== EnterpriseBench Cross-Repo Test Runner ===" >&2
echo "Workspace: $WORKSPACE" >&2

# List repos for diagnostics (stderr so it doesn't pollute JSON stdout)
mapfile -t REPOS < <(discover_repos)
echo "Repos:" >&2
for repo in "${REPOS[@]}"; do
    echo "  - $repo" >&2
done
echo "" >&2

# Verify cross-repo access: confirm we can cd into each repo
for repo in "${REPOS[@]}"; do
    if ! (cd "$WORKSPACE/$repo" && pwd >/dev/null); then
        printf '{"task_score": 0.0, "all_passed": false, "error": "Cannot access repo: %s"}\n' "$repo"
        exit 1
    fi
done

# Run all verifiers
if [ ! -d "$VERIFIER_DIR" ]; then
    printf '{"task_score": 0.0, "all_passed": false, "checkpoints": [], "error": "No .verifiers/ directory found"}\n'
    exit 1
fi

TOTAL=0
PASSED=0
CHECKPOINT_RESULTS=""
WEIGHTED_SCORE="0"

for verifier in "$VERIFIER_DIR"/*.sh; do
    [ -f "$verifier" ] || continue
    name=$(basename "$verifier" .sh)
    TOTAL=$((TOTAL + 1))

    # Read weight from companion .meta file if present, else default 1.0.
    # Validate it is a plain number: it is interpolated unquoted into both the
    # result JSON and an awk expression below, so a malformed weight is an
    # injection point. .verifiers/ is sealed root-only, but this check is the
    # layer that does not depend on the seal holding.
    weight="1.0"
    meta_file="$VERIFIER_DIR/${name}.meta"
    if [ -f "$meta_file" ]; then
        w=$(grep -oP '(?<=weight=)\S+' "$meta_file" 2>/dev/null || true)
        [[ "$w" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] && weight="$w"
    fi

    # Read timeout from .meta file if present
    checkpoint_timeout=120
    if [ -f "$meta_file" ]; then
        t=$(grep -oP '(?<=timeout=)\S+' "$meta_file" 2>/dev/null || true)
        [ -n "$t" ] && checkpoint_timeout="$t"
    fi

    echo "--- Checkpoint: $name (weight=$weight, timeout=${checkpoint_timeout}s) ---" >&2
    run_verifier "$verifier" "$checkpoint_timeout"

    # Extract score from verifier JSON
    checkpoint_score=$(printf '%s' "$VERIFIER_JSON" | grep -oP '"score"\s*:\s*\K[0-9.]+' || echo "0.0")

    # Extract passed from verifier JSON
    checkpoint_passed=$(printf '%s' "$VERIFIER_JSON" | grep -oP '"passed"\s*:\s*\K(true|false)' || echo "false")

    # Extract the canonical "detail" string (verifier_output.schema.json) as a
    # JSON string token, including escapes, so it can be embedded verbatim.
    # Preserved per-checkpoint in output.json for debugging; empty when absent.
    checkpoint_detail=$(printf '%s' "$VERIFIER_JSON" | grep -oPm1 '"detail"\s*:\s*\K"(\\.|[^"\\])*"')
    [ -n "$checkpoint_detail" ] || checkpoint_detail='""'

    if [ "$VERIFIER_RAN" != "true" ]; then
        echo "  INFRA ERROR (verifier never reached a verdict — not scored)" >&2
    elif [ "$checkpoint_passed" = "true" ]; then
        PASSED=$((PASSED + 1))
        echo "  PASS (score=$checkpoint_score)" >&2
    else
        echo "  FAIL (score=$checkpoint_score)" >&2
    fi

    # Accumulate weighted score using awk for float math
    WEIGHTED_SCORE=$(awk "BEGIN { printf \"%.4f\", $WEIGHTED_SCORE + ($checkpoint_score * $weight) }")

    # Build checkpoint result JSON entry (detail is already a quoted JSON
    # string). name comes from an agent-writable filename in .verifiers/ —
    # escape it the same way repo basenames are escaped above.
    #
    # verifier_ran is the positive attestation the scorer trust boundary gates
    # on: it is emitted here, by the only component that can actually observe
    # whether the verifier reached a verdict. A checkpoint without a true
    # attestation is refused a score rather than given a 0.0.
    entry=$(printf '{"name": "%s", "weight": %s, "score": %s, "passed": %s, "verifier_ran": %s, "detail": %s, "duration_ms": %d, "exit_code": %d}' \
        "$(json_escape "$name")" "$weight" "$checkpoint_score" "$checkpoint_passed" "$VERIFIER_RAN" "$checkpoint_detail" "$VERIFIER_DURATION_MS" "$VERIFIER_EXIT")

    if [ -z "$CHECKPOINT_RESULTS" ]; then
        CHECKPOINT_RESULTS="$entry"
    else
        CHECKPOINT_RESULTS="$CHECKPOINT_RESULTS, $entry"
    fi
    echo "" >&2
done

echo "Results: $PASSED/$TOTAL checkpoints passed" >&2

ALL_PASSED="false"
EXIT_CODE=1
if [ "$PASSED" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    ALL_PASSED="true"
    EXIT_CODE=0
fi

# Render the repos array as a JSON list. Must expand the whole array —
# `echo "$REPOS"` would emit only ${REPOS[0]} and silently drop every other
# repo from the output. The ${arr[@]+...} guard keeps this safe under set -u
# when no repos were discovered. Repo names come from discover_repos(), which
# globs agent-owned /workspace/*/ — escape each one via json_escape() before
# embedding, the same way verifier detail strings already are, so an agent
# cannot break out of the JSON array via a crafted directory name.
REPOS_JSON=$(
    for repo in ${REPOS[@]+"${REPOS[@]}"}; do
        json_escape "$repo"
        printf '\n'
    done | awk 'NF{printf "%s\"%s\"", (c++?", ":""), $0}'
)

# Build the result JSON once, then emit to both stdout and the results file.
RESULT_JSON=$(cat <<RESULT_JSON
{
  "task_score": $WEIGHTED_SCORE,
  "all_passed": $ALL_PASSED,
  "checkpoints_passed": $PASSED,
  "checkpoints_total": $TOTAL,
  "repos": [$REPOS_JSON],
  "checkpoints": [$CHECKPOINT_RESULTS]
}
RESULT_JSON
)

printf '%s\n' "$RESULT_JSON"
printf '%s\n' "$RESULT_JSON" > "$RESULTS_FILE"

exit $EXIT_CODE
