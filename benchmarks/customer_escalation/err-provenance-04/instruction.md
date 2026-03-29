# Support Ticket: Container stuck in Error state, never restarts

**Priority:** High
**Submitted by:** Application Developer
**Product:** Kubernetes (pod lifecycle)

---

Hi support,

We have a pod with native sidecar containers (the new restartPolicy: Always init containers). When the main application container crashes, it shows:

```
State:          Terminated
  Reason:       Error
  Exit Code:    2
```

But it never restarts, even though our pod spec has `restartPolicy: Always`. The sidecar container is still running fine. If we kill the sidecar too, then both containers restart correctly.

It seems like the kubelet isn't restarting crashed containers when a sidecar is still alive. There's no explicit error message in the kubelet logs about why it's not restarting — the container just sits in "Terminated" state.

We need to understand:
1. Which part of the kubelet code decides whether to restart a terminated container
2. Why the presence of a running sidecar container prevents the restart
3. What the specific condition is that causes the prober/restart logic to skip this container

The repository is available under `/workspace/kubernetes/`.

Thanks,
Casey
