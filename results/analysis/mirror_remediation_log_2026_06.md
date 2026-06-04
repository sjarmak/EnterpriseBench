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

---

# Wave-2 (bead EnterpriseBench-768k.3) — next 12 tasks (#13–#24)

Continues the 88-pin remediation. **Wave-2 = the 13th–24th distinct tasks** by
first-appearance order in the truly-missing table of
`results/analysis/mirror_resweep_corrected_2026_06.md`, resuming at
`support-mapping-dual-django-wagtail-treepath-001` per wave-1's cutoff.

- **Same decision rule as wave-1:** pin is intended ground truth → **CREATE** mirror as-is + register; pin unintended (incl. does-not-resolve-upstream) → **REPIN** task.toml + re-validate gold, then create under the corrected ref.
- **Validation per pin:** (a) ref resolves upstream via anonymous `git ls-remote` (tags) / `gh api commits` (hex); (b) unregistered in `repo_versions.json`; (c) gold/checkpoints coherent with the pin; (d) no conflicting same-task managed pin.
- **Outcome of wave-2: 12/12 tasks remediated → 10 CREATE-as-is, 2 REPIN.** 25 unique mirrors created (all public, anonymously cloneable, non-empty).

## Per-task decisions

| # | task | mirror (pin) | decision | rationale |
|---|------|--------------|----------|-----------|
| 13 | support-mapping-dual-django-wagtail-treepath-001 | `django--4.2.10` (tag), `wagtail--v5.2.2` (tag) | CREATE | both tags resolve; gold version-generic (Django 4.2 / Wagtail 5.2 treepath); `wagtail--v5.2.2` needed the push-protection private-toggle workaround (test fixtures), restored **public** |
| 14 | incident-investigation-dual-loki-001 | `loki--v3.3.0` (tag), `dskit--53283a0f` (hex) | CREATE | tag + hex both resolve; dskit pin `53283a0f6b41…`; gold references Loki v3.3 + dskit |
| 15 | incident-investigation-dual-tempo-001 | `tempo--v2.6.0` (tag), `dskit--736c44c8` (hex) | CREATE | tag + 12-char hex resolve (→`736c44c853827731…`); distinct dskit rev from #14 |
| 16 | support-mapping-dual-envoy-istio-xds-001 | `envoy--v1.29.4` (tag), `istio--1.21.1` (tag) | CREATE | both resolve; gold references Envoy 1.29 + Istio 1.21 xDS |
| 17 | support-mapping-dual-fastapi-pydantic-validator-001 | `fastapi--0.110.0` (tag), `pydantic--v2.6.4` (tag) | CREATE | both resolve; gold references FastAPI 0.110 + pydantic 2.6 validator |
| 18 | api-contract-dual-pydantic-fastapi-001 | `fastapi--0.99.1` (tag, CREATE); `pydantic` `v2.0.0`→`v2.0` (**REPIN**) | **REPIN** | **`pydantic@v2.0.0` does not exist upstream** — pydantic's 2.0.0 release is tagged `v2.0` (`git ls-remote` has `refs/tags/v2.0`, no `v2.0.0`; `gh api …/commits/v2.0.0`→HTTP 422). Repinned `task.toml` rev `v2.0.0`→`v2.0` (**same release**, not a version change). Gold is version-generic ("pydantic v2 BaseModel API"; required files `pydantic/main.py`, `fastapi/encoders.py`) — unaffected. Mirror created as `pydantic--v2.0`. `fastapi--0.99.1` created as-is. |
| 19 | support-mapping-dual-flask-werkzeug-ctxvar-001 | `flask--2.3.3` (tag), `werkzeug--2.3.7` (tag) | CREATE | both Pallets tags resolve; gold references Flask 2.3 / Werkzeug 2.3 ctxvar |
| 20 | incident-investigation-dual-opa-001 | `frameworks--v0.20.0` (tag), `opa--v0.69.0` (tag) | CREATE | open-policy-agent/frameworks + opa both resolve; gold references OPA v0.69 + gatekeeper frameworks v0.20 |
| 21 | support-mapping-dual-grpc-protobuf-reflection-001 | `grpc--v1.62.0` (tag), `protobuf--v25.2` (tag) | CREATE | both resolve; gold references gRPC 1.62 + protobuf 25.2 reflection (the `3.21`/`4.25` strings in task.toml are protobuf-runtime context refs, not pins) |
| 22 | config-drift-tri-javax-jakarta-spring-001 | `spring-boot--v3.0.0` (tag, CREATE), `tomcat--10.1.0` (tag, CREATE); `hibernate-orm` `6.0.0.Final`→`6.0.0` (**REPIN**) | **REPIN** | **`hibernate-orm@6.0.0.Final` does not exist upstream** — Hibernate ORM's 6.0.0.Final release is git-tagged `6.0.0` (`refs/tags/6.0.0` exists, no `6.0.0.Final`; `gh api …/commits/6.0.0.Final`→HTTP 422; upstream switched away from the `.Final` tag suffix at 6.0). Repinned `task.toml` rev `6.0.0.Final`→`6.0.0` (**same release**; the javax→jakarta migration landed in 6.0). Gold is version-generic ("Hibernate 6 jakarta migration"; required file `hibernate-core/.../cfg/Configuration.java`) — unaffected. Mirror created as `hibernate-orm--6.0.0`. spring-boot v3.0.0 + tomcat 10.1.0 created as-is. Tri-repo task. |
| 23 | dep-graph-dual-spring-hibernate-001 | `hibernate-orm--6.2.0` (tag), `spring-boot--v3.1.0` (tag) | CREATE | both resolve; gold references Spring Boot 3.1 + Hibernate 6.2 dependency graph |
| 24 | support-mapping-dual-spring-hibernate-flush-001 | `spring-framework--v6.1.4` (tag), `hibernate-orm--6.4.4` (tag) | CREATE | both resolve; gold references Spring Framework 6.1 + Hibernate 6.4 flush ordering |

## Wave-2 tally

- **Tasks processed:** 12 (CREATE: 10, REPIN: 2).
- **Unique mirrors created:** 25 (all public, anonymously cloneable, non-empty). No mirror shared within wave-2 — `hibernate-orm` appears in 3 tasks but at 3 distinct revs (`6.0.0`/`6.2.0`/`6.4.4`); `spring-boot` at 2 (`v3.0.0`/`v3.1.0`); `dskit`/`fastapi`/`pydantic` each at 2 distinct revs.
- **REPINs (2) — defensibility record:** `pydantic` `v2.0.0`→`v2.0` (api-contract-dual-pydantic-fastapi-001); `hibernate-orm` `6.0.0.Final`→`6.0.0` (config-drift-tri-javax-jakarta-spring-001). Both are tag-name corrections to the **same release** (the original pins do not resolve to any upstream tag/commit). Verified gold/checkpoints are version-generic, so neither repin alters ground truth.
- **Push-protection private-toggle workaround (1):** `wagtail--v5.2.2`, restored to **public**.
- **Hex pins (2):** `dskit--53283a0f` (loki), `dskit--736c44c8` (tempo).
- **Registered in `configs/repo_versions.json`:** 25 new `(url, pinned_rev)` entries, `last_verified=2026-06-04` (corrected pins `pydantic@v2.0`, `hibernate-orm@6.0.0`). Count 205→230. No existing entries lost; canonical case-sensitive sort.
- **Verification:** GitHub `visibility=PUBLIC` 25/25 + `isEmpty=false` 25/25; anonymous smart-HTTP `info/refs` returned 200 for 25/25; SG mirror naming correct by construction (full-tag, `/`→`_`, hex `rev[:8]`).
- **Not modified (out of scope / concurrent work):** `configs/sg_indexing_list.json`, `configs/runs/mirror_creation_manifest.json`. SG-side indexing of the sg-evals org happens out-of-band; `verify_sg_indexing.py --check-api` is a stub.

## Cutoff for wave-3 resume

**Last task processed: #24 `support-mapping-dual-spring-hibernate-flush-001`**
(mirrors `spring-framework--v6.1.4`, `hibernate-orm--6.4.4`).

Wave-3 resumes at the **25th distinct task** by first-appearance order in the
truly-missing table — `support-mapping-dual-httpx-httpcore-001`
(mirror `httpx--0.27.0`) — and continues through the remaining **27 tasks**
(51 total truly-missing − 24 done) and their not-yet-created mirrors.

---

# Wave-3 (bead EnterpriseBench-768k.4) — next 12 tasks (#25–#36)

Continues the 88-pin remediation. **Wave-3 = the 25th–36th distinct tasks** by
first-appearance order in the truly-missing table of
`results/analysis/mirror_resweep_corrected_2026_06.md`, resuming at
`support-mapping-dual-httpx-httpcore-001` per wave-2's cutoff.

- **Same decision rule as waves 1–2:** pin is intended ground truth → **CREATE** mirror as-is + register; pin unintended (incl. does-not-resolve-upstream) → **REPIN** task.toml + re-validate gold, then create under the corrected ref.
- **Validation per pin:** (a) tag resolves upstream via anonymous `git ls-remote` (all 19 wave-3 pins are tags); (b) unregistered in `repo_versions.json` (matches the truly-missing set); (c) gold/checkpoint version references coherent with the pin (no contradicting version); (d) no conflicting same-task managed pin.
- **Outcome of wave-3: 12/12 tasks → 12 CREATE-as-is, 0 REPIN.** Every pin resolved upstream on its first tag form (unlike wave-2's pydantic/hibernate `.Final` corrections). 19 unique new mirrors created (all public, anonymously cloneable, non-empty); 0 needed the push-protection private-toggle workaround.

## Per-task decisions

| # | task | mirror (pin) | decision | rationale |
|---|------|--------------|----------|-----------|
| 25 | support-mapping-dual-httpx-httpcore-001 | `httpx--0.27.0` (tag) | CREATE | tag resolves; gold references httpx 0.27 / httpcore 1.0; `httpcore--1.0.5` already registered (not in truly-missing set) |
| 26 | api-contract-dual-hyper-reqwest-001 | `hyper--v1.0.0` (tag), `reqwest--v0.11.22` (tag) | CREATE | both resolve; gold references hyper 1.0 + reqwest 0.11 API contract |
| 27 | support-mapping-dual-tokio-hyper-graceful-001 | `hyper--v1.2.0` (tag), `tokio--tokio-1.36.0` (tag) | CREATE | both resolve; gold references hyper 1.2 graceful shutdown + tokio 1.36 |
| 28 | api-contract-dual-jackson-spring-001 | `jackson-databind--jackson-databind-2.15.0` (tag) | CREATE | jackson 2.15.0 resolves; gold references jackson 2.15 + Spring Boot 3.1; `spring-boot--v3.1.0` already created+registered in wave-2 (#23, skip-existing) |
| 29 | support-mapping-dual-jackson-spring-deserializer-001 | `jackson-databind--jackson-databind-2.16.2` (tag), `spring-boot--v3.2.4` (tag) | CREATE | both resolve; gold references jackson 2.16 deserializer + Spring Boot 3.2 |
| 30 | config-drift-dual-jaeger-otel-001 | `jaeger--v1.51.0` (tag), `opentelemetry-collector--v0.89.0` (tag) | CREATE | both resolve; gold references Jaeger 1.51 + otel-collector 0.89 config drift |
| 31 | error-prov-dual-otel-jaeger-001 | `opentelemetry-go--v1.21.0` (tag) | CREATE | otel-go 1.21 resolves; gold references otel-go 1.21 + Jaeger 1.51; `jaeger--v1.51.0` created in #30 (shared, skip-existing) |
| 32 | dep-graph-dual-junit-mockito-001 | `junit5--r5.10.0` (tag), `mockito--v5.5.0` (tag) | CREATE | both resolve (junit5 `r`-prefixed tag); gold references JUnit 5.10 + Mockito 5.5 dependency graph |
| 33 | support-mapping-dual-spring-kafka-rebalance-002 | `kafka--3.6.1` (tag), `spring-kafka--v3.1.4` (tag) | CREATE | both resolve; gold references Kafka 3.6 rebalance + Spring Kafka 3.1 |
| 34 | support-mapping-dual-celery-kombu-prefetch-001 | `kombu--v5.3.5` (tag) | CREATE | resolves; gold references kombu 5.3 prefetch; `celery--v5.3.6` already registered (not in truly-missing set) |
| 35 | dep-graph-dual-log4j-spring-001 | `logging-log4j2--rel_2.20.0` (tag, rev `rel/2.20.0`) | CREATE | log4j2 `rel/2.20.0` resolves (slash tag → mirror `rel_2.20.0`); gold references log4j2 2.20 + Spring Boot 3.1; `spring-boot--v3.1.0` already done in wave-2 (skip-existing) |
| 36 | support-mapping-dual-log4j-slf4j-async-001 | `logging-log4j2--rel_2.23.1` (tag, rev `rel/2.23.1`), `slf4j--v_2.0.13` (tag) | CREATE | both resolve (log4j2 slash tag → `rel_2.23.1`; slf4j underscore tag `v_2.0.13`); gold references log4j2 2.23 async + slf4j 2.0 |

## Wave-3 tally

- **Tasks processed:** 12 (CREATE: 12, REPIN: 0).
- **Unique mirrors created:** 19 (all public, anonymously cloneable, non-empty).
  - Shared/skip-existing within scope: `jaeger--v1.51.0` (#30, #31 — created once); `spring-boot--v3.1.0` (#28, #35 — already created+registered in wave-2 #23).
  - Already-registered non-truly-missing repos (untouched): `httpcore--1.0.5` (#25), `celery--v5.3.6` (#34).
  - Slash tags handled: `logging-log4j2` `rel/2.20.0`→`rel_2.20.0`, `rel/2.23.1`→`rel_2.23.1`. Underscore tag: `slf4j` `v_2.0.13`.
  - **0** mirrors required the push-protection private-toggle workaround.
- **REPINs:** 0 — every pin resolved upstream on its declared tag form; no `.Final`-style corrections needed this wave.
- **Registered in `configs/repo_versions.json`:** 19 new `(url, pinned_rev)` entries, `last_verified=2026-06-04`. Count 230→249. No existing entries lost; canonical case-sensitive sort by `(url, pinned_rev)` preserved; 0 duplicate keys.
- **Verification:** GitHub `visibility=PUBLIC` 19/19 + `isEmpty=false` 19/19; anonymous smart-HTTP `info/refs?service=git-upload-pack` returned HTTP 200 for 19/19; SG mirror naming correct by construction (full-tag, `/`→`_`).
- **Not modified (out of scope / concurrent work):** `configs/sg_indexing_list.json`, `configs/runs/mirror_creation_manifest.json`. SG-side indexing of the sg-evals org happens out-of-band; `verify_sg_indexing.py --check-api` is a stub.

## Cutoff for wave-4 resume

**Last task processed: #36 `support-mapping-dual-log4j-slf4j-async-001`**
(mirrors `logging-log4j2--rel_2.23.1`, `slf4j--v_2.0.13`).

Wave-4 resumes at the **37th distinct task** by first-appearance order in the
truly-missing table — `incident-investigation-dual-nats-001`
(mirrors `nats-server--v2.10.22`, `nats.go--v1.37.0`) — and continues through the
remaining **15 tasks** (51 total truly-missing − 36 done) and their not-yet-created mirrors.

Running tally after wave-3: **36/51 tasks, 66/88 mirrors** (22 wave-1 + 25 wave-2 + 19 wave-3).
