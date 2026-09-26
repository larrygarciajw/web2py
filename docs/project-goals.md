# Web2py Modernization Project

## Objective

Create a modernized fork of web2py while preserving the fundamental
web2py development model and maintaining reasonable compatibility
with existing web2py applications.

## Main goals

- Preserve the web2py programming model.
- Preserve compatibility with existing applications whenever possible.
- Modernize the internal framework for modern Python.
- Improve code maintainability.
- Improve automated testing.
- Improve type safety.
- Improve security.
- Improve documentation.
- Reduce legacy technical debt.
- Improve developer tooling and IDE support.

## Core principle

The current source code of the repository is the authoritative source
of truth.

Documentation provides architectural and historical context but must
always be verified against the actual implementation.

## Initial scope

The first phase will focus on understanding and documenting:

- framework bootstrap
- WSGI request lifecycle
- routing
- execution environment
- models
- controllers
- views
- template engine
- PyDAL integration
- sessions
- authentication
- caching
- scheduler
- error handling
- security
- deployment

## Out of scope for the initial phase

Do not:

- migrate web2py to Django
- migrate web2py to Flask
- migrate web2py to FastAPI
- migrate web2py to py4web
- rewrite the framework
- remove compatibility mechanisms
- replace core subsystems without tests

## Development strategy

Modernization must be incremental.

For every important change:

1. Understand the current implementation.
2. Identify existing behavior.
3. Identify tests.
4. Add characterization tests when needed.
5. Make a small change.
6. Run tests.
7. Review compatibility.
8. Document the change.