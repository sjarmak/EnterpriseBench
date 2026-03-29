# Support Ticket: Pods getting killed even though servers have enough memory

**Priority:** High
**Submitted by:** Application Team Lead
**Product:** Kubernetes cluster (self-managed)

---

Hello,

We keep having pods get evicted from our cluster with the reason "memory pressure" but when we check the nodes, they have plenty of RAM available. Our monitoring shows the nodes are typically at 60-65% memory utilization, well under any reasonable threshold.

This is causing outages because critical application pods get killed and have to restart. Sometimes the same pods get evicted again right after they come back up, creating a cycle that takes the whole service down.

We've looked at the pod resource requests and limits and they seem reasonable. The nodes aren't actually running out of memory based on everything we can see from the OS level. It feels like Kubernetes is making a wrong decision about when to evict.

We need to understand what code in Kubernetes decides to evict pods for memory pressure and how it calculates whether there's actually memory pressure or not. There might be a mismatch between what the system reports and what the eviction logic thinks is happening.

Can you help us trace through the eviction decision path?

Thanks,
Sam
