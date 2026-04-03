# Plan: Multi-Repo Deps + Refactor Tasks

## 6 Tasks to Create

### Dependency Graph Tasks (benchmarks/dependency_management/)

1. **dep-traversal-tri-jackson-001** (Java)
   - Repos: FasterXML/jackson-databind, spring-projects/spring-framework, spring-projects/spring-boot
   - Scenario: Trace how Jackson's ObjectMapper configuration flows through Spring Framework's MappingJackson2HttpMessageConverter into Spring Boot's autoconfiguration (JacksonAutoConfiguration)
   - Output: DEPENDENCY_TRACE.md
   - Checkpoints: identify_packages (0.25), trace_integration_path (0.40), autoconfiguration_analysis (0.35)

2. **dep-traversal-tri-openssl-001** (C)
   - Repos: openssl/openssl, curl/curl, git/git
   - Scenario: Trace TLS certificate verification from git's HTTP transport through curl/libcurl to OpenSSL's X509 verification
   - Output: DEPENDENCY_TRACE.md
   - Checkpoints: identify_tls_entry (0.25), trace_curl_integration (0.40), openssl_verification_path (0.35)

3. **dep-traversal-tri-boto3-001** (Python)
   - Repos: boto/boto3, boto/botocore, boto/s3transfer
   - Scenario: Trace S3 multipart upload from boto3's high-level API through s3transfer's transfer manager to botocore's low-level API calls
   - Output: DEPENDENCY_TRACE.md
   - Checkpoints: identify_api_surface (0.25), trace_transfer_path (0.40), botocore_integration (0.35)

### Refactor Orchestration Tasks (benchmarks/technical_debt/)

4. **refactor-orchestration-tri-spring-001** (Java)
   - Repos: spring-projects/spring-framework, spring-projects/spring-boot, spring-projects/spring-kafka
   - Scenario: Plan refactoring Spring's KafkaTemplate integration across Framework messaging/Boot autoconfiguration/Kafka client
   - Output: REFACTOR_PLAN.md
   - Checkpoints: identify_repos (0.25), topological_order (0.45), parallelism (0.30)

5. **refactor-orchestration-tri-tokio-001** (Rust)
   - Repos: tokio-rs/tokio, hyperium/hyper, tokio-rs/axum
   - Scenario: Plan refactoring async HTTP handler chain when tokio runtime changes propagate through hyper to axum
   - Output: REFACTOR_PLAN.md
   - Checkpoints: identify_repos (0.25), topological_order (0.45), parallelism (0.30)

6. **refactor-orchestration-tri-babel-001** (JavaScript)
   - Repos: babel/babel, webpack/webpack, vercel/next.js
   - Scenario: Plan refactoring JS compilation pipeline when Babel parser changes propagate through webpack loaders to Next.js build
   - Output: REFACTOR_PLAN.md
   - Checkpoints: identify_repos (0.25), topological_order (0.45), parallelism (0.30)

## File Structure Per Task

- task.toml
- ground_truth.json
- instruction.md
- checks/ (2-3 scripts)

## Ecosystems Covered

- Java (jackson, spring)
- C (openssl, curl, git)
- Python (boto3, botocore, s3transfer)
- Rust (tokio, hyper, axum)
- JavaScript (babel, webpack, next.js)
