# Mirror Remediation Log — 2026-06 (bead EnterpriseBench-768k.2 / wave-1)

Per-task decision record for the Stephanie-authorized 88-pin mirror remediation
(parent EnterpriseBench-768k). **Wave-1 = first 12 tasks** of the 51 with ≥1
truly-missing mirror, in deterministic order of first appearance in the
truly-missing table of `results/analysis/mirror_resweep_corrected_2026_06.md`.

- **Source of truth:** `results/analysis/mirror_resweep_corrected_2026_06.md` (768k.1, REPORT ONLY).
- **Decision rule:** pin is the intended ground truth → **CREATE** the sg-evals mirror as-is + register in `configs/repo_versions.json`; pin is unintended → **REPIN** task.toml to a managed/mirrored version + re-validate gold.
- **Validation per pin:** (a) tag resolves upstream via anonymous `git ls-remote`; (b) pin unregistered in `repo_versions.json` (matches the 88 truly-missing set); (c) task gold/instruction version references coherent with the pin; (d) no conflicting same-task managed pin.
- **Outcome of wave-1: 12/12 tasks → CREATE-as-is, 0 repins.** Every pin resolved upstream, every gold referenced exactly its pinned version. The 22 unique mirrors were created public + anonymously cloneable, named per the SG scheme (full-tag for tags, `/`→`_`; no hex pins in this wave).

## Per-task decisions

| # | task | mirror (pin) | decision | rationale |
|---|------|--------------|----------|-----------|
| 1 | api-contract-dual-sqlalchemy-alembic-001 | `sqlalchemy--rel_2_0_0` (tag), `alembic--rel_1_12_0` (tag) | CREATE | both tags resolve upstream; gold references rel_2_0_0 + rel_1_12_0 exactly; intended API-contract pairing |
| 2 | support-mapping-dual-sqlalchemy-alembic-metadata-001 | `sqlalchemy--rel_2_0_29` (tag), `alembic--rel_1_13_1` (tag) | CREATE | both tags resolve; gold references rel_2_0_29 + rel_1_13_1 exactly; intended metadata-mapping pairing |
| 3 | incident-investigation-dual-cortex-001 | `cortex--v1.18.0` (tag), `alertmanager--v0.27.0` (tag) | CREATE | both tags resolve; gold references v1.18.0 + v0.27.0; managed alertmanager v0.26.0 is a different task's pin, not a repin target |
| 4 | refactor-dual-axum-tower-001 | `axum--axum-v0.7.0` (tag), `tower--tower-0.4.13` (tag) | CREATE | both prefixed tags resolve; gold references axum-v0.7 + tower-0.4; managed axum-v0.6.19 is another task's pin |
| 5 | support-mapping-dual-axum-tower-middleware-001 | `axum--axum-v0.7.5` (tag), `tower--tower-0.4.13` (tag, shared w/ #4) | CREATE | axum-v0.7.5 resolves; tower-0.4.13 already created in #4 (skip-existing) |
| 6 | support-mapping-dual-babel-swc-decorators-001 | `babel--v7.24.0` (tag), `swc--v1.4.6` (tag) | CREATE | both resolve; gold references v7.24.0 + v1.4.6; managed babel v7.22–v7.25 pins belong to other tasks |
| 7 | support-mapping-dual-jest-babel-cache-001 | `jest--v29.7.0` (tag), `babel--v7.24.0` (tag, shared w/ #6) | CREATE | jest v29.7.0 resolves; babel v7.24.0 already created in #6 (skip-existing); managed jest v29.0.0 is another task's pin |
| 8 | incident-investigation-dual-cilium-001 | `cilium--v1.16.4` (tag), `ebpf--v0.16.0` (tag) | CREATE | both resolve; gold references v1.16.4 + v0.16.0; intended dual-repo pairing |
| 9 | incident-investigation-dual-cockroach-001 | `cockroach--v24.2.5` (tag), `pebble--v1.1.2` (tag) | CREATE | both resolve; gold references v24.2.5 + v1.1.2; intended storage-engine pairing |
| 10 | incident-inv-dual-cortex-thanos-001 | `cortex--v1.16.0` (tag), `thanos--v0.32.0` (tag) | CREATE | both resolve; gold references v1.16.0 + v0.32.0; managed thanos v0.32.5 is another task's pin, not a repin target |
| 11 | dep-graph-dual-cryptography-paramiko-001 | `cryptography--41.0.0` (tag), `paramiko--3.2.0` (tag) | CREATE | both resolve; gold references 41.0.0 + 3.2.0 (the `1.1.1` string is an OpenSSL-version context ref, not a pin) |
| 12 | support-mapping-dual-openssl-curl-cipher-001 | `curl--curl-8_6_0` (tag), `openssl--openssl-3.0.13` (tag) | CREATE | both underscore/prefixed tags resolve; gold references curl-8_6_0 + openssl-3.0.13 (the `1.1.1` string is an OpenSSL-EOL context ref); managed openssl-3.1.1 / curl-7_82_0 / curl-8_1_2 are other tasks' pins |

## Wave-1 tally

- **Tasks processed:** 12 (CREATE: 12, REPIN: 0).
- **Unique mirrors created:** 22 (all public, all anonymously cloneable, all non-empty).
  - 2 mirrors shared across tasks: `tower--tower-0.4.13` (#4, #5), `babel--v7.24.0` (#6, #7).
  - 2 mirrors required the push-protection private-toggle workaround (test tokens in source), both restored to **public**: `cortex--v1.18.0`, `cortex--v1.16.0`.
- **Registered in `configs/repo_versions.json`:** 22 new `(url, pinned_rev)` entries, `last_verified=2026-06-04`. No existing entries lost; canonical case-sensitive sort applied (incidentally fixed pre-existing containerd / httpx ordering drift).
- **Verification:** GitHub visibility=PUBLIC + isEmpty=false (22/22); anonymous smart-HTTP `info/refs` returned 200 (22/22); SG mirror naming scheme correct by construction (full-tag, `/`→`_`).
- **Not modified (out of scope / concurrent work):** `configs/sg_indexing_list.json`, `configs/runs/mirror_creation_manifest.json`. SG-side indexing of the sg-evals org happens out-of-band; `verify_sg_indexing.py --check-api` is a stub.

## Cutoff for wave-2 resume

**Last task processed: #12 `support-mapping-dual-openssl-curl-cipher-001`**
(mirrors `curl--curl-8_6_0`, `openssl--openssl-3.0.13`).

Wave-2 resumes at the **13th distinct task** by first-appearance order in the
truly-missing table — `support-mapping-dual-django-wagtail-treepath-001`
(mirrors `django--4.2.10`, `wagtail--v5.2.2`) — and continues through the
remaining **39 tasks** (51 total truly-missing − 12 done) and their not-yet-created
mirrors.
