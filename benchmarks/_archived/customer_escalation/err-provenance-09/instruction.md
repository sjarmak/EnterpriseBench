# Support Ticket: Wrong error message during Terraform backend migration

**Priority:** Low
**Submitted by:** DevOps Engineer
**Product:** Terraform

---

Hello,

When migrating our Terraform backend configuration, we get an error message that doesn't match our situation. The message talks about a different migration scenario than what we're actually doing.

It seems like the error message was copied from another code path and not updated for this specific migration case. The error is technically correct (migration fails), but the explanation is wrong and confusing.

We need to understand:
1. Where in the Terraform source code the backend migration error messages are defined
2. Which file contains the error message templates for different migration scenarios
3. Which specific error constant is being incorrectly referenced (copy-paste error)

The repository is available under `/workspace/terraform/`.

Thanks,
Taylor
