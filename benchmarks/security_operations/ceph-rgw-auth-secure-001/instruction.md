# Task: Security Audit of Ceph RADOS Gateway S3 Authentication

## Context

Our security team is conducting a quarterly audit of storage infrastructure. As the security engineer assigned to the Ceph deployment, you need to review the S3 authentication implementation in the RADOS Gateway (RGW) before we expose our object storage endpoints to external partners.

The codebase is available at `/workspace/ceph/`.

## Objective

Perform a security audit of the S3 authentication implementation in Ceph's RADOS Gateway (RGW) and create a findings report with remediation recommendations.

## Steps

1. Locate the S3 authentication implementation within the RGW source tree (look for AWS Signature V4 handling, the auth framework, and the S3 REST layer)
2. Identify the request signing and verification flow
3. Check for common S3 auth vulnerabilities:
   - Signature version fallback (V2 vs V4)
   - Timing attacks in signature comparison
   - Request replay prevention (timestamp validation window)
   - Secret key storage and access patterns
4. Create `security_audit.md` in `/workspace/` documenting:
   - Authentication flow overview (file paths and key functions)
   - Each finding with severity, description, file location, and remediation
   - At least 3 specific findings with code references
   - Summary risk assessment

## Success Criteria

- security_audit.md exists
- Contains specific file paths and function references from the RGW source
- Identifies at least 3 security findings
- Includes remediation recommendations
