# CVE Blast Radius Analysis: HPACK DoS in golang.org/x/net

## Context

CVE-2022-41723 is a denial-of-service vulnerability in the HPACK header compression implementation in golang.org/x/net. A malicious HTTP/2 client can craft headers that cause the server to consume excessive memory.

Our observability and infrastructure stack is all Go-based: Prometheus for monitoring, Consul for service discovery, Vault for secrets management. All three likely import golang.org/x/net. I need to know which are actually exposed.

## What I Need

1. **CVE Identification**: CVE, module, version range.

2. **Direct Dependents**: Check go.mod in each workspace repo.

3. **Dependency Paths**: Map both direct imports of x/net and transitive imports through intermediary modules. Some repos may use x/net only through grpc-go or other HTTP frameworks.

4. **Version Analysis**: Check go.sum for resolved versions. HashiCorp projects and Prometheus may be on different update cadences — some may already be patched.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
