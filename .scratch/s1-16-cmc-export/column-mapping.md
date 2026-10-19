# CMC Markets export: column mapping (S1-16)

Status: draft. Branch `feature/s1-16-cmc-markets-export`. Commits: `S1-16: …`.

Real exports captured 2026-10-17 for FY 2025-26 (01/07/2025 to 30/06/2026), one
trading account. Raw files live in `data/recon/cmc/` (gitignored, never committed).
Masked copies will go to `tests/fixtures/cmc/`.

## Summary

Two exports are enough to import everything CMC gives us:

| Export | Used for | Importer role |
|---|---|---|
| `Confirmation.csv` | Trades | Primary source. One row per executed order, fees split out. |
| `CashTransactionSummary-<acct>-<from>-<to>.csv` | Dividends, deposits | Only source of dividend credits and of cash deposits. |

Reviewed and rejected, see the last section: `Statement.csv`, `Holdings.csv`, the
EOFY PDF.

Dedupe key for a Trade: the **Confirmation Number**. It is the `Reference` in
`Statement.csv` and the trailing number on a trade line in the cash summary. All 34
FY trades matched across the three on reference, code, quantity, price and
consideration.

## Confirmation.csv

Dialect: UTF-8, no BOM, header unquoted, comma-separated, dates `YYYY-MM-DD`, no
trailer or blank rows.

| Column | Example | Maps to | Notes |
|---|---|---|---|
| Account Number | `822650` | (account lookup) | Identifies the CMC account. Not stored on the Trade. |
| Account Name | person's name | ignored | Personal data. Never stored or logged. |
| AsxCode | `IVV` | `Trade.code` | Plain ticker. No parsing needed. |
| Confirmation Number | `38553674` | `Trade.external_ref` (unique) | Dedupe key. Integer-shaped, store as text. |
| Order Type | `Buy` / `Sell` | `Trade.side` (`StrEnum`) | Only these two seen. |
| As at Date | empty | ignored | Empty in every row. |
| Trade Date | `2026-06-19` | `Trade.trade_date` | Cost-basis and Snapshot date. |
| Settlement Date | `2026-06-23` | `Trade.settlement_date` | Usually T+2, not always. Matches the cash movement date. |
| Avg Price | `"63.5200 AUD"` | ignored | Text duplicate of Price, with currency. |
| Exch Rate | `1.000000` | ignored (v1) | Always 1 for ASX. International trades need it later. |
| Price | `63.52000000` | `Trade.unit_price` | `Decimal`, 8 dp. Never a float. |
| Quantity | `3.000000000` | `Trade.quantity` | `Decimal`, 9 dp. Whole numbers so far. |
| Brokerage | `10.00` | `Trade.brokerage_cents` | Excludes GST. Sells only so far. |
| GST | `1.00` | `Trade.gst_cents` | GST on brokerage and other fees. |
| Stampduty | `0.00` | ignored (v1) | Zero throughout. |
| Application Fee | `0.00` | ignored (v1) | Zero throughout. |
| OtherCharge | `0.00` | `Trade.other_fees_cents` | Zero throughout. |
| Fee | `0.00` | `Trade.other_fees_cents` | Zero throughout. |
| Discount | `0.00` | ignored (v1) | Zero throughout. |
| Consideration | `474.1000` | `Trade.consideration_cents` | 4 dp in the file. Round once, via the `domain/` rounding function. |
| Reverse Confirmation Number | `0` | cancellation link | Always `0` so far. A reversal's format is unobserved. |

Validation to run on import (a failure rejects the row):

- Buy: `consideration == quantity × price + brokerage + GST + other fees`.
- Sell: `consideration == quantity × price − brokerage − GST − other fees`.
- Compared in cents after the single rounding step. All 34 FY rows satisfy this.

Observations:

- Brokerage so far is $10.00 + $1.00 GST on every sell and $0 on every buy. Only two
  sells exist, both small. Treat fees as stored values, never as a constant.
- `Quantity` is 9 dp, so fractional units appear to be supported by the format.
- Price precision matters: one buy is at 4 dp (`9.9251`). `Decimal` is required.
- Rows come newest first. Order must not be relied on.

## CashTransactionSummary-<acct>-<from>-<to>.csv

Dialect: UTF-8 **with BOM**, every field quoted, dates `DD/MM/YYYY`, columns
`Date, Description, Debit $, Credit $, Balance $`. Amounts have no thousands
separator in this export. The filename carries the account number and the period.

Structure:

- First row `OPENING BALANCE`, last data row `CLOSING BALANCE`, both with the
  balance in the `Balance $` column and no debit or credit.
- Then a blank line, then a `TOTALS` row with an empty date and the total debits and
  credits.
- `Balance $` is a running cash balance. It reconciled exactly across the FY.

Each data row is classified by `Description`:

| Pattern | Meaning | Importer action |
|---|---|---|
| `OPENING BALANCE`, `CLOSING BALANCE`, `TOTALS`, blank line | Structure | Skip. Use them to validate: opening + credits − debits == closing. |
| `JNL<n> ]NPP VRN:<n> DEP:<n>` (credit) | Deposit from the bank | Candidate Transfer, to be matched with the bank-side leg. Never counts as spend or Income. |
| `Bght <q> <CODE> @ <price> AUD <ref>` / `Sold …` | Trade cash leg, dated at settlement | Skip. Cross-check the `<ref>` against a Confirmation. |
| `EXTERNAL - DIV <CODE> <text>` (credit) | Dividend or distribution receipt | Dividend candidate. See the gap below. |
| `EXTERNAL - <MMMYY>/<n> TRANS…` (credit) | Receipt with no security named | Unclassified. Do not guess. |
| `Statement Balance Alignment` (credit) | CMC adjustment | Unclassified. Do not treat as income. |

Dividend row detail:

- The description is truncated at 31 characters after `EXTERNAL - `
  (`DIV IVV PAYMENT TRAN`, `DST DIV A20`). The ticker is the token after `DIV`, with
  `DST`/`PAYMENT` wording varying by issuer.
- The row has a date (pay date) and a net cash amount. Nothing else.

## Known gaps (dividends)

The importer can get **pay date, ticker and net cash amount** for a Dividend. It
cannot get any of these from CMC:

- Franking credits (CONTEXT.md says a Dividend is recorded with them).
- Per-unit amount, ex-date, record date, or the units held at the ex-date.
- Whether a payment is a dividend or a distribution, or whether it was reinvested.
- The security, when the line is an `OCT25/…` receipt or an alignment credit.

Neither the EOFY statement nor any export checked has a domestic dividend section.
The statement's only dividend section is for international shares, and it was empty.

Candidates, to be decided in S1-23 and a follow-up ticket:

1. Import cash receipts as Dividends with franking unknown, and flag them.
2. Add a manual entry form for franking, using the annual tax statement or the
   registry or fund manager.
3. Do nothing at v1 beyond showing the cash receipts.

## Open questions

1. Is brokerage flat at $10 + $1 GST, or tiered by trade size? Needs a larger sell
   or CMC's fee schedule. - For Aus stocks and ETF its $11.00 or 0.10%, which ever is greater.
2. What does a cancelled or reversed trade look like (`Reverse Confirmation Number`,
   `As at Date`)? No example in the FY. - Not Sure, i don't have an example, so we might have to handle this later
3. What do the `OCT25/…` receipts and the three `Statement Balance Alignment` credits
   (total $87.40) represent? Ask CMC, or check against registry statements. - No idea, this might have to be v2 thing. We might have to find where else to get them from
4. Where are the missing dividends? VEU, held throughout, shows no credit in the FY. - no idea
5. What does a withdrawal back to the bank look like? None occurred in the FY. - not sure, haven't done this yet, so we might have to handle this later
6. Does the dedupe key stay unique across FYs and accounts? Check when the earlier
   statements are loaded. - Yes
7. Pre-FY positions: Trade history only starts at 01/07/2025. Earlier statements
   are needed before any Holding can be derived (Jake to supply). - Yes i will supply

## Reviewed and rejected

- **Statement.csv**: every trade in it is already in `Confirmation.csv` with fees split
  out. The rest is settlement plumbing (`PG`/`RG` rows) and bank details. Its
  `Debit`/`Credit` signs are inverted from the cash view.
- **Holdings.csv**: Holdings are derived from Trades. It is a point-in-time view that
  includes pending buys and excludes pending sells (CMC glossary), so it cannot be
  reconciled against settled Trades without care. Removed from scope.
- **EOFY PDF**: no text layer (the text is in embedded forms with an offset glyph
  encoding), rounds prices to 3 dp, and carries a home address. Its content is a
  subset of the CSVs. Not parsed.

## Test fixtures (next step)

- `tests/fixtures/cmc/Confirmation.csv` and
  `tests/fixtures/cmc/CashTransactionSummary.csv`, produced by a masking script.
- Quantities scaled per ticker by a keyed factor, applied identically to both files.
  Every derived value (consideration, brokerage-adjusted proceeds, running balance,
  closing balance, totals) is recomputed so each file still validates.
- Confirmation Numbers remapped consistently in both files, so a trade's two lines
  still share a reference.
- Unit prices kept (public market data). Account number and name replaced. Bank
  details in deposit descriptions replaced. BOM, quoting and date formats preserved
  byte for byte.
- Small hand-built extras: a sell, a fractional quantity, a row that fails the
  consideration check, and a cash summary with a missing trailer.
