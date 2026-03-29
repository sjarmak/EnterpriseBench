# RBAC / Permission Audit Candidates

Mining date: 2026-03-28
Go/no-go threshold: >= 5 viable tasks with multi-layer policy chains
**Result: GO (5 candidates found)**

## Candidate 1: Keycloak Privilege Escalation via manage-clients (CVE-2026-3121)

- **Repo**: keycloak/keycloak
- **PR**: #46895 (merged 2026-03-05)
- **Issue**: #46719
- **CVE**: CVE-2026-3121
- **Description**: Administrator with `manage-clients` permission can escalate privileges when Admin Permissions are enabled at the realm level. The flaw is in fine-grained admin permissions V2 (`RealmPermissionsV2.java`).
- **Files changed**:
  - `services/src/main/java/org/keycloak/services/resources/admin/fgap/RealmPermissionsV2.java` (+11/-2)
  - `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/AbstractPermissionTest.java` (+15)
  - `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/PermissionRESTTest.java` (+100/-1)
- **Multi-layer**: Realm-level admin permissions -> FGAP V2 permission model -> client management scope
- **Difficulty**: hard
- **Task type**: Permission escalation audit in identity management system
- **Viability**: HIGH - clear CVE, well-defined permission chain, pinnable commit

## Candidate 2: Calico Tier RBAC Authorization Bypass on Policy Tier Changes

- **Repo**: projectcalico/calico
- **PR**: #12006 (merged 2026-03-06)
- **Description**: When policies change tiers, the apiserver only checked the old tier and the webhook only checked the new tier. Either path allowed moving a policy into/out of a tier the user lacks permission for.
- **Files changed** (11 files):
  - `apiserver/pkg/registry/projectcalico/globalpolicy/storage.go` (+17/-4)
  - `apiserver/pkg/registry/projectcalico/networkpolicy/storage.go` (+17/-4)
  - `apiserver/pkg/registry/projectcalico/stagedglobalnetworkpolicy/storage.go` (+17/-4)
  - `apiserver/pkg/registry/projectcalico/stagednetworkpolicy/storage.go` (+17/-4)
  - `webhooks/pkg/rbac/rbac.go` (+66/-25)
  - `webhooks/pkg/rbac/rbac_test.go` (+104)
  - Felix calc graph tests (+multiple)
- **Multi-layer**: Kubernetes apiserver storage -> admission webhook RBAC -> Felix policy sorter
- **Difficulty**: hard
- **Task type**: Multi-layer RBAC bypass across apiserver and webhook components
- **Viability**: HIGH - affects 4 policy types, dual authorization path, rich code context

## Candidate 3: Harbor Webhook Policy RBAC for Project Maintainer

- **Repo**: goharbor/harbor
- **PR**: #22135 (merged 2025-07-25)
- **Issue**: #22031
- **Description**: Project maintainer role lacked `ActionRead` permission for `NotificationPolicy` resource, causing 403 errors when viewing webhook policies.
- **Files changed**:
  - `src/common/rbac/project/rbac_role.go` (+1)
- **Multi-layer**: Harbor project roles -> RBAC evaluator -> notification policy resources
- **Difficulty**: medium (single file, but requires understanding Harbor's RBAC model)
- **Task type**: Permission gap audit in container registry
- **Viability**: MEDIUM - small fix but good for calibration; requires understanding role hierarchy

## Candidate 4: Harbor System Robot Wildcard Permission Bypass

- **Repo**: goharbor/harbor
- **PR**: #22352 (closed, not merged, but issue #21406 is real)
- **Description**: System robots with wildcard project permissions (`/project/*/robot`) could not create project-level robots due to missing `filterRobotPolicies` parameter in RBAC evaluator.
- **Files affected**:
  - `src/common/security/robot/context.go` - RBAC policy filtering for robot accounts
  - `src/server/v2.0/handler/robot.go` - wildcard permission validation
- **Multi-layer**: System robot security context -> RBAC evaluator -> project-level robot creation
- **Difficulty**: hard
- **Task type**: Robot account RBAC gap analysis
- **Viability**: HIGH - complex permission chain, real issue, affects security boundary

## Candidate 5: Keycloak Bearer Token Validation (CVE-2026-0707)

- **Repo**: keycloak/keycloak
- **PR**: #45787 (merged)
- **Description**: Missing validation on Authorization Header with Bearer token allowing potential bypass.
- **Files changed**: Authorization header validation in token endpoint
- **Multi-layer**: HTTP request handling -> Bearer token parsing -> authorization flow
- **Difficulty**: medium
- **Task type**: Authentication header validation audit
- **Viability**: HIGH - CVE-backed, clear security impact

## Candidate 6 (backup): Argo CD Cluster Permission with Name-based Policy

- **Repo**: argoproj/argo-cd
- **PR**: #24992
- **Description**: Cluster permission denied when using cluster name-based RBAC policy instead of server URL.
- **Multi-layer**: Argo CD RBAC -> cluster name resolution -> policy evaluation
- **Difficulty**: medium
- **Viability**: MEDIUM - good for single-repo calibration task

## Selected for Task Authoring

1. **Candidate 2** (Calico tier RBAC) - Best multi-layer example: apiserver + webhook + felix
2. **Candidate 1** (Keycloak CVE-2026-3121) - Real CVE, identity management RBAC
3. **Candidate 4** (Harbor robot RBAC) - Container registry security boundary
4. **Candidate 5** (Keycloak CVE-2026-0707) - Authentication validation
5. **Candidate 3** (Harbor webhook RBAC) - Calibration-level task
