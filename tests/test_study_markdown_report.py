"""Publication-contract tests for the capsule Markdown renderer."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.analysis.study_markdown_report import render_markdown

REPO_ROOT = Path(__file__).resolve().parent.parent


def _complete_analysis() -> dict[str, object]:
    method = {
        "bootstrap_repetitions": 10_000,
        "bootstrap_seed": 20_260_728,
        "bootstrap_sampling": "within_task_type_fixed_stratum_sizes",
        "primary_confidence_level": 0.95,
        "parity_confidence_level": 0.9,
        "multiplicity": "holm",
        "significance_testing": "withheld_raw_p_value_estimator_not_frozen",
    }
    primary = {
        "mcp_only_vs_baseline": {
            "n_paired": 2,
            "mean_delta": 0.05,
            "confidence_interval_95": {"low": -0.01, "high": 0.11},
            "parity": {
                "absolute_task_score_margin": 0.05,
                "confidence_interval_90": {"low": 0.0, "high": 0.1},
                "established": False,
            },
        },
        "cli_vs_baseline": {
            "n_paired": 2,
            "mean_delta": 0.0,
            "confidence_interval_95": {"low": -0.02, "high": 0.02},
            "parity": {
                "absolute_task_score_margin": 0.05,
                "confidence_interval_90": {"low": -0.02, "high": 0.02},
                "established": True,
            },
        },
    }
    by_arm = {
        "baseline": {"n": 2, "mean": 0.5},
        "mcp_only": {"n": 2, "mean": 0.55},
        "cli": {"n": 2, "mean": 0.5},
    }
    by_type = {
        "dependency_graph": {
            "n_tasks": 1,
            "by_arm": {
                "baseline": {"mean": 0.4},
                "mcp_only": {"mean": 0.5},
                "cli": {"mean": 0.45},
            },
            "contrasts": {
                "mcp_only_vs_baseline": {
                    "n_paired": 1,
                    "mean_delta": 0.1,
                    "confidence_interval_95": {"low": 0.1, "high": 0.1},
                },
                "cli_vs_baseline": {
                    "n_paired": 1,
                    "mean_delta": 0.05,
                    "confidence_interval_95": {"low": 0.05, "high": 0.05},
                },
            },
        },
        "error_provenance": {
            "n_tasks": 1,
            "by_arm": {
                "baseline": {"mean": 0.6},
                "mcp_only": {"mean": 0.6},
                "cli": {"mean": 0.55},
            },
            "contrasts": {
                "mcp_only_vs_baseline": {
                    "n_paired": 1,
                    "mean_delta": 0.0,
                    "confidence_interval_95": {"low": 0.0, "high": 0.0},
                },
                "cli_vs_baseline": {
                    "n_paired": 1,
                    "mean_delta": -0.05,
                    "confidence_interval_95": {"low": -0.05, "high": -0.05},
                },
            },
        },
    }
    per_task = {
        "dep-traversal-001": {
            "baseline": 0.4,
            "mcp_only": 0.5,
            "cli": 0.45,
        },
        "err-provenance-001": {
            "baseline": 0.6,
            "mcp_only": 0.6,
            "cli": 0.55,
        },
    }
    token_arm = {
        "baseline": {"combined_tokens": 100},
        "mcp_only": {"combined_tokens": 120},
        "cli": {"combined_tokens": 80},
    }
    timing_arm = {
        "baseline": {
            "trials": 2,
            "mean_elapsed_seconds": 60.0,
            "total_elapsed_seconds": 120.0,
        },
        "mcp_only": {
            "trials": 2,
            "mean_elapsed_seconds": 65.0,
            "total_elapsed_seconds": 130.0,
        },
        "cli": {
            "trials": 2,
            "mean_elapsed_seconds": 50.0,
            "total_elapsed_seconds": 100.0,
        },
    }
    return {
        "schema_version": 3,
        "generated_at": "2026-07-29T00:00:00+00:00",
        "provenance": {
            "study_id": "rryas-headline-v6",
            "model": "claude-sonnet-5",
            "revision": "db7fa87",
            "spec_hash": "sha256:" + "1" * 64,
            "task_manifest_hash": "sha256:" + "2" * 64,
            "analysis_plan_hash": "sha256:" + "3" * 64,
            "candidate_manifest_hash": "sha256:" + "4" * 64,
            "candidate_lock_revision": "abc123",
            "execution_order_hash": "sha256:" + "5" * 64,
            "execution_order_count": 6,
            "agent_account": 3,
            "judge_account": 1,
            "task_type_counts": {
                "dependency_graph": 1,
                "error_provenance": 1,
            },
        },
        "analysis": {
            "status": "complete",
            "analysis_plan_hash": "sha256:" + "3" * 64,
            "task_manifest_hash": "sha256:" + "2" * 64,
            "method": method,
        },
        "completeness": {
            "headline_eligible": True,
            "declared_tasks": 2,
            "paired_tasks": 2,
            "declared_slots": 6,
            "valid_slots": 6,
            "excluded_tasks": {},
            "missing_or_invalid_slots": [],
        },
        "reward": {
            "by_arm": by_arm,
            "primary_contrasts": primary,
            "descriptive_only": {
                "contrast": "cli_vs_mcp_only",
                "mean_delta": -0.05,
                "confidence_interval_95": {"low": -0.1, "high": 0.0},
                "reason": "interface and source availability both change",
                "confirmatory_claim_eligible": False,
            },
            "by_task_type": by_type,
            "per_task": per_task,
            "trace_evidence": {
                task_id: {
                    arm: [
                        f"rryas-headline-v6/{task_id}/{arm}/rep1/att1",
                    ]
                    for arm in per_task[task_id]
                }
                for task_id in per_task
            },
            "method": method,
        },
        "economics": {
            "paired_valid": {
                "trials": 6,
                "total_cost_usd": 3.0,
                "by_arm_usd": {
                    "baseline": 1.0,
                    "mcp_only": 1.2,
                    "cli": 0.8,
                },
                "cost_coverage": {
                    "costed_trials": 6,
                    "missing_cost_trials": 0,
                },
            },
            "all_attempts": {
                "receipts": 6,
                "total_cost_usd": 3.0,
                "by_arm_usd": {
                    "baseline": 1.0,
                    "mcp_only": 1.2,
                    "cli": 0.8,
                },
                "cost_coverage": {
                    "costed_trials": 6,
                    "missing_cost_trials": 0,
                },
            },
        },
        "tokens": {
            "paired_valid": {
                "by_arm": token_arm,
                "total": {"combined_tokens": 300},
                "coverage": {
                    "tokenized_receipts": 6,
                    "missing_usage_receipts": 0,
                },
            },
            "all_attempts": {
                "by_arm": token_arm,
                "total": {"combined_tokens": 300},
                "coverage": {
                    "tokenized_receipts": 6,
                    "missing_usage_receipts": 0,
                },
            },
        },
        "timing": {
            "paired_valid": {
                "by_arm": timing_arm,
                "total_elapsed_seconds": 350.0,
            },
            "all_attempts": {
                "by_arm": timing_arm,
                "total_elapsed_seconds": 350.0,
            },
        },
    }


@pytest.mark.parametrize(
    ("section", "field", "secret"),
    (
        ("provenance", "model", "sk-proj-SECRET-SENTINEL-123456789"),
        (
            "reward.descriptive_only",
            "reason",
            "Bearer SECRET-SENTINEL-SECOND",
        ),
    ),
)
def test_renderer_rejects_secret_shaped_text(
    section: str,
    field: str,
    secret: str,
) -> None:
    analysis = _complete_analysis()
    target: dict[str, object] = analysis
    for part in section.split("."):
        value = target[part]
        assert isinstance(value, dict)
        target = value
    target[field] = secret

    with pytest.raises(ValueError, match="secret"):
        render_markdown(analysis)


def test_render_contains_publication_results_and_trace_deep_links() -> None:
    rendered = render_markdown(
        _complete_analysis(),
        console_url="../../../rootcause_console.html",
    )

    assert rendered.startswith("# EnterpriseBench headline study: rryas-headline-v6")
    assert "## Primary paired results" in rendered
    assert "## Task-type stratification" in rendered
    assert "## Tokenomics and timing" in rendered
    assert "## Trace evidence" in rendered
    assert "## Reproduce" in rendered
    assert "## Limitations" in rendered
    assert "mcp_only_vs_baseline" in rendered
    assert "dependency_graph" in rendered
    assert "Significance testing is withheld" in rendered
    assert "Holm-adjusted" not in rendered
    assert "Reject at FWER" not in rendered
    assert "descriptive, not confirmatory" in rendered
    assert "No comparative efficiency claim is licensed" in rendered
    assert (
        "../../../rootcause_console.html?"
        "q=dep-traversal-001&arm=mcp_only&"
        "trial=rryas-headline-v6%2Fdep-traversal-001%2F"
        "mcp_only%2Frep1%2Fatt1" in rendered
    )
    assert "--analysis-plan" in rendered
    assert "--task-manifest" in rendered
    assert "sha256:" + "3" * 64 in rendered


def test_incomplete_inference_cannot_produce_publication_markdown() -> None:
    analysis = _complete_analysis()
    analysis["analysis"] = {"status": "withheld_incomplete"}
    analysis["reward"] = None

    with pytest.raises(ValueError, match="complete confirmatory inference"):
        render_markdown(analysis)


def test_publication_refuses_ambiguous_trace_evidence() -> None:
    analysis = _complete_analysis()
    del analysis["reward"]["trace_evidence"]["dep-traversal-001"]["mcp_only"]

    with pytest.raises(ValueError, match="trace evidence"):
        render_markdown(analysis)


def test_publication_refuses_unreported_cross_study_trace_evidence() -> None:
    analysis = _complete_analysis()
    analysis["reward"]["trace_evidence"]["unreported-task"] = {
        "baseline": ["foreign-study/unreported-task/baseline/rep1/att1"],
    }

    with pytest.raises(ValueError, match="trace evidence tasks"):
        render_markdown(analysis)


def test_missing_provider_accounting_is_disclosed_not_treated_as_zero() -> None:
    analysis = _complete_analysis()
    analysis["economics"]["paired_valid"]["total_cost_usd"] = None
    analysis["economics"]["paired_valid"]["by_arm_usd"]["mcp_only"] = None
    analysis["economics"]["paired_valid"]["cost_coverage"] = {
        "costed_trials": 5,
        "missing_cost_trials": 1,
    }
    analysis["economics"]["all_attempts"]["total_cost_usd"] = None
    analysis["economics"]["all_attempts"]["cost_coverage"] = {
        "costed_trials": 5,
        "missing_cost_trials": 1,
    }
    analysis["tokens"]["paired_valid"]["by_arm"]["mcp_only"] = None
    analysis["tokens"]["paired_valid"]["total"] = None
    analysis["tokens"]["paired_valid"]["coverage"] = {
        "tokenized_receipts": 5,
        "missing_usage_receipts": 1,
    }
    analysis["tokens"]["all_attempts"]["total"] = None
    analysis["tokens"]["all_attempts"]["coverage"] = {
        "tokenized_receipts": 5,
        "missing_usage_receipts": 1,
    }

    rendered = render_markdown(analysis)

    assert "| `mcp_only` | 0.5500 | unavailable | unavailable |" in rendered
    assert "All-attempt spend: unavailable" in rendered
    assert "missing cost receipts `1`" in rendered
    assert "missing usage receipts `1`" in rendered
    assert "$0.0000" not in rendered


def test_cli_writes_deterministic_markdown_and_refuses_nonfinite_json(
    tmp_path: Path,
) -> None:
    analysis_path = tmp_path / "score_analysis.json"
    output_path = tmp_path / "report.md"
    analysis_path.write_text(json.dumps(_complete_analysis()))

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "analysis" / "study_markdown_report.py"),
        "--analysis",
        str(analysis_path),
        "--output",
        str(output_path),
        "--console-url",
        "../../../rootcause_console.html",
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)

    assert first.returncode == 0, first.stderr
    expected = render_markdown(
        _complete_analysis(),
        console_url="../../../rootcause_console.html",
    )
    assert output_path.read_text() == expected

    invalid = deepcopy(_complete_analysis())
    invalid["economics"]["paired_valid"]["total_cost_usd"] = float("nan")
    analysis_path.write_text(json.dumps(invalid))
    output_path.unlink()
    second = subprocess.run(command, capture_output=True, text=True, check=False)

    assert second.returncode != 0
    assert not output_path.exists()


@pytest.mark.parametrize(
    "console_url",
    (
        "javascript:alert(1)",
        "$(touch /tmp/REPORT_PWNED)",
        "https://example.com/report",
    ),
)
def test_renderer_rejects_nonlocal_console_urls(console_url: str) -> None:
    with pytest.raises(ValueError, match="console URL"):
        render_markdown(_complete_analysis(), console_url=console_url)


def test_renderer_rejects_active_html_in_contract_text() -> None:
    analysis = _complete_analysis()
    analysis["reward"]["descriptive_only"]["reason"] = "<img src=x onerror=alert(1)>"

    with pytest.raises(ValueError, match="publication text"):
        render_markdown(analysis)


def test_renderer_escapes_active_html_in_dynamic_identifiers() -> None:
    analysis = _complete_analysis()
    old_task_id = "dep-traversal-001"
    new_task_id = "<img src=x onerror=alert(1)>"
    task = analysis["reward"]["per_task"].pop(old_task_id)
    analysis["reward"]["per_task"][new_task_id] = task
    evidence = analysis["reward"]["trace_evidence"].pop(old_task_id)
    analysis["reward"]["trace_evidence"][new_task_id] = {
        arm: [key.replace(f"/{old_task_id}/", f"/{new_task_id}/") for key in keys]
        for arm, keys in evidence.items()
    }

    rendered = render_markdown(analysis)

    assert "<img src=x" not in rendered
    assert r"&lt;img src=x onerror=alert\(1\)&gt;" in rendered


def test_renderer_escapes_markdown_links_in_contract_text() -> None:
    analysis = _complete_analysis()
    analysis["reward"]["descriptive_only"]["reason"] = "[click](javascript:alert(1))"

    rendered = render_markdown(analysis)

    assert "[click](javascript:alert(1))" not in rendered
    assert r"\[click\]\(javascript:alert\(1\)\)" in rendered


def test_reproduction_commands_shell_quote_the_study_identifier() -> None:
    analysis = _complete_analysis()
    old_study_id = analysis["provenance"]["study_id"]
    new_study_id = "$(id)"
    analysis["provenance"]["study_id"] = new_study_id
    analysis["reward"]["trace_evidence"] = {
        task_id: {
            arm: [
                key.replace(f"{old_study_id}/", f"{new_study_id}/", 1) for key in keys
            ]
            for arm, keys in arms.items()
        }
        for task_id, arms in analysis["reward"]["trace_evidence"].items()
    }

    rendered = render_markdown(analysis)

    assert "--spec 'results/official_runs/$(id)/study_spec.json'" in rendered
