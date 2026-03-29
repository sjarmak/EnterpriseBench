# CVE Blast Radius Analysis: jackson-databind Deep Nesting DoS

## Context

CVE-2020-36518 is a denial-of-service in jackson-databind. Deeply nested JSON objects cause a stack overflow during deserialization. This is the default JSON library in Spring Boot — every REST API endpoint that accepts JSON input is potentially affected.

The dependency management is complex: Spring Boot uses a BOM (Bill of Materials) to manage jackson versions centrally, and Dropwizard has its own BOM. The version your app actually uses isn't in your pom.xml — it's inherited from layers of parent POMs.

## What I Need

1. **CVE Identification**: CVE, artifact coordinates, both version ranges.

2. **Direct Dependents**: How do Spring Boot and Dropwizard declare the jackson-databind dependency?

3. **BOM Inheritance Chain**: Trace jackson-databind -> jackson-bom -> spring-boot-dependencies -> spring-boot-starter-web. In Maven, the version is managed by the BOM, not declared in the consumer. Show me the chain.

4. **Version Resolution**: What version of jackson-databind does each framework resolve? Is it in the vulnerable range?

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
