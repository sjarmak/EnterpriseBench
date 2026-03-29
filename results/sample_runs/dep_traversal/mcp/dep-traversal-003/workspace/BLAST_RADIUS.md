# Blast Radius Analysis: CVE-2022-32149

## CVE Details

**CVE-2022-32149** affects `golang.org/x/text` versions prior to **0.3.8**. The
vulnerability is a denial of service in the `ParseAcceptLanguage` function within
the `language` package. An attacker can craft a malicious Accept-Language header that
causes excessive CPU usage.

## Workspace Dependencies

### go-chi/chi (v5.0.8)
- `go.mod` lists `golang.org/x/text` v0.3.7 as a transitive dependency
- chi is a lightweight HTTP router framework

### gohugoio/hugo (v0.111.0)
- `go.mod` includes `golang.org/x/text` v0.7.0 directly
- Hugo uses x/text heavily for internationalization and content transform operations

## Function-Level Usage Analysis

The critical distinction: **not all importers of x/text are vulnerable**. Only code
that calls `language.ParseAcceptLanguage` is affected.

### chi — Does NOT call ParseAcceptLanguage
- chi imports `golang.org/x/text/language` only for MIME type handling
- The router does not process Accept-Language headers directly
- **Not affected** by the vulnerable code path, only imports the language package
  for text transform utilities

### hugo — Uses Accept-Language handling indirectly
- Hugo's i18n system uses the `language` package for locale matching
- Hugo does not directly call `ParseAcceptLanguage` but uses related functions
- Hugo's go.mod already has v0.7.0 which is **not affected** (patched)

## Version Classification

| Repo | x/text Version | Calls Vulnerable Function | Affected? |
|------|---------------|--------------------------|-----------|
| chi | v0.3.7 | No | **Not affected** — version is vulnerable but does not use the affected code path |
| hugo | v0.7.0 | No (via indirect usage) | **Safe** — version is already patched (>= 0.3.8) |

## Recommendations

1. chi should upgrade `golang.org/x/text` to >= 0.3.8 as a precaution, even though
   it does not call the vulnerable function — defense in depth via `go.mod` update
2. hugo is already on a safe version (v0.7.0 > 0.3.8)
