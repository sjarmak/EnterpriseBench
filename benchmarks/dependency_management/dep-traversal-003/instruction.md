# CVE Blast Radius Analysis: golang.org/x/text Accept-Language DoS

## Context

CVE-2022-32149 is a denial-of-service vulnerability in golang.org/x/text. The issue is specifically in the `language.ParseAcceptLanguage` function — it can be exploited with crafted Accept-Language headers to consume excessive CPU.

The tricky part: many Go projects import `golang.org/x/text` but never call the vulnerable function. I need you to distinguish between repos that are actually exposed and those that just happen to have it in their go.mod.

## What I Need

1. **CVE Identification**: CVE ID, affected module, version range.

2. **Module Graph**: Which workspace repos list golang.org/x/text in their go.mod?

3. **Function-Level Analysis**: This is the critical step. Grep for actual usage of `language.ParseAcceptLanguage` or the `language` sub-package. A repo that only uses `golang.org/x/text/transform` is NOT affected.

4. **Version + Usage Classification**: Combine version analysis with usage analysis to classify each consumer.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
