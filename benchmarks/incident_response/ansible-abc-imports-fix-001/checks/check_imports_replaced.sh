#!/usr/bin/env bash
# check_imports_replaced.sh — verify _collections_compat imports replaced with collections.abc
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

# Count remaining internal imports of _collections_compat (excluding the shim itself)
REMAINING=$(grep -r "from ansible.module_utils.common._collections_compat" \
    "$WORKSPACE/ansible/lib/ansible/" \
    --include="*.py" \
    -l 2>/dev/null | \
    grep -v "_collections_compat.py" | wc -l || echo 0)

if [ "$REMAINING" -eq 0 ]; then
    printf '{"score": 1.0, "passed": true, "detail": "All _collections_compat imports replaced"}\n'
else
    SCORE=$(awk "BEGIN {s=1.0-$REMAINING*0.1; if(s<0)s=0; printf \"%.2f\", s}")
    printf '{"score": %s, "passed": false, "detail": "%d files still import _collections_compat"}\n' "$SCORE" "$REMAINING"
fi
