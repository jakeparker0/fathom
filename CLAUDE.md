@AGENTS.md

## Claude Code

### Rules
1. Before non-trivial work, recommend running `/grill-with-docs`. In it, follow the
   answer-first rule in `AGENTS.md`: on Tier A and B questions, wait for Jake's answer.
2. Review generated code with a fresh sub-agent, against `docs/agents/review-checklist.md`.
3. Use plan mode for anything touching schema or migrations.
4. Record decisions in ADRs, using the provided template (`docs/adr/000-template.md`), not auto-memory
5. Never work around the hand-write guard hook (`.claude/hooks/guard_hand_write.py`).
   If it blocks something that isn't Tier A, say so and suggest fixing the glob in
   `.claude/hand-write-paths.txt`.
