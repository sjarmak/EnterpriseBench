# CVE Blast Radius Analysis: axios ReDoS

## Context

A ReDoS vulnerability (CVE-2021-3749) was found in the axios HTTP client library. Our frontend teams use axios extensively — it's embedded in Grafana plugins and the Druid web console.

I need to know the full blast radius across our frontend infrastructure before we can prioritize patching.

## What I Need

1. **CVE Identification**: Confirm the CVE, affected package, and version range.

2. **Direct Dependents**: Which workspace repos depend on axios? Show the manifest files.

3. **Transitive Paths**: Trace how axios gets pulled in. Grafana uses a plugin SDK that may vendor axios. Druid has a web-console subfolder with its own package.json.

4. **Version Analysis**: Check resolved versions — are we actually running a vulnerable version, or have we already patched?

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
