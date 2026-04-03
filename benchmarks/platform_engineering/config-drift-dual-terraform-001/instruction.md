# Detect drift between Terraform core state refresh logic and AWS provider resource read implementations

Your infrastructure team reports that `terraform plan` shows phantom diffs for
several AWS resources — the plan proposes changes even when no configuration has
been modified. The issue appeared after upgrading from Terraform 1.6.x to 1.7.0
alongside terraform-provider-aws v5.31.0.

The root cause is suspected to be drift between how Terraform core handles state
refresh (reading current resource state and comparing to config) and how the AWS
provider implements the Read function for specific resource types. Terraform core
may normalize or flatten certain state attributes differently than the provider
expects.

Your task:

1. Find where Terraform core implements the state refresh/plan diff logic —
   locate the resource evaluation, state refresh, and diff computation code in
   the `terraform/` package. Focus on how attributes are compared between prior
   state and refreshed state.
2. Find where the AWS provider implements Read functions for resources that
   commonly cause phantom diffs (e.g., aws_security_group, aws_iam_policy,
   aws_lambda_function). Identify how the provider normalizes attributes like
   JSON policy documents, list ordering, and default values.
3. Identify the specific drift points where Terraform core's attribute comparison
   logic disagrees with the AWS provider's state representation — particularly
   around JSON normalization, set vs list ordering, and computed default values.
4. Document each drift point with source files from both repos.

Write your analysis to /workspace/DRIFT_REPORT.json with:
{
"drift_points": [
{
"config_key": "<resource attribute causing phantom diff>",
"terraform_core_behavior": "<how core handles comparison>",
"terraform_core_file": "<path in terraform repo>",
"provider_behavior": "<how AWS provider represents state>",
"provider_file": "<path in terraform-provider-aws repo>",
"impact": "<phantom diff description>"
}
]
}
