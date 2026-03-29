# Support Code Mapping — Mined Candidates

Task type: `support-map-*`
Suite mapping: `customer_escalation` (primary), `incident_response` (secondary)
Mined: 2026-03-28

---

## CSB Adaptation Candidates (12)

These existing CodeScaleBench tasks can be reframed from "trace error/find code" to "given vague user issue, identify code paths producing the behavior."

### CSB-A1: Envoy Connection Pool Exhaustion

- **CSB task:** `csb_org_incident/ccx-incident-032`
- **Issue description (reframed):** "Our production Envoy proxy keeps logging 'upstream connect error or disconnect/reset before headers. reset reason: overflow' and requests are failing intermittently."
- **Code paths (ground truth):** C++ source defining `overflow` reset reason string; connection pool implementation under `source/common/conn_pool/` or `source/common/http/`; circuit breaker protobuf config in `envoyproxy/data-plane-api` controlling `max_connections` and `max_pending_requests`
- **Repo:** `envoyproxy/envoy` (v1.31.2)
- **Difficulty:** hard
- **Adaptation notes:** Original task already follows "error message -> find code" pattern. Reframe instruction as a vague support ticket from a platform engineer.

### CSB-A2: LLVM Assertion Failure During Build

- **CSB task:** `csb_org_incident/ccx-incident-108`
- **Issue description (reframed):** "Our CI build system started crashing with 'Cannot expand this type; LLVM lacks the right hooks'. We didn't change anything — it started after updating the compiler toolchain."
- **Code paths (ground truth):** `llvm/lib/CodeGen/SelectionDAG/` type legalization expansion logic; EVT class in `llvm/include/llvm/CodeGen/`; `LegalizeDAG` class orchestrating type legalization
- **Repo:** `llvm/llvm-project`
- **Difficulty:** hard
- **Adaptation notes:** User-facing description is already vague (non-developer reporting CI failure). Good semantic gap between "build crashes" and SelectionDAG internals.

### CSB-A3: Grafana Dashboard Import Loses Settings

- **CSB task:** `csb_org_incident/ccx-incident-113`
- **Issue description (reframed):** "After importing a dashboard, all my table panel column widths and text alignment are gone. The panels look completely different from the exported version."
- **Code paths (ground truth):** Go source under `pkg/services/dashboardimport/` or `pkg/services/dashboards/` implementing v38 schema migration; function handling `fieldConfig` merging; schema version constant file registering v38
- **Repo:** `grafana/grafana`
- **Difficulty:** hard
- **Adaptation notes:** Excellent semantic gap — user sees "settings gone" but root cause is migration field merge logic. Cross-module (import service + schema migration).

### CSB-A4: Grafana Alerts Running Slow

- **CSB task:** `csb_org_incident/ccx-incident-145`
- **Issue description (reframed):** "We're seeing 'alert evaluation took longer than expected' warnings in Grafana logs. Some of our alerts are firing late or not at all."
- **Code paths (ground truth):** Go source implementing alerting evaluation scheduler tick; code detecting and logging evaluation cycle overruns
- **Repo:** `grafana/grafana`
- **Difficulty:** medium
- **Adaptation notes:** User symptom ("alerts late") maps to evaluation scheduler internals. Good natural language gap.

### CSB-A5: Kubernetes Pods Randomly Evicted

- **CSB task:** `csb_org_incident/ccx-incident-144`
- **Issue description (reframed):** "Our pods keep getting evicted with 'memory pressure' even though we have plenty of RAM on the node. It happens randomly across different workloads."
- **Code paths (ground truth):** Go source defining memory pressure eviction thresholds; eviction manager decision logic for memory-pressure-based pod eviction
- **Repo:** `kubernetes/kubernetes`
- **Difficulty:** hard
- **Adaptation notes:** "Random eviction" is a classic vague user report. Semantic gap between "plenty of RAM" and kernel memory pressure thresholds.

### CSB-A6: Firefox Crashes on CSS Pages

- **CSB task:** `csb_org_incident/ccx-incident-149`
- **Issue description (reframed):** "Firefox crashes when loading certain web pages. I noticed it only happens on pages with complex CSS animations using calc() values."
- **Code paths (ground truth):** C++ files parsing CSS calc() expressions; numeric overflow handling during calc() value resolution
- **Repo:** `mozilla/gecko-dev`
- **Difficulty:** hard
- **Adaptation notes:** User sees "crash on certain pages," root cause is numeric overflow in calc() parser. Large codebase with deep code path.

### CSB-A7: LibreOffice Spreadsheet Gives Wrong Results

- **CSB task:** `csb_org_incident/ccx-incident-139`
- **Issue description (reframed):** "My SUM formulas in LibreOffice Calc are showing incorrect results. Some cells that should update when I change values aren't recalculating."
- **Code paths (ground truth):** Formula tokenizer/compiler (`sc/source/core/tool/compiler.cxx`); `ScInterpreter` bytecode interpreter; `ScFormulaCell` class; recalculation scheduling (`ScRecalcMode`)
- **Repo:** `LibreOffice/core`
- **Difficulty:** hard
- **Adaptation notes:** User sees "wrong formula results," root cause requires tracing entire formula evaluation pipeline. Excellent semantic gap.

### CSB-A8: Browser App Crashes on Startup After Update

- **CSB task:** `csb_sdlc_debug/qutebrowser-adblock-cache-regression-prove-001`
- **Issue description (reframed):** "qutebrowser crashes immediately on startup after my system had a power outage. I can't use the browser at all — it just exits with an error."
- **Code paths (ground truth):** Ad-blocker filter cache deserialization code; cache loading path on startup; error handling for corrupted cache files
- **Repo:** `qutebrowser/qutebrowser`
- **Difficulty:** medium
- **Adaptation notes:** User doesn't know about ad-blocker cache — they just see "crash after power outage." Semantic gap between power outage → corrupted cache → unhandled deserialization error.

### CSB-A9: Chat App Threads Panel Crashes

- **CSB task:** `csb_sdlc_fix/element-web-roomheaderbuttons-can-crash-fix-001`
- **Issue description (reframed):** "Element Web crashes when I try to view threads in some rooms. It works fine in other rooms but certain rooms just show a white screen when I click the threads button."
- **Code paths (ground truth):** `RoomHeaderButtons` component; thread notification state access; room prop null safety checks; thread panel toggle logic
- **Repo:** `element-hq/element-web`
- **pre_fix_rev:** `8ebdcab7d92f90422776c4390363338dcfd98ba5`
- **Difficulty:** medium
- **Adaptation notes:** User sees "crashes in some rooms" — root cause is homeserver thread notification support detection. Good cross-component investigation.

### CSB-A10: Chat App Shows Unread When Everything Is Read

- **CSB task:** `csb_sdlc_fix/element-web-unread-indicators-diverge-fix-001`
- **Issue description (reframed):** "Element shows rooms as unread even after I've read everything. Sometimes a room shows as read but there are actually new messages in threads I haven't seen."
- **Code paths (ground truth):** Unread detection logic for room timeline and threads; read receipt handling; thread-scoped receipt processing; event type filtering for unread calculation
- **Repo:** `element-hq/element-web`
- **pre_fix_rev:** `526645c79160ab1ad4b4c3845de27d51263a405e`
- **Difficulty:** hard
- **Adaptation notes:** Classic vague user report. Root cause spans multiple timelines (room + threads) and receipt handling logic.

### CSB-A11: Forum Notifications Don't Show Up

- **CSB task:** `csb_sdlc_fix/nodebb-notif-dropdown-fix-001`
- **Issue description (reframed):** "When I click the notification bell in NodeBB, sometimes it shows empty or doesn't update. Also, when I try to move a topic to a different category, the category dropdown appears in the wrong place."
- **Code paths (ground truth):** Notifications dropdown async loading/toggle logic; category selector in fork/move topic modals; dropdown class management (`dropup` handling)
- **Repo:** `NodeBB/NodeBB`
- **pre_fix_rev:** `8fd8079a84d8e71ab02eaa69ef15cb33fcea85c7`
- **Difficulty:** hard
- **Adaptation notes:** Two related UI issues that map to different code paths. Good multi-symptom investigation task.

### CSB-A12: Kafka Messages Appearing on Wrong Topic

- **CSB task:** `csb_sdlc_fix/kafka-producer-bufpool-fix-001`
- **Issue description (reframed):** "We're seeing messages published to topic A occasionally appear on topic B instead. It happens in bursts during broker restarts. We've double-checked our producer code and it's sending to the right topic."
- **Code paths (ground truth):** `Sender.java` — `sendProducerData()` and `failBatch()`; `BufferPool` memory management; batch accumulation and buffer reuse logic
- **Repo:** `apache/kafka`
- **Difficulty:** expert
- **Adaptation notes:** Extremely vague symptom ("messages on wrong topic") with root cause in buffer pool race condition. Requires deep understanding of producer internals.

---

## Fresh-Mined Candidates (7)

### FM-1: Grafana Query Editor White Screen on Bad Input

- **Repo:** `grafana/grafana`
- **Issue:** Query editor breaks (white screen / crash) when invalid query entered and page refreshed
- **Issue description (user-facing):** "I pasted a trace ID into the Tempo query editor and the whole page went white. Now every time I open that dashboard it crashes."
- **Fix PR:** grafana/grafana#118409 (3 files changed)
- **Code paths:** `public/app/plugins/datasource/tempo/traceql/TraceQLEditor.tsx`, `highlighting.ts`, `highlighting.test.ts`
- **Difficulty:** medium

### FM-2: Grafana Alert Rule Edit Crashes

- **Repo:** `grafana/grafana`
- **Issue:** Alert rules with reduce expressions containing conditions arrays cause undefined error when editing
- **Issue description (user-facing):** "I can't edit my alert rules anymore. When I open the alert rule editor, I get an error and the page breaks. The alerts were working fine until the recent update."
- **Fix PR:** grafana/grafana#119875 (7 files changed)
- **Code paths:** `public/app/features/alerting/unified/components/rule-editor/query-and-alert-condition/SimpleCondition.tsx`, `public/app/features/expressions/components/Condition.tsx`, `public/app/features/expressions/types.ts`, `public/app/features/expressions/utils/expressionTypes.ts` + tests
- **Difficulty:** hard

### FM-3: Grafana Chrome Query Fields Broken

- **Repo:** `grafana/grafana`
- **Issue:** grafana/grafana#54535 — Input fields broken in recent Chrome versions causing cursor jumps and focus loss
- **Issue description (user-facing):** "Since updating Chrome, I can't type in any query fields in Grafana. The cursor keeps jumping around and I lose focus randomly. Works fine in Firefox."
- **Fix PR:** grafana/grafana#54566 (34 files changed — slate library upgrade)
- **Code paths:** `packages/grafana-ui/src/components/QueryField/QueryField.tsx`, `packages/grafana-ui/src/components/DataLinks/DataLinkInput.tsx`, slate plugins under `packages/grafana-ui/src/slate-plugins/`
- **Difficulty:** expert (34 files, library-level dependency, cross-component)

### FM-4: Grafana CloudWatch Logs Return Empty

- **Repo:** `grafana/grafana`
- **Issue:** grafana/grafana#35448 — CloudWatch log queries stopped working after Grafana 8.0 upgrade
- **Issue description (user-facing):** "After upgrading to Grafana 8.0, all my CloudWatch Logs queries return no data. The same queries work fine in the AWS console. Nothing changed on the AWS side."
- **Fix PR:** grafana/grafana#35724 (2 files changed)
- **Code paths:** `pkg/tsdb/cloudwatch/live.go`, `pkg/tsdb/cloudwatch/logs.go`
- **Difficulty:** medium
- **Notes:** Root cause was a migration (#31149) that changed data types, breaking response data parsing. Good semantic gap between "no data" and data type migration.

### FM-5: Grafana Login Keeps Timing Out

- **Repo:** `grafana/grafana`
- **Issue:** grafana/grafana#56994 — Login timeout after v9.2.0 upgrade, sessions expire unexpectedly
- **Issue description (user-facing):** "After upgrading to Grafana 9.2.0, users get logged out constantly. We have to log in multiple times a day. Nothing changed in our auth configuration."
- **Fix PR:** referenced in grafana/grafana#57485 (cross-referenced)
- **Code paths:** Session/cookie management, authentication middleware, token rotation logic
- **Difficulty:** hard
- **Notes:** 40+ comments on original issue. Classic "upgrade broke auth" user report with deep backend root cause.

### FM-6: Nextcloud HMAC Session Errors

- **Repo:** `nextcloud/server`
- **Issue:** nextcloud/server#42157 — "HMAC does not match. Could not decrypt or decode encrypted session data"
- **Issue description (user-facing):** "After upgrading Nextcloud, I keep getting logged out with 'Could not decrypt session data' errors. It happens randomly and I have to clear cookies to fix it temporarily."
- **Fix PR:** nextcloud/server#34012 (referenced)
- **Code paths:** Session encryption/decryption, HMAC validation, cookie handling, HKDF key derivation
- **Difficulty:** hard
- **Notes:** 284 comments, multiple potential causes. Root cause involves session encryption key derivation and proxy cache interactions. Excellent vague user report.

### FM-7: Sentry Unmerge Feature Stuck

- **Repo:** `getsentry/sentry`
- **Issue:** getsentry/sentry#108372 — "Already being unmerged" message appears but unmerge never completes
- **Issue description (user-facing):** "I'm trying to unmerge some grouped issues in Sentry but it just says 'Already being unmerged' and nothing happens. I've waited 24+ hours and the issues are still merged."
- **Code paths:** Issue unmerge/grouping logic, fingerprint management, async task processing for unmerge operations
- **Difficulty:** hard
- **Notes:** Django backend with celery task processing. Good semantic gap between "stuck UI" and async task pipeline.

---

## Summary

| Source | Count | Repos Covered |
|--------|-------|---------------|
| CSB adaptation | 12 | envoy, llvm, grafana, k8s, gecko-dev, libreoffice, qutebrowser, element-web, nodebb, kafka |
| Fresh-mined | 7 | grafana (5), nextcloud (1), sentry (1) |
| **Total** | **19** | **10 distinct repos** |

### Difficulty Distribution
- Medium: 5 (26%)
- Hard: 12 (63%)
- Expert: 2 (11%)

### Next Steps (for P1.7)
1. Extract exact file lists from fix PRs for each fresh-mined candidate
2. Verify CSB task ground truth files against current repo versions
3. Build checkpoint structures per PRD specification
4. Confirm all candidates have sufficient semantic gap (user description vs code paths)
