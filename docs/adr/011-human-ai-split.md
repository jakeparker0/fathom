# ADR-011: Human versus AI split of the work

**Status:** Proposed
**Date:** 2026-10-14

## Context

Fathom is a learning project and, from v1 (target ~22 Jan 2027), public evidence for a job search. Both goals fail if the agent ends up building everything: I learn nothing, and I can't defend the code in an interview.

The first full run of the build loop (S1-06) showed how it slips. `/grill-with-docs` recommended an answer to every design question and I accepted each one. The tickets went out `ready-for-agent`. A week later I couldn't explain the test database design, even though the previous split listed test strategy as hand-written. That split also existed in two different versions (`AGENTS.md` and the project note), and nothing enforced either one.

The forces at play:

- **Learning:** the code that teaches the most is the code with real design tension: the data model, the relationship rules and sync.
- **Deadline:** about 14 weeks of evenings to a live v1. If everything is hand-written, v1 won't ship.
- **Momentum:** writing docs and boilerplate drains my motivation, and I'm likely to give up on the hard parts when tired.
- **Interviews:** I need to be able to explain any part of the system without notes.

## Options Considered

### Option A: Hand-write everything important, with no enforcement
- Pros: maximum learning on paper.
- Cons: the list is too long for the deadline, and with nothing enforcing it, it doesn't hold. S1-06 already proved that.

### Option B: Let the agent build everything, and I review
- Pros: fastest route to v1.
- Cons: reviewing isn't learning. The S1-06 result is the evidence. Fails the interview test.

### Option C: Three tiers, a short hand-write list, and guards that don't depend on willpower
- Pros: hand-writing goes where the learning and the risk are. Everything else moves fast. The guards work when I'm tired.
- Cons: some setup (the hook, the label line), and the tiers need maintaining as modules appear.

## Decision

**Option C.** Every ticket belongs to one of three tiers:

| Tier | Who designs | Who writes the code | Label |
|---|---|---|---|
| **A: Hand-write** | Me | Me. The agent asks questions, gives hints and reviews | `ready-for-human` |
| **B: Design-led** | Me, answering first in grilling | Agent | `ready-for-agent` + `Mode: design-led` |
| **C: Agent-built** | Agent, I approve the spec | Agent | `ready-for-agent` |

**Tier A** (the list in `AGENTS.md` and `.claude/hand-write-paths.txt` is the source of truth):
- Data model and schema, including migrations (S1-20, S1-22 to S1-25)
- The transaction relationship model: Transfers, Covers, Splits, Reimbursements (S1-21)
- Sync and idempotency: fetch orchestration, dedupe, the advisory lock
- Balance forecasting (post-v1)

**Tier B:** the error model, the CI pipeline, AWS deployment, the Up API client.

**Tier C:** frontend, CRUD endpoints, CSV parsing, test fixtures and setup, boilerplate, and first drafts of docs.

The test for Tier A: an interviewer would dig into it, and it would be expensive to redo if I didn't understand it. Something that only meets the first test can be Tier B, because what I'll be asked to defend is the design.

**The rules:**
1. **The guard hook.** A `PreToolUse` hook blocks agent edits to Tier A paths, including shell writes and generating migrations.
2. **Answer first in grilling.** For Tier A and B questions, the agent asks and waits for my answer before giving its own view. Tier C questions can come with a recommendation.
3. **The hint ladder** on Tier A, in this order: a question, then the concept, then where to look, then pseudocode. Never real code. I only move up a rung after a 20–25 minute attempt, logged in the ticket's Comments.
4. **Explain it back before merging** (Tier B): I explain the diff to the agent without looking at it, and anything I get wrong blocks the merge.
5. **Moving work out of Tier A costs something:** I relabel the ticket, write the reason in its Comments, and add a line to the README's "Moved out of hand-written" list.
6. **Decide the deadline fallback in advance.** At the checkpoint at the end of November I decide which Tier A items drop to B if I'm behind. S1-21 and sync stay in Tier A regardless. I never reclassify in the middle of a session.

## Consequences

- The agent writes the docs I'd otherwise stall on (Tier C). That includes this ADR. I review it and accept it.
- Tier A work is slower, by design. The deadline pressure is handled by rule 6, not by giving up in the moment.
- Module names for Tier A are fixed before the code exists (`models/`, `domain/relationships`, `services/sync`, `jobs/sync`). New Tier A code must use these names or extend `hand-write-paths.txt`.
- The hook is a speed bump, not a sandbox. A Bash command that hides its target, or me pasting the agent's code in myself, gets past it. Rules 3 to 5 cover that by making it visible.
- S1-06 is recorded as agent-built and agent-designed (ADR-010). It isn't being rewritten.
- The tests for Tier A code can be agent-written once my implementation exists. Tests that try to break my code are useful review.

## Notes

- Revisit at the end-of-November checkpoint, and again when S1-38 settles the v1 scope.
- If the hook gets in the way of a legitimate non-Tier A edit, fix the glob, don't disable the hook.
