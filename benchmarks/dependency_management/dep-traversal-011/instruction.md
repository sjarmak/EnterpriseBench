# CVE Blast Radius Analysis: Log4Shell (CVE-2021-44228)

## Context

Log4Shell. You know this one. CVE-2021-44228 is a critical RCE in Apache Log4j 2. A crafted string in a log message triggers JNDI lookup, allowing remote code execution. It affected virtually every Java application that uses log4j-core.

Our Java infrastructure includes Spring Boot services and Kafka. I need a thorough blast radius assessment that goes beyond just checking pom.xml — there are shaded JARs, relocated packages, and OSGi bundles that repackage log4j under different artifact coordinates.

## What I Need

1. **CVE and Artifact Identification**: Not just log4j-core. Also identify pax-logging-log4j2 (OSGi repackaging) and any other artifacts that contain the vulnerable code.

2. **Direct Dependents**: How does each workspace repo pull in log4j? Spring Boot uses an optional starter (spring-boot-starter-log4j2). Kafka may use it directly.

3. **Transitive Paths**: Map through Spring Boot's starter system and Kafka's module structure. Are there shaded JARs that bundle log4j classes under different package names? These are invisible to simple dependency scanning.

4. **Fix Version Complexity**: There are multiple fix versions:
   - 2.15.0 (partial fix, still exploitable under certain configs)
   - 2.16.0 (full fix)
   - 2.3.1 (backport for Java 6)
   - 2.12.2 (backport for Java 7)
   Classify each consumer and note if they need 2.16.0+ for a complete fix.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
