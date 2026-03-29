# CVE Blast Radius Analysis: OpenSSL BN_mod_sqrt Infinite Loop

## Context

CVE-2022-0778 is a denial-of-service in OpenSSL's BN_mod_sqrt function. A crafted certificate with an invalid explicit curve can trigger an infinite loop in certificate verification. This is a system-level vulnerability that affects every language runtime differently.

This is the hardest kind of dependency analysis — it crosses ecosystem boundaries. OpenSSL is a C library that Python, Node.js, Ruby, and even Go (sometimes) link against. I need to understand the actual exposure across our entire stack.

## What I Need

1. **CVE Identification**: CVE, all three affected version branches (1.0.2, 1.1.1, 3.0.x).

2. **Cross-Ecosystem Consumers**:
   - **C/C++**: curl uses OpenSSL for TLS. git uses curl for HTTP transport. This gives us: OpenSSL -> curl -> git -> every CI/CD pipeline.
   - **Python**: The ssl module in CPython links against system OpenSSL. This means: OpenSSL -> Python ssl -> pip -> requests -> boto3.
   - **Go**: Kubernetes uses crypto/tls. By default Go uses pure-Go crypto, but with CGO_ENABLED=1 it can use system OpenSSL. Determine which applies.

3. **Linking Strategy Analysis**: This is key. For each consumer, determine:
   - **Dynamic linking**: Uses whatever OpenSSL is on the system (affected if system OpenSSL is vulnerable)
   - **Static linking**: Bundles a specific OpenSSL version (check which version)
   - **Pure implementation**: Doesn't use OpenSSL at all (e.g., Go's pure-Go TLS)

4. **Actual Exposure**: Combine linking strategy with OpenSSL version to classify each repo.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
