# Impact Analysis: gRPC-Go Balancer/Resolver Type Alias Removal

## Context

We need to upgrade our etcd dependency to work with gRPC-Go v1.27.0+. The gRPC-Go team removed backward-compatibility type aliases from the `balancer` and `resolver` packages (PR #3309). These aliases were temporary bridges added during an earlier refactoring.

Our etcd clientv3 package has a custom balancer and resolver implementation that may be affected. Before we start the upgrade, I need a complete impact assessment.

## What I Need

1. **Source changes**: What exactly was removed from `grpc-go/balancer/balancer.go` and `grpc-go/resolver/resolver.go`? Which type aliases are gone?

2. **Affected etcd files**: Find every file in etcd's `clientv3/` package tree that references the removed types — custom pickers, balancers, resolvers.

3. **Dependency chain**: Map out how etcd's custom balancer components depend on each other and on the removed grpc-go types. Which files are the entry points and which are transitively affected?

4. **Fix assessment**: Is this a simple find-and-replace of import paths, or does etcd's custom balancer architecture need a deeper rework? The answer determines whether this is a 1-day fix or a multi-week project.

## Output

Write your findings to `/workspace/analysis/IMPACT_REPORT.md` with the source changes, a file-by-file impact table, the dependency chain, and your fix assessment.
