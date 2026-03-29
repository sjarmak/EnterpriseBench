# Dependency Graph Traversal — Mined Candidates

**Mining date:** 2026-03-28
**Source:** OSV database, GitHub Security Advisories (GHSA GraphQL API), NVD
**Task type:** `dep-graph-*` (PRD Section 3)
**Target:** 12-15 candidates for 10-12 final tasks

## Summary

15 candidates across 4 ecosystems: JavaScript/npm (3), Go (4), Python (3), Java/Maven (4), System/cross-ecosystem (1). Each has a real CVE, traceable dependency chain of 2+ hops, and a fix reference.

**Difficulty mix:** 4 medium (27%), 7 hard (47%), 4 expert (27%)

---

## Candidate 1: lodash Command Injection (JS)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2021-23337 |
| **GHSA** | GHSA-35jh-r3h4-6jhm |
| **Severity** | HIGH |
| **CWE** | CWE-77 (Command Injection), CWE-94 (Code Injection) |
| **Affected package** | `lodash` (npm) |
| **Affected versions** | < 4.17.21 |
| **Fix** | lodash/lodash@3469357 |
| **Difficulty** | medium |

**Dependency chain:**
```
lodash → webpack (devDependency, build tooling)
lodash → @babel/traverse (internal usage)
lodash → jest (jest-haste-map, jest-config)
lodash → create-react-app → downstream apps
```

**Task potential:** HIGH. lodash was depended on by ~73% of npm. Agent must identify which lodash sub-packages (lodash.template, lodash.merge) are also affected. Well-documented CVE makes this a good medium-difficulty calibration task.

**Repos for sandbox:** `lodash/lodash`, `webpack/webpack`, `jestjs/jest`

---

## Candidate 2: axios ReDoS (JS)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2021-3749 |
| **GHSA** | GHSA-cph5-m8f7-6c5x |
| **Severity** | HIGH |
| **CWE** | CWE-1333 (Inefficient Regex), CWE-400 (Resource Consumption) |
| **Affected package** | `axios` (npm) |
| **Affected versions** | < 0.21.2 |
| **Fix** | axios/axios@5b457116e31db0e88fede6c428e969e87f290929 |
| **Difficulty** | medium |

**Dependency chain:**
```
axios → vue-cli / create-react-app (HTTP client in scaffolded projects)
axios → Apache Druid (frontend)
axios → Grafana frontend plugins
```

**Task potential:** HIGH. Most popular JS HTTP client. Agent must trace through both direct and transitive dependants across frontend/backend boundaries. Good medium-difficulty calibration.

**Repos for sandbox:** `axios/axios`, `grafana/grafana`, `apache/druid`

---

## Candidate 3: protobuf.js Prototype Pollution (JS/cross-ecosystem)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2022-25878 |
| **GHSA** | GHSA-g954-5hwp-pp24 |
| **Severity** | HIGH |
| **CWE** | CWE-1321 (Prototype Pollution) |
| **Affected package** | `protobufjs` (npm) |
| **Affected versions** | 6.10.0-6.10.2, 6.11.0-6.11.2 |
| **Fix** | protobufjs/protobuf.js#1731, #1735; commit b5f1391 |
| **Difficulty** | hard |

**Dependency chain:**
```
protobufjs → @grpc/grpc-js → CNCF ecosystem (k8s client-node, Envoy xDS)
protobufjs → firebase-admin → Google Cloud Functions
protobufjs → @google-cloud/* (pubsub, storage)
```

**Task potential:** HIGH. Bridges JS and Go/CNCF ecosystems. Multi-language dependency chain traversal. Agent must understand that the npm package `protobufjs` feeds into the broader protobuf/gRPC ecosystem.

**Repos for sandbox:** `protobufjs/protobuf.js`, `grpc/grpc-node`, `kubernetes-client/javascript`

---

## Candidate 4: golang.org/x/net HTTP/2 Rapid Reset (Go)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2023-39325 |
| **GHSA** | GHSA-4374-p667-p6c8 |
| **Go Advisory** | GO-2023-2102 |
| **Severity** | HIGH |
| **CWE** | CWE-400, CWE-770 |
| **Affected package** | `golang.org/x/net` (Go module) |
| **Affected versions** | < 0.17.0 |
| **Fix** | go.dev/cl/514907 (x/net), go.dev/cl/514905 (stdlib) |
| **Difficulty** | hard |

**Dependency chain:**
```
golang.org/x/net → kubernetes/kubernetes (API server, kubelet, kubectl)
golang.org/x/net → etcd-io/etcd → CoreDNS → every k8s cluster
golang.org/x/net → grpc/grpc-go → virtually all Go gRPC services
golang.org/x/net → containerd/containerd → Docker → CI/CD pipelines
```

**Task potential:** CRITICAL. Related to CVE-2023-44487 (HTTP/2 Rapid Reset). 100+ Red Hat advisories. Agent must traverse Go module graph across CNCF projects. Deep and wide blast radius.

**Repos for sandbox:** `kubernetes/kubernetes`, `etcd-io/etcd`, `grpc/grpc-go`

---

## Candidate 5: golang.org/x/net HPACK DoS (Go)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2022-41723 |
| **GHSA** | GHSA-vvpx-j8f3-3w6h |
| **Go Advisory** | GO-2023-1571 |
| **Severity** | HIGH |
| **Affected package** | `golang.org/x/net` (Go module) |
| **Affected versions** | < 0.7.0 |
| **Fix** | go.dev/cl/468135, go.dev/cl/468295 |
| **Difficulty** | hard |

**Dependency chain:**
```
golang.org/x/net → kubernetes/kubernetes, etcd, grpc-go, containerd
golang.org/x/net → prometheus/prometheus
golang.org/x/net → hashicorp/consul, hashicorp/vault
```

**Task potential:** HIGH. Same deep Go module graph as Candidate 4. Can be paired for a "multiple CVE remediation" chained task. Different fix version threshold makes version range analysis non-trivial.

**Repos for sandbox:** `prometheus/prometheus`, `hashicorp/consul`, `hashicorp/vault`

---

## Candidate 6: google.golang.org/protobuf JSON Unmarshal Infinite Loop (Go)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2024-24786 |
| **GHSA** | GHSA-8r3f-844c-mc37 |
| **Go Advisory** | GO-2024-2611 |
| **Severity** | HIGH |
| **Affected package** | `google.golang.org/protobuf` (Go module) |
| **Affected versions** | < 1.33.0 |
| **Fix** | go.dev/cl/569356 |
| **Difficulty** | hard |

**Dependency chain:**
```
google.golang.org/protobuf → grpc-go → kubernetes, etcd, Istio
google.golang.org/protobuf → Prometheus → monitoring stacks
google.golang.org/protobuf → Envoy xDS → service mesh
```

**Task potential:** HIGH. Protobuf is foundational to the entire CNCF stack. Agent must identify which services unmarshal `Any` types (the vulnerable code path), not just which import the module. Requires understanding of protobuf message types in use.

**Repos for sandbox:** `grpc/grpc-go`, `istio/istio`, `envoyproxy/go-control-plane`

---

## Candidate 7: golang.org/x/text Accept-Language DoS (Go)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2022-32149 |
| **GHSA** | GHSA-69ch-w2m2-3vjp |
| **Go Advisory** | GO-2022-1059 |
| **Severity** | HIGH |
| **Affected package** | `golang.org/x/text` (Go module) |
| **Affected versions** | < 0.3.8 |
| **Fix** | go.dev/cl/442235 |
| **Difficulty** | medium |

**Dependency chain:**
```
golang.org/x/text → kubernetes/kubernetes (i18n, API responses)
golang.org/x/text → go-chi/chi, gorilla/mux (middleware stacks)
golang.org/x/text → gohugoio/hugo (static site generator)
```

**Task potential:** MEDIUM. Narrower blast radius — only `ParseAcceptLanguage` callers are affected. Agent must determine which dependants actually call the vulnerable function vs. just importing the module. Good test of code-level analysis beyond manifest scanning.

**Repos for sandbox:** `go-chi/chi`, `gorilla/mux`, `gohugoio/hugo`

---

## Candidate 8: requests Proxy-Authorization Header Leak (Python)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2023-32681 |
| **GHSA** | GHSA-j8r2-6x86-q33q |
| **Severity** | MODERATE |
| **Affected package** | `requests` (PyPI) |
| **Affected versions** | >= 2.3.0, < 2.31.0 |
| **Fix** | psf/requests@74ea7cf7a6a27a4eeb2ae24e162bcc942a6706d5 |
| **Difficulty** | hard |

**Dependency chain:**
```
requests → boto3 → awscli → AWS infrastructure automation
requests → docker-py → docker-compose → CI/CD
requests → ansible → configuration management
requests → pip (vendored) → every Python project
```

**Task potential:** HIGH. `requests` is in virtually every Python project. Agent must trace through `boto3→botocore→awscli` chain and identify proxy usage patterns. The vendored copy in pip adds complexity.

**Repos for sandbox:** `psf/requests`, `boto/boto3`, `aws/aws-cli`

---

## Candidate 9: urllib3 Cookie Header Leak on Redirect (Python)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2023-43804 |
| **GHSA** | GHSA-v845-jxx5-vc9f |
| **Severity** | HIGH |
| **Affected package** | `urllib3` (PyPI) |
| **Affected versions** | < 1.26.17 (1.x), 2.0.0-2.0.5 (2.x) |
| **Fix** | urllib3@644124ecd0b6e417c527191f866daa05a5a2056d (1.x), urllib3@01220354d389cd05474713f8c982d05c9b17aafb (2.x) |
| **Difficulty** | hard |

**Dependency chain:**
```
urllib3 → requests → boto3 → awscli (3-hop transitive chain)
urllib3 → requests → docker-py → docker-compose
urllib3 → pip (vendored urllib3)
urllib3 → selenium → test infrastructure
```

**Task potential:** HIGH. Demonstrates a 3-hop transitive vulnerability. Agent must understand that `requests` vendors/pins `urllib3` and trace through the indirection. Two separate fix branches (1.x/2.x) add version range complexity.

**Repos for sandbox:** `urllib3/urllib3`, `psf/requests`, `boto/boto3`

---

## Candidate 10: certifi TrustCor Root Certificate Removal (Python)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2022-23491 |
| **GHSA** | GHSA-43fp-rhv2-5gv8 |
| **Severity** | MODERATE |
| **Affected package** | `certifi` (PyPI) |
| **Affected versions** | >= 2017.11.05, < 2022.12.07 |
| **Fix** | certifi/python-certifi@9e9e840925d7b8e76c76fdac1fab7e6e88c1c3b8 |
| **Difficulty** | medium |

**Dependency chain:**
```
certifi → requests → boto3 → awscli
certifi → httpx → FastAPI applications
certifi → elasticsearch-py → ELK stacks
```

**Task potential:** MEDIUM. Not a code fix but a certificate store update. Agent must understand trust chain implications. Interesting because the "fix" is removing a root CA, not patching code. Good for testing agent judgment on non-code vulnerabilities.

**Repos for sandbox:** `certifi/python-certifi`, `psf/requests`, `encode/httpx`

---

## Candidate 11: Log4Shell — Apache Log4j RCE (Java)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2021-44228 |
| **GHSA** | GHSA-jfh8-c2jp-5v3q |
| **Severity** | CRITICAL |
| **CWE** | CWE-917, CWE-502 |
| **Affected package** | `org.apache.logging.log4j:log4j-core` (Maven) |
| **Affected versions** | 2.0-beta9 - 2.14.1 (fixed 2.15.0, fully 2.16.0) |
| **Fix** | apache/logging-log4j2#608 |
| **Difficulty** | expert |

**Dependency chain:**
```
log4j-core → spring-boot-starter-log4j2 → Spring Boot apps
log4j-core → Elasticsearch → ELK stack
log4j-core → Apache Kafka → streaming infrastructure
log4j-core → Apache Solr → search infrastructure
log4j-core → Apache Flink → data processing
```

**Task potential:** CRITICAL. The canonical enterprise CVE. Massive transitive blast radius. Agent must trace through shaded/relocated JARs, Spring Boot starters, OSGi bundles, and the pax-logging mirror. Multiple fix versions (2.15.0 incomplete, 2.16.0 full, backports 2.3.1 and 2.12.2).

**Repos for sandbox:** `apache/logging-log4j2`, `spring-projects/spring-boot`, `apache/kafka`

---

## Candidate 12: jackson-databind Deep Nesting DoS (Java)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2020-36518 |
| **GHSA** | GHSA-57j2-w4cx-62h2 |
| **Severity** | HIGH |
| **CWE** | CWE-787 (Out-of-bounds Write / Stack Overflow) |
| **Affected package** | `com.fasterxml.jackson.core:jackson-databind` (Maven) |
| **Affected versions** | <= 2.12.6.0 (fix 2.12.6.1), 2.13.0-2.13.2 (fix 2.13.2.1) |
| **Fix** | FasterXML/jackson-databind@3cc52f8, @8238ab4, @b358792 |
| **Difficulty** | hard |

**Dependency chain:**
```
jackson-databind → spring-boot-starter-web → every Spring Boot REST API
jackson-databind → Apache Spark → data pipelines
jackson-databind → Elasticsearch → search
jackson-databind → Dropwizard → microservices
```

**Task potential:** HIGH. jackson-databind is the default JSON library in Spring Boot. Agent must navigate BOM (bill of materials) inheritance in Maven/Gradle to determine resolved versions.

**Repos for sandbox:** `FasterXML/jackson-databind`, `spring-projects/spring-boot`, `dropwizard/dropwizard`

---

## Candidate 13: jackson-databind UNWRAP_SINGLE_VALUE_ARRAYS DoS (Java)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2022-42003 |
| **GHSA** | GHSA-jjjh-jjxp-wpff |
| **Severity** | HIGH |
| **CWE** | CWE-400, CWE-502 |
| **Affected package** | `com.fasterxml.jackson.core:jackson-databind` (Maven) |
| **Affected versions** | 2.4.0-rc1 - 2.12.7.0 (fix 2.12.7.1), 2.13.0 - 2.13.4.1 (fix 2.13.4.2), fixed in 2.14.0 |
| **Fix** | FasterXML/jackson-databind@cd090979, @d78d00ee |
| **Difficulty** | hard |

**Dependency chain:** Same as Candidate 12 (Spring Boot, Spark, Elasticsearch, Dropwizard)

**Task potential:** HIGH. Can be paired with Candidate 12 for "multiple jackson-databind CVE remediation" task. Agent must understand that 2.13.4.1 exists but causes Gradle build failures due to a broken jackson-bom reference — real-world complication.

**Repos for sandbox:** `FasterXML/jackson-databind`, `spring-projects/spring-boot`, `apache/spark`

---

## Candidate 14: jackson-databind Cyclic Dependencies DoS — Disputed (Java)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2023-35116 |
| **Severity** | DISPUTED |
| **Affected package** | `com.fasterxml.jackson.core:jackson-databind` (Maven) |
| **Affected versions** | < 2.16.0 |
| **Fix** | FasterXML/jackson-databind@74621b01 |
| **Difficulty** | expert |

**Dependency chain:** Same as Candidates 12/13 (Spring Boot ecosystem)

**Task potential:** MEDIUM but unique. This CVE is disputed by the vendor — requires constructing cyclic data structures to exploit. Agent must assess whether the CVE is actually exploitable in the target codebase. Good for testing agent judgment: should the agent recommend upgrading for a disputed CVE?

**Repos for sandbox:** `FasterXML/jackson-databind`, `spring-projects/spring-boot`

---

## Candidate 15: OpenSSL BN_mod_sqrt Infinite Loop (System/cross-ecosystem)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2022-0778 |
| **GHSA** | GHSA-x3mh-jvjw-3xwx |
| **Severity** | HIGH |
| **Affected package** | OpenSSL (system library) |
| **Affected versions** | 1.0.2-1.0.2zc, 1.1.1-1.1.1m, 3.0.0-3.0.1 |
| **Fix** | OpenSSL 1.0.2zd, 1.1.1n, 3.0.2 |
| **Difficulty** | expert |

**Dependency chain:**
```
OpenSSL → curl → git → every CI/CD pipeline
OpenSSL → Python (ssl module) → pip → requests → boto3
OpenSSL → Node.js (crypto) → npm → every JS project
OpenSSL → nginx/Apache → every web server
OpenSSL → Kubernetes (via Go's crypto/tls when CGO_ENABLED=1)
```

**Task potential:** CRITICAL for multi-repo and cross-ecosystem. System library affects every ecosystem. Agent must understand static linking (Go) vs dynamic linking (Python, Node) and determine actual exposure per language. Excellent expert-level cross-ecosystem traversal task.

**Repos for sandbox:** `curl/curl`, `git/git`, `kubernetes/kubernetes`

---

## Recommended Task Groupings

These groupings show how candidates can be combined into benchmark tasks aligned with the PRD checkpoint structure.

### Medium difficulty (30% target — 3 tasks)

| Task ID | Candidates | Repos | Focus |
|---------|-----------|-------|-------|
| dep-graph-001 | #1 (lodash) | webpack, jest | JS transitive tree, well-documented CVE |
| dep-graph-002 | #2 (axios) | Grafana, Druid | JS HTTP client chain |
| dep-graph-003 | #7 (x/text) + #10 (certifi) | Go/Python calibration | Narrower blast radius, function-level analysis |

### Hard difficulty (50% target — 5-6 tasks)

| Task ID | Candidates | Repos | Focus |
|---------|-----------|-------|-------|
| dep-graph-004 | #4 (x/net Rapid Reset) | k8s, etcd, grpc-go | Go CNCF module graph |
| dep-graph-005 | #5 (x/net HPACK) | prometheus, consul, vault | Go multi-CVE remediation |
| dep-graph-006 | #6 (protobuf Go) | grpc-go, istio | Protobuf-specific code path analysis |
| dep-graph-007 | #3 (protobufjs) | grpc-node, k8s-client-js | Cross-language protobuf chain |
| dep-graph-008 | #8 (requests) | boto3, awscli | Python AWS toolchain |
| dep-graph-009 | #9 (urllib3) + #12 (jackson) | 3-hop chains | Multi-ecosystem version range |

### Expert difficulty (20% target — 2 tasks)

| Task ID | Candidates | Repos | Focus |
|---------|-----------|-------|-------|
| dep-graph-010 | #11 (Log4Shell) | log4j, spring-boot, kafka | Shaded JARs, BOM inheritance, multiple fix versions |
| dep-graph-011 | #15 (OpenSSL) | curl, git, k8s | Cross-ecosystem system lib, static vs dynamic linking |
| dep-graph-012 | #14 (disputed jackson) + #13 | spring-boot, spark | Agent judgment on disputed CVEs |

---

## Ecosystem Coverage

| Ecosystem | Candidates | Count |
|-----------|-----------|-------|
| JavaScript/npm | #1, #2, #3 | 3 |
| Go | #4, #5, #6, #7 | 4 |
| Python/PyPI | #8, #9, #10 | 3 |
| Java/Maven | #11, #12, #13, #14 | 4 |
| System/cross-ecosystem | #15 | 1 |

## Difficulty Distribution

| Difficulty | Candidates | Count | Percentage |
|------------|-----------|-------|------------|
| Medium | #1, #2, #7, #10 | 4 | 27% |
| Hard | #3, #4, #5, #6, #8, #9, #12, #13 | 8 | 53% |
| Expert | #11, #14, #15 | 3 | 20% |

## Next Steps (P2.3)

For each candidate selected for task authoring:
1. Clone repos at specific tagged versions where the CVE is present
2. Parse manifest/lock files to extract exact dependency paths
3. Build ground truth: `{package, version_range, dependency_path}` tuples
4. Validate paths against OSV known-affected lists
5. Write checkpoint verifiers per PRD Section 3
