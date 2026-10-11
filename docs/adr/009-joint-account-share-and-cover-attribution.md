# ADR-009: Joint account share and Spend attribution through Covers

**Status:** Accepted
**Date:** 2026-10-11

## Context

Fathom is single-user, but the user co-owns a Joint account (Up's "2Up": one spending account and one Saver) with their partner. The partner's own accounts are never in Fathom. Up returns Joint accounts from `/accounts` with `ownershipType: JOINT`, and movements to or from the partner's accounts appear as one leg whose `transferAccount` is not one of the user's Accounts.

Two things need deciding:

1. How much of a Joint account's balance, Spend and Income belongs to the user.
2. What happens when a purchase is made on one Account but paid for from another with a different share. The couple use Up's Cover feature for this in both directions: a shared purchase on a personal card is Covered from the Joint account, and a personal purchase on the joint card is Covered from a personal account.

Up does not link a Cover's transfer leg to its purchase. The transfer leg is an ordinary `Transfer` whose description starts with "Cover".

## Options Considered

### Option A: Count Joint accounts at 100%
- Pros: No share arithmetic. Totals match what Up shows.
- Cons: Spend and Net worth are overstated by the partner's half.

### Option B: Exclude Joint accounts, and count contributions into them as Spend
- Pros: Simple. Spend equals what leaves the user's own accounts.
- Cons: Rent, groceries and other shared costs lose their categories. The user's half of the balance is missing from Net worth.

### Option C: Fixed 50% share, with a per-Transaction override
- Pros: Handles a personal purchase on the joint card directly.
- Cons: A second mechanism for something the couple already record in Up with a Cover. Every override is manual work.

### Option D: Fixed 50% share, and a confirmed Cover moves Spend to the funding Account
- Pros: Uses the signal the couple already create. One rule covers Savers, Joint accounts and personal accounts. Spend stays consistent with the change in Net worth.
- Cons: A Cover now changes reported numbers, not only the display. The number is wrong until the user confirms the Cover. A Cover made by the partner out of the Joint account has no visible purchase.

## Decision

Option D. A Joint account counts at a fixed 50% for balance, Spend and Income, whoever made the Transaction. A confirmed Cover moves the purchase's Spend to the Account that funded it, where it counts at that Account's share.

The rules that follow from it:

- The user's own movements into and out of a Joint account are Transfers at the full amount and never Spend.
- A movement between a Joint account and the partner's own account is a Partner transfer: never Income, Spend or a Reimbursement.
- A personal-card purchase Covered from a Joint account counts at 50%. A Joint account purchase Covered from the user's own account counts at 100%. A Joint account purchase Covered from the partner's own account counts at nothing.
- The partner's Up-labelled "Cover" out of a Joint account is a Partner-covered purchase. It counts as Spend at 50% and is categorised by hand, because the purchase it funded is never visible.
- Moved Spend shows under the funding Account, keeps the purchase's category, merchant and Tags, and stays on the purchase's date.
- Until the user confirms a Cover, the purchase counts at its own Account's share. The Cover's transfer leg is excluded from Spend from the start.
- A Cover is the whole purchase and Up-labelled only. A manual Transfer made for the same reason stays a Transfer.

## Consequences

- Spend is attributed to an Account that may differ from the Account the Transaction is on. Every Spend aggregation has to use the attributed Account and its share.
- Net worth and Spend agree only while both partners contribute equally. Unequal contributions are not tracked, and settling up between the two is outside Fathom.
- Unconfirmed Covers leave Spend temporarily misstated, so the confirmation queue matters for accuracy and not only for display.
- The rule "Transfers and Covers never count as Spend" still holds, because a Partner-covered purchase is a separate term. Anything that classifies Up's "Cover" label has to tell the two apart by who made it and which way it went.
- There is no per-Transaction share override. A shared or personal purchase that was not Covered in Up cannot be corrected in Fathom in v1.
- The share is a constant 50%. Changing it later, or letting it vary over time, would restate history.

## Notes

- Evidence: `data/recon/up/2026-09-20/` (7 accounts, 50 transactions), which includes one partner Cover out of the Joint account and three partner deposits into it.
- Still open under S1-14: the rule for proposing a Cover's purchase, and whether Up allows a Cover for less than the purchase amount. `tests/fixtures/up/TD_transaction_cover_from_saver.json` is empty and needs a real Cover from one of the user's own Savers.
- Revisit if contributions stop being equal, if uncovered exceptions become common, or if a second co-owner arrangement appears.
- Terms are defined in `CONTEXT.md`.
