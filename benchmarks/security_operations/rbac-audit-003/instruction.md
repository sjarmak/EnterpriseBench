# RBAC Gap Analysis: Harbor Robot Account Wildcard Permissions

## Context

Our Harbor container registry uses system-level robot accounts with wildcard
project permissions to automate cross-project operations. After upgrading, our
CI/CD pipeline robot (which has `/project/*/robot` permission) started getting
403 errors when creating project-scoped robot accounts for individual teams.

The robot has system-level wildcard permissions that should cover all projects,
but something in the RBAC evaluation chain is not resolving the wildcard
correctly for robot creation operations.

## What I Need

1. **RBAC Architecture**: Explain Harbor's robot account permission model. How
   are system robots different from project robots? Where does the RBAC
   evaluator chain get built?

2. **Evaluator Chain Analysis**: In `src/common/security/robot/context.go`,
   compare how system robots and project robots construct their RBAC evaluator
   chain. Is there a parameter (`filterRobotPolicies`) that one has but the
   other doesn't?

3. **Permission Check Trace**: In `src/server/v2.0/handler/robot.go`, trace
   the `CreateRobot()` and `requireAccess()` flow. Where exactly does the 403
   come from?

4. **Root Cause**: Why does the wildcard permission not get evaluated
   correctly? What is missing from the system robot's evaluator construction?

5. **Remediation**: What specific code changes would fix this?

## Output

Write your findings to `/workspace/security_audit.md`.
