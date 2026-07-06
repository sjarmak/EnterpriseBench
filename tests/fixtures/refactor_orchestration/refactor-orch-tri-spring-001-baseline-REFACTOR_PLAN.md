# Refactor Plan: Spring Kafka Listener Container Threading Model

## Objective

Refactor from direct use of single-threaded `KafkaMessageListenerContainer` to
`ConcurrentMessageListenerContainer` with configurable concurrency, propagating the
change through the dependency chain: spring-framework → spring-kafka → spring-boot.

---

## 1. Topologically Sorted Execution Order

```
[1] spring-framework   (no inter-repo deps; provides abstractions)
[2] spring-kafka        (depends on spring-framework)
[3] spring-boot         (depends on spring-kafka)
```

### Step 1 — spring-framework (foundation)

**Scope:** Verify/extend core threading abstractions used by the Kafka threading model.

Key files:
- `spring-core/src/main/java/org/springframework/core/task/AsyncTaskExecutor.java`
- `spring-core/src/main/java/org/springframework/core/task/TaskExecutor.java`
- `spring-context/src/main/java/org/springframework/context/SmartLifecycle.java`
- `spring-jms/src/main/java/org/springframework/jms/listener/MessageListenerContainer.java`
- `spring-jms/src/main/java/org/springframework/jms/config/JmsListenerContainerFactory.java`

**Changes required:**
- No breaking interface changes anticipated; `AsyncTaskExecutor`, `SmartLifecycle`, and
  `ErrorHandler` already cover the required contracts.
- If concurrency-lifecycle semantics need formalization (e.g., a `ConcurrentListenerContainer`
  marker interface), add it here as a compatible extension.
- Publish a SNAPSHOT of spring-framework before spring-kafka work begins.

**Change type:** COMPATIBLE (additive only)
**Risk:** LOW — existing interfaces are untouched; changes are purely additive.

---

### Step 2 — spring-kafka (primary implementation)

**Scope:** Refactor the container model so `ConcurrentMessageListenerContainer` is the
canonical container, and make concurrency configurable end-to-end.

Key files:
- `spring-kafka/src/main/java/org/springframework/kafka/listener/KafkaMessageListenerContainer.java` (lines 165–615, inner `ListenerConsumer` 618+)
- `spring-kafka/src/main/java/org/springframework/kafka/listener/ConcurrentMessageListenerContainer.java` (field `concurrency` line 70, `doStart` line 211, `constructContainer` line 273)
- `spring-kafka/src/main/java/org/springframework/kafka/listener/ContainerProperties.java` (field `listenerTaskExecutor` line 244)
- `spring-kafka/src/main/java/org/springframework/kafka/config/ConcurrentKafkaListenerContainerFactory.java` (field `concurrency` line 49, `setConcurrency` line 56, `createContainerInstance` line 61)
- `spring-kafka/src/main/java/org/springframework/kafka/config/KafkaListenerEndpointRegistry.java` (field `listenerContainers` line 80, `createListenerContainer` line 267)

**Sub-steps (some parallelizable — see §3):**

  **2a.** Audit all internal call sites that instantiate `KafkaMessageListenerContainer`
          directly (outside of `ConcurrentMessageListenerContainer.constructContainer`).
          Change them to go through `ConcurrentMessageListenerContainer`.

  **2b.** Set a sensible non-1 default for `ConcurrentMessageListenerContainer.concurrency`
          (e.g., derive from available processors or keep explicit configuration mandatory).
          Document migration from implicit single-thread to explicit concurrency config.

  **2c.** Extend `ContainerProperties` with any new threading properties (e.g.,
          per-container executor strategy, shutdown timeout for concurrent stop).

  **2d.** Update `ConcurrentKafkaListenerContainerFactory.initializeContainer` (line 81)
          to propagate new properties correctly to child containers.

  **2e.** Update `KafkaListenerEndpointRegistry.createListenerContainer` (line 267) to
          always produce `ConcurrentMessageListenerContainer` instances, never bare
          `KafkaMessageListenerContainer` instances.

  **2f.** Write/update tests: unit tests per sub-step, plus an integration test verifying
          N consumer threads poll independently under concurrency > 1.

**Change type:** POTENTIALLY BREAKING
- Any code that casts the return of `createListenerContainer` to
  `KafkaMessageListenerContainer` will break.
- Changing the default `concurrency` value from 1 to N changes consumer group
  partition assignment behavior (observable, behavioral breaking change).

**Risk:** HIGH
- Consumer-group rebalancing behavior changes when concurrency increases.
- Partition assignment across child containers must be validated (see
  `ConcurrentMessageListenerContainer.partitionSubset`, line 287).
- Thread-safety in `ListenerConsumer` (line 618+) must be audited for shared state.
- Offset commit ordering across concurrent consumers must be verified.

---

### Step 3 — spring-boot (autoconfiguration)

**Scope:** Expose the concurrency setting as a first-class property and ensure the
autoconfigured factory reflects the refactored defaults.

Key files:
- `spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/kafka/KafkaAutoConfiguration.java` (lines 69–229)
- `spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/kafka/KafkaProperties.java` (Listener inner class, field `concurrency` line 977, getter lines 1078–1080)
- `spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/kafka/ConcurrentKafkaListenerContainerFactoryConfigurer.java` (concurrency binding line 176)
- `spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/kafka/KafkaAnnotationDrivenConfiguration.java` (factory bean lines 121–130)

**Sub-steps:**

  **3a.** Update `KafkaProperties.Listener.concurrency` (line 977) default value and
          Javadoc to reflect the new threading model semantics.

  **3b.** Verify `ConcurrentKafkaListenerContainerFactoryConfigurer.configureListenerFactory`
          (line 176) propagates any new `ContainerProperties` fields added in step 2c.

  **3c.** If new `ContainerProperties` fields were added in step 2c, add corresponding
          `spring.kafka.listener.*` properties to `KafkaProperties.Listener`.

  **3d.** Update `spring-configuration-metadata.json` so IDE tooling reflects new
          properties with correct defaults and deprecation notices for removed ones.

  **3e.** Add smoke tests / integration tests verifying the full autoconfiguration
          stack creates a properly concurrent container.

**Change type:** COMPATIBLE (property additions) / POTENTIALLY BREAKING (default changes)
- Adding new properties is backward-compatible.
- Changing the default value of `spring.kafka.listener.concurrency` is a breaking
  behavioral change for users relying on the default.

**Risk:** MEDIUM
- Property default changes affect all users who rely on autoconfiguration.
- Requires a deprecation period and migration guide entry in the release notes.

---

## 2. Dependency Graph

```
spring-framework
      │
      │  provides: AsyncTaskExecutor, SmartLifecycle, ErrorHandler,
      │            MessageListenerContainer (JMS pattern), Lifecycle
      ▼
spring-kafka
      │
      │  provides: KafkaMessageListenerContainer, ConcurrentMessageListenerContainer,
      │            ContainerProperties, ConcurrentKafkaListenerContainerFactory,
      │            KafkaListenerEndpointRegistry
      ▼
spring-boot
         provides: KafkaProperties, KafkaAutoConfiguration,
                   ConcurrentKafkaListenerContainerFactoryConfigurer,
                   KafkaAnnotationDrivenConfiguration
```

Dependency edges (who depends on whom):
- spring-kafka → spring-framework (compile dependency on AsyncTaskExecutor, SmartLifecycle)
- spring-boot  → spring-kafka    (compile dependency on all Kafka config/listener classes)
- spring-boot  → spring-framework (transitive + direct for context abstractions)

---

## 3. Parallelization Annotations

```
Timeline (left = earlier, right = later):

[spring-framework]  ──── Step 1 ────────────────────────────────────────┐
                                                                         │ publish SNAPSHOT
[spring-kafka]              ├── Step 2a ──┐                             │
                             │             ├── Step 2b ──┐              │
                             │             │              ├── 2c+2d+2e ──┤
                             │             │              │              │ publish SNAPSHOT
[spring-boot]                │             │              │              └── Step 3a ──┬── 3b ──┬── 3c ──┬── 3d ──┬── 3e
                             │             │              │                            │         │         │         │
                    PARALLEL: 2a can start │              │               SEQUENTIAL: 3a→3b→3c→3d→3e (each depends on prior)
                    as soon as step 1 is   │              │
                    published.  2b requires │              │
                    2a analysis complete.   │              │
                                           2c+2d+2e can run concurrently WITHIN spring-kafka
                                           once 2b defines the new property surface.
```

**Concurrency rules:**
| Step pair           | Can run in parallel? | Constraint |
|---------------------|----------------------|------------|
| 1 + (2a analysis)   | YES                  | 2a write depends on 1 SNAPSHOT |
| 2a + 2b             | NO                   | 2b depends on 2a audit findings |
| 2c + 2d             | YES                  | Both depend only on 2b decisions |
| 2c + 2e             | YES                  | Both depend only on 2b decisions |
| 2d + 2e             | YES                  | Both depend only on 2b decisions |
| 2f + step 3         | NO                   | spring-boot needs spring-kafka SNAPSHOT |
| 3a + 3b             | YES (mostly)         | 3b may need 3a to finalize property names |
| 3c + 3d             | YES                  | Both depend on 3b completing |

---

## 4. Breaking vs. Compatible Change Annotations

| Repo              | Change                                       | Type              |
|-------------------|----------------------------------------------|-------------------|
| spring-framework  | Add marker interface (if any)                | COMPATIBLE        |
| spring-framework  | No changes to existing interfaces            | COMPATIBLE        |
| spring-kafka      | Internal direct uses of KMLC → CMLC          | COMPATIBLE (internal) |
| spring-kafka      | Default concurrency change (1 → N)           | **BREAKING** (behavioral) |
| spring-kafka      | Cast-breaking: registry returns CMLC not KMLC| **BREAKING** (API) |
| spring-kafka      | New ContainerProperties fields               | COMPATIBLE (additive) |
| spring-kafka      | ConcurrentKafkaListenerContainerFactory API  | COMPATIBLE if only additive |
| spring-boot       | New spring.kafka.listener.* properties       | COMPATIBLE        |
| spring-boot       | Default concurrency property value change    | **BREAKING** (behavioral) |
| spring-boot       | Metadata / IDE completion updates            | COMPATIBLE        |

---

## 5. Risk Assessment per Repo

### spring-framework
- **Risk level: LOW**
- Changes are additive; all existing abstractions (`AsyncTaskExecutor`, `SmartLifecycle`)
  already support the required threading model.
- No downstream breakage expected from this repo's changes.
- Mitigation: Verify existing interfaces via `@since` annotations; do not modify
  method signatures.

### spring-kafka
- **Risk level: HIGH**
- **Partition assignment regression:** `ConcurrentMessageListenerContainer.partitionSubset`
  (line 287) distributes partitions across child containers. If concurrency > number of
  assigned partitions, idle containers result. Must validate partition assignment logic.
- **Offset commit ordering:** Concurrent consumers sharing a consumer group must not
  commit offsets out of order. The `ListenerConsumer` (line 618+) ack logic must be
  audited for thread-safety across the N child containers.
- **API breakage:** Any user code that directly casts `MessageListenerContainer` to
  `KafkaMessageListenerContainer` (e.g., to access `getAssignedPartitions`, line 269)
  breaks if the registry now returns `ConcurrentMessageListenerContainer`. Mitigation:
  expose needed methods on the `ConcurrentMessageListenerContainer` type or a common
  interface.
- **Behavioral regression with concurrency=1:** The single-container code path must
  remain functionally identical post-refactor. Add a regression test suite.
- **Executor resource leak:** Each child `KafkaMessageListenerContainer` allocates its
  own `SimpleAsyncTaskExecutor` thread by default (`ContainerProperties.listenerTaskExecutor`,
  line 244). With concurrency=N, ensure the executor is either shared or properly
  bounded, and that shutdown releases all threads.

### spring-boot
- **Risk level: MEDIUM**
- **Default value migration:** If `spring.kafka.listener.concurrency` default changes,
  all Spring Boot apps relying on the default single-thread behavior change behavior
  silently on upgrade. Requires a deprecation/migration note in the release notes and
  ideally a `@DeprecatedConfigurationProperty` annotation with the old default.
- **Property binding completeness:** Any new `ContainerProperties` fields from spring-kafka
  must have corresponding property entries in `KafkaProperties.Listener` and bindings
  in `ConcurrentKafkaListenerContainerFactoryConfigurer` (line 176). Gaps cause silent
  misconfiguration.
- **Test coverage:** The smoke tests in `spring-boot-autoconfigure-tests` must be updated
  to assert on the new defaults.

---

## Summary Table

| Order | Repo               | Key Risk     | Breaking? | Can Parallelize With |
|-------|--------------------|--------------|-----------|----------------------|
| 1     | spring-framework   | LOW          | No        | —                    |
| 2     | spring-kafka       | HIGH         | Yes       | 2c/2d/2e concurrently after 2b |
| 3     | spring-boot        | MEDIUM       | Behavioral| 3a+3b partially; 3c+3d concurrently |
