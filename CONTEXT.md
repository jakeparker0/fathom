# Fathom — Domain Context

The shared vocabulary for Fathom. Use these terms exactly, in code, tests, commits and
conversation. If a term is missing or ambiguous, raise it rather than inventing a synonym.

Seeded from the old README glossary and the Requirements workbook (S1-31); this file is
now the single source for definitions. Entries marked
**Open** are unresolved and must not be assumed.

## Periods

**Pay-cycle month**: The default reporting period, running from the 15th to the 14th,
aligned to salary. The pay day is a user setting, not a constant. When the pay day
falls on a weekend, the period starts on the preceding Friday. The boundary is a
calendar rule and never depends on when salary actually arrived. Public holidays are
ignored in v1.
_Avoid_: "month" on its own, which is ambiguous.

**Reporting period**: Any date range a view reports on: pay-cycle month (default),
week, calendar month, quarter, financial year, calendar year, or custom range.

**Date-range resolver**: The single component that turns a reporting period into
concrete start and end dates. Every chart, budget and forecast goes through it.
Period boundaries are never computed anywhere else.

## Accounts and transactions

**Account**: A place money is held or owed. Every account has a source:
`up_api` (synced from Up) or `manual` (entered or CSV-imported, e.g. AMEX, Bendigo).

**Saver**: A named Up savings pocket (e.g. "Clothes"). A Saver is an Account in its
own right. The user may have several.

**Joint account**: An Account the user co-owns with their partner. Its balance counts
at 50% in Net worth, and its Spend and Income count at 50%, whichever of the two made
the Transaction. The share is fixed: there is no per-Transaction override, and unequal
contributions are not tracked. The partner's own accounts are never in Fathom.
_Avoid_: "2Up", which is Up's brand name for it.

**Partner transfer**: A movement between a Joint account and one of the partner's own
accounts, in either direction. Only the Joint account's side is visible. Never Income,
Spend or a Reimbursement.

**Partner-covered purchase**: A movement out of a Joint account that Up labels "Cover"
and that funds a purchase on the partner's own card. The purchase itself is never
visible, so this movement stands in for it: it counts as Spend at 50% and is
categorised by hand. It is not a Partner transfer and not a Cover.

**Liability account**: An account whose balance is owed rather than held. AMEX is the
only one in v1, and it is subtracted in Net worth.

**Transaction**: A single money movement on one Account.

**Sync**: Pulling transactions and balances from the Up API, either on the daily
schedule or via the manual Sync Now trigger. Syncs are idempotent.

## Relationships between transactions

**Transfer**: A movement between two Accounts the user owns or co-owns, always at the
full amount, including movements into and out of a Joint account. Detected
automatically for Up-to-Up movements, or marked manually (e.g. to or from AMEX or
Bendigo). Never counts as Spend. Paying the AMEX balance from Up is a Transfer: the
AMEX purchases are the Spend. What Up labels a "Forward" is a Transfer.
_Avoid_: "Forward" as a term of its own.

**External payment**: Outgoing money to an account the user does not own (e.g. paying
a friend or a landlord). Counts as Spend and is categorised like a purchase.
_Avoid_: "transfer" for these. Transfer is reserved for the user's own Accounts.

**Cover**: An Up-specific event where a purchase made on one Account is funded from
another (a Saver, a Joint account, or the user's own account funding a Joint account
purchase). It produces a purchase leg and a transfer leg. The transfer leg is the one
Up labels "Cover". Up does not link it to the purchase, so Fathom proposes the
purchase and the user confirms. Once confirmed, the legs are merged for display (e.g.
"Funded by Clothes"), the transfer leg is excluded from Spend, and the purchase's
Spend moves to the Account that funded it and counts at that Account's share. So a
personal-card purchase Covered from a Joint account counts at 50%, a Joint account
purchase Covered from the user's own account counts at 100%, and a Joint account
purchase Covered from the partner's own account counts at nothing. The moved Spend
shows under the funding Account in every view, keeps the purchase's category,
merchant and Tags, and stays on the purchase's date. Until the user confirms, the
purchase counts at its own Account's share. A Cover is always the whole purchase and
always Up-labelled: a manual Transfer made for the same reason stays a Transfer.
Proposing the purchase (S1-14): Up creates the Cover as a pair of Transfer legs, one
on each Account, about a second apart, with swapped `account` and `transferAccount`,
equal and opposite amounts, and descriptions starting "Cover to" and "Cover from". The
purchase is not linked to them. Fathom proposes as the purchase every Transaction on
the receiving Account with the same amount, created before the Cover, and not already
claimed by a confirmed Cover. There is no time limit, because a Cover can be made
while the purchase is held or after it settles. The user picks when there is more
than one candidate. Up allows no partial Covers, so the amounts always match.

**Split**: One Transaction divided across several categories, by dollar amount or
percentage, summing to the full amount. Splits never carry transfer logic.

**Reimbursement**: An incoming payment linked by the user to an earlier expense (e.g.
a friend paying back dinner), reducing that expense's net cost. One expense may have
several partial Reimbursements. Linking is manual in v1.
_Avoid_: "refund". A Refund is not a Reimbursement.

**Refund**: Money returned by a merchant for an earlier purchase. It is negative Spend
in the original purchase's category, counted in the period it arrives. Never Income
and never a Reimbursement.

## Reporting

**Spend**: Outgoing money that counts towards spending totals. Includes purchases,
External payments, Partner-covered purchases, fees and interest charged, less Refunds.
Excludes Transfers, Partner transfers and Cover transfer legs, with no toggle to
include them. Each amount counts at the share of the Account it is attributed to.
Reported net of Reimbursements by default; gross is an opt-in view.

**Net spend / Gross spend**: Spend after or before linked Reimbursements. Net is the
default everywhere.

**Income**: Incoming money that is not a Transfer or Reimbursement, tracked as distinct
types: salary and interest (savings accounts and Term deposits).

**Category / Sub-category**: How Spend is classified. User-managed, extending Up's
built-in categories. Each category may have one or more sub-categories.
_Open_: the taxonomy itself, pending S1-19.

**Tag**: A user-managed label applied to Transactions, many-to-many (e.g. "Holiday
2026", "Tax deductible"). Independent of Category.

**Subscription**: A recurring charge detected heuristically (same merchant, similar
amount, regular interval).

## Investments and net worth

**Trade**: A buy or sell of an ASX security, stored as a permanent record. Never
edited to change a Holding.

**Holding**: A current position in one security, always derived from the full Trade
history, never stored as an editable figure.

**Cost basis**: What a Holding cost, used for gain calculations. The method (average
cost, FIFO or specific lot) is decided in ADR-007.

**Dividend**: A cash distribution on a Holding, recorded with its franking credits.
May optionally link to a reinvestment (DRP) buy Trade.

**Managed fund**: A Vanguard fund holding, entered manually (units, unit price, cost
basis). No API, by design.

**Term deposit**: A manually tracked deposit (principal, rate, maturity, balance).

**Snapshot**: A stored daily row capturing state at a point in time. Portfolio
Snapshots are stored per holding per day, not pre-aggregated, and can be regenerated
when backdated Trades are imported.

**Net worth**: The user's own Up accounts + 50% of each Joint account + Bendigo +
portfolio value + Managed funds + Term deposits, minus the AMEX balance. Snapshotted
daily.

## Infrastructure terms

**Vault**: AWS Secrets Manager, the production secrets store. Never an in-app concept.

## Flagged ambiguities

Summary of the **Open** items above, to resolve in grilling sessions:

1. The Category and Sub-category taxonomy (pending S1-19).
