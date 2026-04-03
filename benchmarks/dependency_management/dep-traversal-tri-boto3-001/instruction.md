# Dependency Trace: S3 Multipart Upload from boto3 through s3transfer to botocore

## Context

When uploading large files to S3 with boto3, the actual work is split across
three libraries: boto3 provides the high-level API, s3transfer handles
multipart upload orchestration (splitting, concurrency, completion), and
botocore provides the low-level AWS API calls with serialization and retries.

A timeout issue with large uploads requires understanding how configuration
flows through all three layers.

## Task

Trace a single `upload_file` call from boto3's S3 resource through s3transfer's
multipart upload logic to botocore's API call serialization. Document
configuration options at each layer.

## Repos in Workspace

- `/workspace/boto3/` -- boto3 1.28.0 (high-level SDK)
- `/workspace/s3transfer/` -- s3transfer 0.6.1 (transfer orchestration)
- `/workspace/botocore/` -- botocore 1.31.0 (low-level API client)

## Expected Output

Write `/workspace/DEPENDENCY_TRACE.md` containing:

1. boto3's upload_file entry point and TransferConfig options
2. s3transfer's TransferManager multipart upload orchestration
3. botocore's low-level S3 operations (CreateMultipartUpload, UploadPart, CompleteMultipartUpload)
4. Configuration options at each layer that affect upload behavior
5. The complete call chain from upload_file to HTTP requests
