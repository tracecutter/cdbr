# AGENTS.md

## Project Overview

`cdbk` is a Python command-line utility for solving **Codeword / Code Break** crossword puzzles. It is built using the **npkg ecosystem**, an opinionated collection of tools, conventions, and reusable infrastructure for developing, documenting, testing, and distributing Python applications.

The project was bootstrapped from `pkit-cmd`, an npkg prototype project, by cloning and renaming its established application structure. The precise fork history and current package layout should be confirmed from the repository rather than assumed.

This document defines the project's engineering philosophy, puzzle semantics, architectural boundaries, development priorities, and rules for AI coding agents. It is a guide to deliberate evolution, not authorization to implement the entire roadmap at once.

## 1. The npkg Way

The npkg ecosystem follows a **prototype-and-fork development model**.

Rather than starting each project from an empty directory, new projects are created by cloning and renaming an established prototype containing a working application structure, build system, documentation pipeline, test infrastructure, and distribution machinery.

The prototype is deliberately opinionated. A newly forked project inherits more functionality than it initially needs. This is intentional.

Some inherited capabilities may appear unused, redundant, or unnecessarily elaborate when viewed in isolation. They are not necessarily technical debt. Think of them as **inherited candy**: useful, tested capabilities already available when the application grows into them.

### Guiding principles

- Prefer established npkg conventions over introducing alternative frameworks.
- Preserve inherited capabilities unless there is a concrete reason to change them.
- Distinguish demonstration functionality from reusable infrastructure.
- Extend existing mechanisms before creating parallel implementations.
- Avoid architectural simplification merely for the sake of reducing code.
- Favor small, composable components and explicit interfaces.
- Keep projects recognizable as members of the npkg ecosystem.

The objective is not the smallest possible codebase. It is to build useful applications efficiently on a consistent, capable foundation.

## 2. Understand Before Modifying

Before proposing structural changes, examine the existing implementation and its conventions. Distinguish three categories of code:

## 3. Environment integrity

AI agents must not install, upgrade, uninstall, relink, or otherwise modify Homebrew packages, system interpreters, global Python packages, or shell configuration without explicit user authorization. All dependency installation and environment changes must be confined to explicitly approved project-local virtual environments.

### Infrastructure

Reusable mechanisms inherited from npkg, including:

- CLI initialization and dispatch
- Application context
- Public and internal API conventions
- Documentation generation
- Build and packaging infrastructure
- Testing utilities
- Logging, tracing, and telemetry support

These should generally be preserved.

### Demonstration code

The prototype includes example functionality intended to demonstrate available capabilities. For example, `pkit-cmd` includes Click options illustrating argument types, defaults, flags, and validation mechanisms. These are examples, not application requirements; review and adapt them as `cdbk` takes shape.

### Application code

The functionality specific to `cdbk`. Concentrate new development here while leveraging inherited infrastructure.

**Preserve capability. Replace demonstration. Build the application.**

## 3. Command-Line Interface

`cdbk` is a CLI-first application built using Click. Its command-line interface is a primary design concern, not an afterthought.

An early priority is to establish correct arguments and options for puzzle input, solving, and output. Do not assume a particular command syntax until it has been discussed and reconciled with the inherited CLI.

### Conventions

- Preserve the existing Click-based command architecture.
- Maintain separation between option declarations, command dispatch, and implementation.
- Prefer clear, consistent option names and semantics.
- Use Click's native validation and type mechanisms where appropriate.
- Preserve established npkg conventions for common options.
- Do not introduce another CLI framework.
- Keep the public interface small and understandable.
- Keep solver logic usable independently of Click and terminal output.

Do not assume an inherited option is either necessary or disposable without examining its purpose.

## 4. Documentation Is Part of the Code

Documentation is a first-class component of the npkg development process. The ecosystem uses **psym** to keep documentation close to implementation. Structured documentation embedded in source material is projected into multiple publication formats, including:

- `README.md`
- Unix manpages
- Sphinx documentation
- HTML documentation through Sphinx

This reduces duplication and keeps documentation synchronized with implementation.

### Documentation conventions

- Follow the existing psym documentation structure.
- Update canonical documentation sources rather than generated output.
- Do not replace psym with an independent documentation system.
- Do not manually maintain parallel copies of generated documentation.
- Keep CLI help, examples, and user documentation consistent.
- Use the existing documentation build and synchronization targets.
- Document puzzle semantics and solver limitations alongside their implementation.

Documentation changes should accompany user-visible behavior changes.

## 5. Build and Development Tooling

The repository inherits a reusable Makefile and standardized workflow. Retain this infrastructure as close to its inherited form as practical.

The established toolchain includes:

- **Make** for build orchestration
- **ruff** for linting
- **black** for formatting
- **mypy** for static type checking
- **pytest** and the inherited test harness
- **pfig** for configuration and environment validation
- **psym** for documentation generation

### Working conventions

- Prefer existing Makefile targets over ad hoc shell commands.
- Avoid rewriting the Makefile for application-specific convenience.
- Add small, focused targets only when necessary.
- Reuse inherited testing utilities and fixtures.
- Maintain compatibility with existing linting and formatting configuration.
- Preserve packaging and distribution mechanisms.
- Do not introduce competing tools without demonstrated need.

The Makefile is infrastructure, not disposable scaffolding.

## 6. Python Conventions

Follow established repository conventions:

- Four-space indentation and PEP 8
- Type annotations for public interfaces and nontrivial internal functions
- Black-compatible formatting and Ruff-compliant code
- Mypy-compatible typing
- Clear module boundaries and small, testable functions
- Explicit error handling
- Minimal unnecessary dependencies

Prefer existing package structure and idioms over new organizational patterns. Avoid speculative abstractions.

## 7. Puzzle Semantics

### Standard Codeword puzzle

The initial target is the numbered crossword-like puzzle shown in the supplied reference photographs, not a Mastermind-style guessing game.

A puzzle comprises:

- A rectangular grid of blocked and playable cells.
- A symbol (normally an integer from 1 through 26) in every playable cell.
- Horizontal and vertical runs of playable cells forming word slots.
- A substitution mapping from symbols to letters.
- Zero or more supplied symbol-to-letter clues.

For the standard 26-symbol English variant:

1. Every occurrence of a symbol represents the same letter.
2. Different symbols represent different letters.
3. Each symbol maps to exactly one letter, and each letter to exactly one symbol: the mapping is a **bijection** between 1–26 and A–Z.
4. Supplied clues are fixed constraints, not guesses.
5. Blocked cells are separators, not symbols.
6. Horizontal and vertical slots share the same global mapping.

A **structurally valid puzzle** satisfies the representation and clue invariants. A **substitution-consistent assignment** satisfies the mapping constraints. A **lexically accepted solution** additionally satisfies an explicitly selected vocabulary policy. These are distinct claims.

Word-slot extraction rules (including minimum length and whether one-letter runs count) must be specified and tested rather than assumed. The 15×15 dimensions of the supplied examples are fixtures, not a hardcoded engine limit.

### Solver state and evidence

Distinguish clearly among:

- **Given**: a fact encoded in the input puzzle.
- **Forced deduction**: an assignment entailed by the stated constraints and lexical policy.
- **Candidate**: a possible assignment or word compatible with current constraints.
- **Hypothesis**: a provisional assumption used in search.
- **Heuristic preference**: a ranking or suggestion, not a proof.
- **Verified solution**: a complete assignment checked against the declared constraints and vocabulary policy.

A contradiction must be reported as a contradiction under the active assumptions and vocabulary policy; dictionary omissions must not silently be presented as mathematical impossibility.

## 8. Solver Architecture

Separate responsibilities conceptually; do not prematurely create a framework of classes or packages for each one.

### Puzzle model

Represent grid topology, symbols, slots, and fixed clues. Prefer immutable values or controlled state transitions. Preserve the distinction between source puzzle data and derived solver state.

### Constraint engine

Enforce the global bijection, propagate assignments and exclusions, and detect inconsistencies. Its correctness must not depend on CLI formatting.

### Lexical engine

Provide word candidates for numbered slot patterns under current constraints. Keep vocabulary sources pluggable and explicit: normalization, inflections, proper nouns, unusual words, and exclusions can materially affect results. Record dictionary identity/version where practical.

### Search engine

Explore unresolved assignments systematically, with reversible hypotheses/backtracking. Detect zero, one, or multiple solutions under declared limits. Never claim uniqueness when search was stopped early.

### Explanation and provenance

Make it possible to report why an assignment was made, including source clues, slot constraints, vocabulary dependence, and search assumptions. Prefer a compact, reproducible trace over opaque assertions. Full proof-trace infrastructure need not be built in milestone one, but the architecture must not conflate guesses with deductions.

### Presentation

Provide readable text output for puzzle grids, partial assignments, ambiguity, contradictions, and solutions through the inherited CLI architecture. Human-assisted solving is a possible later extension.

## 9. Reference Puzzles and Input Data

Two supplied photographs show 15×15 puzzles identified by printed page numbers **5** and **7**. Their visible initial reference-grid mappings are:

- Page 5: `5=U`, `10=T`, `20=G`.
- Page 7: `5=S`, `10=U`, `26=Z`.

These are **different puzzles with different substitution mappings**. Never combine their assignments into one puzzle state.

Eventually transcribe the photographs into machine-readable fixtures. Preserve:

- Original cell positions, blocks, and symbols.
- Supplied clues separately from inferred assignments.
- Puzzle provenance and any transcription uncertainty.
- Expected results separately from source inputs.

Verify transcriptions independently before treating them as authoritative regression data. Do not treat a solver's own output as independent ground truth. Start with small, hand-constructed fixtures for invariant tests.

The initial input format should be human-readable, deterministic, easy to diff, and suitable for tests. Select its precise syntax deliberately; do not introduce image recognition into the first milestone.

## 10. Testing and Validation

Use inherited npkg testing infrastructure. The standard project-wide validation command is:

```bash
make check
```

Documentation can be built and synchronized using:

```bash
make docs
make docs-sync
```

Confirm the targets exist and work in the cloned repository; report failures accurately.

Tests should cover:

- Parsing, dimensions, blocked cells, and slot extraction.
- Symbol range, fixed clues, and bijection invariants.
- Repeated-symbol patterns within and across slots.
- Candidate-word compatibility and lexical normalization.
- Constraint propagation and contradiction detection.
- Search backtracking, completeness, ambiguity, and limits.
- Separation of givens, deductions, hypotheses, and heuristics.
- Stable output and CLI error behavior.
- Independently verified published-puzzle fixtures once available.

Add tests for new behavior, preserve existing tests unless behavior intentionally changes, and reuse inherited helpers. Never claim a test passed unless executed.

## 11. Development Priorities

The project is intentionally exploratory. The exact input grammar, API, search strategy, and vocabulary source are not yet settled.

### Milestone 1 — Foundations

1. Inspect the forked repository and identify inherited infrastructure versus demonstrations.
2. Agree on minimal CLI commands/options and a canonical text puzzle format.
3. Implement and test a read-only puzzle parser/model and slot extraction.
4. Implement and test the bijective mapping and fixed-clue constraints.
5. Print a faithful partial decoding of a puzzle.

### Milestone 2 — Solving

1. Introduce an explicit lexical source and candidate matching.
2. Propagate constraints across slots.
3. Add deterministic search/backtracking with limits.
4. Report contradictions, ambiguity, and verified solutions.
5. Add small constructed tests and checked reference fixtures.

### Milestone 3 — Assistance and explanation

Explore ranked suggestions, human-in-the-loop interaction, explanation traces, alternate dictionaries, and performance improvements after the core semantics are verified.

**Out of initial scope:** OCR/photo ingestion, graphical interfaces, network services, and automatic puzzle acquisition. Keep them possible without making them prerequisites.

Do not prematurely introduce databases, elaborate plugin frameworks, or external solving services.

## 12. Working With AI Coding Agents

AI agents are encouraged to investigate, question, and recommend improvements, grounded in repository architecture and project requirements.

### Expected behavior

- Read relevant code and documentation before proposing changes.
- Understand inherited npkg mechanisms before modifying them.
- Distinguish deliberate architecture from accidental complexity.
- State the semantic purpose of a proposed change and affected invariants.
- Prefer incremental, reviewable changes and explicit verification.
- Preserve existing functionality unless instructed otherwise.
- Ask before significant architectural decisions or unresolved semantic choices.
- Do not perform broad refactoring as a side effect of focused work.
- Do not modify unrelated files.
- Do not commit, tag, publish, or push changes without explicit authorization.
- Report what changed, what was verified, and what remains uncertain.
- Never silently promote a heuristic guess into a proven result.

### Architectural criticism

Existing design decisions are not beyond criticism. If a mechanism is demonstrably problematic, identify the problem and propose an improvement. Do not recommend removal merely because functionality is not immediately used by `cdbk`.

The right question is not *“Can this code be removed?”* but *“Does changing this code improve the application without undermining the benefits of the shared ecosystem?”*

## 13. Engineering Philosophy

The npkg ecosystem values continuity, composability, accumulated engineering investment, and human-understandable reasoning.

Treat development as a sequence of **semantically described, implemented, and verified transformations**. Explanations are not decoration: they make it possible to understand why a result should be trusted. For the solver itself, preserve the distinction between logical consequence, lexical assumption, and search hypothesis.

New applications should develop their own identities while retaining the advantages of a shared foundation.

**Preserve capability. Replace demonstration. Build the application.**
