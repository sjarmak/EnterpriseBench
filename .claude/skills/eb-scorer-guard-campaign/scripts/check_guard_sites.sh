#!/usr/bin/env bash
# check_guard_sites.sh — read-only drift check for eb-scorer-guard-campaign.
#
# Verifies that every ground-truth claim in the skill still holds at the
# current checkout: guard-site anchors, corpus/scorer_guard existence,
# unlanded integrity branches, two-scorer split, .meta weighting, and the
# branch-only status of the dose-response script.
#
# Usage: bash .claude/skills/eb-scorer-guard-campaign/scripts/check_guard_sites.sh
# Run from anywhere inside the repo. Exits 0 if all claims hold, 1 if any
# drifted (drift means: re-verify the skill's line numbers before trusting it).
# This script only reads; it never mutates the tree or git state.

set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "FATAL: not inside a git checkout" >&2
    exit 1
}
cd "$ROOT"

PASS=0
DRIFT=0

check() {
    # check <description> <command...>  — command must succeed quietly
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "PASS  $desc"
        PASS=$((PASS + 1))
    else
        echo "DRIFT $desc"
        DRIFT=$((DRIFT + 1))
    fi
}

check_absent() {
    # check_absent <description> <path-or-pattern-check command...> — command must FAIL
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "DRIFT $desc (now exists — skill assumes it does not)"
        DRIFT=$((DRIFT + 1))
    else
        echo "PASS  $desc"
        PASS=$((PASS + 1))
    fi
}

RT=scripts/orchestration/run_task.py
CP=lib/eb_verify/plugins/code_patch.py

echo "== Guard-site anchors (skill state map, verified 2026-07-07 @ 7cfb8b0) =="
check "site 1: _run_scoring exists in run_task.py" grep -q "def _run_scoring" "$RT"
check "site 1: no-output path still returns task_score 0.0 (LIVE bug)" grep -q "test.sh produced no output" "$RT"
check "site 2: _apply_llm_judge exists" grep -q "def _apply_llm_judge" "$RT"
check "site 2: no-agent-output branch writes verifier_infra_error" grep -q 'scores\["verifier_infra_error"\]' "$RT"
check "site 3: infra-error consumption present in run_task()" grep -q 'scores.get("verifier_infra_error")' "$RT"
check "site 4: code_patch broad-except collapse still present (LIVE bug)" grep -q "except (subprocess.TimeoutExpired, Exception)" "$CP"
check "site 5: hktt fix — mkdir -p before docker cp of eb_verify" grep -q 'mkdir.*-p.*\.eb_verify\|"/workspace/.eb_verify"' "$RT"
check "site 6: s58f fix — _assert_agent_readable gate present" grep -q "_assert_agent_readable" "$RT"

echo "== Campaign deliverables (skill assumes NOT YET BUILT) =="
check_absent "scorer_guard not yet implemented" grep -rq "def scorer_guard" lib/ scripts/
check_absent "tests/integrity/ corpus not yet created" test -d tests/integrity

echo "== Surrounding claims =="
check "two-scorer split: CheckpointRunner defined in library" grep -q "class CheckpointRunner" lib/eb_verify/runner.py
check_absent "two-scorer split: CheckpointRunner still unused by scripts/" grep -rqI --exclude-dir=__pycache__ "CheckpointRunner" scripts/
check_absent ".meta weights still never written by run_task.py (equal-weighted prod)" grep -q "\.meta" "$RT"
check "test_runner.sh still reads .meta weight sidecars" grep -q "weight=" scripts/sandbox/test_runner.sh
check_absent "dose-response still branch-only (not on main)" test -f scripts/analysis/mcp_lift_doseresponse.py

echo "== Unlanded integrity branches (skill assumes parked, not dead) =="
for b in fix/eb-wbsq-scoring-gaps fix/eb-7jpm-grading-integrity \
    fix/eb-cdzi-runner-consolidation feature/eb-1av-unified-scoreresult \
    fix/eb-5eq9-preserve-branch-triage; do
    if git rev-parse --verify -q "$b" >/dev/null 2>&1; then
        n=$(git log --oneline "main..$b" 2>/dev/null | wc -l)
        if [ "$n" -gt 0 ]; then
            echo "PASS  branch $b exists with $n unlanded commit(s)"
            PASS=$((PASS + 1))
        else
            echo "DRIFT branch $b fully merged — skill's 'parked' claim stale"
            DRIFT=$((DRIFT + 1))
        fi
    else
        echo "DRIFT branch $b missing — skill's branch table stale"
        DRIFT=$((DRIFT + 1))
    fi
done

echo
echo "Result: $PASS pass, $DRIFT drift"
if [ "$DRIFT" -gt 0 ]; then
    echo "Drift detected: re-verify the skill's state map before following its line numbers."
    exit 1
fi
exit 0
