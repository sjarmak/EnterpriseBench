# Support Ticket: kube-apiserver fails readyz after upgrade to v1.33

**Priority:** Critical
**Submitted by:** Cluster Operations Lead
**Product:** Kubernetes (control plane)

---

We're performing a rolling upgrade from v1.32 to v1.33 and the apiserver on the upgraded nodes is failing its readiness check. The logs show:

```
PostStartHook "start-service-ip-repair-controllers" failed: unable to perform initial IP and Port allocation check
```

Followed by:
```
ipaddresses.networking.k8s.io "10.211.95.185" is forbidden: not yet ready to handle request
```

And then the readyz endpoint reports:
```
informer-sync,poststarthook/start-service-ip-repair-controllers check failed: readyz
```

This only happens during the upgrade window — once all nodes are on v1.33, it stabilizes. But during the rolling upgrade, the mixed-version period causes the apiserver to be unavailable.

We need to understand:
1. Where the "unable to perform initial IP and Port allocation check" error is generated in the source code
2. The full error propagation chain from the PostStartHook through to the readyz failure
3. What race condition between the repair controller and API readiness causes this during upgrades

The repository is available under `/workspace/kubernetes/`.

Thanks,
Morgan
