# Up API: pagination, rate limits and transaction ID stability (S1-15)

Sources: the Up developer docs (https://developer.up.com.au/) and the committed
fixtures in `tests/fixtures/up/`. Checked 2026-10-20.

## Pagination

- Cursor-based and opaque. The client must follow the `links.next` URL it is given,
  never build a cursor itself.
- `links` is `{"prev": ..., "next": ...}`. Both are full URLs carrying a
  `page[after]` or `page[before]` cursor, or `null`. Page forward until `next` is `null`.
- Page size is set with `page[size]`. The docs say it is "generally constrained to an
  upper limit of 100" and that the default varies by endpoint. Always send it
  explicitly.
- The transaction list filters (`filter[since]`, `filter[until]`, `filter[status]`) are
  not for paging, and the docs say so. Use them to bound a sync window, and page with
  the links.
- A real `next` link (seen 2026-10-20 with `page[size]=1`) repeats the original
  `filter[since]`, `filter[until]` and `page[size]` and adds `page[after]`. So the
  client can follow it as-is and the window and size carry over.
- The cursor is base64 of a JSON pair, the transaction's `createdAt` in UTC and its
  ID. That is an implementation detail, not a contract. Never decode or build one.
- The committed fixtures only show the last page (`prev` and `next` both `null`, for
  example in `tags.json`). A test that exercises paging needs a hand-built fixture
  with a populated `next`.

## Rate limits

- No quota or window is documented. The only documented signals are the
  `X-RateLimit-Remaining` response header and `429`, where the docs advise retrying
  later "ideally with exponential backoff".
- Fathom is one user running a daily sync, which is a handful of calls. No throttling
  logic is needed.
- The Up client should treat a `429` as a retryable error with backoff. That belongs
  in the client ticket, not here.

## Transaction ID stability

- The docs define the ID only as "the unique identifier for this transaction". They do
  not promise stability.
- Evidence from the fixtures: `transaction_held.json` and
  `transaction_settled_after_hold.json` carry the same `id`
  (`5d8756a1-…`), the same `createdAt`, and the same `deepLinkURL`. Only `status`,
  `settledAt` and `transactionType` change. So HELD to SETTLED keeps the ID.
- A settled transaction keeps its original hold amount in `holdInfo`, so an upsert on
  ID can update status and `settledAt` in place without losing the hold amount.
- Conclusion: upserting on transaction ID is safe for the HELD to SETTLED transition,
  which is the case that matters for ADR-006's idempotency rule.
- Not verified: whether an ID survives a reversal or a hold that is released and
  re-posted. Watch for orphaned HELD rows that never settle, and revisit if the
  real data shows them.
