# S1-17 spec: AMEX and Bendigo fixtures, and the transaction-date rule

Status: draft, awaiting Jake's approval. Nothing below is implemented.
Tier: C (agent-built). The ADR is Jake's decision, already made in conversation.
Input: `column-mapping.md` in this directory (the findings and open questions).
Stories: S1-17.

## Goal

Close S1-17: the AMEX and Bendigo column mappings are documented (`column-mapping.md`),
the one cross-cutting decision is recorded as an ADR, and masked, committable test
fixtures exist for both sources, each produced by its own masking script.

## Deliverables

1. **ADR-012** (text below), added to `docs/adr/` on approval.
2. **`scripts/mask_amex_fixtures.py`**, writing `tests/fixtures/amex/`.
3. **`scripts/mask_bendigo_fixtures.py`**, writing `tests/fixtures/bendigo/`.
4. **`tests/test_mask_amex_fixtures.py`** and **`tests/test_mask_bendigo_fixtures.py`**.
5. `column-mapping.md` promoted with this spec. Ticking S1-17 in the vault when done.

The two scripts are separate on purpose. They share nothing but the primitives already in
`scripts/mask_fixtures.py` (`Masker`, `MaskConfig`, `MaskError`, `load_key`, the default
key and config paths), as `mask_cmc_fixtures.py` does. They do not import each other.

## ADR-012 (proposed text)

# ADR-012: Which date places a statement-import Transaction in a period

**Status:** Proposed
**Date:** 2026-10-19

### Context

AMEX exports two dates per row: `Date` (the purchase) and `Date Processed` (posting, 0 to
3 days later). Bendigo exports one posting date, plus, on a retail purchase only, the
purchase date embedded in a free-text reference column. All period boundaries come from
the Date-range resolver, so every imported Transaction needs exactly one date for the
resolver to place it. In the 99-row AMEX sample for 2025, 4 rows land in different
pay-cycle months depending on the date chosen: purchases on the 14th that post on the
15th.

### Options Considered

**Option A: Posting date everywhere.**
- Pros: Every source has one. Matches what the bank balance shows on that day.
- Cons: A purchase on the 14th lands in the next pay-cycle month. Disagrees with Up,
  where a card purchase carries its purchase time.

**Option B: Purchase date where the source has it, else posting date.**
- Pros: Spend lands in the period the money was spent in.
- Cons: Bendigo's purchase date is only in an inferred parse of a free-text column, from
  one sample row. Mixed rules per source.

**Option C: Purchase date for AMEX (a named column), posting date for Bendigo.**
- Pros: Uses a date only where the source gives it as a clean column. Bendigo is mainly
  savings, where the difference rarely matters.
- Cons: The rule differs by source.

### Decision

Option C. The importer stores the date a source names as the transaction date: AMEX
`Date`, Bendigo column 1 (posting date). `Date Processed` is kept as a second field and
never used for period placement. Bendigo's embedded purchase date is not parsed.

### Consequences

- The Transaction schema (S1-20, Tier A) needs a primary date and an optional posted date.
  This ADR decides which one the resolver reads, not the column names.
- A AMEX refund or payment is placed by its own `Date`.
- Reconciling a card statement by posting date needs the second field. It is kept for that.
- Revisit if Bendigo becomes a spending Account.

### Notes

Evidence in `column-mapping.md` (AMEX section, open question 1). Related: CONTEXT.md
"Date-range resolver".

## Masking scripts: shared behaviour

Follow `mask_cmc_fixtures.py`: deterministic keyed masking (`data/recon/.mask-key`),
`run(raw_dir, out_dir, key_path)` returning files written, `main()` with `--raw` and
`--out`, an unrecognised row shape aborts, nothing is written unless every file passes,
and a final scan aborts if any real replaced identifier survives in the output. Quirks
are preserved byte for byte. Equal real values mask to equal fake values across files.

## `scripts/mask_amex_fixtures.py`

Raw: `data/recon/raw/amex/` (`activity.csv`, `activity_2026_YTD.csv`). Out:
`tests/fixtures/amex/`, one masked file per raw file.

Behaviour:

- Parse with `csv` and `newline=''`, by header name. Reject a file whose header lacks
  `Reference` (matches the importer's rule).
- Preserve: header, column order, LF endings, quoting, embedded newlines in `Address` and
  `Town/City`, the apostrophe wrapper on `Reference`, row order.
- Mask `Reference`: keep the shape (`'AT` + 20 digits, `'S000` + digits, the 23-digit fee
  shape) and uniqueness. Keep the day-of-year digits consistent with `Date Processed`
  so the fixtures stay realistic.
- Mask `Description` and `Appears On Your Statement As` together so they stay equal:
  merchant names through `mask-config.json` `merchants`, otherwise `Merchant xxxx`. Keep
  the fixed-width padding and the town where it is public. Keep payment and fee
  descriptions as they are (`PayID Payment Received, Thank you`,
  `ONLINE PAYMENT RECEIVED - THANKYOU W<n>` with the `W` number masked, `MEMBERSHIP
  FEE`, `INSUFFICIENT FUNDS FEE`, `INTEREST CHARGES`).
- Mask `Address`, `Town/City`, `Postcode` to fixed fake values. Keep `Country`.
- Mask amounts through `Masker.cents` (sign, digit count, whole-dollar-ness kept). For a
  foreign row, recompute so `Commission` stays 3.00% (or 3.50%) of `Amount − Commission`
  and `Foreign Spend Amount` keeps its format, including the thousands separator.
- Keep dates, so the 14th/15th boundary rows and the 0 to 3 day lag survive.
- Keep the two same-day repeat purchases as two rows with different references.

Fixture shape: not the full 99 rows. A selected subset (about 25 rows) covering every
case above, chosen by the script from rules, not hand-picked IDs: one of each description
kind, every foreign row, both repeat pairs, the four boundary rows, a `Reference`-shaped
row of each type. The 7-row `activity.csv` is masked whole.

Hand-built, committed directly (not from the script, no real data): an AMEX refund
row, a 4-column file (to prove rejection), a file with the `Reference` column missing, and
the Qantas-style credit, treated as a refund.

## `scripts/mask_bendigo_fixtures.py`

Raw: `data/recon/raw/bendigo/` (`transactions_extended.csv`,
`transactions_extended_savings.csv`). The basic CSV and the QIF are not masked: the
extended files replace them. Out: `tests/fixtures/bendigo/`.

Behaviour:

- Parse positionally, 7 columns, no header. A row that is not 7 columns aborts.
- Preserve: no header, CRLF, every field quoted, row order, the date and amount format.
- Mask column 0 (BSB and account number) to one fake per real account.
- **Mask the E-Banking receipt number (col 5) identically in both files**, so each
  Transfer pair still matches on receipt, amount and date. Check this in `run` and abort
  if a pair no longer matches.
- Mask the account reference in col 6 on transfers (`00544909741401` and
  `0054490974NA01`): keep the shape and the different tail per account.
- Mask the Osko nickname-and-id in col 5 (`Savings 924313840`): keep the nickname, mask the
  9-digit id. Mask payer or payee names in col 6, but keep `CMC`.
- Mask BPAY biller reference in col 6. Keep the biller kind `BPAY TO: TAX OFFICE
  PAYMENTS`, which is public.
- Mask `RETAIL PURCHASE` merchant text, and the `DDMM AUD<amount>` in col 6 so it
  matches the masked amount.
- Mask amounts through `Masker.cents`, with the equal and opposite transfer legs kept equal
  and opposite. Zero amounts stay zero.
- Keep `INTEREST` and `REWARD RECEIVED` rows (kind, codes, fixed text).
- Keep dates, type codes, and kind labels.

Hand-built, committed directly: a file with a header row (to prove rejection), an amount
with a thousands separator (`"1,234.56"`), and two rows identical on every column.

## Tests

Per script, using a small hand-written raw input in `tmp_path` (as
`test_mask_cmc_fixtures.py` does), never the real files. Named for behaviour. Cover:

- Output carries none of the real identifiers seeded in the input.
- Same real value masks to the same fake across rows and across files.
- Quirks preserved (AMEX embedded newlines and apostrophe references; Bendigo no header,
  CRLF, full quoting).
- AMEX: commission relationship holds after masking; repeat purchases stay two rows;
  `Reference` shapes kept; header without `Reference` aborts.
- Bendigo: transfer pairs still match across the two files; an unmatched pair aborts;
  a row of the wrong width aborts.
- An unrecognised description aborts and nothing is written.

## Out of scope

- The importers, the Transaction schema (S1-20, Tier A), and dedupe or sync (Tier A).
  The scripts only document facts; the dedupe design is Jake's.
- Parsing Bendigo's embedded purchase date.
- Masking the basic Bendigo CSV and the QIF.
- Re-exporting 2026 AMEX data.

## Open questions

Carried from `column-mapping.md`: refunds, cheques, fees and international transfers on
Bendigo are unobserved, and the Bendigo type-code numerics (`WDL52` vs `WDL53`, the `06`
and `10` suffixes) are unexplained. Neither blocks the fixtures.
