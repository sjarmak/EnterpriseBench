# CVE Blast Radius Analysis: requests Proxy-Authorization Header Leak

## Context

CVE-2023-32681 affects the `requests` Python HTTP library. When making requests through an HTTP proxy, the Proxy-Authorization header is incorrectly forwarded to the destination server on redirects. This is a credential leak vulnerability.

Our AWS infrastructure automation is built on boto3 and awscli, both of which use requests via botocore for HTTP communication. If our AWS tooling is running through a proxy (which it is in our corporate environment), this could leak proxy credentials.

## What I Need

1. **CVE Identification**: CVE, package, version range.

2. **Direct Dependents**: Which repos depend on requests? Check setup.py, setup.cfg, and requirements.txt.

3. **Transitive Chain**: This is a 3-hop chain: requests -> botocore -> boto3 -> awscli. Map the full path. Note that botocore vendors or pins requests — check how the dependency is declared.

4. **Version Analysis**: What version of requests does each consumer pin? Are they in the vulnerable range (>= 2.3.0, < 2.31.0)?

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
