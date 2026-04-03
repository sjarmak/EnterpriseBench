# Verify protobuf well-known type contract compliance across protobuf compiler, gRPC runtime, and googleapis

Your team maintains a gRPC-based microservice architecture that depends on
protobuf well-known types (Timestamp, Duration, FieldMask, Struct, Any). After
upgrading protobuf to v25.1 and gRPC to v1.60.0, some services report
serialization errors when exchanging messages containing well-known types.

The issue may stem from contract drift between how protobuf defines well-known
types, how the gRPC C++ core runtime handles their serialization, and how
googleapis common protos depend on specific well-known type behaviors.

Your task:

1. Find where protobuf defines the well-known types — locate the .proto files
   and the language-specific runtime implementations (particularly the JSON
   serialization for Timestamp, Duration, and Struct). Identify any v25.x
   changes to serialization behavior.
2. Find where the gRPC C++ core handles protobuf serialization — locate the
   protobuf serialization integration, message codec, and any well-known type
   special-casing in the gRPC runtime.
3. Find where googleapis common protos reference well-known types — locate
   the .proto files that import google/protobuf/\*.proto and identify any
   assumptions about serialization format or field presence.
4. Map the contract chain: protobuf definitions -> gRPC runtime serialization
   -> googleapis consumer expectations.

Write your analysis to /workspace/analysis/IMPACT_REPORT.md with:

- Well-known type definition locations (protobuf repo)
- gRPC serialization integration points
- googleapis dependencies on well-known type behavior
- Contract violations or drift points
