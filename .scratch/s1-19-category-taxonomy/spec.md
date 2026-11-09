# S1-19 spec: Category taxonomy

Status: draft, awaiting Jake's approval. Nothing below is implemented.
Tier: the taxonomy is Jake's decision, made in a grilling session on 2026-11-09. The
schema that stores it is S1-22 (Tier A, hand-written).
Inputs: Up's category tree (`tests/fixtures/up/categories_list.json`), Jake's old
HomeBank category list, and the AMEX and Bendigo mappings
(`.scratch/s1-17-amex-bendigo-export/column-mapping.md`).
Stories: S1-19.

## Goal

Close S1-19 by settling the final Category list, the rule for Category vs Tag, and the
names of the levels. Also close Flagged ambiguity 1 in `CONTEXT.md`.

## Deliverables

1. This taxonomy, as the seed list for S1-22.
2. The `CONTEXT.md` changes below, applied on approval.
3. Ticking S1-19 in the vault when done.

## Rules

1. **Category vs Tag.** A Category is *what* the money bought. Each Transaction has
   exactly one, so Category totals add up to total Spend. A Tag is *why* or *for what*.
   A Transaction has zero or more Tags, and Tag totals can overlap.
   - A pastime that spans several kinds of purchase (Surfing, Photography) is a Tag,
     not a Category.
   - Spending on a trip is categorised by what was bought (a meal on holiday is
     Restaurants & Cafes) and tagged with the trip.
2. **Three levels, at most:** Group → Category → Sub-category.
   - A Group holds no Transactions.
   - A Transaction (or each part of a Split) sits on a Category or a Sub-category. A
     Category that has Sub-categories can still hold Transactions directly.
   - Spend with no Category yet is Uncategorised: a state, not a Category.
3. **Up's Groups and Categories are fixed.** Up's four Groups and their Categories stay
   exactly as Up defines them: no renaming or deleting. New Up Categories are added
   automatically. Jake can add Groups, Categories and Sub-categories, including
   Sub-categories under Up's Categories.
4. **Spend only.** The taxonomy classifies Spend. Income, Transfers, Cover transfer
   legs and Reimbursements are handled by their own rules, never by a Category. A
   Refund takes the original purchase's Category and Sub-category. Review states
   ("TODO", "Processed") are statuses, not Categories.
5. **Start lean.** Add a Sub-category only when a report needs it.

## Taxonomy

Groups and Categories are Up's unless marked **(new)**. Every Sub-category is new.

### Good Life
- Adult
- Apps, Games & Software
- Booze
- Events & Gigs
- Hobbies
- Holidays & Travel
  - Accommodation
  - Flights
  - Travel insurance
  - Visas
- Lottery & Gambling
- Pubs & Bars
- Restaurants & Cafes
  - Coffee
- Takeaway
  - Snacks
- Tobacco & Vaping
- TV, Music & Streaming
- **Other (new)**

### Personal
- Children & Family
- Clothing & Accessories
- Education & Student Loans
- Fitness & Wellbeing
  - Social sport
- Gifts & Charity
- Hair & Beauty
- Health & Medical
  - GP
  - Medicine
  - Psychologist
- Investments (kept because it's Up's, unused; see Deferred)
- Life Admin
  - Fines
- Mobile Phone
- News, Magazines & Books
- Technology

### Home
- Groceries
  - Coffee beans
  - Protein
- Homeware & Appliances
- Internet
- Maintenance & Improvements
- Pets
- Rates & Insurance
- Rent & Mortgage
  - Bond
- Utilities
  - Electricity
  - Gas
  - Water

### Transport
- Car Insurance, Rego & Maintenance
- Cycling
- Fuel
- Parking
- Public Transport
- Repayments (kept because it's Up's, unused; see Deferred)
- Taxis & Share Cars
- Tolls

### Fees & Interest (new)
- Account fees (new): e.g. the AMEX membership fee
- Penalty fees (new): late payment, overdue payment, insufficient funds
- Interest charged (new)

### Starting Tags
- Work: covers what was HomeBank's Clothes → Work, applied more broadly
- Surfing
- Photography
- One Tag per trip or event, as needed (e.g. "Holiday 2026")

Essential / Discretionary would be a Tag if it's ever wanted. It isn't needed now.

## Specific decisions

- **Bond** is Spend, in Home → Rent & Mortgage → Bond. Getting it back at the end of the
  lease is a Refund in the same Category. The two net out over the lease, at the cost
  of one distorted month at each end.
- **Good Life → Other** is a deliberate name.
- **Fines** go in Personal → Life Admin, not Transport: a fine is a penalty, not a cost
  of getting around.
- **Dropped from HomeBank:** Bills (covered by Utilities), Taxes, the Travel → Food and
  Misc categories, every income category, Not an Expense, Transfer From Alex, Payback,
  Refund, Processed and both TODO categories.

## `CONTEXT.md` changes (applied on this branch)

- **Group / Category / Sub-category** replaces Category / Sub-category: three levels,
  "what" the money bought, one Category per piece of Spend (each part of a Split has
  its own), names unique among siblings only. `_Avoid_: "parent category"`.
- **Uncategorised** (new): a state, never a Category, shown as its own line in reports.
- **Tag** reworded: "why or for what", cuts across Categories, totals can overlap.
- **Interest earned / Interest charged** (new). Bare "interest" is avoided. Income and
  Spend entries now use these terms.
- **Refund** lands on the original Category *and* Sub-category.
- Flagged ambiguity 1 removed. None are open.

## Decisions from the grill-with-docs session (2026-11-09)

Recorded here for S1-22 and the sync work. Not in `CONTEXT.md`, which holds terms only.

1. **Fathom is the source of truth for a Category once the user changes it in Fathom.**
   Any change counts, including only adding a Sub-category. Until then, a Transaction
   follows Up's latest Category on each Sync, including changes made in the Up app.
2. **Fathom never writes a Category back to Up.** Up's API could take one (the
   `relationships.category.links.self` link), but only for Up's own Categories, and
   Sync stays one-way.
3. **Up's `isCategorizable` flag decides nothing.** `transaction_cover_from_partner.json`
   is `false`, yet a Partner-covered purchase is categorised by hand. Fathom's own rules
   decide: Spend needs a Category; Transfers, Cover transfer legs, Income and
   Reimbursements never take one.
4. **A new Up Category is added to the tree automatically**, under its Up Group.
5. **A Category is never deleted while a Transaction sits on it.** What happens when Up
   retires a Category is otherwise deferred.
6. **Names are unique among siblings at every level.** Two Groups can't share a name.
   Reports show the full path where names repeat.
7. **Hiding.** An unused Up Category can be hidden from pickers. Hiding never affects
   reports or Transactions already on it (Up can still assign it).
8. **Refunds** go to the original purchase's Category and Sub-category.
9. **No ADR for S1-19.** The fixed-Up-tree-plus-user-additions design is recorded in
   S1-22's ADR alongside the schema.

## Carried to S1-22 (schema)

Inputs for Jake's design, not decisions:

- Up's Groups and Categories are keyed by Up's IDs (`restaurants-and-cafes`) and kept as
  Up defines them. User-added ones are editable. The schema needs to express that.
- An override flag or equivalent, for decision 1.
- Uniqueness within a parent (decision 6), and the never-delete rule (decision 5).
- A hidden flag (decision 7).
- AMEX and Bendigo rows arrive Uncategorised. Bendigo's `L` code might seed a rule.

## Deferred

- **Loan account type.** A loan repayment is a movement against a debt, not Spend. Up's
  Repayments Category stays unused until then. Education & Student Loans holds education
  Spend only; a student-loan repayment would follow the same rule.
- **Up's Investments Category.** Up doesn't use it on money going to CMC today. If it
  ever does, that money is a Transfer, not Spend.
