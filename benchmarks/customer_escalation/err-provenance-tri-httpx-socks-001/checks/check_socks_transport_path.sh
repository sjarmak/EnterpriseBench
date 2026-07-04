#!/usr/bin/env bash
# check_socks_transport_path.sh -- agent traced the socks5 branch in httpx,
# httpcore's SOCKS proxy classes, and the post-handshake handoff to the
# HTTP/1.1 parser layer. Score = matched groups / total groups.

set -euo pipefail

export ANSWER_FILE="$WORKSPACE/agent_output/answer.json"

if [[ ! -f "$ANSWER_FILE" ]]; then
    echo '{"score": 0.0, "passed": false, "detail": "No answer.json found"}'
    exit 1
fi

python3 -c "
import json, os

answer_text = json.dumps(json.load(open(os.environ['ANSWER_FILE']))).lower()

groups = {
    'httpx_socks_branch': ['asyncsocksproxy'],
    'httpx_transport_file': ['_transports/default.py', 'asynchttptransport'],
    'socks_module': ['socks_proxy.py'],
    'socks_connection': ['asyncsocks5connection', '_init_socks5_connection'],
    'http11_handoff': ['asynchttp11connection'],
    'h11_parser': ['h11.connection'],
}

matched = [name for name, alts in groups.items()
           if any(alt in answer_text for alt in alts)]
score = len(matched) / len(groups)
detail = f'Matched {len(matched)}/{len(groups)} transport path groups: {sorted(matched)}'
print(json.dumps({'score': round(score, 2), 'passed': score >= 0.5, 'detail': detail}))
"
