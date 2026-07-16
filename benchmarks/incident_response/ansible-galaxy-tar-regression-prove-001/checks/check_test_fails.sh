#!/usr/bin/env bash
# check_test_fails.sh — checkpoint "test_fails_on_buggy_code"
#
# The agent's regression test must FAIL against the unpatched tree: a test that
# passes has not demonstrated the bug. Two properties this check must keep.
#
#   * Nothing but the verdict on stdout. pytest used to run inside the `if`
#     condition, so its report landed on this script's stdout ahead of the JSON.
#     test_runner.sh:parse_score refuses a payload with anything beside the root
#     value, so the checkpoint yielded NO verdict and routed to
#     verifier_infra_error on every run — for a correct agent as much as a no-op
#     one. pytest output is captured here and never printed.
#
#   * Only exit 1 is a demonstrated failure. "Non-zero" is not the same claim:
#     pytest exits 1 when tests ran and failed, but 2 on a collection error, 4
#     on a usage error and 5 when it collected nothing. The old non-zero branch
#     credited all of them, so any unparseable file — `cp instruction.md
#     regression_test.py` included — scored 1.0 for "Test correctly fails on
#     buggy code". Only the stdout-noise bug above kept that from being live
#     credit, so the two fixes ship together: repairing the verdict without
#     tightening the exit code would turn a masked leak into a real one.
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
TEST_FILE="$WORKSPACE/regression_test.py"

verdict() {
    printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"
    exit 0
}

# pytest is ours, not the agent's. If it is absent the verifier did not really
# run, and reporting that as a legitimate 0.0 would bury a broken grader under
# an agent failure. Route it to re-run instead.
if ! python3 -m pytest --version >/dev/null 2>&1; then
    verdict 0.0 false "VERIFIER_INFRA_ERROR: pytest unavailable to the verifier"
fi

# regression_test.py is agent-owned: refuse a symlink rather than run whatever
# it aims at.
if [[ -L "$TEST_FILE" ]]; then
    verdict 0.0 false "regression_test.py is a symlink, not a regular file"
fi
if [[ ! -f "$TEST_FILE" ]]; then
    verdict 0.0 false "regression_test.py not found"
fi

# A failure only demonstrates THIS bug if the buggy code ran. `def test_x():
# assert False` also exits 1, and without this floor it would take the full
# checkpoint. Gate on an import of the subject, never on a string the prompt
# supplies: instruction.md contains no import statement and never spells the
# dotted module path or concrete_artifact_manager, so an echo cannot satisfy
# this — whereas "ansible-galaxy", "tarfile" and "getmember" are all prompt
# vocabulary and would.
export TEST_FILE
set +e
python3 -c '
import ast, os, sys

try:
    with open(os.environ["TEST_FILE"], encoding="utf-8", errors="replace") as fh:
        tree = ast.parse(fh.read())
except (SyntaxError, ValueError):
    sys.exit(2)

for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        if any(a.name.split(".")[0] == "ansible" for a in node.names):
            sys.exit(0)
    elif isinstance(node, ast.ImportFrom):
        if (node.module or "").split(".")[0] == "ansible":
            sys.exit(0)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        if "ansible.galaxy.collection" in node.value \
           or "ansible/galaxy/collection" in node.value \
           or "concrete_artifact_manager" in node.value:
            sys.exit(0)
sys.exit(1)
'
SUBJECT_RC=$?
set -e

if [[ "$SUBJECT_RC" -eq 2 ]]; then
    verdict 0.0 false "regression_test.py is not a valid Python module"
fi
if [[ "$SUBJECT_RC" -ne 0 ]]; then
    verdict 0.0 false "regression_test.py never imports the ansible Galaxy collection code, so a failure cannot demonstrate the bug"
fi

# --timeout kills a hung test; the outer timeout covers a pytest that hangs
# before the plugin arms. Both are the agent's artifact misbehaving, not infra.
set +e
cd "$WORKSPACE"
timeout 120 python3 -m pytest --timeout=60 "$TEST_FILE" -q >/dev/null 2>&1
RC=$?
set -e

case "$RC" in
    1)   verdict 1.0 true  "Test ran and failed on the buggy code (pytest rc=1)" ;;
    0)   verdict 0.0 false "Test passed on the buggy code — it must fail to demonstrate the bug" ;;
    5)   verdict 0.0 false "pytest collected no tests from regression_test.py (rc=5)" ;;
    124) verdict 0.0 false "regression_test.py exceeded the 120s verifier timeout" ;;
    *)   verdict 0.0 false "regression_test.py is not runnable: pytest rc=$RC (collection or usage error, not a demonstrated failure)" ;;
esac
