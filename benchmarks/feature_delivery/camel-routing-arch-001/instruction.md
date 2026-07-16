# big-code-camel-arch-001: Apache Camel Message Routing Architecture

## Task

Trace how Apache Camel routes a message from endpoint reception through the EIP pipeline to a destination. Map the complete Component→Endpoint→Consumer→Processor→Producer hierarchy, including the Pipeline processor chain, Channel interceptor wiring, and the RouteReifier model-to-runtime bridge.

## Context

- **Repository**: apache/camel (Java, ~2.8M LOC)
- **Codebase**: Available at `/workspace/camel/`
- **Category**: Architectural Understanding
- **Difficulty**: hard
- **Subsystem Focus**: core/ — the Camel core routing engine (camel-api, camel-core-model, camel-support, camel-core-processor, camel-base-engine, camel-core-reifier)

## Requirements

1. Identify all relevant components in the Component→Endpoint→Consumer→Processor→Producer hierarchy (API interfaces + base implementations)
2. Trace the dependency chain from route definition through reification to runtime message processing
3. Document the Pipeline and Channel architecture (how processors are chained and intercepted)
4. Explain how the RouteReifier bridges the DSL model (RouteDefinition) to the runtime Route

## Evaluation Criteria

- File recall: Did you find the correct set of architecturally relevant files?
- Dependency accuracy: Did you trace the correct dependency/call chain?
- Architectural coherence: Did you correctly identify the design patterns and component relationships?
