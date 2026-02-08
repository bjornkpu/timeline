---
name: principles
descripton: A concise set of engineering principles SOLID, DRY, KISS, YAGNI, and more. Guides code quality, simplicity, commit hygiene, and security best practices
---
# Principles

## Code Principles (SOLID)

- **Single Responsibility:** One class/function = one reason to change
- **Open/Closed:** Extend via composition, not modification
- **Liskov Substitution:** Subtypes must be substitutable
- **Interface Segregation:** Small, focused interfaces (Protocols)
- **Dependency Inversion:** Depend on abstractions, inject dependencies

## Additional Principles

- **DRY (Don't Repeat Yourself):** Extract duplicated logic into reusable functions/classes
- **KISS (Keep It Simple, Stupid):** Simple solutions over complex ones; clarity beats cleverness
- **YAGNI (You Ain't Gonna Need It):** Don't add features until actually needed
- **CoC (Convention over Configuration):** Follow established patterns; minimize explicit configuration
- **LoD (Law of Demeter):** Minimize object coupling; don't reach through multiple layers

## General Approach

- **Minimize over-engineering:** Only add what's needed for the current task
- **Avoid premature abstraction:** Three similar lines is better than an abstraction used once
- **No speculative features:** Don't design for hypothetical future requirements
- **Trust internal guarantees:** Validate only at system boundaries (user input, external APIs)
- **Delete unused code:** Remove completely instead of leaving commented/deprecated code

## When to Ask vs Proceed

- **Ask first:** Before making architectural decisions, major refactors, or changes affecting multiple files
- **Proceed independently:** Bug fixes, small features with clear requirements, obvious improvements
- **No time estimates:** Don't ask or provide predictions about task duration

## Code Quality Standards

- **Keep it simple:** Lowest complexity needed, not cleverness
- **No unnecessary additions:** Don't add docstrings, comments, or type hints beyond what you modified
- **Comments only when needed:** Only when logic isn't self-evident
- **Error handling at boundaries:** Not for internal code paths that can't fail

## Git & Commits

- **Meaningful commits:** Reflect the "why" not just the "what"
- **Atomic changes:** One logical change per commit
- **No force pushes to main:** Always warn if requested
- **Stage selectively:** Avoid accidental inclusion of secrets or unrelated files

## Security Awareness

- Watch for: SQL injection, XSS, command injection, credential leaks
- Fix immediately if introduced, don't defer
- Validate user input and external API responses
- Don't commit secrets (.env, credentials files)
