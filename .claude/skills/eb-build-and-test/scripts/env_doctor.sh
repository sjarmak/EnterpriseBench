#!/usr/bin/env bash
# env_doctor.sh — read-only diagnostic for the EnterpriseBench dev environment.
#
# Usage: bash .claude/skills/eb-build-and-test/scripts/env_doctor.sh [python]
#   python: interpreter to test (default: venv/bin/python, else python3)
#
# Checks (nothing is mutated, nothing is installed):
#   1. interpreter version (CI uses 3.12; lib requires >=3.10)
#   2. eb_verify importable (pip install -e lib/ done?)
#   3. validator registry: 10 (full) vs 9 (fact_triples degraded)
#   4. optional heavy deps needed for full test collection
#   5. audit_consistency.py hardcoded-path reachability
#   6. untracked test modules that will error on collection locally
#   7. benchmark check scripts missing the executable bit
set -uo pipefail

PY="${1:-}"
if [ -z "$PY" ]; then
  if [ -x "venv/bin/python" ]; then PY="venv/bin/python"; else PY="python3"; fi
fi

if [ ! -f "lib/pyproject.toml" ] || [ ! -d "tests" ]; then
  echo "FAIL: run from the EnterpriseBench repo root (lib/pyproject.toml not found)"
  exit 2
fi

fails=0
note() { printf '%-4s %s\n' "$1" "$2"; }

# 1. interpreter
ver=$("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null) || {
  note FAIL "interpreter '$PY' not runnable"; exit 2; }
note OK "python: $PY ($ver; CI uses 3.12, floor is 3.10)"

# 2. eb_verify importable
if "$PY" -W ignore -c 'import eb_verify' 2>/dev/null; then
  note OK "import eb_verify"
else
  note FAIL "import eb_verify -> ModuleNotFoundError (run: $PY -m pip install -e lib/)"
  fails=$((fails+1))
fi

# 3. validator registry
count=$("$PY" -W ignore -c 'from eb_verify.plugins import list_validators; print(len(list_validators()))' 2>/dev/null || echo 0)
if [ "$count" = "10" ]; then
  note OK "validator registry: 10 (fact_triples registered)"
elif [ "$count" = "9" ]; then
  note WARN "validator registry: 9 (fact_triples DEGRADED; fact_triples artifacts will score valid=False)"
else
  note FAIL "validator registry unreadable (count=$count)"
  fails=$((fails+1))
fi

# 4. heavy deps for full test collection
for mod in numpy sklearn matplotlib seaborn; do
  if "$PY" -c "import $mod" 2>/dev/null; then
    note OK "optional dep: $mod"
  else
    note WARN "optional dep missing: $mod (pytest collection of tracked tests will error)"
  fi
done

# 5. audit_consistency hardcoded path
hard=$(grep -oP 'BENCH_DIR = Path\("\K[^"]+' scripts/audit_consistency.py 2>/dev/null || true)
if [ -n "$hard" ] && [ -d "$hard" ]; then
  note OK "audit_consistency BENCH_DIR exists: $hard"
elif [ -n "$hard" ]; then
  note WARN "audit_consistency BENCH_DIR hardcoded to '$hard' (missing here; script will crash with FileNotFoundError)"
else
  note OK "audit_consistency: no hardcoded BENCH_DIR found (defect may have been fixed; re-read the script)"
fi

# 6. untracked test modules (collection errors CI never sees)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  untracked=$(git ls-files --others --exclude-standard tests/ 2>/dev/null | grep -c '\.py$' || true)
  if [ "${untracked:-0}" -gt 0 ]; then
    note WARN "$untracked untracked .py file(s) under tests/ (local-only; check 'git ls-files' before blaming main)"
    git ls-files --others --exclude-standard tests/ | grep '\.py$' | sed 's/^/       /'
  else
    note OK "no untracked test files under tests/"
  fi
else
  note WARN "not a git work tree; cannot separate tracked vs untracked tests"
fi

# 7. non-executable check scripts
nonexec=$(find benchmarks -name "*.sh" -not -path "*/_archived/*" ! -perm -u+x 2>/dev/null | wc -l)
if [ "$nonexec" -eq 0 ]; then
  note OK "all non-archived benchmark .sh scripts have the exec bit"
else
  note WARN "$nonexec benchmark script(s) missing exec bit (test_all_tasks_valid + audit_consistency will flag these)"
fi

echo
if [ "$fails" -gt 0 ]; then
  echo "RESULT: $fails hard failure(s); see FAIL lines above."
  exit 1
fi
echo "RESULT: environment usable (WARN lines list known gaps; see eb-build-and-test SKILL.md)."
