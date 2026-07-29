#!/usr/bin/env python3
"""Render a complete schema-v3 capsule analysis as publication Markdown."""

from __future__ import annotations

import argparse
import html
import math
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))

from eb_study import strict_json_loads  # noqa: E402
from eb_verify.redact import redact  # noqa: E402

LOCAL_CONSOLE_URL_RE = re.compile(r"(?:\.\./)*rootcause_console\.html\Z")


def render_markdown(
    analysis: Mapping[str, Any],
    *,
    console_url: str = "../../../rootcause_console.html",
) -> str:
    """Render only a complete, headline-eligible capsule analysis."""

    _validate_console_url(console_url)
    _reject_secret_text(analysis)
    provenance, completeness, reward = _validate_publication_input(analysis)
    trace_evidence = _object(reward, "trace_evidence", "reward")
    method = _object(
        _object(analysis, "analysis", "analysis"),
        "method",
        "analysis",
    )
    if (
        method.get("significance_testing")
        != "withheld_raw_p_value_estimator_not_frozen"
    ):
        raise ValueError("analysis significance-testing status is not publication-safe")
    study_id = _text(provenance, "study_id", "provenance")
    by_arm = _object(reward, "by_arm", "reward")
    arms = tuple(by_arm)
    per_task = _object(reward, "per_task", "reward")
    if set(trace_evidence) != set(per_task):
        raise ValueError("trace evidence tasks must exactly match reported tasks")
    lines = [
        f"# EnterpriseBench headline study: {_markdown(study_id)}",
        "",
        (
            "This report is generated from the named, immutable Study Capsule. "
            "Confirmatory output is present only because every declared slot was valid."
        ),
        "",
        "## Study and completeness",
        "",
        f"- Model: `{_markdown(_text(provenance, 'model', 'provenance'))}`",
        f"- Revision: `{_markdown(_text(provenance, 'revision', 'provenance'))}`",
        (
            f"- Complete paired population: "
            f"{_integer(completeness, 'paired_tasks', 'completeness')} tasks, "
            f"{_integer(completeness, 'valid_slots', 'completeness')} valid slots"
        ),
        (
            f"- Generated analysis timestamp: "
            f"`{_markdown(_text(analysis, 'generated_at', 'analysis'))}`"
        ),
        "",
        "## Primary paired results",
        "",
        (
            "Significance testing is withheld: the frozen plan names Holm "
            "multiplicity control but does not freeze the raw p-value estimator."
        ),
        "",
        "| Contrast | Paired tasks | Mean Δ task score | 95% CI | Parity gate |",
        "|---|---:|---:|---:|---|",
    ]
    primary = _object(reward, "primary_contrasts", "reward")
    for contrast, result_value in primary.items():
        result = _mapping(result_value, f"primary contrast {contrast}")
        interval = _object(result, "confidence_interval_95", str(contrast))
        parity = _object(result, "parity", str(contrast))
        parity_interval = _object(parity, "confidence_interval_90", str(contrast))
        parity_label = (
            "established"
            if _boolean(parity, "established", str(contrast))
            else "not established"
        )
        margin = _number(parity, "absolute_task_score_margin", str(contrast))
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{_markdown(str(contrast))}`",
                    str(_integer(result, "n_paired", str(contrast))),
                    _metric(_number(result, "mean_delta", str(contrast))),
                    _interval(interval),
                    (
                        f"{parity_label}; 90% CI {_interval(parity_interval)} "
                        f"within ±{_metric(margin)}"
                    ),
                )
            )
            + " |"
        )

    descriptive = _object(reward, "descriptive_only", "reward")
    lines.extend(
        (
            "",
            (
                f"CLI versus MCP-only is **descriptive, not confirmatory**: "
                f"`{_markdown(_text(descriptive, 'contrast', 'descriptive result'))}` "
                f"has mean Δ "
                f"{_metric(_number(descriptive, 'mean_delta', 'descriptive result'))} "
                f"with 95% CI "
                f"{_interval(_object(descriptive, 'confidence_interval_95', 'descriptive result'))}. "
                f"{_markdown(_text(descriptive, 'reason', 'descriptive result'))}."
            ),
            "",
            "## Task-type stratification",
            "",
            "| Task type | n | Absolute arm means | Contrast | Mean Δ | 95% CI |",
            "|---|---:|---|---|---:|---:|",
        )
    )
    by_type = _object(reward, "by_task_type", "reward")
    for task_type, stratum_value in by_type.items():
        stratum = _mapping(stratum_value, f"task type {task_type}")
        stratum_arms = _object(stratum, "by_arm", f"task type {task_type}")
        means = "; ".join(
            f"{_markdown(arm)}={_metric(_number(_mapping(value, arm), 'mean', arm))}"
            for arm, value in stratum_arms.items()
        )
        contrasts = _object(stratum, "contrasts", f"task type {task_type}")
        for contrast, result_value in contrasts.items():
            result = _mapping(result_value, f"{task_type}/{contrast}")
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"`{_markdown(str(task_type))}`",
                        str(_integer(stratum, "n_tasks", f"task type {task_type}")),
                        means,
                        f"`{_markdown(str(contrast))}`",
                        _metric(
                            _number(result, "mean_delta", f"{task_type}/{contrast}")
                        ),
                        _interval(
                            _object(
                                result,
                                "confidence_interval_95",
                                f"{task_type}/{contrast}",
                            )
                        ),
                    )
                )
                + " |"
            )

    lines.extend(_tokenomics_lines(analysis, by_arm, arms))
    lines.extend(
        (
            "",
            "## Trace evidence",
            "",
            (
                "Each link opens the self-contained root-cause console filtered to "
                "the declared task and arm. Scores remain traceable to the exact run "
                "artifacts and judge provenance."
            ),
            "",
        )
    )
    for task_id, scores_value in per_task.items():
        scores = _mapping(scores_value, f"task {task_id}")
        if set(scores) != set(arms):
            raise ValueError(f"task {task_id} is missing a declared arm score")
        task_evidence = _mapping(
            trace_evidence.get(task_id),
            f"trace evidence for task {task_id}",
        )
        if set(task_evidence) != set(arms):
            raise ValueError(f"trace evidence for task {task_id} is incomplete")
        links = [
            link
            for arm in arms
            for link in _trace_links(
                console_url,
                study_id,
                str(task_id),
                arm,
                task_evidence.get(arm),
            )
        ]
        lines.append(f"- `{_markdown(str(task_id))}`: " + " · ".join(links))

    lines.extend(_provenance_lines(provenance))
    lines.extend(_reproduction_lines(study_id, console_url))
    lines.extend(
        (
            "",
            "## Limitations",
            "",
            (
                "- No comparative efficiency claim is licensed by this report. "
                "The frozen plan locks reward parity as a prerequisite but does not "
                "lock an inferential estimator for cost, tokens, or latency."
            ),
            (
                "- Cost and token counts are provider-reported. Missing coverage is "
                "shown rather than interpreted as zero."
            ),
            (
                "- Elapsed-time totals sum trial durations and are not parallel "
                "makespan."
            ),
            (
                "- CLI versus MCP-only changes both interface and source availability, "
                "so that contrast is descriptive only."
            ),
            (
                "- Findings are limited to the locked task manifest and represented "
                "task types; they do not generalize to structured deliverables."
            ),
            (
                "- Forced Code Finder and Codex/OpenCode comparisons are outside this "
                "confirmatory capsule and must remain separately labeled descriptive "
                "analyses."
            ),
            "",
        )
    )
    return "\n".join(lines)


def _validate_publication_input(
    analysis: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(analysis, Mapping) or analysis.get("schema_version") != 3:
        raise ValueError("publication requires schema-v3 analysis")
    inference = _object(analysis, "analysis", "analysis")
    completeness = _object(analysis, "completeness", "analysis")
    reward = analysis.get("reward")
    if (
        inference.get("status") != "complete"
        or completeness.get("headline_eligible") is not True
        or not isinstance(reward, Mapping)
    ):
        raise ValueError("publication requires complete confirmatory inference")
    paired = _integer(completeness, "paired_tasks", "completeness")
    declared = _integer(completeness, "declared_tasks", "completeness")
    if (
        paired < 1
        or paired != declared
        or completeness.get("excluded_tasks") != {}
        or completeness.get("missing_or_invalid_slots") != []
    ):
        raise ValueError("publication requires the complete declared population")
    return (
        _object(analysis, "provenance", "analysis"),
        completeness,
        reward,
    )


def _tokenomics_lines(
    analysis: Mapping[str, Any],
    by_arm: Mapping[str, Any],
    arms: Sequence[str],
) -> list[str]:
    economics = _object(analysis, "economics", "analysis")
    tokens = _object(analysis, "tokens", "analysis")
    timing = _object(analysis, "timing", "analysis")
    paired_cost = _object(economics, "paired_valid", "economics")
    all_cost = _object(economics, "all_attempts", "economics")
    paired_tokens = _object(tokens, "paired_valid", "tokens")
    all_tokens = _object(tokens, "all_attempts", "tokens")
    paired_timing = _object(timing, "paired_valid", "timing")
    all_timing = _object(timing, "all_attempts", "timing")
    arm_costs = _object(paired_cost, "by_arm_usd", "paired economics")
    arm_tokens = _object(paired_tokens, "by_arm", "paired tokens")
    arm_timing = _object(paired_timing, "by_arm", "paired timing")
    paired_cost_coverage = _object(paired_cost, "cost_coverage", "paired economics")
    all_cost_coverage = _object(all_cost, "cost_coverage", "all-attempt economics")
    paired_token_coverage = _object(paired_tokens, "coverage", "paired tokens")
    all_token_coverage = _object(all_tokens, "coverage", "all-attempt tokens")
    lines = [
        "",
        "## Tokenomics and timing",
        "",
        (
            "These are descriptive accounting views over the paired-valid "
            "population; parity is required before comparative efficiency "
            "interpretation."
        ),
        "",
        "| Arm | Mean task score | Paired-valid cost | Combined tokens | Mean elapsed |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in arms:
        score = _mapping(by_arm.get(arm), f"arm {arm}")
        timing_row = _mapping(arm_timing.get(arm), f"timing for {arm}")
        cost = arm_costs.get(arm)
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{_markdown(arm)}`",
                    _metric(_number(score, "mean", f"arm {arm}")),
                    _money(cost),
                    _combined_tokens(arm_tokens.get(arm), f"tokens for {arm}"),
                    f"{_metric(_number(timing_row, 'mean_elapsed_seconds', arm))} s",
                )
            )
            + " |"
        )
    lines.extend(
        (
            "",
            (
                f"All-attempt spend: {_money(all_cost.get('total_cost_usd'))} "
                f"across {_integer(all_cost, 'receipts', 'all-attempt economics')} "
                f"receipts; "
                f"{_combined_tokens(all_tokens.get('total'), 'all-attempt token total')} "
                f"combined tokens; "
                f"{_metric(_number(all_timing, 'total_elapsed_seconds', 'all-attempt timing'))} "
                "summed trial-seconds."
            ),
            (
                "Accounting coverage — paired-valid: "
                f"costed receipts "
                f"`{_integer(paired_cost_coverage, 'costed_trials', 'paired cost coverage')}`, "
                f"missing cost receipts "
                f"`{_integer(paired_cost_coverage, 'missing_cost_trials', 'paired cost coverage')}`; "
                f"tokenized receipts "
                f"`{_integer(paired_token_coverage, 'tokenized_receipts', 'paired token coverage')}`, "
                f"missing usage receipts "
                f"`{_integer(paired_token_coverage, 'missing_usage_receipts', 'paired token coverage')}`."
            ),
            (
                "Accounting coverage — all attempts: "
                f"costed receipts "
                f"`{_integer(all_cost_coverage, 'costed_trials', 'all-attempt cost coverage')}`, "
                f"missing cost receipts "
                f"`{_integer(all_cost_coverage, 'missing_cost_trials', 'all-attempt cost coverage')}`; "
                f"tokenized receipts "
                f"`{_integer(all_token_coverage, 'tokenized_receipts', 'all-attempt token coverage')}`, "
                f"missing usage receipts "
                f"`{_integer(all_token_coverage, 'missing_usage_receipts', 'all-attempt token coverage')}`."
            ),
        )
    )
    return lines


def _provenance_lines(provenance: Mapping[str, Any]) -> list[str]:
    rows = (
        ("StudySpec", "spec_hash"),
        ("Task manifest", "task_manifest_hash"),
        ("Analysis plan", "analysis_plan_hash"),
        ("Candidate manifest", "candidate_manifest_hash"),
        ("Execution order", "execution_order_hash"),
    )
    lines = ["", "## Frozen provenance", "", "| Artifact | Digest |", "|---|---|"]
    for label, key in rows:
        value = provenance.get(key)
        lines.append(f"| {label} | `{_markdown(str(value or 'not recorded'))}` |")
    lines.extend(
        (
            "",
            (
                f"Agent account `{provenance.get('agent_account')}`; judge account "
                f"`{provenance.get('judge_account')}`; execution-order entries "
                f"`{provenance.get('execution_order_count')}`."
            ),
        )
    )
    return lines


def _reproduction_lines(study_id: str, console_url: str) -> list[str]:
    base = f"results/official_runs/{study_id}"
    return [
        "",
        "## Reproduce",
        "",
        "From the repository root:",
        "",
        "```bash",
        "python3 scripts/analysis/study_report.py \\",
        f"  --spec {_shell_path(base, 'study_spec.json')} \\",
        f"  --receipts {_shell_path(base, 'receipts.jsonl')} \\",
        f"  --analysis-plan {_shell_path(base, 'analysis_plan.json')} \\",
        f"  --task-manifest {_shell_path(base, 'final_manifest.json')} \\",
        f"  --output {_shell_path(base, 'reproduced_score_analysis.json')}",
        "python3 scripts/analysis/study_markdown_report.py \\",
        f"  --analysis {_shell_path(base, 'reproduced_score_analysis.json')} \\",
        f"  --console-url {shlex.quote(console_url)} \\",
        f"  --output {_shell_path(base, 'reproduced_report.md')}",
        "```",
    ]


def _shell_path(base: str, name: str) -> str:
    return shlex.quote(f"{base}/{name}")


def _trace_links(
    console_url: str,
    study_id: str,
    task_id: str,
    arm: str,
    trial_keys_value: Any,
) -> list[str]:
    if not isinstance(trial_keys_value, list) or not trial_keys_value:
        raise ValueError(f"trace evidence for {task_id}/{arm} must be non-empty")
    if any(not isinstance(key, str) or not key for key in trial_keys_value):
        raise ValueError(f"trace evidence for {task_id}/{arm} has an invalid trial key")
    trial_keys = tuple(trial_keys_value)
    if len(set(trial_keys)) != len(trial_keys):
        raise ValueError(f"trace evidence for {task_id}/{arm} has duplicate trial keys")
    prefix = f"{study_id}/{task_id}/{arm}/"
    if any(
        not key.startswith(prefix)
        or re.fullmatch(r"rep[1-9][0-9]*/att[1-9][0-9]*", key[len(prefix) :]) is None
        for key in trial_keys
    ):
        raise ValueError(f"trace evidence for {task_id}/{arm} is not in the study")
    return [
        (
            f"[{_markdown(arm if len(trial_keys) == 1 else f'{arm} {key.rsplit('/', 2)[-2]}/{key.rsplit('/', 1)[-1]}')}]"
            f"({_trace_link(console_url, task_id, arm, key)})"
        )
        for key in trial_keys
    ]


def _trace_link(
    console_url: str,
    task_id: str,
    arm: str,
    trial_key: str,
) -> str:
    parts = urlsplit(console_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend((("q", task_id), ("arm", arm), ("trial", trial_key)))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _object(payload: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    return _mapping(payload.get(key), f"{label}.{key}")


def _text(payload: Mapping[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}.{key} must be a non-empty string")
    if any(character in value for character in "<>") or any(
        ord(character) < 32 and character not in "\n\t" for character in value
    ):
        raise ValueError(f"{label}.{key} contains unsafe publication text")
    return value


def _number(payload: Mapping[str, Any], key: str, label: str) -> float:
    value = payload.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{label}.{key} must be finite")
    return float(value)


def _integer(payload: Mapping[str, Any], key: str, label: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label}.{key} must be a non-negative integer")
    return value


def _boolean(payload: Mapping[str, Any], key: str, label: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be boolean")
    return value


def _interval(interval: Mapping[str, Any]) -> str:
    return (
        "["
        + _metric(_number(interval, "low", "interval"))
        + ", "
        + _metric(_number(interval, "high", "interval"))
        + "]"
    )


def _metric(value: float) -> str:
    return f"{value:.4f}"


def _money(value: Any) -> str:
    if value is None:
        return "unavailable"
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("cost must be a finite non-negative number or null")
    return f"${float(value):.4f}"


def _count_or_missing(value: Any) -> str:
    if value is None:
        return "unavailable"
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("token count must be a non-negative integer or null")
    return f"{value:,}"


def _combined_tokens(value: Any, label: str) -> str:
    if value is None:
        return "unavailable"
    return _count_or_missing(_mapping(value, label).get("combined_tokens"))


def _markdown(value: str) -> str:
    escaped = html.escape(value, quote=True)
    return re.sub(r"([\\|`()\[\]])", r"\\\1", escaped)


def _reject_secret_text(value: Any) -> None:
    if isinstance(value, str):
        if redact(value) != value:
            raise ValueError("analysis contains secret-shaped text")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_secret_text(key)
            _reject_secret_text(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            _reject_secret_text(item)


def _load_analysis(path: Path) -> Mapping[str, Any]:
    try:
        payload = strict_json_loads(path.read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"analysis is unreadable: {path}: {exc}") from exc
    return _mapping(payload, "analysis")


def _validate_console_url(console_url: str) -> None:
    if (
        not isinstance(console_url, str)
        or LOCAL_CONSOLE_URL_RE.fullmatch(console_url) is None
    ):
        raise ValueError("console URL must be a local rootcause_console.html path")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--console-url",
        default="../../../rootcause_console.html",
        help="URL used for per-task trace deep links",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        rendered = render_markdown(
            _load_analysis(args.analysis),
            console_url=args.console_url,
        )
        _atomic_write(args.output, rendered)
    except (OSError, ValueError) as exc:
        print(f"study_markdown_report: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
