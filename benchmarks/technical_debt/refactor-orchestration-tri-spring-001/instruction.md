# Refactor Orchestration: Spring Kafka Listener Container Threading Model

## Context

Spring Kafka's listener container threading model needs refactoring from
single-threaded KafkaMessageListenerContainer to ConcurrentMessageListenerContainer
with configurable concurrency. This change touches three repositories:

- spring-framework provides core messaging abstractions
- spring-kafka implements Kafka-specific listener containers
- spring-boot autoconfigures and exposes properties for listener containers

The dependency chain: spring-framework -> spring-kafka -> spring-boot

## Task

Produce a topologically sorted execution plan for this refactoring across all
three repos, identifying ordering constraints, parallelization opportunities,
and breaking changes.

## Repos in Workspace

- `/workspace/spring-framework/` -- Spring Framework 6.0.11 (upstream abstractions)
- `/workspace/spring-kafka/` -- Spring Kafka 3.0.9 (primary implementation)
- `/workspace/spring-boot/` -- Spring Boot 3.1.2 (autoconfiguration consumer)

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of repos in the order they should be updated
2. Dependency graph (who depends on whom)
3. Parallelization annotations (which steps can run concurrently)
4. Breaking vs. compatible change annotations per step
5. Risk assessment for each repo change
