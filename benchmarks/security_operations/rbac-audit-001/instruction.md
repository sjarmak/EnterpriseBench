# RBAC Authorization Audit: Calico Network Policy Tier Changes

## Context

Our platform security team received a report from a cluster administrator who
noticed that a user with permissions only on the "default" tier was able to move
a network policy into the "restricted" tier. This should not be possible — tier
permissions are supposed to gate which tiers a user can read and write policies
in.

Calico uses a dual authorization model:
- The **Kubernetes apiserver** (custom resource storage) checks RBAC on policy
  operations
- An **admission webhook** provides additional tier-based authorization checks

We suspect the two authorization paths are checking different things, creating a
gap that allows unauthorized tier changes.

## What I Need

1. **Affected policy types**: Identify all policy types that support tier
   assignment (hint: look in `apiserver/pkg/registry/projectcalico/` for
   storage implementations).

2. **Apiserver authorization analysis**: In each policy type's storage
   `Update()` method, trace what tier authorization check is performed. Does it
   check the old tier, the new tier, or both?

3. **Webhook authorization analysis**: In `webhooks/pkg/rbac/rbac.go`, find the
   `authorize()` function. On UPDATE operations, which object does it inspect
   for tier — the old object, the new object, or both?

4. **The bypass**: Describe the specific scenario. If the apiserver only checks
   tier X and the webhook only checks tier Y, explain how a user could exploit
   this inconsistency.

5. **Remediation**: What changes would close the gap?

## Output

Write your findings to `/workspace/security_audit.md` with clear sections for
each of the above.
