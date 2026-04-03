# Support Ticket: Unexpected SessionAffinity warning on headless services

**Priority:** Low
**Submitted by:** Developer
**Product:** Kubernetes (services)

---

Hi,

We're getting this warning every time we create or update headless services:

```
Warning: spec.SessionAffinity is ignored for headless services
```

But we never set SessionAffinity in our service specs. We're using a simple headless service for StatefulSet DNS:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-db
spec:
  clusterIP: None
  selector:
    app: my-db
  ports:
    - port: 5432
```

No SessionAffinity field anywhere. The warning is just noise in our CI pipelines and we'd like to understand why it fires when we haven't set the field.

Can you find:
1. Where in the Kubernetes source code this warning message is generated
2. What logic determines when to show it
3. Why it fires even when SessionAffinity is not explicitly set by the user

The repository is available under `/workspace/kubernetes/`.

Thanks,
Pat
