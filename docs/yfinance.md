# yfinance: current and historical ASX prices (S1-18)

Source: `scripts/check_yfinance.py` run against the 10 codes in the CMC fixture
(`tests/fixtures/cmc/Confirmation.csv`) with yfinance 1.7.0. Checked 2026-10-24 (a
Saturday, so the latest bar was Friday 2026-10-23). Rerun the script to repeat the
check; `--dump` writes each code's raw daily history to `data/recon/yfinance/`.

Codes: A200, CLNE, GOLD, IVV, NDQ, QUAL, URAN, XMET (held) and ICOR, SEMI (closed).

## Verdict

yfinance is usable as the ASX end-of-day price provider. Every code resolves as
`<CODE>.AX`, and current and historical daily prices are available back to the first
trade. Every CMC trade price sits inside that day's low to high range (34 of 34
trades). The gaps below must be handled by the price provider and the Snapshot job.
The price-provider interface (ADR-005) stays, so the source can be swapped later.

## Symbols and metadata

- Append `.AX` to the ASX code. All 10 return `currency=AUD`, `exchange=ASX` and
  `timezone=Australia/Sydney`.
- `quoteType` is `ETF` for nine codes and `EQUITY` for GOLD (a structured product).
  Don't assume every holding is `ETF`.
- `longName` and `fundFamily` are populated (GOLD has no fund family). `sector` and
  `category` are empty for every code. The allocation-by-sector view needs its own
  mapping, not yfinance.

## Current price

- `Ticker.fast_info` gives `lastPrice` and `previousClose`. During trading hours
  `lastPrice` is intraday.
- `history(period="5d")` includes today's partial bar while the market is open. The
  EOD job should run after the close (16:30 Sydney is a safe cut-off) or drop a bar
  dated today. The recon script drops it before 16:30.
- One `yf.download([...], group_by="ticker")` call returned closes for all 10 codes.
  That is the shape the daily EOD job should use (ADR-006, SP-08).

## Historical prices

- Fetch with `history(start, end, auto_adjust=False, actions=True)`. `end` is
  exclusive.
- The index is midnight in `Australia/Sydney` (`+10:00` or `+11:00`). Take `.date()`
  for the trading day. Don't convert to UTC first, or the date shifts back a day.
- No duplicate dates, missing closes or zero closes in any code.
- The weekdays missing from every code are all ASX holidays: 2025-12-25, 2025-12-26,
  2026-01-01, 2026-01-26, 2026-04-03, 2026-04-06 and 2026-06-08.

## Adjustment

- Use `Close`, not `Adj Close`. With `auto_adjust=False`, `Close` is the traded price
  and `Adj Close` is back-adjusted for distributions. They differ on most days for
  every distributing code (281 of 300 for IVV).
- yfinance back-adjusts every price for splits even with `auto_adjust=False`. No code
  had a split in the window. A future split would make earlier closes disagree with
  CMC units held, so the provider should detect a non-zero `Stock Splits` and flag it.

## Precision

- Prices come back as float32-derived floats (`72.63999938964844` for 72.64).
- Rounding to 3 decimal places recovers the exchange price. On real bars the
  remainder is at most 7.3e-6. Convert with `Decimal(repr(float(x))).quantize(...)`
  in the provider, before the price leaves it as a `Decimal` (ADR-004).
- Some closes above $2 carry a half cent (URAN 15.975, XMET 14.185, SEMI 22.525).
  The ASX tick above $2 is one cent, so these may not be the official closing price.
  Not resolved: compare one against the ASX or CMC close before relying on it.
  Store 3 decimal places either way.

## Gaps and placeholder bars

- **2025-10-24 is missing.** It was an ordinary trading Friday. Eight codes have no
  bar for it. NDQ and SEMI have a placeholder bar: volume 0 and open, high, low and
  close all equal, at a price that is not on any tick (NDQ 57.4667).
- URAN has a similar zero-volume, flat bar on 2026-09-07 at 15.975, which may just be
  a day with no trades.
- So:
  - Snapshots need a rule for a missing price. Carrying the last close forward is
    the obvious choice. Decide it in S1-24.
  - The provider should treat a zero-volume flat bar as missing, not as a price.
  - A gap can't be told apart from a holiday by looking at the bars. The job needs
    an ASX trading calendar to know when a bar is missing.

## Distributions

- `actions=True` returns ex-dates and amounts per unit. They are not reliable:
  URAN lists 0.02 on both 2026-06-30 and 2026-07-01, which looks like a duplicate.
- yfinance has no franking credits. Dividends come from the CMC cash summary, not
  from yfinance.

## Not verified

- Whether the half-cent closes match the official ASX close.
- How quickly after the close the day's bar settles to its final value.
- Behaviour after a delisting or a code change. None of the held codes has had one.
- Rate limits. Yahoo publishes none. One batched call a day is well inside any
  plausible limit, but the job should retry with backoff on failure (ADR-006).
