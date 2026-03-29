# Permission Escalation Audit: Keycloak Fine-Grained Admin Permissions

## Context

We operate a Keycloak identity provider with fine-grained admin permissions (FGAP V2)
enabled. A security audit flagged CVE-2026-3121: an administrator who is granted only
`manage-clients` permission can escalate their privileges beyond client management.

This is a serious concern because we delegate client management to team leads who should
not have broader realm administration capabilities.

## What I Need

1. **FGAP V2 Architecture**: Describe how Keycloak's fine-grained admin permissions V2
   works. Where is the permission model defined? How are permission scopes enforced?

2. **manage-clients Scope**: What should `manage-clients` permission allow? What should
   it NOT allow? Trace the permission check in `RealmPermissionsV2.java`.

3. **Escalation Path**: How can a user with only `manage-clients` escalate to broader
   admin access? What specific code path fails to enforce the scope boundary?

4. **Impact Assessment**: What additional operations can the attacker perform? Rate
   the severity.

5. **Remediation**: What code changes would prevent this escalation?

## Output

Write your findings to `/workspace/security_audit.md`.
