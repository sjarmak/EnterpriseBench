# Support Ticket: Confusing error when updating Job status

**Priority:** Medium
**Submitted by:** Platform Engineer
**Product:** Kubernetes (batch workloads)

---

Hi team,

We're running batch jobs on our k8s cluster and hit a confusing validation error when our custom controller tries to update a Job's status. The error says:

```
Job.batch "job-c4nbt" is invalid: status.startTime: Required value: startTime cannot be removed for unsuspended job
```

But we're not removing startTime — we're updating it. The controller modifies `status.startTime` to reflect when the job actually started running (after a scheduling delay), and this error fires even though we're setting a valid timestamp.

The message says "cannot be removed" but nothing is being removed. Is this a bug in the validation, or are we misunderstanding the API contract?

We need to know:
1. Where exactly in the Kubernetes source code this error message is generated
2. What validation logic actually triggers it (is it checking for removal, or something else?)
3. Under what conditions does this error fire — is it any modification to startTime, or specifically removal?

The repository is available under `/workspace/kubernetes/`.

Thanks,
Alex
