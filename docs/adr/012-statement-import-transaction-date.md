# ADR-012: Which date places a statement-import Transaction in a period

**Status:** Accepted
**Date:** 2026-10-20

## Context

AMEX exports two dates per row: `Date` (the purchase) and `Date Processed` (posting, 0 to 3 days later). Bendigo exports one posting date, plus, on a retail purchase only, the purchase date embedded in a free-text reference column. All period boundaries come from the Date-range resolver, so every imported Transaction needs exactly one date for the resolver to place it. In the 99-row AMEX sample for 2025, 4 rows land in different pay-cycle months depending on the date chosen: purchases on the 14th that post on the 15th.

## Options Considered

### Option A: Posting date everywhere
- Pros: Every source has one. Matches what the bank balance shows on that day.
- Cons: A purchase on the 14th lands in the next pay-cycle month. Disagrees with Up, where a card purchase carries its purchase time.

### Option B: Purchase date where the source has it, else posting date
- Pros: Spend lands in the period the money was spent in.
- Cons: Bendigo's purchase date is only in an inferred parse of a free-text column, from one sample row. Mixed rules per source.

### Option C: Purchase date for AMEX (a named column), posting date for Bendigo
- Pros: Uses a date only where the source gives it as a clean column. Bendigo is mainly savings, where the difference rarely matters.
- Cons: The rule differs by source.

## Decision

Option C. The importer stores the date a source names as the transaction date: AMEX `Date`, Bendigo column 1 (posting date). `Date Processed` is kept as a second field and never used for period placement. Bendigo's embedded purchase date is not parsed.

## Consequences

- The Transaction schema (S1-20, Tier A) needs a primary date and an optional posted date. This ADR decides which one the resolver reads, not the column names.
- An AMEX refund or payment is placed by its own `Date`.
- Reconciling a card statement by posting date needs the second field. It is kept for that.
- Revisit if Bendigo becomes a spending Account.

## Notes

Evidence is in `.scratch/s1-17-amex-bendigo-export/column-mapping.md` (AMEX section, open question 1). Related: CONTEXT.md "Date-range resolver".
