# Task: Refactor PipelineOptions Validation in Apache Beam

## Context

As part of the Q2 tech debt reduction initiative, the data platform team has identified PipelineOptions validation as a high-priority cleanup target. Validation logic is scattered across the codebase, making it difficult to add new pipeline configuration rules consistently.

The codebase is available at `/workspace/beam/`.

## Background

The PipelineOptions validation in Apache Beam is scattered across multiple locations. This task consolidates validation into a dedicated validator class using the Builder pattern.

## Objective

Create a `PipelineOptionsValidator` class that centralizes validation for PipelineOptions, replacing scattered validation calls.

## Steps

1. Study the existing PipelineOptions interface and the factory class that constructs options instances — both live in the `sdks/java/core` options package. Understand where validation logic currently exists.
2. Create a new `PipelineOptionsValidator` class in the same package with:
   - A Builder that accumulates validation rules
   - Methods: `validateRequired()`, `validateType()`, `validateRange()`
   - A `validate()` method that runs all accumulated rules and returns a `ValidationResult`
3. Create a `ValidationResult` class that holds errors and warnings
4. Create a test file for the validator

## Success Criteria

- PipelineOptionsValidator.java exists with Builder pattern
- ValidationResult class exists
- Test file exists
- Validator has validateRequired, validateType, and validate methods
