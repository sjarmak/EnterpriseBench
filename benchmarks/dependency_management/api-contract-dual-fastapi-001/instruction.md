# Trace API schema handling differences between FastAPI server validation and httpx client request encoding

Your team uses FastAPI for backend services and httpx as the HTTP client in
service-to-service communication. After upgrading FastAPI to 0.109.0 and httpx
to 0.26.0, some inter-service requests that previously worked now fail with
422 Unprocessable Entity errors.

The issue appears to be a contract mismatch in how FastAPI's Pydantic v2
validation handles request body encoding vs how httpx constructs and encodes
request bodies. Specifically, the handling of nested models, optional fields
with defaults, and union types differs between the two libraries.

Your task:

1. Find where FastAPI processes incoming request bodies — locate the dependency
   injection, body parsing, and Pydantic model validation logic. Identify how
   FastAPI handles Content-Type negotiation and body deserialization for JSON
   requests with nested models.
2. Find where httpx constructs outgoing request bodies — locate the request
   encoding, JSON serialization, and Content-Type header logic. Identify how
   httpx handles nested dict/model serialization and None/default value handling.
3. Identify the specific contract drift points: where FastAPI expects a
   certain JSON structure that httpx's default serialization does not produce
   (e.g., None vs missing keys, nested model serialization, union type encoding).
4. Document each drift point with source files from both repos.

Write your analysis to /workspace/analysis/IMPACT_REPORT.md with:

- FastAPI request validation chain (file paths)
- httpx request encoding chain (file paths)
- Contract drift points with examples
- Recommended fixes
