# AMEX and Bendigo exports: column mapping (S1-17)

Status: draft. Branch `s1-17-amex-bendigo-data-mapping`. Commits: `S1-17: …`.

Real exports captured 2026-10-17. Raw files live in `data/recon/raw/` (gitignored,
never committed): `amex/activity.csv`, `amex/activity_2026_YTD.csv`, `bendigo/bendigo_bank.csv`,
`bendigo/bendigo_bank.qif`, `bendigo/transactions_extended.csv` (everyday), `bendigo/transactions_extended_savings.csv` (Reward Saver). Masked copies will go to `tests/fixtures/amex/` and
`tests/fixtures/bendigo/`.

Sample size: 7 AMEX rows in `activity.csv` (11 Aug to 1 Sep 2026), 99 AMEX rows in
`activity_2026_YTD.csv` (**despite the name, 18 Mar to 22 Dec 2025**, full 14 columns),
18 Bendigo basic rows
(Reward Saver, 1 Jul to 17 Sep 2026), 6 Bendigo extended rows (the everyday account,
15 Jul to 17 Sep 2026), 18 Bendigo extended Saver rows (same 18 transactions as the
basic CSV). Everything below is what the sample shows. Anything
inferred from a single row is marked **(inferred)**.

## Summary

| Source | Format | Header | Signs | Unique ID | Balance column |
|---|---|---|---|---|---|
| AMEX `activity.csv` | CSV, 14 columns | yes | charge `+`, payment/credit `−` | `Reference` | no |
| AMEX `activity_2026_YTD.csv` | CSV, 14 columns (same as above) | yes | same | `Reference` | no |
| AMEX 4-column export (seen once, no longer on disk) | CSV, **4 columns** | yes | same | **none** | no |
| Bendigo `bendigo_bank.csv` | CSV, 3 columns | **no** | credit `+`, debit `−` | **none** | no |
| Bendigo `bendigo_bank.qif` | QIF, same rows | n/a | credit `+`, debit `−` | **none** | no |
| Bendigo `transactions_extended*.csv` | CSV, 7 columns | **no** | credit `+`, debit `−` | **none per row** (see below) | no |

The AMEX and basic Bendigo exports do not name the account or card. The importer must be
told which Account it is loading. The **extended** Bendigo export does carry the account
number in column 0.

Both put rows newest first. Order must not be relied on.

Recommendation: import Bendigo from **`transactions_extended.csv`**. It fixes the
account identification and the type code that the basic CSV lacks. It does not fix the
missing header, balance or per-row ID. The Saver export confirms the format is the same
for both accounts. The basic CSV and QIF are redundant. See the extended section.

## AMEX `activity.csv`

Dialect: UTF-8, no BOM, LF line endings, header present, comma-separated, dates
`DD/MM/YYYY`, amounts plain decimals with `.` and no thousands separator. **Quoted
fields contain embedded newlines** (`Address`, `Town/City`), so parse with the `csv`
module opened with `newline=''`. Never split on lines. No trailer or blank rows.

| Column | Example | Maps to | Notes |
|---|---|---|---|
| Date | `01/09/2026` | transaction date | When the purchase was made. See open question 1. |
| Date Processed | `02/09/2026` | posted date | Same day or 1 to 3 days later. |
| Description | `LENNOX BAKERY           LENNOX HEAD` | raw description | Merchant and town fixed-width padded with runs of spaces. Store raw, normalise whitespace only for matching and display. |
| Amount | `28.28` / `-1688.84` | `amount_cents` (negated) | Positive is a charge, negative is a payment or refund. **Opposite sign to Bendigo and Up.** Negate on import so Spend is negative-signed like other Accounts. Parse as `Decimal`, round once via `domain/`. |
| Foreign Spend Amount | `294.49 USD` | foreign amount and currency | Empty for AUD. When present: amount, space, ISO code. Text, needs splitting. |
| Commission | `14.52` | foreign fee (cents) | Empty for AUD. See the foreign-row note below. |
| Exchange Rate | empty | ignored | Empty even on the foreign row. Cannot be relied on. |
| Additional Information | empty | ignored | Empty in every row. |
| Appears On Your Statement As | same as Description | ignored | Identical to `Description` in all 7 rows. |
| Address | `40 BLUE SEAS\nPDE` | ignored | Merchant address, often multi-line, often blank. Not needed. |
| Town/City | `LENNOX HEAD\nNSW` | ignored | Town and state, often multi-line, often blank. |
| Postcode | `2478` | ignored | |
| Country | `AUSTRALIA` | ignored | Blank for some AUD rows (the fuel row). |
| Reference | `'AT262450004000010456641'` | `external_ref` (unique) | **Dedupe key.** Carries literal apostrophes around the value (Excel text trick). Strip them. Value is text. |

Foreign-currency rows (8 across both files: 5 IDR, 2 USD in 2025, 1 USD in 2026):

- `Foreign Spend Amount` is text `<amount> <ISO code>`, and the amount **can contain
  thousands separators** (`"1,936,165 IDR"`, quoted). `Amount` itself never does. Strip
  the commas before parsing to `Decimal`.
- `Amount` **includes** `Commission`: in all 8 rows, `Commission = rate × (Amount −
  Commission)` to the cent. The rate is **3.00%** on the seven 2025 rows and **3.50%** on
  the 2026 row, so the rate changes. Do not recompute it. Spend is `Amount`, and
  `Commission` is a component, never added on top.
- `Exchange Rate` is empty in all 106 rows. The rate is not available and would have to be
  derived.
- `Country` is not a reliable foreign signal. Two AUD-billed rows have a foreign country
  (`UNITED STATES`, `UNITED KINGDOM`) with no foreign amount, and one foreign row
  (Booking.com) has a blank `Country`. Use `Foreign Spend Amount` being non-empty.

References (106 rows across both files, all unique):

- `Reference` is unique across both files (no overlap, no duplicates), so it is a sound
  dedupe key within what was seen. Uniqueness across a supplementary card is untested.
- Shapes: `'AT` + 20 digits for purchases **and for `ONLINE PAYMENT RECEIVED`** payments;
  `'S000` + digits for `PayID Payment Received`; and a 23-digit number beginning
  `1000000001` for card-level fees (`MEMBERSHIP FEE`, `INSUFFICIENT FUNDS FEE`), which
  have no address data.
- In all 97 `AT` references the digits after `AT25`/`AT26` are a day-of-year equal to
  `Date Processed`. A curiosity, not to be parsed or relied on.
- **Two pairs of rows are identical on date, processed date, description and amount**
  but have different references: `LS GLAMORAMA` 22.61 on 8 Jun 2025 and `HOTEL SPENCER`
  17.28 on 5 Apr 2025. They are genuine repeat purchases. A composite key
  (`date + description + amount`) would merge them, so `Reference` is required.

Row classification:

| Pattern | Meaning | Importer action |
|---|---|---|
| `Amount > 0` | Purchase | Spend, on the card Account. |
| `PayID Payment Received, Thank you`, `Amount < 0` | Payment to the card | Candidate Transfer leg. Never Spend or Income. The paying leg is **not** in the Bendigo sample (it was paid from another Account). |
| `ONLINE PAYMENT RECEIVED - THANKYOU W<4 digits>`, `Amount < 0` | Payment to the card | Candidate Transfer leg. 9 in 2025 and (see below) 6 in 2026. |
| `MEMBERSHIP FEE`, `INSUFFICIENT FUNDS FEE`, `Amount > 0` | Card fee | Spend (a fee). Needs a category. Fee reference shape differs (above). |
| `Amount < 0`, other description | Refund or credit | None in the 2025 file. See the 4-column section for 2026 examples. |

Dates in the 2025 file: `Date Processed` lags `Date` by 0 to 3 days (0: 21 rows, 1: 60,
2: 17, 3: 1). **Four rows land in a different pay-cycle month depending on the date
used**, because `Date` is the 14th and `Date Processed` the 15th: `HOPE ST RADIO` 12.13
and 24.26 (14/12/2025), `ANGLESEA IGA` 50.07 (14/04/2025) and an `ONLINE PAYMENT
RECEIVED` of −500.19 (14/06/2025). Question 1 is a real decision, not a theoretical one.

Two payments of the same amount, −1605.64, appear on 19 May and 25 May 2025 with
different references and `W` codes. They are two payments, not a duplicate.

## AMEX 4-column export (earlier version of `activity_2026_YTD.csv`)

**This file has been overwritten.** The first `activity_2026_YTD.csv` was a 4-column export
of 63 rows (7 Jan to 17 Oct 2026). Jake re-exported all columns over it, and the new file
holds different dates (Mar to Dec 2025). The notes in this section come from the first
version and cannot be re-checked. If they matter, re-export the 2026 data in full.

Dialect: UTF-8, no BOM, LF, header, unquoted except descriptions containing a comma.
Columns are exactly `Date, Date Processed, Description, Amount`, same formats and sign
as the 14-column file. No embedded newlines, because the address fields are gone.

It was a **different column selection** of the same activity: all 7 rows of
`activity.csv` appeared in it with identical date, description and amount.

What the narrow export loses: `Reference` (the only unique key), `Foreign Spend Amount`,
`Commission` and all merchant address data. The foreign DXO row shows only `429.23`, and
the Airbnb London and Immigration Canada rows show no hint they are foreign.

Consequences:

- **Importer must read columns by header name, not position**, and accept either
  layout.
- With no `Reference`, dedupe falls back to a composite
  (`date + processed date + description + amount`). In the 63 YTD rows that composite is
  unique, but same-day repeats at one merchant are common (two `HOYTS` on 8 Aug and two
  `AMAZON` on 27 May, all at different amounts). An exact repeat is plausible and
  would be wrongly merged, and the 2025 file now proves it happens (two pairs). Tier A
  decision: require the 14-column export and refuse imports without `Reference`.
- Lag between `Date` and `Date Processed` is 0 to 3 days (0: 25 rows, 1: 30, 2: 8,
  3: 1).

Row kinds seen in the YTD file (only the first two were in the 14-column sample):

| Description | Amount | Meaning | Importer action |
|---|---|---|---|
| `PayID Payment Received, Thank you` | `−` | Payment to the card, by PayID | Transfer leg. 4 seen. |
| `ONLINE PAYMENT RECEIVED - THANKYOU W<4 digits>` | `−` | Payment to the card, by direct debit or bank transfer | Transfer leg. 6 seen. The `W` code is an AMEX payment ref **(inferred)**. |
| `Qantas Ultimate Annual Travel Credit` | `−450.00` | Card benefit credit | Not a payment, not a refund. Unclassified. See open question 11. |
| `SP LARRIET` | `+185.00` 1 Jun, `−185.00` 18 Jun | Charge, then full refund | Refund, same merchant and amount. Reimbursement-style link candidate. |
| `IMMIGRATION CANADA ONLI` | `−85.78`, `−100.92`, `−186.44` on 2 Jun | Three partial refunds, total 373.14 | Refunds. Do not equal the charges (388.77 on 5 Jun, 387.23 on 16 Apr), so matching by amount fails. |
| `MEMBERSHIP FEE` | `+450.00` | Annual card fee | Spend (a fee). Needs a category. |
| `INTEREST CHARGES` | `+4.85`, `+10.19` | Interest on balance | Spend (a financial cost), not Income. Needs a category. |
| `CHARGE FOR OVERDUE PAYMENT` | `+30.00` | Late fee | Spend (a fee). |

Refunds therefore arrive as negative rows with the merchant's normal description, so
`Amount < 0` alone does not distinguish a payment from a refund. Classify payments by
description pattern (`PayID Payment Received`, `ONLINE PAYMENT RECEIVED`), refunds
by exclusion, and flag them for review.

## Bendigo `bendigo_bank.csv`

Dialect: UTF-8, no BOM, **CRLF** line endings, **no header row**, every field quoted,
dates `DD/MM/YYYY`, amounts two decimals, no thousands separator seen (largest 2500.00).
Three columns, by position only.

| Pos | Example | Maps to | Notes |
|---|---|---|---|
| 0 | `"17/09/2026"` | `posted_date` | Single date, no time. |
| 1 | `"-1000.00"` | `amount_cents` | Signed: credit `+`, debit `−`. Same convention as Up. Zero amounts occur (below). |
| 2 | `"Osko Payment Sent Invest CMC 907556777"` | raw description | Free text, carries any identifiers. |

There is no balance, no reference, no ID and no account number column. The sample is
one account only (a Reward Saver, from the `REWARD RECEIVED` lines). Detect a header
defensively: if row 0 col 0 does not parse as a date, fail loudly rather than skip.

### Description patterns

| Pattern | Meaning | Importer action |
|---|---|---|
| `E-BANKING TRANSFER <10 digits> <14 digits>` | Internet-banking transfer. The 14-digit number is identical in all 5 rows. | Transfer. The 10-digit number is a receipt id. The 14-digit one is an account number (own account or counterparty, unconfirmed). Not to be stored in logs. |
| `Osko Payment Received <payer nickname> <payer name> <9 digits>` | Incoming Osko | Candidate Transfer if the payer is an own Account. Payer nickname (`Savings`, `Cc`) is chosen by the payer. |
| `Osko Payment Sent <my nickname> <payee name> <9 digits>` | Outgoing Osko | `Invest CMC` / `Investment CMC` are deposits to CMC: Transfers. `..` is a blank nickname. |
| `BILL PAYMENT BPAY TO: <biller> <biller code/ref>` | BPAY | Real Spend (tax office payment), unless it proves to be a Transfer. |
| `INTEREST` | Monthly interest, 1st of month | Income. Keep the description (matches `keep_descriptions` in the mask config). |
| `REWARD RECEIVED BONUS RATE FOR PREVIOUS MONTH Reward Saver` | Bonus-rate marker, **$0.00** | Skip, or import as a zero row. Decide. A zero amount must not break validation. |

The trailing 9-digit number on Osko lines is the payment id. It is the best available
unique key but exists only on Osko rows. See dedupe below.

### Dedupe (hand-over to Tier A)

Sync and idempotency is hand-written (ADR-011), so this records facts, not a design:

- The CSV has **no per-row unique ID**. The only candidates are the receipt or payment
  numbers inside `Description`, present on `E-BANKING`, `Osko` and `BPAY` rows and absent
  on `INTEREST` and `REWARD`.
- `date + amount + description` is unique in the sample (all 18 rows distinct), but
  two same-day, same-amount, same-text rows would collide. Interest and the reward
  marker only recur monthly, so they are safe today.
- Two E-BANKING rows on 17 Sep are equal and opposite (+2000 / −2000) with different
  receipt numbers. They are separate rows and must both be kept.

## Bendigo `transactions_extended.csv`

Dialect: UTF-8, no BOM, CRLF, **no header row**, every field quoted, dates
`DD/MM/YYYY`, newest first. Seven columns, by position only.

| Pos | Example | Maps to | Notes |
|---|---|---|---|
| 0 | `"633-000 217265651"` | Account lookup | `BSB account-number`. Identifies the Account. Resolves the "which account" gap. Sensitive, do not log. |
| 1 | `"17/09/2026"` | `posted_date` | |
| 2 | `"TDR06"` | type code | Letters plus two digits. Seen: `TDR06`, `TCR06`, `WDL05`, `JDR10`. Same letters as the QIF `L` code, plus a numeric suffix. |
| 3 | `"-2000.00"` | `amount_cents` | Signed: credit `+`, debit `−`. |
| 4 | `"E-BANKING TRANSFER"` | transaction kind | Stable text label, split out from the free text. Seen: `E-BANKING TRANSFER`, `RETAIL PURCHASE`, `DIRECT DEBIT`. |
| 5 | `"0663124689"` / `"VICROADS ONLINE PAYMEN, KEW"` | description / payee or id | For a transfer: the receipt number. For a purchase: merchant and town. For a direct debit: biller name and a number. |
| 6 | `"1408 AUD000000024922"` | reference | Kind-specific, see below. |

Column 6 by kind:

- `E-BANKING TRANSFER`: a constant per export. Everyday has `0054490974NA01`, Saver has
  `00544909741401`. Same `0054490974` stem, different two-character tail (`NA` / `14`), so
  it varies by account. It is not the BSB-account number. Whether it is the own or the
  counterparty reference is unconfirmed.
- `RETAIL PURCHASE`: `1408 AUD000000024922`. Reads as `DDMM`, currency, amount in cents
  zero-padded to 12 digits **(inferred, 1 row)**. The row is dated 16 Aug but the `DDMM` is
  14 Aug, so this carries the **purchase** date while col 1 is the **posting** date.
- `DIRECT DEBIT`: `379516625061005`, meaning unknown.

Code to kind: `TDR`/`TCR` = transfer debit/credit, `WDL` = retail purchase,
`JDR` = direct debit. The numeric suffix is unexplained. Classify on kind (col 4), not
on the code.

### Saver export: column 5 and 6 layout depends on the kind

The Saver file has the same 7 columns and the same 18 rows as the basic CSV (date and
amount verified equal on all 18). The kinds it adds show that columns 5 and 6 are
**kind-specific**, so parsing must branch on column 4:

| Kind (col 4) | Code | Col 5 | Col 6 |
|---|---|---|---|
| `E-BANKING TRANSFER` | `TCR06` / `TDR06` | receipt number | account reference constant |
| `Osko Payment Received` | `DEP52` | `<payer nickname> <payment id>` e.g. `Savings 924313840` | payer name |
| `Osko Payment Sent` | `WDL52`, `WDL53` | `<my nickname> <payment id>`, nickname may be `..` | payee name, or `CMC` |
| `BILL PAYMENT` | `WDL40` | `BPAY TO: <biller>` | BPAY reference number |
| `INTEREST` | `JCR99` | empty string | empty string |
| `REWARD RECEIVED` | `MCR90` | `BONUS RATE FOR PREVIOUS MONTH` | `Reward Saver` |

Observations:

- Interest and reward rows have empty col 5 and 6 (or fixed text), so they have no ID.
  They recur monthly on the 1st, so `account + date + code` is unique.
- `WDL52` is Osko to a person, `WDL53` is Osko to CMC (both CMC rows). Possibly 53 is
  Osko to a business or a saved payee **(inferred, 2 rows)**. Do not classify on it. The
  CMC Transfer is identified by the payee `CMC`, and even that needs the CMC side to
  confirm.
- The 9-digit Osko payment id is not in the Up export, so it cannot be used to match
  an Osko across to Up. Whether the sending bank shows the same id is unknown.
- The Saver export has the same `BPAY` row as Spend-or-Transfer ambiguity as before. A
  tax office payment is Spend.

### What it fixes versus the basic CSV

| Gap in basic CSV | Extended |
|---|---|
| No account identifier | **Fixed.** Column 0. |
| No type code (only in the QIF) | **Fixed.** Column 2, plus a clean kind in column 4. |
| Identifiers buried in free text | **Mostly fixed.** Receipt number in its own column for transfers. |
| No header | Still none. |
| No balance | Still none. |
| No unique ID per row | **Not fixed.** Transfers have a receipt number. `RETAIL PURCHASE` and `DIRECT DEBIT` do not. |

Dedupe stays a composite for non-transfer rows. A candidate key is
`account + posted date + code + amount + col 4 + col 5`, with an ordinal for exact
repeats. That is for Tier A to decide.

### Transfer matching: the receipt number is shared across both legs

Cross-checking the extended file against the basic one, the E-BANKING receipt number
appears in **both accounts** and pairs the two legs of one transfer:

| Receipt | Reward Saver (basic) | Everyday (extended) |
|---|---|---|
| `0663124689` 17 Sep | +2000.00 | −2000.00 |
| `0663124646` 17 Sep | −2000.00 | +2000.00 |
| `0655453744` 14 Aug | −249.22 | +249.22 |
| `0648539203` 15 Jul | −966.43 | +966.43 |

All four match on receipt, equal and opposite amount, and same date. This is a clean
Transfer match key between the two Bendigo Accounts, no heuristics needed. The chain on
15 to 17 Jul continues: the 966.43 that arrived in Everyday is paid out by `DIRECT DEBIT
AMERICAN EXPRESS` for −966.43 on 17 Jul (not in the AMEX sample, which starts 11 Aug).
The 14 Aug 249.22 is moved in two days before the `RETAIL PURCHASE` of 249.22, so the
purchase is Spend and the funding leg is a Transfer.

## Bendigo `bendigo_bank.qif`

Same 18 rows, same order. Checked row by row: date, amount and description match the
CSV in all 18. Dialect: `!Type:Bank` header, CRLF, one record per `^` line, dates
`DD/MM/YYYY` (not the QIF-standard form), amount with `.`.

| Tag | Example | Notes |
|---|---|---|
| `D` | `D17/09/2026` | Date. |
| `T` | `T-2000.00` | Amount. |
| `M` | `ME-BANKING TRANSFER …` | Memo. Identical to `P` in all rows. |
| `P` | `PE-BANKING TRANSFER …` | Payee. Identical to `M`. |
| `L` | `LTDR` | **Category code.** The only extra field versus the CSV. |

`L` values seen, mapped to the descriptions they accompany:

| Code | Seen on |
|---|---|
| `TCR` / `TDR` | `E-BANKING TRANSFER` credit / debit |
| `DEP` | `Osko Payment Received` |
| `WDL` | `Osko Payment Sent`, `BILL PAYMENT BPAY` |
| `JCR` | `INTEREST` |
| `MCR` | `REWARD RECEIVED …` |

Nothing else is in the QIF: no balance, ID, time or account.

`TCR`/`TDR` are Bendigo's own "transfer" codes, which the CSV description also implies.
`WDL` is **not** a reliable Spend signal: the CMC deposits are `WDL` but are Transfers.
The code adds little over the description. Importing from CSV and ignoring the QIF
is enough unless the code proves useful for classification.

## Cross-source observations (for S1-21)

- Bendigo `Osko Payment Sent … CMC` (−1000.00 on 15 Jul and 14 Aug) should match a
  CMC `JNL… ]NPP` deposit. CMC's FY file ends 30/06/2026, so these cannot be checked
  yet.
- **Matched:** Bendigo everyday `DIRECT DEBIT AMERICAN EXPRESS` −966.43 on 17 Jul equals
  AMEX `ONLINE PAYMENT RECEIVED - THANKYOU W5277` −966.43 on 17 Jul. Same date, equal and
  opposite. The AMEX `W5277` is not in the Bendigo row (`JDR10` ref is `379516625061005`),
  so the match is by amount and date.
- The AMEX `PayID Payment Received` payments (−1688.84 on 14 Aug, others) have no Bendigo
  counterpart. The paying Account is elsewhere (Up is the likely one).
- Bendigo Saver 15 Jul has `+966.43 Osko Received Cc` and `−966.43 E-BANKING TRANSFER`,
  netting to zero the same day. Both are Transfers. The `−966.43` is paired with
  Everyday by receipt number (see above). The `+966.43` counterpart is still unknown.
- Bendigo `Received Savings` credits (2500.00, 2500.72) match a payer nickname, not a
  known Account. Matching needs the other side's export.

## Open questions

1. Which AMEX date drives the pay-cycle month: `Date` or `Date Processed`? **A real
   decision:** in the 99-row 2025 file, 4 rows (3 purchases, 1 payment) fall in different
   pay-cycle months depending on which is used. The single date-range resolver needs one
   answer. **Decided (Jake, 2026-10-19): `Date`.** Needs recording in an ADR or the
   resolver docs before the importer is built. - Date
2. (Resolved.) `Amount` includes `Commission`, on all 8 foreign rows (3.00% in 2025,
   3.50% in 2026 of the pre-commission amount). Spend is `Amount`.
3. (Resolved, within the sample.) `Reference` is unique across all 106 rows from both
   files. Untested: a supplementary card, and a re-export of an overlapping period.
4. (Resolved.) A refund is a negative row with the merchant's normal description,
   full (`SP LARRIET`) or partial (`IMMIGRATION CANADA`). See the YTD section.
5. Does Bendigo ever emit a header, thousands separators or a trailer in the CSV for
   larger or older exports? Not in this sample (CSV and QIF both clean).
6. Do `E-BANKING TRANSFER` numbers identify the counterparty Account? The 14-digit
   number is constant across all 5 rows, which suggests an own-account identifier.
7. **Decided (Jake): skip** the `$0.00` `REWARD RECEIVED` marker. Skip on kind
   `REWARD RECEIVED` with amount zero, and log a count, never import it.
8. (Resolved.) The extended format works for the Reward Saver and includes interest,
   reward and Osko rows. Still unobserved: refunds, cheques, fees, international
   transfers and card purchases on the Saver.
9. Which date drives the pay-cycle month for Bendigo purchases: posting date (col 1) or
   the purchase date inside col 6? **Decided (Jake): posting date (col 1).** Bendigo is
   mostly savings, so the difference is not worth the inferred parse of col 6.
10. What do the `NA01`/`14` account reference (col 6, transfers) and the `JDR10` reference mean? Why `WDL52` versus `WDL53`?
11. How should the `Qantas Ultimate Annual Travel Credit` (−450.00) be treated? It is
    neither a payment nor a purchase refund. It plausibly offsets the 450.00 membership
    fee, which would make it a Reimbursement of that fee. **Decided (Jake): treat it as a
    refund.** It is a negative card row that reduces Spend like the other refunds, and the
    $450 membership fee stays as Spend. (Jake notes the benefit appears as a line when the
    credit is used.) Not a Reimbursement unless linked, and never Income.
12. (Recommendation firm.) Require the 14-column AMEX export. Two same-day repeat
    purchases in the 2025 file prove `date + description + amount` cannot dedupe.
    Reject a file whose header lacks `Reference`.
13. The 2026 4-column rows were overwritten. **Decided (Jake): not needed now.** A full
    2026 export is only wanted if it is required later. Refund fixtures are hand-built.

## Test fixtures (built)

Produced by `scripts/mask_amex_fixtures.py` and `scripts/mask_bendigo_fixtures.py`
(spec: `spec.md`; date rule: ADR-012).

- `tests/fixtures/amex/activity.csv` (7 rows, whole) and
  `tests/fixtures/amex/activity_2026_YTD.csv` (25 rows chosen by rule from the 99-row
  file, which actually holds Mar to Dec 2025). Output names match the raw names.
- `tests/fixtures/bendigo/transactions_extended.csv` (everyday) and
  `transactions_extended_savings.csv` (Reward Saver). The basic CSV and the QIF are not
  masked. Transfer receipts are masked identically in both, so the pairs still match.
- Hand-built, no real data, in `handbuilt/` beside each: AMEX `refunds.csv` (full and
  partial refunds, the Qantas-style credit), `four_columns.csv` and
  `missing_reference.csv` (both rejected); Bendigo `with_header.csv` (rejected),
  `thousands_separator.csv` and `repeated_rows.csv` (for the importer's tests, not
  masked).
- Deliberate deviations from the spec: the BSB `633-000` is kept (public); every
  merchant town becomes `TESTTOWN`.
