#!/usr/bin/env bash
# Checkpoint 3: Verify agent identified OpenSSL X509 verification chain and error origin
set -euo pipefail

REPORT="${WORKSPACE:-/workspace}/DEPENDENCY_TRACE.md"
if [[ ! -f "$REPORT" ]]; then
  printf '{"score": 0.0, "passed": false, "reason": "DEPENDENCY_TRACE.md not found"}\n'
  exit 0
fi

FOUND=0
TOTAL=4
if grep -qiE 'x509_vfy|X509_verify_cert' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'SSL_CTX_load_verify_locations|load_verify' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'UNABLE_TO_GET_ISSUER_CERT|issuer.cert' "$REPORT"; then FOUND=$((FOUND + 1)); fi
if grep -qiE 'vtls/openssl|openssl\.c' "$REPORT"; then FOUND=$((FOUND + 1)); fi

SCORE=$(awk "BEGIN {printf \"%.2f\", $FOUND/$TOTAL}")
if [ "$FOUND" -ge 3 ]; then PASSED=true; else PASSED=false; fi

printf '{"score": %s, "passed": %s, "reason": "Found %d/%d OpenSSL verification concepts"}\n' "$SCORE" "$PASSED" "$FOUND" "$TOTAL"
