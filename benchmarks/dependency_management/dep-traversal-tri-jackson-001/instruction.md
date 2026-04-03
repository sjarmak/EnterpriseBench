# Dependency Trace: Jackson ObjectMapper through Spring Framework to Spring Boot

## Context

Jackson is the default JSON library in the Spring ecosystem. When a developer
registers a custom Jackson Module bean in a Spring Boot application, it should
be auto-detected and applied to all REST endpoints. But the path from bean
definition to actual serialization crosses three repositories:

- Jackson provides ObjectMapper and the Module registration API
- Spring Framework provides Jackson2ObjectMapperBuilder and MappingJackson2HttpMessageConverter
- Spring Boot provides JacksonAutoConfiguration that wires everything together

## Task

Trace how a custom Jackson Module bean flows from Spring Boot autoconfiguration
through Spring Framework's builder into Jackson's ObjectMapper.

## Repos in Workspace

- `/workspace/jackson-databind/` -- jackson-databind 2.15.2 (upstream library)
- `/workspace/spring-framework/` -- Spring Framework 6.0.11 (intermediary)
- `/workspace/spring-boot/` -- Spring Boot 3.1.2 (consumer/autoconfigurer)

## Expected Output

Write `/workspace/DEPENDENCY_TRACE.md` containing:

1. Key classes and methods in jackson-databind for module registration
2. How Spring Framework's Jackson2ObjectMapperBuilder and MappingJackson2HttpMessageConverter integrate with Jackson
3. How Spring Boot's JacksonAutoConfiguration auto-detects and registers Module beans
4. The complete class/method chain from Module bean to REST serialization
