#!/usr/bin/env bash
# check_regression_test.sh — checkpoint "regression_test_written"
#
# Grades the deliverable's structure: is this a pytest module that targets the
# Galaxy collection code? Whether it actually fails is check_test_fails.sh.
#
# Credit requires work. The old check paid 0.2 for a file that merely existed
# with no test functions, so `cp instruction.md regression_test.py` collected
# free credit for the prompt (EnterpriseBench-jn73.2.7.3.1 quarantine). Absence
# of work now scores 0.0, and an AST parse — not a `def test_` grep — is what
# rejects the prompt copy: prose is not a Python module, whatever words it
# contains. That keeps this check off the prompt's vocabulary entirely, so it
# cannot grade concepts instruction.md already handed over.
#
# It also drops the old count/2 gradient, which paid for the NUMBER of test
# functions and so rewarded splitting one test into stubs. The gradient that
# means something is whether the test reaches the subject under test.
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
TEST_FILE="$WORKSPACE/regression_test.py"
MAX_TEST_BYTES=1048576

verdict() {
    printf '{"score": %s, "passed": %s, "detail": "%s"}\n' "$1" "$2" "$3"
    exit 0
}

# regression_test.py is agent-owned: refuse a symlink rather than read whatever
# it aims at.
if [[ -L "$TEST_FILE" ]]; then
    verdict 0.0 false "regression_test.py is a symlink, not a regular file"
fi
if [[ ! -f "$TEST_FILE" ]]; then
    verdict 0.0 false "regression_test.py not found"
fi
if [[ "$(wc -c <"$TEST_FILE")" -gt "$MAX_TEST_BYTES" ]]; then
    verdict 0.0 false "regression_test.py exceeds ${MAX_TEST_BYTES} bytes"
fi

export TEST_FILE
python3 -c '
import ast, json, os

def verdict(score, detail):
    print(json.dumps({"score": round(score, 2), "passed": score >= 0.5, "detail": detail}))
    raise SystemExit(0)

with open(os.environ["TEST_FILE"], encoding="utf-8", errors="replace") as fh:
    source = fh.read()

try:
    tree = ast.parse(source)
except (SyntaxError, ValueError) as exc:
    verdict(0.0, f"regression_test.py is not a valid Python module: {type(exc).__name__}")

tests = [n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name.startswith("test_")]
if not tests:
    verdict(0.0, "regression_test.py defines no test_ functions")

# Does the test reach the real Galaxy collection code? An import of the subject
# is the floor for "regression test" rather than "a test": the bug cannot be
# demonstrated by a module that never loads the code under test. Accept the
# import forms an agent actually writes, including an importlib string.
subject = False
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        if any(a.name.split(".")[0] == "ansible" for a in node.names):
            subject = True
    elif isinstance(node, ast.ImportFrom):
        if (node.module or "").split(".")[0] == "ansible":
            subject = True
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        v = node.value
        if "ansible.galaxy.collection" in v or "ansible/galaxy/collection" in v \
           or "concrete_artifact_manager" in v:
            subject = True

if not subject:
    verdict(0.5, f"{len(tests)} test function(s), but nothing imports the ansible "
                 f"Galaxy collection code under test")
verdict(1.0, f"{len(tests)} test function(s) exercising the ansible Galaxy collection code")
'
