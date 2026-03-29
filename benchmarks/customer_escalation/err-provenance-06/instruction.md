# Support Ticket: Container creation fails with "invalid UTF-8" when env var contains $

**Priority:** High
**Submitted by:** Application Developer
**Product:** Kubernetes (container runtime)

---

Hello,

We have a container that needs an environment variable containing a dollar sign followed by some Unicode text. Something like:

```yaml
env:
  - name: PRICE_LABEL
    value: "$20 cafe\u0301"
```

When we try to create this pod, it fails with a gRPC error:

```
grpc: error while marshaling: string field contains invalid UTF-8
```

The string is valid UTF-8 in our YAML. The dollar sign seems to trigger some kind of variable expansion that corrupts the UTF-8 encoding. If we remove the `$` sign, it works fine.

We need to understand:
1. Where in the Kubernetes source code environment variable values are processed/expanded
2. How the `$` character triggers expansion that breaks the UTF-8 encoding
3. What exactly happens to multi-byte UTF-8 characters during the expansion process

The repository is available under `/workspace/kubernetes/`.

Thanks,
Lin
