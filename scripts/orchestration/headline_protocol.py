"""Immutable protocol definitions shared by headline builders and preflight."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from eb_verify.judge.backends import CLAUDE_CODE_MAX_RETRIES

STUDY_ID = "rryas-headline-v1"
CANDIDATE_LOCK_REVISION = "bb60d7e11cbdc77ae94e54dfcaceb7d975ed3e6e"
POST_LOCK_EXPOSURES = (
    "dep-graph-dual-junit-mockito-001",
    "dep-traversal-003",
    "error-prov-dual-otel-jaeger-001",
    "incident-investigation-dual-istio-001",
    "incident-investigation-dual-nerdctl-001",
)
POST_LOCK_EXPOSURE_EVIDENCE = {
    "dep-graph-dual-junit-mockito-001": (
        "configs/studies/rryas_code_finder_interface_pilot_v1/pilot_manifest.json",
    ),
    "dep-traversal-003": (
        "configs/studies/rryas_pilot_v1/pilot_manifest.json",
        "configs/studies/rryas_code_finder_canary_v1/canary_manifest.json",
        "configs/studies/rryas_code_finder_canary_v2/canary_manifest.json",
        "configs/studies/rryas_cli_code_finder_canary_v1/canary_manifest.json",
        "configs/studies/rryas_cli_code_finder_canary_v2/canary_manifest.json",
    ),
    "error-prov-dual-otel-jaeger-001": (
        "configs/studies/rryas_code_finder_interface_pilot_v1/pilot_manifest.json",
    ),
    "incident-investigation-dual-istio-001": (
        "configs/studies/rryas_code_finder_interface_pilot_v1/pilot_manifest.json",
    ),
    "incident-investigation-dual-nerdctl-001": (
        "configs/studies/rryas_code_finder_interface_supplement_v1/pilot_manifest.json",
        "configs/studies/rryas_code_finder_interface_supplement_v2/pilot_manifest.json",
    ),
}
V2_ADDITIONAL_EXPOSURES = (
    "api-contract-001",
    "api-contract-002",
    "api-contract-dual-envoy-istio-001",
)
V2_POST_LOCK_EXPOSURES = (
    *V2_ADDITIONAL_EXPOSURES,
    *POST_LOCK_EXPOSURES,
)
V2_POST_LOCK_EXPOSURE_EVIDENCE = {
    **POST_LOCK_EXPOSURE_EVIDENCE,
    **{
        candidate_id: ("results/studies/rryas-headline-v1/receipts.jsonl",)
        for candidate_id in V2_ADDITIONAL_EXPOSURES
    },
}
V3_ADDITIONAL_EXPOSURES = (
    "api-contract-dual-hyper-reqwest-001",
    "api-contract-dual-jackson-spring-001",
    "api-contract-dual-sqlalchemy-alembic-001",
    "config-drift-dual-setuptools-pip-001",
    "dep-graph-dual-cryptography-paramiko-001",
    "dep-graph-dual-spring-hibernate-001",
    "dep-graph-dual-tokio-hyper-001",
    "dep-graph-tri-boto3-urllib3-requests-001",
)
V3_POST_LOCK_EXPOSURES = (
    *V2_POST_LOCK_EXPOSURES,
    *V3_ADDITIONAL_EXPOSURES,
)
V3_POST_LOCK_EXPOSURE_EVIDENCE = {
    **V2_POST_LOCK_EXPOSURE_EVIDENCE,
    **{
        candidate_id: ("results/studies/rryas-headline-v2/receipts.jsonl",)
        for candidate_id in V3_ADDITIONAL_EXPOSURES
    },
}
V4_ADDITIONAL_EXPOSURES = (
    "dep-graph-tri-prometheus-alertmanager-grafana-001",
)
V4_POST_LOCK_EXPOSURES = (
    *V3_POST_LOCK_EXPOSURES,
    *V4_ADDITIONAL_EXPOSURES,
)
V4_POST_LOCK_EXPOSURE_EVIDENCE = {
    **V3_POST_LOCK_EXPOSURE_EVIDENCE,
    **{
        candidate_id: ("results/studies/rryas-headline-v3/receipts.jsonl",)
        for candidate_id in V4_ADDITIONAL_EXPOSURES
    },
}
V5_POST_LOCK_EXPOSURES = V4_POST_LOCK_EXPOSURES
V5_POST_LOCK_EXPOSURE_EVIDENCE = V4_POST_LOCK_EXPOSURE_EVIDENCE
V5_ZERO_AGENT_EXPOSURE_EVIDENCE = (
    "results/studies/rryas-headline-v4/batch-001-terminal.json"
)
V5_ZERO_AGENT_EXPOSURE_EVIDENCE_SHA256 = (
    "sha256:05c65bb88a98276e4065c6eb3ab1cfe9bf18bfbdb68b3553b73adf0ecd10edb9"
)
V6_ADDITIONAL_EXPOSURES = (
    "dep-graph-tri-tokio-hyper-tonic-001",
)
V6_POST_LOCK_EXPOSURES = (
    *V5_POST_LOCK_EXPOSURES,
    *V6_ADDITIONAL_EXPOSURES,
)
V6_PREDECESSOR_TERMINAL_EVIDENCE = (
    "results/studies/rryas-headline-v5/batch-001-terminal.json"
)
V6_PREDECESSOR_TERMINAL_EVIDENCE_SHA256 = (
    "sha256:bbbac4f9a943aff8ab30e3e1e80882824e114570995e5417a1db5fec78733ab3"
)
V6_PREDECESSOR_RECEIPTS = "results/studies/rryas-headline-v5/receipts.jsonl"
V6_PREDECESSOR_RECEIPTS_SHA256 = (
    "sha256:cbd815f188af68c385db044031c9b2edc390cfbba19cac11719db77364333851"
)
V6_UNEXPOSED_FAILED_TASKS = ("dep-traversal-001",)
V6_POST_LOCK_EXPOSURE_EVIDENCE = {
    **V5_POST_LOCK_EXPOSURE_EVIDENCE,
    **{
        candidate_id: (
            V6_PREDECESSOR_RECEIPTS,
            V6_PREDECESSOR_TERMINAL_EVIDENCE,
        )
        for candidate_id in V6_ADDITIONAL_EXPOSURES
    },
}
V7_ADDITIONAL_EXPOSURES = (
    "dep-traversal-001",
    "dep-traversal-002",
    "dep-traversal-004",
)
V7_POST_LOCK_EXPOSURES = (
    *V6_POST_LOCK_EXPOSURES,
    *V7_ADDITIONAL_EXPOSURES,
)
V7_PREDECESSOR_TERMINAL_EVIDENCE = (
    "results/studies/rryas-headline-v6/batch-001-terminal.json"
)
V7_PREDECESSOR_TERMINAL_EVIDENCE_SHA256 = (
    "sha256:b0a2f7e2302dacc90123a90e5c978a5be0c0761b9f23eb9430414840aead9338"
)
V7_PREDECESSOR_RECEIPTS = "results/studies/rryas-headline-v6/receipts.jsonl"
V7_PREDECESSOR_RECEIPTS_SHA256 = (
    "sha256:52f28200ea8f4fa7493045d07568f91bb6b5271abb53be2051742b91ec1c8795"
)
V7_POST_LOCK_EXPOSURE_EVIDENCE = {
    **V6_POST_LOCK_EXPOSURE_EVIDENCE,
    **{
        candidate_id: (
            V7_PREDECESSOR_RECEIPTS,
            V7_PREDECESSOR_TERMINAL_EVIDENCE,
        )
        for candidate_id in V7_ADDITIONAL_EXPOSURES
    },
}


@dataclass(frozen=True)
class HeadlineProtocol:
    """Frozen population and slot counts for one confirmatory capsule."""

    study_id: str
    task_count: int
    slot_count: int
    post_lock_exposures: tuple[str, ...]
    post_lock_exposure_evidence: Mapping[str, tuple[str, ...]]
    arms: tuple[tuple[str, str], ...]
    arm_descriptions: Mapping[str, str]
    forecast_basis: str


REQUIRED_SELECTION_RULE = (
    "retain every structurally eligible candidate in candidate-manifest order "
    "except tasks with agent output after candidate lock; never inspect "
    "candidate reward or tool behavior to select confirmatory tasks"
)
REQUIRED_ARMS = (
    ("baseline", "local-repos:no-mcp:no-sgx:cache-isolated:v2"),
    ("mcp_only", "sourcegraph-mcp:local-repos-denied:cache-isolated:v2"),
    ("cli", "sgx-cli:local-repos-readable:usage-required:cache-isolated:v2"),
)
REQUIRED_ARM_DESCRIPTIONS = {
    "baseline": "local repositories; no Sourcegraph",
    "mcp_only": "Sourcegraph MCP; local repositories denied",
    "cli": "Sourcegraph CLI; local repositories readable; CLI use required",
}
V2_REQUIRED_ARMS = REQUIRED_ARMS[:2] + (
    (
        "cli",
        "sgx-cli:local-repos-readable:retrieval-before-local:cache-isolated:v3",
    ),
)
V2_REQUIRED_ARM_DESCRIPTIONS = {
    **REQUIRED_ARM_DESCRIPTIONS,
    "cli": (
        "Sourcegraph CLI required before local repository inspection; "
        "local repositories readable after first CLI call"
    ),
}
V1_PROTOCOL = HeadlineProtocol(
    study_id=STUDY_ID,
    task_count=43,
    slot_count=129,
    post_lock_exposures=POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=POST_LOCK_EXPOSURE_EVIDENCE,
    arms=REQUIRED_ARMS,
    arm_descriptions=REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No extrapolation from confounded pilot costs; report actual "
        "provider usage before paid authorization."
    ),
)
V2_PROTOCOL = HeadlineProtocol(
    study_id="rryas-headline-v2",
    task_count=40,
    slot_count=120,
    post_lock_exposures=V2_POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=V2_POST_LOCK_EXPOSURE_EVIDENCE,
    arms=V2_REQUIRED_ARMS,
    arm_descriptions=V2_REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No v2 spend authorization before a strengthened-CLI operational canary passes."
    ),
)
V3_PROTOCOL = HeadlineProtocol(
    study_id="rryas-headline-v3",
    task_count=32,
    slot_count=96,
    post_lock_exposures=V3_POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=V3_POST_LOCK_EXPOSURE_EVIDENCE,
    arms=V2_REQUIRED_ARMS,
    arm_descriptions=V2_REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No v3 spend authorization before the v2 rate-limit root cause is "
        "fixed and a provider-reset capacity gate passes."
    ),
)
V4_PROTOCOL = HeadlineProtocol(
    study_id="rryas-headline-v4",
    task_count=31,
    slot_count=93,
    post_lock_exposures=V4_POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=V4_POST_LOCK_EXPOSURE_EVIDENCE,
    arms=V2_REQUIRED_ARMS,
    arm_descriptions=V2_REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No v4 spend authorization before the v3 judge-cap root cause is "
        "fixed and an isolated judge-only canary passes."
    ),
)
V5_PROTOCOL = HeadlineProtocol(
    study_id="rryas-headline-v5",
    task_count=31,
    slot_count=93,
    post_lock_exposures=V5_POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=V5_POST_LOCK_EXPOSURE_EVIDENCE,
    arms=V2_REQUIRED_ARMS,
    arm_descriptions=V2_REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No v5 spend authorization before the v4 pre-inference child-import "
        "failure is fixed and terminally sealed."
    ),
)
V6_PROTOCOL = HeadlineProtocol(
    study_id="rryas-headline-v6",
    task_count=30,
    slot_count=90,
    post_lock_exposures=V6_POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=V6_POST_LOCK_EXPOSURE_EVIDENCE,
    arms=V2_REQUIRED_ARMS,
    arm_descriptions=V2_REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No v6 spend authorization before the v5 mid-batch MCP authentication "
        "failure is terminally sealed and every v5 agent-exposed task is excluded."
    ),
)
V7_PROTOCOL = HeadlineProtocol(
    study_id="rryas-headline-v7",
    task_count=27,
    slot_count=81,
    post_lock_exposures=V7_POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=V7_POST_LOCK_EXPOSURE_EVIDENCE,
    arms=V2_REQUIRED_ARMS,
    arm_descriptions=V2_REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No v7 spend authorization before v6 batch 1 is terminally sealed, "
        "every v6 agent-exposed task is excluded, and the hardened execution "
        "harness is frozen under a new StudySpec."
    ),
)
V3_MAX_SLOTS_PER_DISPATCH = 12
V3_AGENT_MAX_BUDGET_USD_PER_SLOT = 9.1
V3_JUDGE_MAX_BUDGET_USD_PER_CALL = 0.01
V3_MAX_JUDGE_CALLS_PER_SLOT = 5
V3_MAX_JUDGE_ATTEMPTS_PER_CALL = CLAUDE_CODE_MAX_RETRIES
V3_OUTER_SPEND_HARD_CAP_PER_SLOT_USD = round(
    V3_AGENT_MAX_BUDGET_USD_PER_SLOT
    + V3_JUDGE_MAX_BUDGET_USD_PER_CALL
    * V3_MAX_JUDGE_CALLS_PER_SLOT
    * V3_MAX_JUDGE_ATTEMPTS_PER_CALL,
    6,
)
V4_MAX_SLOTS_PER_DISPATCH = 9
V4_AGENT_MAX_BUDGET_USD_PER_SLOT = 9.1
V4_JUDGE_MAX_BUDGET_USD_PER_CALL = 0.1
V4_MAX_JUDGE_CALLS_PER_SLOT = 5
V4_MAX_JUDGE_ATTEMPTS_PER_CALL = CLAUDE_CODE_MAX_RETRIES
V4_OUTER_SPEND_HARD_CAP_PER_SLOT_USD = round(
    V4_AGENT_MAX_BUDGET_USD_PER_SLOT
    + V4_JUDGE_MAX_BUDGET_USD_PER_CALL
    * V4_MAX_JUDGE_CALLS_PER_SLOT
    * V4_MAX_JUDGE_ATTEMPTS_PER_CALL,
    6,
)
CAPACITY_GATED_PROTOCOLS = (
    V4_PROTOCOL,
    V5_PROTOCOL,
    V6_PROTOCOL,
    V7_PROTOCOL,
)
CAPACITY_GATED_STUDY_IDS = frozenset(
    protocol.study_id for protocol in CAPACITY_GATED_PROTOCOLS
)
V4_FAMILY_BATCH_POLICY = {
    "max_slots_per_dispatch": V4_MAX_SLOTS_PER_DISPATCH,
    "agent_max_budget_usd_per_slot": V4_AGENT_MAX_BUDGET_USD_PER_SLOT,
    "judge_max_budget_usd_per_call": V4_JUDGE_MAX_BUDGET_USD_PER_CALL,
    "max_judge_calls_per_slot": V4_MAX_JUDGE_CALLS_PER_SLOT,
    "max_judge_attempts_per_call": V4_MAX_JUDGE_ATTEMPTS_PER_CALL,
    "outer_spend_hard_cap_per_slot_usd": V4_OUTER_SPEND_HARD_CAP_PER_SLOT_USD,
}
HEADLINE_BATCH_POLICIES = {
    V3_PROTOCOL.study_id: {
        "max_slots_per_dispatch": V3_MAX_SLOTS_PER_DISPATCH,
        "agent_max_budget_usd_per_slot": V3_AGENT_MAX_BUDGET_USD_PER_SLOT,
        "judge_max_budget_usd_per_call": V3_JUDGE_MAX_BUDGET_USD_PER_CALL,
        "max_judge_calls_per_slot": V3_MAX_JUDGE_CALLS_PER_SLOT,
        "max_judge_attempts_per_call": V3_MAX_JUDGE_ATTEMPTS_PER_CALL,
        "outer_spend_hard_cap_per_slot_usd": (
            V3_OUTER_SPEND_HARD_CAP_PER_SLOT_USD
        ),
    },
    **{
        protocol.study_id: dict(V4_FAMILY_BATCH_POLICY)
        for protocol in CAPACITY_GATED_PROTOCOLS
    },
}
HEADLINE_STUDY_SPEND_CEILINGS_USD = {
    V3_PROTOCOL.study_id: 890.0,
    **{protocol.study_id: 990.0 for protocol in CAPACITY_GATED_PROTOCOLS},
}
HEADLINE_PROTOCOLS = {
    protocol.study_id: protocol
    for protocol in (
        V1_PROTOCOL,
        V2_PROTOCOL,
        V3_PROTOCOL,
        *CAPACITY_GATED_PROTOCOLS,
    )
}
PAID_BATCH_STUDY_IDS = frozenset(
    (V3_PROTOCOL.study_id, *CAPACITY_GATED_STUDY_IDS)
)
REQUIRED_CACHE_ISOLATION = {
    "schema_version": 1,
    "required": True,
    "mechanism": "prompt-caching-disabled",
    "scope": "fresh random scope generated independently for every invocation",
    "comparison_rule": (
        "valid proof and cross_run_cache_read_tokens == 0 and cache_write_tokens == 0"
    ),
    "legacy_evidence": "comparison_ineligible",
}
REQUIRED_JUDGE = {
    "model": "cc:haiku",
    "account": 1,
    "executable": "claude-1",
    "selection": "explicit --judge-account 1",
    "provenance_required_in_scores": True,
}
V4_REQUIRED_JUDGE = {
    **REQUIRED_JUDGE,
    "isolation": "safe-mode:no-tools:replacement-system-prompt",
}
REQUIRED_EXECUTION_BASE = {
    "agent_account": 3,
    "timeout_seconds": 600,
    "build_timeout_seconds": 1800,
    "verifier_timeout_seconds": 600,
    "memory_mb": 8192,
    "no_build": False,
    "repetitions": 1,
    "max_attempts": 1,
    "concurrency": 1,
}
REQUIRED_ORDER_POLICY = (
    "candidate-manifest order; rotate baseline,mcp_only,cli as a three-row "
    "Latin square by task index; execute sequentially on agent account 3; "
    "judge every completed slot on account 1"
)
REQUIRED_EVIDENCE_POLICY = {
    "confirmatory_population": "post-lock-unexposed-candidates-only",
    "historical_pilots": "operational evidence only; never headline evidence",
    "forced_code_finder": "separate descriptive study; never headline evidence",
    "codex_opencode": (
        "secondary harness-model bundles; never causal cross-model evidence"
    ),
    "invalid_slot": "stop promotion; retain receipt and all-attempt spend",
    "image_identity": (
        "record immutable built image and bound container digests per trial"
    ),
}
REQUIRED_ANALYSIS_PLAN = {
    "schema_version": 1,
    "status": "LOCKED-BEFORE-HEADLINE-INFERENCE",
    "study_id": STUDY_ID,
    "claim_scope": (
        "Claude Sonnet 5 on the 43-task EnterpriseBench markdown-report "
        "confirmatory population at the frozen revisions"
    ),
    "score": {
        "field": "task_score",
        "contract": "weighted-mean-v2",
        "range": [0.0, 1.0],
        "unit": "task",
    },
    "primary_estimands": [
        {
            "name": "mean_paired_reward_difference_mcp_only_minus_baseline",
            "contrast": ["mcp_only", "baseline"],
            "aggregation": "unweighted mean across all 43 paired tasks",
        },
        {
            "name": "mean_paired_reward_difference_cli_minus_baseline",
            "contrast": ["cli", "baseline"],
            "aggregation": "unweighted mean across all 43 paired tasks",
        },
    ],
    "secondary_estimands": [
        "per-arm mean task_score",
        "task-type-stratified paired reward differences",
        "reported_outer_cost_usd",
        "combined_tokens",
        "elapsed_seconds",
        "retrieval activity and validity gates",
    ],
    "descriptive_only": {
        "contrast": "cli_minus_mcp_only",
        "reason": ("the arms jointly change interface and local-source availability"),
    },
    "inference": {
        "confidence_level": 0.95,
        "bootstrap_repetitions": 10000,
        "bootstrap_seed": 20260728,
        "bootstrap_unit": "paired task",
        "stratification": "task_type with locked observed stratum sizes",
        "interval": "percentile paired bootstrap",
        "multiplicity": (
            "Holm correction at familywise alpha 0.05 for the two primary contrasts"
        ),
    },
    "reward_parity_gate_for_efficiency_claims": {
        "method": "two one-sided tests using a 90% paired-bootstrap interval",
        "absolute_task_score_margin": 0.05,
        "claim_rule": (
            "claim cheaper or faster at parity only when the complete 90% "
            "reward-difference interval is within [-0.05, 0.05]"
        ),
    },
    "missing_invalid_handling": {
        "max_attempts_per_slot": 1,
        "retry_after_observing_output_or_score": False,
        "headline_requires_all_129_slots_valid": True,
        "incomplete_pair": "no headline promotion or confirmatory inference",
        "all_attempts": "retain status, tokens, elapsed time, and cost",
    },
    "reporting": {
        "type_counts_and_per_type_results_required": True,
        "absolute_arm_means_required": True,
        "paired_differences_and_intervals_required": True,
        "all_attempt_spend_required": True,
        "account_order_and_revision_provenance_required": True,
        "no_generalization_to_structured_deliverables": True,
    },
}


def required_analysis_plan(protocol: HeadlineProtocol) -> dict[str, Any]:
    """Return the exact analysis plan required for a supported capsule."""

    plan = deepcopy(REQUIRED_ANALYSIS_PLAN)
    if protocol == V1_PROTOCOL:
        return plan
    plan["study_id"] = protocol.study_id
    predecessor_scope = {
        V2_PROTOCOL.study_id: "v1 operational run",
        V3_PROTOCOL.study_id: "v1 and v2 operational runs",
        V4_PROTOCOL.study_id: "v1, v2, and v3 operational runs",
        V5_PROTOCOL.study_id: "v1, v2, v3, and v4 operational attempts",
        V6_PROTOCOL.study_id: "v1-v3 and v5 operational attempts",
        V7_PROTOCOL.study_id: "v1-v3, v5, and v6 operational attempts",
    }[protocol.study_id]
    plan["claim_scope"] = (
        f"Claude Sonnet 5 on the {protocol.task_count}-task EnterpriseBench "
        "markdown-report confirmatory population remaining after the disclosed "
        f"{predecessor_scope}"
    )
    for estimand in plan["primary_estimands"]:
        estimand["aggregation"] = (
            f"unweighted mean across all {protocol.task_count} paired tasks"
        )
    missing = plan["missing_invalid_handling"]
    missing.pop("headline_requires_all_129_slots_valid")
    missing[f"headline_requires_all_{protocol.slot_count}_slots_valid"] = True
    if protocol == V2_PROTOCOL:
        plan["protocol_amendment"] = {
            "predecessor": "rryas-headline-v1",
            "reason": "v1 stopped on a prespecified infra_sgx_unused CLI validity gate",
            "selection_rule": (
                "exclude every task with v1 agent output; retain all other locked "
                "candidates without inspecting reward"
            ),
            "excluded_candidate_ids": list(V2_ADDITIONAL_EXPOSURES),
            "v1_analysis_use": "operational pilot evidence only",
        }
    elif protocol == V3_PROTOCOL:
        plan["protocol_amendment"] = {
            "predecessor": "rryas-headline-v2",
            "reason": "v2 stopped fail-closed on a provider session limit",
            "selection_rule": (
                "exclude every task with v1 or v2 agent output; retain all other "
                "locked candidates without inspecting reward"
            ),
            "excluded_candidate_ids": list(V3_ADDITIONAL_EXPOSURES),
            "predecessor_analysis_use": "operational evidence only",
        }
    elif protocol == V4_PROTOCOL:
        plan["protocol_amendment"] = {
            "predecessor": "rryas-headline-v3",
            "reason": (
                "v3 stopped fail-closed when the native judge budget rejected "
                "the unisolated Claude Code startup context before inference"
            ),
            "selection_rule": (
                "exclude every task with v1, v2, or v3 agent output; retain all "
                "other locked candidates without inspecting reward"
            ),
            "excluded_candidate_ids": list(V4_ADDITIONAL_EXPOSURES),
            "predecessor_analysis_use": "operational evidence only",
        }
    elif protocol == V5_PROTOCOL:
        plan["protocol_amendment"] = {
            "predecessor": "rryas-headline-v4",
            "reason": "v4 stopped during run_task module import before agent startup",
            "selection_rule": (
                "retain the unchanged v4 population because v4 produced no "
                "agent output and exposed no task"
            ),
            "excluded_candidate_ids": [],
            "zero_agent_exposure_evidence": V5_ZERO_AGENT_EXPOSURE_EVIDENCE,
            "zero_agent_exposure_evidence_sha256": (
                V5_ZERO_AGENT_EXPOSURE_EVIDENCE_SHA256
            ),
            "predecessor_analysis_use": "operational evidence only",
        }
    elif protocol == V6_PROTOCOL:
        plan["protocol_amendment"] = {
            "predecessor": "rryas-headline-v5",
            "reason": (
                "v5 stopped fail-closed on a Sourcegraph MCP authentication "
                "failure before agent startup on the fourth attempt"
            ),
            "selection_rule": (
                "exclude every task with v1-v3 or v5 agent output; retain all "
                "other locked candidates without inspecting reward"
            ),
            "excluded_candidate_ids": list(V6_ADDITIONAL_EXPOSURES),
            "predecessor_terminal_evidence": (
                V6_PREDECESSOR_TERMINAL_EVIDENCE
            ),
            "predecessor_terminal_evidence_sha256": (
                V6_PREDECESSOR_TERMINAL_EVIDENCE_SHA256
            ),
            "predecessor_receipts": V6_PREDECESSOR_RECEIPTS,
            "predecessor_receipts_sha256": (
                V6_PREDECESSOR_RECEIPTS_SHA256
            ),
            "unexposed_failed_task_ids": list(V6_UNEXPOSED_FAILED_TASKS),
            "predecessor_analysis_use": (
                "operational evidence and task-level descriptive diagnostics only"
            ),
        }
    elif protocol == V7_PROTOCOL:
        plan["protocol_amendment"] = {
            "predecessor": "rryas-headline-v6",
            "reason": (
                "the execution harness changed after v6 batch 1 was sealed; "
                "continuing v6 would mix harness identities"
            ),
            "selection_rule": (
                "exclude every task with v1-v3, v5, or v6 agent output; retain "
                "all other locked candidates without inspecting reward"
            ),
            "excluded_candidate_ids": list(V7_ADDITIONAL_EXPOSURES),
            "predecessor_terminal_evidence": (
                V7_PREDECESSOR_TERMINAL_EVIDENCE
            ),
            "predecessor_terminal_evidence_sha256": (
                V7_PREDECESSOR_TERMINAL_EVIDENCE_SHA256
            ),
            "predecessor_receipts": V7_PREDECESSOR_RECEIPTS,
            "predecessor_receipts_sha256": (
                V7_PREDECESSOR_RECEIPTS_SHA256
            ),
            "predecessor_analysis_use": (
                "operational evidence and task-level descriptive diagnostics only"
            ),
        }
    else:
        raise ValueError(f"unsupported headline protocol: {protocol.study_id}")
    return plan
