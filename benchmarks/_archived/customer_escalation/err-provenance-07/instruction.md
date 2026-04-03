# Support Ticket: Terraform shows ERROR about missing provider schema

**Priority:** Low
**Submitted by:** DevOps Engineer
**Product:** Terraform

---

Hi,

When running `terraform plan` or `terraform apply` with `TF_LOG=ERROR`, we see this error in the output:

```
[ERROR] AttachSchemaTransformer: No provider config schema available for provider["terraform.io/builtin/terraform"]
```

This happens on every run, even with a minimal configuration that just uses `terraform_data` or `terraform_remote_state`. The plan/apply succeeds, but the ERROR-level log message is alarming our monitoring.

Is this a real error, or is it expected behavior that's logged at the wrong level? We'd like to understand:

1. Where in the Terraform source code this error message is generated
2. Why the builtin terraform provider triggers it
3. Whether this is expected behavior (and should be DEBUG level) or an actual missing schema problem

The repository is available under `/workspace/terraform/`.

Thanks,
Riley
