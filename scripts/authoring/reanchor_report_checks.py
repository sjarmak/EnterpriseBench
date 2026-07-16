#!/usr/bin/env python3
"""Re-anchor gen-1 report checks to the scoring_evidence mechanism (gen-2).

The prompt-echo leak (EnterpriseBench-jn73.2.7.3.1): gen-1 report checks grep
concept vocabulary the prompt already hands the agent, so `cp instruction.md
<deliverable>` scores full. The gen-2 fix (dep-traversal template) grades the
deliverable against `ground_truth.json:scoring_evidence[<checkpoint>]` — tokens
that are (a) absent from instruction.md and (b) present in the curated
expected_solution.json, so only a real investigation earns credit.

This tool performs the mechanical half of the migration for one task:
  1. map each check file -> a task.toml checkpoint,
  2. extract per-checkpoint evidence tokens from expected_solution.json string
     VALUES (file paths first, then code identifiers), dropping any token that
     appears in instruction.md and any structural/generic stopword,
  3. write scoring_evidence into ground_truth.json,
  4. rewrite each mapped check body to the generic scoring_evidence grader,
     preserving the check's existing deliverable path.

It does NOT judge whether expected_solution.json is itself correct (answer-key
fidelity is a separate concern, tracked under the answer-key-fidelity beads).
It refuses (flags) a checkpoint it cannot give >= MIN_EVIDENCE non-prompt
tokens, so a weak check is never silently shipped.

Usage:
  python3 scripts/authoring/reanchor_report_checks.py <task_dir> [--apply]
  python3 scripts/authoring/reanchor_report_checks.py <task_dir> --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

MIN_EVIDENCE = 2
MAX_EVIDENCE = 10

PATH_RE = re.compile(r"[A-Za-z0-9_./-]+\.(?:go|py|rs|java|ts|tsx|js|proto|yaml|yml|toml|rb|c|cc|cpp|h)\b")
SYM_RE = re.compile(r"\b(?:[a-z][a-zA-Z0-9]*[A-Z][A-Za-z0-9]*|[A-Z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*|[a-z][a-z0-9]+_[a-z0-9_]+)\b")
# strong non-prompt evidence in dep/refactor tasks: pinned versions and PR/issue
# refs an agent only learns by reading the manifests / advisories, not the prompt
VER_RE = re.compile(r"\bv?\d+\.\d+(?:\.\d+)+\b")
REF_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#\d+")


def _stem(tok: str) -> str:
    """crude stem so classify/classification, identify/identification match."""
    for suf in ("ication", "ations", "ation", "ifying", "ify", "ing", "ed", "es", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)]
    return tok

# structural keys of expected_solution.json + generic words that are not evidence
STOPWORDS = {
    "expected_solution", "evaluation_criteria", "task_id", "checkpoints",
    "scoring_evidence", "required_files", "sufficient_files", "expected_answer",
    "root_cause", "error_chain", "affected_components", "affected_services",
    "affected_resources", "remediation_proposal", "root_cause_identification",
    "error_chain_trace",
}


def _string_values(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "evaluation_criteria" or k == "expected_solution":
                out.extend(_string_values(v))
            elif isinstance(v, (dict, list)):
                out.extend(_string_values(v))
            elif isinstance(v, str):
                out.append(v)
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_string_values(v))
    return out


def extract_evidence(cp_body: dict, instr_low: str) -> list[str]:
    """Non-prompt evidence tokens for one checkpoint: paths first, then symbols."""
    text = "\n".join(_string_values(cp_body))
    paths, refs, syms = [], [], []
    seen = set()

    def take(tok, bucket):
        low = tok.lower()
        if low in seen or low in instr_low or low in STOPWORDS:
            return
        seen.add(low)
        bucket.append(tok)

    for m in PATH_RE.findall(text):
        take(m, paths)
    for m in VER_RE.findall(text) + REF_RE.findall(text):
        take(m, refs)
    for m in SYM_RE.findall(text):
        if len(m) >= 5:
            take(m, syms)
    # paths + pinned versions/PR refs are the strongest non-prompt evidence;
    # symbols supplement up to the cap
    return (paths + refs + syms)[:MAX_EVIDENCE]


def map_checks_to_checkpoints(task_dir: Path, checkpoints: list[str]) -> dict:
    """check_file -> checkpoint, by token overlap of the filename stem."""
    mapping = {}
    cp_tokens = {cp: {_stem(t) for t in re.split(r"[_\W]+", cp.lower()) if t}
                 for cp in checkpoints}
    for sh in sorted((task_dir / "checks").glob("*.sh")):
        stem = re.sub(r"^check_", "", sh.stem).lower()
        stem_tokens = {_stem(t) for t in re.split(r"[_\W]+", stem) if t}
        best, best_score = None, 0.0
        for cp, toks in cp_tokens.items():
            score = float(len(stem_tokens & toks))
            # partial containment on stems (classif in classifybreakage, etc.)
            if any(st in ct or ct in st
                   for st in stem_tokens for ct in toks if len(st) >= 4 and len(ct) >= 4):
                score += 0.5
            if score > best_score:
                best, best_score = cp, score
        mapping[sh.name] = best if best_score > 0 else None
    return mapping


def deliverable_of(check_text: str) -> str | None:
    """The deliverable path a check grades. md-grep graders only — a structured
    (.json) deliverable is parsed field-by-field and cannot use the grep grader,
    so it returns None (the caller routes it to the structured handler)."""
    m = re.search(r'\$\{?WORKSPACE(?::-[^}]*)?\}?/([^"\s\)`]+\.[A-Za-z0-9]+)', check_text)
    if not m:
        return None
    path = m.group(1)
    if path.split("/")[-1] == "ground_truth.json":
        return None
    if not path.endswith(".md"):
        return None  # structured deliverable — not a grep grader
    return path


GRADER_TEMPLATE = '''#!/usr/bin/env bash
# {check_name} — checkpoint "{checkpoint}"
#
# Re-anchored to ground_truth.json:scoring_evidence[{checkpoint}]
# (EnterpriseBench-jn73.2.7.3.1). Credits ONLY non-prompt evidence — tokens
# absent from instruction.md and present in expected_solution.json — so a
# verbatim prompt copy scores 0. ground_truth.json is sealed root-only.
set -euo pipefail

CHECKPOINT="{checkpoint}"
WORKSPACE="${{WORKSPACE:-/workspace}}"
REPORT="$WORKSPACE/{deliverable}"
GT="${{TASK_DIR:-}}/ground_truth.json"
MAX_REPORT_BYTES=1048576

verdict() {{ printf '{{"score": %s, "passed": %s, "detail": "%s"}}\\n' "$1" "$2" "$3"; exit 0; }}

if [[ ! -f "$GT" ]]; then
  verdict 0.0 false "VERIFIER_INFRA_ERROR: ground_truth.json not found at $GT"
fi
if [[ -L "$REPORT" ]]; then
  verdict 0.0 false "{deliverable_base} is a symlink, not a regular file"
fi
if [[ ! -f "$REPORT" ]]; then
  verdict 0.0 false "{deliverable_base} not found"
fi
if [[ "$(wc -c <"$REPORT")" -gt "$MAX_REPORT_BYTES" ]]; then
  verdict 0.0 false "{deliverable_base} exceeds ${{MAX_REPORT_BYTES}} bytes"
fi

export REPORT GT CHECKPOINT
python3 -c '
import json, os

def verdict(score, detail):
    print(json.dumps({{"score": round(score, 2), "passed": score >= 0.5, "detail": detail}}))
    raise SystemExit(0)

with open(os.environ["GT"]) as fh:
    gt = json.load(fh)
evidence = (gt.get("scoring_evidence") or {{}}).get(os.environ["CHECKPOINT"]) or []
if not evidence:
    verdict(0.0, "VERIFIER_INFRA_ERROR: no scoring_evidence for " + os.environ["CHECKPOINT"])

with open(os.environ["REPORT"], encoding="utf-8", errors="replace") as fh:
    text = fh.read().lower()

found = sum(1 for token in evidence if token.lower() in text)
verdict(found / len(evidence),
        "Cited %d/%d non-prompt evidence tokens for %s" % (found, len(evidence), os.environ["CHECKPOINT"]))
'
'''


def reanchor(task_dir: Path, apply: bool) -> dict:
    toml = tomllib.load(open(task_dir / "task.toml", "rb"))
    checkpoints = [c["name"] for c in toml.get("checkpoints", [])]
    esp = task_dir / "expected_solution.json"
    gtp = task_dir / "ground_truth.json"
    instr_low = (task_dir / "instruction.md").read_text(errors="replace").lower()
    result = {"task": task_dir.name, "checkpoints": {}, "flags": [], "applied": False}
    if not esp.exists():
        result["flags"].append("no expected_solution.json")
        return result
    es = json.loads(esp.read_text())
    es_cps = es.get("checkpoints", {})
    mapping = map_checks_to_checkpoints(task_dir, checkpoints)

    evidence_by_cp: dict[str, list[str]] = {}
    for cp in checkpoints:
        body = es_cps.get(cp)
        if body is None:
            result["flags"].append(f"checkpoint {cp} missing from expected_solution")
            continue
        evidence_by_cp[cp] = extract_evidence(body, instr_low)

    # Prose checkpoints (e.g. remediation_proposal) carry few code tokens of
    # their own. A real remediation names the files it changes, so a thin
    # checkpoint borrows the task's other non-prompt FILE-PATH evidence — still
    # strictly non-prompt (echo-resistant), just not checkpoint-unique. Only
    # paths are pooled (unambiguous investigation evidence), never bare symbols.
    pooled_paths: list[str] = []
    seen = set()
    for ev in evidence_by_cp.values():
        for tok in ev:
            if "/" in tok and tok.lower() not in seen:
                seen.add(tok.lower())
                pooled_paths.append(tok)
    result["pooled"] = []
    for cp in checkpoints:
        ev = evidence_by_cp.get(cp, [])
        if len(ev) < MIN_EVIDENCE:
            have = {t.lower() for t in ev}
            for p in pooled_paths:
                if p.lower() not in have:
                    ev.append(p)
                    have.add(p.lower())
                if len(ev) >= MIN_EVIDENCE:
                    break
            if len(ev) >= MIN_EVIDENCE:
                result["pooled"].append(cp)
            evidence_by_cp[cp] = ev[:MAX_EVIDENCE]

    for cp in checkpoints:
        ev = evidence_by_cp.get(cp, [])
        result["checkpoints"][cp] = ev
        if len(ev) < MIN_EVIDENCE:
            result["flags"].append(f"checkpoint {cp}: only {len(ev)} non-prompt tokens")

    rewrites = {}
    for sh_name, cp in mapping.items():
        text = (task_dir / "checks" / sh_name).read_text()
        deliv = deliverable_of(text)
        if cp is None:
            result["flags"].append(f"check {sh_name}: no checkpoint mapping")
            continue
        if deliv is None:
            result["flags"].append(f"check {sh_name}: no deliverable path found")
            continue
        if len(evidence_by_cp.get(cp, [])) < MIN_EVIDENCE:
            continue
        rewrites[sh_name] = GRADER_TEMPLATE.format(
            check_name=sh_name, checkpoint=cp, deliverable=deliv,
            deliverable_base=Path(deliv).name,
        )
    result["mapping"] = mapping

    if apply and not result["flags"]:
        gt = json.loads(gtp.read_text())
        gt["scoring_evidence"] = evidence_by_cp
        gtp.write_text(json.dumps(gt, indent=2) + "\n")
        for sh_name, body in rewrites.items():
            (task_dir / "checks" / sh_name).write_text(body)
        result["applied"] = True
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = reanchor(Path(args.task_dir), args.apply)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"task: {res['task']}  applied={res['applied']}")
        for cp, ev in res["checkpoints"].items():
            print(f"  {cp}: {ev}")
        if res["flags"]:
            print("  FLAGS:")
            for f in res["flags"]:
                print(f"    - {f}")
    return 1 if res["flags"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
