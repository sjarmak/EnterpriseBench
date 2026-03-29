# CVE Candidates for Dependency Graph Traversal Tasks

Research date: 2026-03-28
Source: osv.dev API, GitHub Security Advisories

## Summary

15 CVE candidates across 4 ecosystems (JS/npm, Go, Python, Java/Maven) with verified dependency chain blast radius. Each candidate has known transitive impact on 2+ downstream repos, making them suitable for EnterpriseBench dependency_management task creation.

---

## JavaScript / npm Ecosystem

### 1. CVE-2021-23337 -- lodash Command Injection
- **GHSA:** GHSA-35jh-r3h4-6jhm
- **Severity:** HIGH (CWE-77 Command Injection, CWE-94 Code Injection)
- **Affected package:** `lodash` (npm), `lodash-es` (npm)
- **Affected versions:** < 4.17.21
- **Fix commit:** lodash/lodash@3469357cff396a26c363f8c1b5a91dde28ba4b1c
- **Dependency chain:**
  - lodash -> webpack (devDependency, used in build tooling)
  - lodash -> babel (via @babel/traverse internal usage)
  - lodash -> jest (via jest-haste-map, jest-config)
  - lodash -> create-react-app -> thousands of downstream apps
- **Task potential:** HIGH -- lodash was depended on by ~73% of npm. Forces traversal across build tooling, test frameworks, and application code. Agent must identify which lodash sub-packages (lodash.template, lodash.merge, etc.) are also affected.

### 2. CVE-2021-3749 -- axios ReDoS
- **GHSA:** GHSA-cph5-m8f7-6c5x
- **Severity:** HIGH (CWE-1333 Inefficient Regex, CWE-400 Resource Consumption)
- **Affected package:** `axios` (npm)
- **Affected versions:** < 0.21.2
- **Fix commit:** axios/axios@5b457116e31db0e88fede6c428e969e87f290929
- **Dependency chain:**
  - axios -> vue-cli / create-react-app (HTTP client in scaffolded projects)
  - axios -> Apache Druid (frontend)
  - axios -> Grafana frontend plugins
- **Task potential:** HIGH -- axios is the most popular HTTP client in JS. Agent must trace through both direct and transitive dependants across frontend/backend.

### 3. CVE-2022-25878 -- protobuf.js Prototype Pollution
- **GHSA:** GHSA-g954-5hwp-pp24
- **Severity:** HIGH (CWE-1321 Prototype Pollution)
- **Affected package:** `protobufjs` (npm)
- **Affected versions:** 6.10.0 - 6.10.2, 6.11.0 - 6.11.2
- **Fix:** 6.10.3 / 6.11.3; PR protobufjs/protobuf.js#1731, #1735
- **Fix commit:** protobufjs/protobuf.js@b5f1391dff5515894830a6570e6d73f5511b2e8f
- **Dependency chain:**
  - protobufjs -> @grpc/grpc-js -> CNCF ecosystem (Kubernetes client-node, Envoy xDS)
  - protobufjs -> firebase-admin -> Google Cloud Functions
  - protobufjs -> google-cloud libraries (@google-cloud/pubsub, @google-cloud/storage)
- **Task potential:** HIGH -- bridges JS and Go/CNCF ecosystems. Multi-language dependency chain traversal.

---

## Go Ecosystem

### 4. CVE-2023-39325 -- golang.org/x/net HTTP/2 Rapid Reset
- **GHSA:** GHSA-4374-p667-p6c8
- **Go Advisory:** GO-2023-2102
- **Severity:** HIGH (CWE-400, CWE-770)
- **Affected package:** `golang.org/x/net` (Go), `stdlib net/http` (Go)
- **Affected versions:** golang.org/x/net < 0.17.0; Go stdlib < 1.20.10, < 1.21.3
- **Fix:** go.dev/cl/514907 (x/net), go.dev/cl/514905 (stdlib)
- **Dependency chain:**
  - golang.org/x/net -> kubernetes/kubernetes (API server, kubelet, kubectl)
  - golang.org/x/net -> etcd -> CoreDNS -> every k8s cluster
  - golang.org/x/net -> grpc-go -> virtually all Go gRPC services
  - golang.org/x/net -> containerd -> Docker -> CI/CD pipelines
- **Task potential:** CRITICAL -- related to CVE-2023-44487 (HTTP/2 Rapid Reset, industry-wide). Massive RHSA blast radius (100+ Red Hat advisories). Agent must traverse Go module graph across CNCF projects.

### 5. CVE-2022-41723 -- golang.org/x/net HPACK DoS
- **Go Advisory:** GO-2023-1571
- **GHSA:** GHSA-vvpx-j8f3-3w6h
- **Severity:** HIGH
- **Affected package:** `golang.org/x/net` (Go), `stdlib net/http` (Go)
- **Affected versions:** golang.org/x/net < 0.7.0; Go < 1.19.6 / < 1.20.1
- **Fix:** go.dev/cl/468135, go.dev/cl/468295
- **Dependency chain:**
  - Same as CVE-2023-39325 (kubernetes, etcd, grpc-go, containerd)
  - Also: prometheus/prometheus, hashicorp/consul, hashicorp/vault
- **Task potential:** HIGH -- same deep Go module graph. Pair with CVE-2023-39325 for a "multiple CVE remediation" chained task.

### 6. CVE-2024-24786 -- google.golang.org/protobuf JSON Unmarshal Infinite Loop
- **Go Advisory:** GO-2024-2611
- **GHSA:** GHSA-8r3f-844c-mc37
- **Severity:** HIGH
- **Affected package:** `google.golang.org/protobuf` (Go)
- **Affected versions:** < 1.33.0
- **Fix:** go.dev/cl/569356
- **Dependency chain:**
  - google.golang.org/protobuf -> grpc-go -> kubernetes, etcd, Istio
  - google.golang.org/protobuf -> Prometheus -> monitoring stacks
  - google.golang.org/protobuf -> Envoy xDS -> service mesh
- **Task potential:** HIGH -- protobuf is foundational to the entire CNCF stack. Agent must identify which services unmarshal Any types (the vulnerable path).

### 7. CVE-2022-32149 -- golang.org/x/text Accept-Language DoS
- **Go Advisory:** GO-2022-1059
- **GHSA:** GHSA-69ch-w2m2-3vjp
- **Severity:** HIGH
- **Affected package:** `golang.org/x/text` (Go)
- **Affected versions:** < 0.3.8
- **Fix:** go.dev/cl/442235
- **Dependency chain:**
  - golang.org/x/text -> kubernetes/kubernetes (i18n, API responses)
  - golang.org/x/text -> go-chi/chi, gorilla/mux (middleware stacks)
  - golang.org/x/text -> Hugo (static site generator)
- **Task potential:** MEDIUM -- narrower blast radius (only ParseAcceptLanguage callers), but forces agent to determine which dependants actually call the vulnerable function vs. just importing the module.

---

## Python / PyPI Ecosystem

### 8. CVE-2023-32681 -- requests Proxy-Authorization Header Leak
- **GHSA:** GHSA-j8r2-6x86-q33q
- **Severity:** MODERATE (CWE-200 Information Exposure)
- **Affected package:** `requests` (PyPI)
- **Affected versions:** 2.3.0 - 2.30.0 (fixed in 2.31.0)
- **Fix commit:** psf/requests@74ea7cf7a6a27a4eeb2ae24e162bcc942a6706d5
- **Dependency chain:**
  - requests -> boto3 -> awscli -> AWS infrastructure automation
  - requests -> docker-py -> docker-compose -> CI/CD
  - requests -> ansible -> configuration management
  - requests -> pip (vendored) -> every Python project
- **Task potential:** HIGH -- requests is in virtually every Python project. Agent must trace through boto3->botocore->awscli chain and identify proxy usage patterns.

### 9. CVE-2023-43804 -- urllib3 Cookie Header Leak on Redirect
- **PYSEC:** PYSEC-2023-192
- **GHSA:** GHSA-v845-jxx5-vc9f
- **Severity:** HIGH
- **Affected package:** `urllib3` (PyPI)
- **Affected versions:** < 1.26.17 (1.x), 2.0.0 - 2.0.5 (2.x)
- **Fix commits:** urllib3@644124ecd0b6e417c527191f866daa05a5a2056d, urllib3@01220354d389cd05474713f8c982d05c9b17aafb
- **Dependency chain:**
  - urllib3 -> requests -> boto3 -> awscli (3-hop transitive chain)
  - urllib3 -> requests -> docker-py -> docker-compose
  - urllib3 -> pip (vendored urllib3)
  - urllib3 -> selenium -> test infrastructure
- **Task potential:** HIGH -- demonstrates 3-hop transitive vulnerability. Agent must understand that requests vendors/pins urllib3 and trace through.

### 10. CVE-2022-23491 -- certifi TrustCor Root Certificate Removal
- **GHSA:** GHSA-43fp-rhv2-5gv8
- **Severity:** MODERATE (CWE-345 Insufficient Verification)
- **Affected package:** `certifi` (PyPI)
- **Affected versions:** 2017.11.05 - 2022.12.06 (fixed in 2022.12.07)
- **Fix commit:** certifi/python-certifi@9e9e840925d7b8e76c76fdac1fab7e6e88c1c3b8
- **Dependency chain:**
  - certifi -> requests -> boto3 -> awscli
  - certifi -> httpx -> FastAPI applications
  - certifi -> elasticsearch-py -> ELK stacks
- **Task potential:** MEDIUM -- interesting because it's not a code fix but a certificate store update. Agent must understand the trust chain implications.

---

## Java / Maven Ecosystem

### 11. CVE-2021-44228 -- Log4Shell (Apache Log4j RCE)
- **GHSA:** GHSA-jfh8-c2jp-5v3q
- **Severity:** CRITICAL (CWE-917 Expression Language Injection, CWE-502 Deserialization)
- **Affected package:** `org.apache.logging.log4j:log4j-core` (Maven)
- **Affected versions:** 2.0-beta9 - 2.14.1 (fixed in 2.15.0, fully in 2.16.0); backports: 2.3.1, 2.12.2
- **Fix:** apache/logging-log4j2#608
- **Dependency chain:**
  - log4j-core -> Spring Boot (via spring-boot-starter-log4j2)
  - log4j-core -> Elasticsearch -> ELK stack
  - log4j-core -> Apache Kafka -> streaming infrastructure
  - log4j-core -> Apache Solr -> search infrastructure
  - log4j-core -> Apache Flink -> data processing
  - Also affected: pax-logging-log4j2 (OSGi), com.guicedee.services:log4j-core
- **Task potential:** CRITICAL -- the canonical enterprise CVE. Massive transitive blast radius. Agent must trace through shaded/relocated JARs, Spring Boot starters, and OSGi bundles.

### 12. CVE-2020-36518 -- jackson-databind Deep Nesting DoS
- **GHSA:** GHSA-57j2-w4cx-62h2
- **Severity:** HIGH (CWE-787 Out-of-bounds Write / Stack Overflow)
- **Affected package:** `com.fasterxml.jackson.core:jackson-databind` (Maven)
- **Affected versions:** <= 2.12.6.0 (fixed 2.12.6.1); 2.13.0 - 2.13.2 (fixed 2.13.2.1)
- **Fix commits:** Multiple -- FasterXML/jackson-databind@3cc52f8, @8238ab4, @b358792
- **Dependency chain:**
  - jackson-databind -> spring-boot-starter-web -> every Spring Boot REST API
  - jackson-databind -> Apache Spark -> data pipelines
  - jackson-databind -> Elasticsearch -> search
  - jackson-databind -> Dropwizard -> microservices
- **Task potential:** HIGH -- jackson-databind is the default JSON library in Spring Boot. Agent must navigate BOM (bill of materials) inheritance in Maven/Gradle.

### 13. CVE-2022-42003 -- jackson-databind UNWRAP_SINGLE_VALUE_ARRAYS DoS
- **GHSA:** GHSA-jjjh-jjxp-wpff
- **Severity:** HIGH (CWE-400 Resource Consumption, CWE-502)
- **Affected package:** `com.fasterxml.jackson.core:jackson-databind` (Maven)
- **Affected versions:** 2.4.0-rc1 - 2.12.7.0 (fixed 2.12.7.1); 2.13.0 - 2.13.4.1 (fixed 2.13.4.2); fixed in 2.14.0
- **Fix commits:** FasterXML/jackson-databind@cd090979, @d78d00ee
- **Dependency chain:** Same as CVE-2020-36518 (Spring Boot, Spark, Elasticsearch, Dropwizard)
- **Task potential:** HIGH -- pair with CVE-2020-36518 for "multiple jackson-databind CVE remediation" task. Agent must understand that 2.13.4.1 exists but causes gradle build failures (broken jackson-bom reference).

### 14. CVE-2023-35116 -- jackson-databind Cyclic Dependencies DoS
- **Severity:** DISPUTED (vendor considers invalid; requires constructing cyclic data structures)
- **Affected package:** `com.fasterxml.jackson.core:jackson-databind` (Maven)
- **Affected versions:** < 2.16.0
- **Fix commit:** FasterXML/jackson-databind@74621b01e69396160cc48b023aa0e85f38964c0f
- **Dependency chain:** Same as above (Spring Boot ecosystem)
- **Task potential:** MEDIUM -- interesting because it's disputed. Agent must assess whether the CVE is actually exploitable in the target codebase (requires attacker-controlled object graph construction). Good for testing agent judgment.

---

## System / C Libraries (Cross-Ecosystem)

### 15. CVE-2022-0778 -- OpenSSL BN_mod_sqrt Infinite Loop
- **GHSA:** GHSA-x3mh-jvjw-3xwx
- **Severity:** HIGH
- **Affected package:** OpenSSL (system library)
- **Affected versions:** 1.0.2 - 1.0.2zc, 1.1.1 - 1.1.1m, 3.0.0 - 3.0.1
- **Fixed in:** 1.0.2zd, 1.1.1n, 3.0.2
- **Dependency chain:**
  - OpenSSL -> curl -> git -> every CI/CD pipeline
  - OpenSSL -> Python (ssl module) -> pip -> requests -> boto3
  - OpenSSL -> Node.js (crypto) -> npm -> every JS project
  - OpenSSL -> nginx/Apache -> every web server
  - OpenSSL -> Kubernetes (via Go's crypto/tls when CGO_ENABLED=1)
- **Task potential:** CRITICAL for multi-repo -- system library affects every ecosystem. Agent must understand the difference between statically linked (Go) and dynamically linked (Python, Node) OpenSSL dependencies. Excellent for cross-ecosystem traversal task.

---

## Recommended Task Groupings

### Tier 1: Multi-Repo Dependency Chain Tasks (30% of tasks)
| Task | CVEs | Repos | Difficulty |
|------|------|-------|------------|
| CNCF Go module audit | CVE-2023-39325 + CVE-2024-24786 | kubernetes, etcd, grpc-go | Hard |
| Python AWS toolchain audit | CVE-2023-32681 + CVE-2023-43804 | requests, boto3, awscli | Medium |
| Spring Boot jackson remediation | CVE-2020-36518 + CVE-2022-42003 | jackson-databind, spring-boot, spring-framework | Medium |

### Tier 2: Single-Repo Deep Traversal (25% of tasks)
| Task | CVE | Repo | Difficulty |
|------|-----|------|------------|
| Log4Shell impact assessment | CVE-2021-44228 | Large Java monorepo | Hard |
| lodash template injection audit | CVE-2021-23337 | Large JS monorepo | Medium |

### Tier 3: Cross-Ecosystem Tasks (10% of tasks)
| Task | CVEs | Ecosystems | Difficulty |
|------|------|------------|------------|
| OpenSSL blast radius | CVE-2022-0778 | Go, Python, Node.js, system | Expert |
| protobuf cross-language audit | CVE-2022-25878 + CVE-2024-24786 | npm (protobufjs) + Go (google.golang.org/protobuf) | Hard |

### Tier 4: Calibration / Single-Repo (15% of tasks)
| Task | CVE | Purpose |
|------|-----|---------|
| certifi update | CVE-2022-23491 | Easy calibration |
| axios ReDoS | CVE-2021-3749 | Easy calibration |
| golang.org/x/text DoS | CVE-2022-32149 | Medium calibration |
