# Support Ticket: kube-proxy crashing with nftables segfault

**Priority:** High
**Submitted by:** Infrastructure SRE
**Product:** Kubernetes (networking/kube-proxy)

---

Hi,

After upgrading our nodes to a newer OS image, kube-proxy started failing with these errors in the logs:

```
"Failed to list existing sets" err="failed to run nft: signal: segmentation fault (core dumped)"
"nftables sync failed" err="signal: segmentation fault (core dumped)"
"Sync failed" ipFamily="IPv4" retryingTime="30s"
```

kube-proxy is running in nftables mode. The nft binary works fine on its own — we can list and create sets manually. The segfault only happens when kube-proxy tries to list sets.

We suspect it might be related to the nftables version change in the new OS (from 1.0.x to 1.1.3), but we don't understand why kube-proxy would be affected.

Can you trace through the kube-proxy source to find:
1. Which file generates the "Failed to list existing sets" error message
2. How the error propagates from the nft command execution to the logged messages
3. What specific condition in the nftables interaction causes the segfault

The repository is available under `/workspace/kubernetes/`.

Thanks,
Sam
