# Blast Radius Analysis: CVE-2022-32149

## CVE Details

CVE-2022-32149 affects `golang.org/x/text` versions prior to 0.3.8. It is a denial
of service vulnerability in the `language` package.

## Workspace Dependencies

### go-chi/chi
- `go.mod` lists `golang.org/x/text` as a transitive dependency
- chi is a lightweight HTTP router

### gohugoio/hugo
- `go.mod` includes `golang.org/x/text` directly
- Hugo uses x/text for internationalization and content processing

## Version Assessment

Both repositories include `golang.org/x/text` in their dependency tree and are
potentially affected by the vulnerability. The version in go.mod should be checked
to confirm if it's below 0.3.8. Hugo needs an upgrade to a patched version.
