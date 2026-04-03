# Plan: convert-incident-inv-004

## Changes

### 1. task.toml

- Change `difficulty_stratum` from "large_single" to "dual_repo"
- Add second `[[repos]]` entry: containerd v1.7.24, path="containerd", role="dependency"
- Add `repo_deps` to each checkpoint:
  - root_cause_identification: ["moby"]
  - error_chain_trace: ["moby", "containerd"]
  - affected_services: ["moby", "containerd"]
  - remediation_proposal: ["moby"]
- Update `metadata.dependency_depth` to 2 (already 2, confirm)
- Update `tool_access.expected_mcp_benefit` to "high"
- Update `tool_access.mcp_benefit_rationale` for cross-repo
- Add containerd entries to ground_truth.required_files and sufficient_files
- Update prompt to reference /workspace/containerd/

### 2. instruction.md

- Add containerd repo to Environment section
- Update investigation steps to mention containerd shim code

### 3. ground_truth.json

- Add "containerd/containerd" to repos array
- Add containerd entries to error_chain

### 4. Check scripts

- Update check_error_chain.sh to also check for containerd-specific file references
- Update check_affected_services.sh to check for containerd shim components
- All scripts remain valid bash

## CRNT Verification

- Remove moby: max_score = 0.00 (all checkpoints depend on moby)
- Remove containerd: max_score = 0.55 (lose error_chain 0.30 + affected_services 0.15)
- Both <= 0.60 threshold => passes_crnt = true
- Scores differentiated: 0.00 vs 0.55
