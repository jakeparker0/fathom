# ADR-001: Branching Strategy

**Status:** Accepted
**Date:** 2026-09-07

## Context

Fathom is a single-developer project. A branching strategy needs to be picked before meaningful commit history accumulates, since retrofitting one later is disruptive. The project will also lean on AI coding agents to generate a significant portion of the codebase, which raises the value of having a review checkpoint before code lands on the main line, even without a second human reviewer.

## Options Considered

### Option A: Git Flow
- Pros: Well-documented, structured around formal releases, clear separation of `develop`/`release`/`hotfix` branches.
- Cons: Designed for multi-developer teams with scheduled releases. The branch overhead (`develop`, `release/*`, `hotfix/*`) is ceremony with no payoff for a solo, continuously-deployed personal app.

### Option B: Trunk-based development with short-lived feature branches
- Pros: `main` stays always-deployable. Feature branches are small and short-lived, merged via PR even when solo, which gives CI (S1-29) and AI-generated code a review checkpoint. Minimal overhead, matches solo/local-first project shape.
- Cons: No formal release branch if multiple in-flight versions ever needed to be supported simultaneously — not a real concern for this project.

### Option C: No branching (commit directly to `main`)
- Pros: Simplest possible workflow, zero ceremony.
- Cons: No checkpoint before code lands on main — meaningful given a large share of code will be AI-generated and benefits from a review pause. No CI gate opportunity via PR.

## Decision

Trunk-based development with short-lived feature branches, merged into `main` via pull request.

- `main` is always deployable.
- Feature branches are named `feature/<sprint-task-ref>-<short-description>` (e.g. `feature/s1-04-env-config`), keeping traceability back to the Sprint Planning workbook.
- Branches live days, not weeks, consistent with the S/M task sizing used across the sprint plan.
- No `develop` branch and no long-lived release branches.

## Consequences

- Every change, including AI-generated code, passes through a PR — this is what makes the S1-29 CI pipeline (lint, type checks, tests) an actual gate rather than a passive check against history.
- Branch naming stays traceable to the Sprint Planning workbook's task refs, making it easy to reconcile git history against planned work.
- No overhead from managing parallel release lines — appropriate since Fathom has one deployment target (the OCI instance) and no external users depending on version stability.
- If the project ever grew beyond single-developer, single-deployment-target use, this strategy would need revisiting — not a concern in the current scope.

## Notes

Decided as part of S1-01 (repo creation task).