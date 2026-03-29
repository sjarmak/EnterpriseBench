#!/usr/bin/env bash
# build_all.sh — Build all sandbox templates and report results.
# Usage: bash scripts/sandbox/build_all.sh [--measure]
#
# Copies health_check.sh and test_runner.sh into each template's build context,
# then builds each Dockerfile. Reports success/failure and optional measurements.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/templates"

MEASURE=false
if [[ "${1:-}" == "--measure" ]]; then
    MEASURE=true
fi

echo "=============================================="
echo "  EnterpriseBench Sandbox Template Builder"
echo "=============================================="
echo "Date: $(date -Iseconds)"
echo ""

TEMPLATES=(
    "go_multi_repo"
    "python_multi_repo"
    "java_multi_repo"
)

PASSED=0
FAILED=0
RESULTS=""

for tmpl in "${TEMPLATES[@]}"; do
    dockerfile="$TEMPLATE_DIR/${tmpl}.Dockerfile"
    if [[ ! -f "$dockerfile" ]]; then
        echo "SKIP: $tmpl — Dockerfile not found at $dockerfile"
        FAILED=$((FAILED + 1))
        RESULTS="${RESULTS}\n  SKIP  $tmpl"
        continue
    fi

    echo "====== Building: $tmpl ======"
    tag="eb-template-${tmpl}"

    # Create a temporary build context with the Dockerfile and helper scripts
    BUILD_CTX=$(mktemp -d)
    trap "rm -rf $BUILD_CTX" EXIT

    cp "$dockerfile" "$BUILD_CTX/Dockerfile"
    cp "$SCRIPT_DIR/health_check.sh" "$BUILD_CTX/health_check.sh"
    cp "$SCRIPT_DIR/test_runner.sh" "$BUILD_CTX/test_runner.sh"

    START_TIME=$(date +%s)

    if docker build -t "$tag" "$BUILD_CTX" 2>&1; then
        END_TIME=$(date +%s)
        ELAPSED=$((END_TIME - START_TIME))
        echo ""
        echo "OK: $tmpl built in ${ELAPSED}s"
        PASSED=$((PASSED + 1))
        RESULTS="${RESULTS}\n  PASS  $tmpl  (${ELAPSED}s)"

        if [[ "$MEASURE" == "true" ]]; then
            echo "--- Measurements: $tmpl ---"

            # Image size
            IMG_SIZE=$(docker image inspect "$tag" --format '{{.Size}}' 2>/dev/null || echo "0")
            IMG_SIZE_MB=$(awk "BEGIN { printf \"%.1f\", $IMG_SIZE / 1048576 }")
            echo "  Image size: ${IMG_SIZE_MB} MB"

            # Workspace size
            WS_SIZE=$(docker run --rm "$tag" du -sh /workspace/ 2>/dev/null | cut -f1 || echo "?")
            echo "  Workspace:  ${WS_SIZE}"

            # Per-repo sizes
            docker run --rm "$tag" du -sh /workspace/*/ 2>/dev/null | while IFS=$'\t' read -r size path; do
                repo=$(basename "$path")
                [[ "$repo" == "*" ]] && continue
                echo "  $repo: $size"
            done

            RESULTS="${RESULTS}  image=${IMG_SIZE_MB}MB ws=${WS_SIZE}"
            echo ""
        fi

        # Clean up image to save disk
        docker rmi "$tag" >/dev/null 2>&1 || true
    else
        END_TIME=$(date +%s)
        ELAPSED=$((END_TIME - START_TIME))
        echo ""
        echo "FAIL: $tmpl failed after ${ELAPSED}s"
        FAILED=$((FAILED + 1))
        RESULTS="${RESULTS}\n  FAIL  $tmpl  (${ELAPSED}s)"
    fi

    # Clean up build context
    rm -rf "$BUILD_CTX"

    echo ""
done

echo "=============================================="
echo "  Results: ${PASSED} passed, ${FAILED} failed"
echo -e "$RESULTS"
echo ""
echo "=============================================="

if [[ "$FAILED" -gt 0 ]]; then
    exit 1
fi
