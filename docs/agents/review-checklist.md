# Review checklist

What a reviewer checks a diff against. Each item is a yes-or-no question with the
document that owns the rule: read that document when an item is in doubt, and cite it
in the finding.

## How to review

1. Read the ticket or spec the diff implements, then the full diff.
2. Answer every item below as pass, fail or n/a. The review is done when every item
   has an answer, not when the first failure is found.
3. Report each fail as `file:line`, the item it breaks, and the owning document.
   Mark it **blocking** unless the item says otherwise.
4. Report anything the diff does that the ticket did not ask for.

Ruff and pre-commit own formatting, import order and lint. Review what they cannot see.

## Scope

- [ ] The diff does what the ticket asks and nothing else.
- [ ] Tier A paths (`.claude/hand-write-paths.txt`) hold no generated implementation.
      Tests and review comments for them are fine. (ADR-011)
- [ ] An architectural change comes with a new or amended ADR. A diff that works around
      an ADR fails. (`docs/adr/`)

## Layering (ADR-005)

- [ ] Every new file sits in the layer its content belongs to, in a module named for
      its feature (`api/transactions.py`, `services/transactions.py`).
- [ ] Imports run `api` → `services` → `repositories` only.
- [ ] Routers hold request and response wiring only, and reach data through a service.
- [ ] Every SQLAlchemy query is in `repositories/`.
- [ ] Services return Pydantic schemas. ORM models stay at or below the service layer.
- [ ] `domain/` takes and returns plain values: its imports are the standard library
      and other `domain/` modules.
- [ ] `providers/` is imported by services only.
- [ ] Jobs and importers call services.

## Domain rules (`AGENTS.md`, `CONTEXT.md`, ADR-009)

- [ ] Every Spend aggregation excludes Transfers, Partner transfers and Cover transfer
      legs, with no parameter that includes them.
- [ ] Spend is net of linked Reimbursements unless the caller asks for gross.
- [ ] Spend uses the attributed Account and that Account's share. The share comes from
      one place: a literal `0.5`, `/ 2` or `50` beside a balance, Spend or Income fails.
- [ ] Every period boundary comes from the Date-range resolver. Date arithmetic on the
      15th, the 14th or a pay day outside it fails.
- [ ] Money amounts are integer cents end to end: `int`, `BIGINT`, a JSON number. A
      `float` or `Decimal` holding a money amount fails, including in tests. (ADR-004)
- [ ] Unit prices, units held, rates and percentages are `Decimal` / `NUMERIC`.
- [ ] A non-integer result becomes cents through the single rounding function in
      `domain/`. `round()`, `int()` or `//` on a money amount anywhere else fails.
- [ ] Each rule above is implemented once. A second implementation fails even when it
      is correct.
- [ ] Identifiers, test names and messages use `CONTEXT.md` terms, including the
      distinctions it draws (Refund and Reimbursement, Transfer and External payment,
      Cover and Partner-covered purchase).
- [ ] The diff assumes nothing `CONTEXT.md` marks **Open**.

## Sync only (ADR-002)

- [ ] Every function is a plain `def`, and every client and session is synchronous.
      `async def`, `await` or `httpx.AsyncClient` fails.

## Coding standards (`AGENTS.md`)

- [ ] Signatures are fully annotated, with no `Any` and no bare `dict` or `list` in a
      public signature.
- [ ] A closed set of values is a `StrEnum`.
- [ ] Each `# type: ignore` and `# noqa` names its code and gives a reason on the line.
- [ ] Errors are specific exception types raised where the problem is found. Only `api/`
      turns them into HTTP responses.
- [ ] Every `except` handles the error or re-raises it. Catch-and-continue fails.
- [ ] External data (Up payloads, CSV rows, prices) is validated into a typed model in
      `providers/` or the importer before a service sees it.

## Config and secrets (`AGENTS.md`)

- [ ] Config is read through `get_settings()`. `os.environ` or `os.getenv` outside
      `config.py` fails.
- [ ] Secrets are `SecretStr`, unwrapped only at the point of use, and absent from logs,
      exception messages, test output and fixtures.
- [ ] `.env` is untouched and unread.

## Jobs (ADR-006)

- [ ] Each job is a standalone entry point with no scheduling logic inside it.
- [ ] Running the job twice changes nothing the second time, and a test proves it.
- [ ] The job takes the advisory lock and records its outcome in `job_run`, failures
      included.

## Tests (`AGENTS.md`)

- [ ] Every behaviour change has a test that fails without it.
- [ ] `domain/` tests run with no database. Database tests use the isolated fixture.
- [ ] Up responses come from `tests/fixtures/up/`. A network call from a test fails.
- [ ] Tests assert behaviour through the public interface, with names that state the
      behaviour (`test_blank_secret_is_rejected`).

## Frontend (ADR-003)

- [ ] The client renders values the API computed. Currency formatting, period
      boundaries, net-versus-gross and share arithmetic in TypeScript fail.
- [ ] API types are generated from the OpenAPI schema, and a response schema change
      regenerates them in the same diff.

## Commits (`AGENTS.md`)

- [ ] Every commit message carries the task or story ID.
- [ ] Pre-commit passed without `--no-verify`.

## Before merge (Jake, not the review agent)

- [ ] Tier B (`Mode: design-led`): I explained the diff to the agent without looking at
      it, and the agent found no gaps. Anything I got wrong blocks the merge. (ADR-011)
