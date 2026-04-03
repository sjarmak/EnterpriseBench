# Trace Terraform plan 'InvalidParameterValue' error to AWS provider resource implementation

A customer reports this error during `terraform plan`:

    Error: creating EC2 Instance: InvalidParameterValue: Value (m6g.xlarge)
    for parameter instanceType is not valid. Reason: The requested instance type
    is not supported in the requested Availability Zone.

The customer is confused because the instance type works in other availability zones
and wants to understand why Terraform doesn't validate this before the plan phase.

Your task:
1. Find where Terraform core processes provider errors during the plan phase —
   trace from the plan command through the provider plugin protocol.
2. Find where the AWS provider creates EC2 instances and handles the
   InvalidParameterValue error — trace through the aws_instance resource
   implementation.
3. Trace the full error chain: AWS API → provider error handling → Terraform core
   plugin protocol → user-visible plan output. Document each file and function.
4. Determine why this error only surfaces at plan time rather than during validation —
   examine the provider's ValidateResourceConfig implementation and what pre-flight
   checks exist (or don't exist) for instance type / AZ compatibility.

Write your analysis to /workspace/ERROR_PROVENANCE.md with:
- Full error chain (file:function at each step)
- AWS provider error origin
- Terraform core error processing
- Why pre-flight validation doesn't catch this
