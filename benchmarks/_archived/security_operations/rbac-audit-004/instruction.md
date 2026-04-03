# Authentication Header Audit: Keycloak Bearer Token Validation

## Context

Our security scanner flagged CVE-2026-0707 in our Keycloak deployment. The
vulnerability is in how Keycloak parses the Authorization header when
extracting Bearer tokens. The current implementation does not comply with
RFC 6750, which defines the Bearer token format:

```
b64token    = 1*( ALPHA / DIGIT / "-" / "." / "_" / "~" / "+" / "/" ) *"="
credentials = "Bearer" 1*SP b64token
```

We need a security audit to understand the exact nature of the vulnerability
and what attack vectors it opens.

## What I Need

1. **Token Extraction Logic**: Find where Keycloak extracts Bearer tokens from
   the Authorization header. The key class is `AppAuthManager.java` in the
   services module.

2. **RFC 6750 Compliance Check**: Evaluate the token extraction against the RFC:
   - Case sensitivity of the "Bearer" scheme
   - Whitespace handling between "Bearer" and the token
   - Token character set validation
   - Handling of trailing/leading whitespace

3. **Attack Vectors**: What could an attacker do with malformed Authorization
   headers? Consider:
   - Whitespace smuggling (non-ASCII spaces, tabs)
   - Token value injection (characters outside b64token)
   - Case manipulation of the Bearer scheme

4. **Remediation**: What specific changes to AppAuthManager.java would make it
   RFC 6750 compliant?

## Output

Write your findings to `/workspace/security_audit.md`.
