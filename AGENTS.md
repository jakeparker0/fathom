# Fathom — agent instructions

Single-user personal finance app. Python 3.12, FastAPI (sync), React + Vite SPA, Postgres.
Domain terms (pay-cycle month, Transfer, Cover, Saver, Split, Reimbursement, Snapshot)
are defined in `CONTEXT.md`. Use them exactly; don't invent synonyms.

## Commands

- Install: `uv sync`
- Database: `docker compose up -d`
- Tests: `uv run pytest`
- Lint and format: `uv run ruff check --fix` then `uv run ruff format`
- Pre-commit must pass before any commit. Never use `--no-verify`.
<!-- Add migration and run-app commands once S1-25 and the walking skeleton land. -->

## Domain rules (non-negotiable)

- Transfers and Covers never count as spend, in any aggregation. There is no toggle.
- Spend is net of linked Reimbursements by default; gross is opt-in.
- All period boundaries come from the single date-range resolver. Never compute
  the 15th–14th pay-cycle (or any period) inline.
- Money Representation will be integers in cents (base units).

## Architecture

- Layering follows ADR-005. <!-- Name the layers and the allowed import direction in one line. -->
- `domain/` is pure: no database, HTTP or framework imports.
- Read the relevant ADR in `docs/adr/` before changing anything architectural.
  To deviate, propose a new ADR. Don't quietly work around one.

## Work I hand-write (do not implement)

These are learning and high-risk areas. Discuss, review and test them, but don't
write the implementation. Label related tickets `ready-for-human`.
- The transaction relationship model (Transfers, Covers, Splits, Reimbursements)
- The data model and schema design
- Balance forecasting
<!-- Keep in sync with S1-33. -->

## Secrets and config

- All config goes through the typed settings object. No `os.environ` reads elsewhere.
- Never read, print, log or commit `.env` or the Up token.

## Testing

- Every behaviour change ships with tests.
- Tests use the isolated test database fixture and committed fixtures.
  Never call the live Up API from tests.
<!-- Add fixture locations once S1-13 lands. -->

## Commits

- Reference the task or story ID in every commit message (e.g. `S1-36: …`, `ET-12: …`).

## Coding standards

<!-- S1-32: a handful of rules that apply to every edit (typing, naming, error handling).
     The full review checklist goes in docs/agents/, referenced not imported. -->


## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, using their default names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` at the repo root plus ADRs in `docs/adr/`. See `docs/agents/domain.md`.
