#!/usr/bin/env bash
# check_source_files.sh -- agent identified the GCC pass-infrastructure files.
#
# Uses the shared file_extraction scorer (the same one 33 other checks use), so
# matching stays comparable across tasks: it reads ONLY agent_output/answer.json,
# matches claimed paths against the sealed ground_truth.json by path component
# (never a token grep over the whole answer blob), and fails closed on a missing
# answer key. The instruction is de-leaked (names no answer-key paths), so a
# correct answer is reachable only by an agent that actually read the repo.

set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"
export GT_FILE="$TASK_DIR/ground_truth.json"

exec python3 -m eb_verify.plugins.file_extraction \
    --keys files,source_files,code_paths,error_source.files,citations
