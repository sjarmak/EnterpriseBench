# Support Ticket: Terraform panics during backend migration to GCS

**Priority:** High
**Submitted by:** Infrastructure Engineer
**Product:** Terraform

---

Hi support,

We're migrating our Terraform state from local to GCS backend. When we run `terraform init -migrate-state`, Terraform panics:

```
panic: runtime error: invalid memory address or nil pointer dereference
```

The GCS bucket exists and we can access it with gsutil. However, our service account might not have the `storage.objects.get` permission specifically (it has `storage.objects.list` and `storage.objects.create`).

The panic gives us no useful information about what went wrong. We suspect the permission error is being swallowed somewhere and then the code tries to use a nil pointer.

We need to find:
1. Where in the Terraform source code the nil pointer dereference occurs during backend migration
2. How the GCS permission error gets lost (where is it swallowed?)
3. What conditions cause the migration code to receive a nil state without an accompanying error

The repository is available under `/workspace/terraform/`.

Thanks,
Jamie
