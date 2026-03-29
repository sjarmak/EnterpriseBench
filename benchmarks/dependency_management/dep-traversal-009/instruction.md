# CVE Blast Radius Analysis: urllib3 Cookie Header Leak on Redirect

## Context

CVE-2023-43804 is a cookie header leak in urllib3. When following cross-origin redirects, the Cookie header is not stripped, potentially leaking session cookies to unintended hosts. This is a 3-hop problem for us because urllib3 is the HTTP transport underneath requests, which is underneath all of our AWS tooling.

The version situation is complex: there are two affected branches (1.x and 2.x), and requests historically pins to urllib3 1.x while newer releases are moving to 2.x.

## What I Need

1. **CVE Identification**: CVE, package, and both affected version ranges (1.x and 2.x).

2. **Direct Dependents**: Which repos directly depend on urllib3? The main one is requests.

3. **3-Hop Chain**: Map urllib3 -> requests -> botocore -> boto3. Investigate how requests manages the urllib3 dependency — does it vendor it, pin it, or use a range?

4. **Version Branch Analysis**: Determine which urllib3 branch (1.x or 2.x) each consumer uses. requests 2.28.x pins urllib3 1.x, which has different fix versions than 2.x.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
