"""Check that yfinance returns usable prices for the ASX codes in a CMC export (S1-18).

    uv run python scripts/check_yfinance.py
    uv run python scripts/check_yfinance.py --codes IVV NDQ
    uv run python scripts/check_yfinance.py --trades path/to/Confirmation.csv --dump

The codes come from a CMC Markets ``Confirmation.csv``: the real export in
``data/recon/cmc/`` if it is there, otherwise the masked fixture. A code is "held" when
its bought quantity exceeds its sold quantity. Closed codes are checked too, because a
historical Snapshot needs their prices for the days they were held.

For each code the script reports:

- Metadata: the ``.AX`` symbol resolves, and currency, exchange, quote type and time
  zone are AUD, ASX, ETF or equity, and Australia/Sydney. Name, fund family, category
  and sector, which the allocation-by-sector view would need.
- Current price: last price, previous close, the date of the latest daily bar and how
  many weekdays old it is.
- History from the first trade to today, unadjusted (``auto_adjust=False``): row count,
  missing or zero closes, zero-volume days, duplicate dates, and weekdays missing for
  this code that other codes have (a real gap rather than an ASX holiday).
- Adjustment: how many days ``Close`` and ``Adj Close`` differ. Valuation must use
  ``Close``, which ``auto_adjust=False`` leaves unadjusted for distributions. yfinance
  still back-adjusts every price for splits, so any split in the window is flagged.
- Trade check: every CMC trade price sits inside that day's low to high range.
- Precision: yfinance returns float32-derived floats (``72.63999938964844``). The script
  measures how far each close is from the nearest 0.001, to confirm that rounding to a
  fixed number of places recovers the exact exchange price.
- Distributions and splits yfinance lists in the history window.

Before 16:30 Sydney time on a weekday, today's bar is intraday, not a close, so it is
dropped from the history and labelled in the current-price line.

It finishes with one batched ``yf.download`` call over every code, the shape the daily
EOD price job would use.

``--dump`` writes each code's raw daily history to ``data/recon/yfinance/<CODE>.csv``
(gitignored) for inspection or for building price-provider fixtures later.
"""

from __future__ import annotations

import argparse
import csv
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import yfinance as yf

if TYPE_CHECKING:
    import pandas as pd

# yfinance 1.7 trips pandas' inplace deprecation on every call; it is not our code.
warnings.filterwarnings("ignore", message=".*inplace keyword.*")

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_TRADES = REPO_ROOT / "data" / "recon" / "cmc" / "Confirmation.csv"
FIXTURE_TRADES = REPO_ROOT / "tests" / "fixtures" / "cmc" / "Confirmation.csv"
DEFAULT_DUMP_DIR = REPO_ROOT / "data" / "recon" / "yfinance"

ASX_SUFFIX = ".AX"
ASX_TZ = ZoneInfo("Australia/Sydney")
HISTORY_LEAD_DAYS = 7
STALE_WEEKDAYS = 1
PRICE_STEP = Decimal("0.001")
# Float32 noise is about 1e-5 at these prices and a third decimal is 1e-3, so this sits
# well clear of both.
PRECISION_TOLERANCE = Decimal("0.0001")
CENT = Decimal("0.01")
# The ASX tick is a cent from $2 up, so a sub-cent close above that is not a
# traded price.
CENT_TICK_FLOOR = Decimal(2)
ASX_CLOSE = time(16, 30)
MAX_LISTED_ISSUES = 5
EXPECTED_QUOTE_TYPES = {"ETF", "EQUITY"}


class Status(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


class OrderType(StrEnum):
    BUY = "Buy"
    SELL = "Sell"


@dataclass(frozen=True)
class Trade:
    code: str
    order_type: OrderType
    trade_date: date
    price: Decimal
    quantity: Decimal


@dataclass
class Finding:
    status: Status
    check: str
    detail: str


@dataclass
class CodeReport:
    code: str
    held: bool
    findings: list[Finding] = field(default_factory=list)
    history: pd.DataFrame | None = None

    def add(self, status: Status, check: str, detail: str) -> None:
        self.findings.append(Finding(status, check, detail))

    @property
    def worst(self) -> Status:
        statuses = {f.status for f in self.findings}
        for status in (Status.FAIL, Status.WARN):
            if status in statuses:
                return status
        return Status.OK


def load_trades(path: Path) -> list[Trade]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        Trade(
            code=row["AsxCode"].strip().upper(),
            order_type=OrderType(row["Order Type"].strip()),
            trade_date=date.fromisoformat(row["Trade Date"].strip()),
            price=Decimal(row["Price"].strip()),
            quantity=Decimal(row["Quantity"].strip()),
        )
        for row in rows
    ]


def net_quantities(trades: list[Trade]) -> dict[str, Decimal]:
    net: dict[str, Decimal] = defaultdict(Decimal)
    for trade in trades:
        sign = 1 if trade.order_type is OrderType.BUY else -1
        net[trade.code] += sign * trade.quantity
    return dict(net)


def weekdays_between(start: date, end: date) -> int:
    days = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:  # noqa: PLR2004 Monday to Friday are 0 to 4
            days += 1
        current += timedelta(days=1)
    return days


def bar_dates(history: pd.DataFrame) -> list[date]:
    return [ts.date() for ts in history.index]


def check_metadata(report: CodeReport, ticker: yf.Ticker) -> None:
    fast = ticker.fast_info
    currency = fast.get("currency")
    exchange = fast.get("exchange")
    quote_type = fast.get("quoteType")
    timezone = fast.get("timezone")
    ok = (
        currency == "AUD"
        and exchange == "ASX"
        and quote_type in EXPECTED_QUOTE_TYPES
        and timezone == "Australia/Sydney"
    )
    report.add(
        Status.OK if ok else Status.WARN,
        "metadata",
        f"currency={currency} exchange={exchange} type={quote_type} tz={timezone}",
    )

    info = ticker.info
    report.add(
        Status.OK if info.get("longName") else Status.WARN,
        "names",
        f"name={info.get('longName')!r} family={info.get('fundFamily')!r} "
        f"category={info.get('category')!r} sector={info.get('sector')!r}",
    )


def check_current(report: CodeReport, ticker: yf.Ticker, now: datetime) -> None:
    fast = ticker.fast_info
    last_price = fast.get("lastPrice")
    previous_close = fast.get("previousClose")
    if last_price is None:
        report.add(Status.FAIL, "current", "fast_info has no lastPrice")
        return

    recent = ticker.history(period="5d", auto_adjust=False)
    if recent.empty:
        report.add(Status.FAIL, "current", "no daily bars in the last 5 days")
        return
    latest = bar_dates(recent)[-1]
    age = weekdays_between(latest, now.date())
    intraday = " (intraday)" if is_intraday(latest, now) else ""
    report.add(
        Status.OK if age <= STALE_WEEKDAYS else Status.WARN,
        "current",
        f"last={last_price!r} prev_close={previous_close!r} "
        f"latest_bar={latest}{intraday} ({age} weekday(s) old) "
        f"bar_close={recent['Close'].iloc[-1]!r}",
    )


def is_intraday(bar: date, now: datetime) -> bool:
    return bar == now.date() and now.time() < ASX_CLOSE


def fetch_history(ticker: yf.Ticker, start: date, today: date) -> pd.DataFrame:
    # end is exclusive in yfinance.
    return ticker.history(
        start=start.isoformat(),
        end=(today + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        actions=True,
    )


def check_history_shape(report: CodeReport, history: pd.DataFrame) -> None:
    if history.empty:
        report.add(Status.FAIL, "history", "no rows returned")
        return
    dates = bar_dates(history)
    duplicates = len(dates) - len(set(dates))
    missing_close = int(history["Close"].isna().sum())
    zero_close = int((history["Close"] <= 0).sum())
    zero_volume = history["Volume"] == 0
    # A zero-volume bar with open, high, low and close all equal is a placeholder
    # yfinance filled in, not a traded price.
    flat = history[["Open", "High", "Low"]].eq(history["Close"], axis=0).all(axis=1)
    placeholders = [str(ts.date()) for ts in history.index[zero_volume & flat]]
    status = Status.OK
    if duplicates or missing_close or zero_close:
        status = Status.FAIL
    elif zero_volume.any():
        status = Status.WARN
    detail = (
        f"{len(history)} rows {dates[0]} to {dates[-1]}, tz={history.index.tz}; "
        f"duplicates={duplicates} missing_close={missing_close} "
        f"zero_close={zero_close} zero_volume_days={int(zero_volume.sum())}"
    )
    if placeholders:
        detail += f"; flat zero-volume bars: {', '.join(placeholders)}"
    report.add(status, "history", detail)


def check_gaps(report: CodeReport, all_dates: set[date]) -> None:
    if report.history is None or report.history.empty:
        return
    own = set(bar_dates(report.history))
    first, last = min(own), max(own)
    missing = sorted(d for d in all_dates if first <= d <= last and d not in own)
    if not missing:
        report.add(Status.OK, "gaps", "no days missing that other codes have")
        return
    shown = ", ".join(str(d) for d in missing[:MAX_LISTED_ISSUES])
    report.add(
        Status.WARN,
        "gaps",
        f"{len(missing)} day(s) other codes have but this one lacks: {shown}",
    )


def check_adjustment(report: CodeReport, history: pd.DataFrame) -> None:
    if history.empty or "Adj Close" not in history:
        return
    differs = int((history["Close"] - history["Adj Close"]).abs().gt(1e-6).sum())
    report.add(
        Status.OK,
        "adjustment",
        f"Close and Adj Close differ on {differs} of {len(history)} days "
        "(valuation must use Close)",
    )


def check_trades(
    report: CodeReport, history: pd.DataFrame, trades: list[Trade]
) -> None:
    if history.empty:
        return
    by_date = {ts.date(): row for ts, row in history.iterrows()}
    outside: list[str] = []
    no_bar: list[str] = []
    for trade in trades:
        row = by_date.get(trade.trade_date)
        if row is None:
            no_bar.append(str(trade.trade_date))
            continue
        low = Decimal(repr(float(row["Low"]))) - PRECISION_TOLERANCE
        high = Decimal(repr(float(row["High"]))) + PRECISION_TOLERANCE
        if not low <= trade.price <= high:
            outside.append(
                f"{trade.trade_date} {trade.order_type} @ {trade.price} "
                f"vs {row['Low']:.3f}-{row['High']:.3f}"
            )
    status = Status.FAIL if outside or no_bar else Status.OK
    detail = f"{len(trades) - len(outside) - len(no_bar)}/{len(trades)} trade prices "
    detail += "inside the day's low-high"
    if no_bar:
        detail += f"; no bar on {', '.join(no_bar[:MAX_LISTED_ISSUES])}"
    if outside:
        detail += f"; outside: {'; '.join(outside[:MAX_LISTED_ISSUES])}"
    report.add(status, "trades", detail)


def check_precision(report: CodeReport, history: pd.DataFrame) -> None:
    if history.empty:
        return
    worst = Decimal(0)
    sub_cent = 0
    off_tick: list[str] = []
    for ts, value in history["Close"].dropna().items():
        exact = Decimal(repr(float(value)))
        rounded = exact.quantize(PRICE_STEP)
        worst = max(worst, abs(exact - rounded))
        if rounded != rounded.quantize(CENT):
            sub_cent += 1
            if rounded >= CENT_TICK_FLOOR:
                off_tick.append(f"{ts.date()}={rounded}")
    detail = (
        f"max distance from nearest {PRICE_STEP} is {worst:.2E}; "
        f"{sub_cent} close(s) carry a third decimal"
    )
    if off_tick:
        detail += f"; off the 1c tick: {', '.join(off_tick[:MAX_LISTED_ISSUES])}"
    ok = worst <= PRECISION_TOLERANCE and not off_tick
    report.add(Status.OK if ok else Status.WARN, "precision", detail)


def check_distributions(report: CodeReport, history: pd.DataFrame) -> None:
    if history.empty or "Dividends" not in history:
        return
    paid = history.loc[history["Dividends"] > 0, "Dividends"]
    listed = ", ".join(f"{ts.date()}={value!r}" for ts, value in paid.items())
    report.add(
        Status.OK,
        "distributions",
        f"{len(paid)} ex-date(s) in window" + (f": {listed}" if listed else ""),
    )


def check_splits(report: CodeReport, history: pd.DataFrame) -> None:
    if history.empty or "Stock Splits" not in history:
        return
    splits = history.loc[history["Stock Splits"] > 0, "Stock Splits"]
    if splits.empty:
        report.add(Status.OK, "splits", "none in window")
        return
    listed = ", ".join(f"{ts.date()}={value!r}" for ts, value in splits.items())
    report.add(
        Status.WARN,
        "splits",
        f"{listed}: earlier prices are split-adjusted, so they do not match CMC units",
    )


def check_code(
    code: str,
    trades: list[Trade],
    *,
    held: bool,
    now: datetime,
) -> CodeReport:
    report = CodeReport(code=code, held=held)
    ticker = yf.Ticker(code + ASX_SUFFIX)
    start = min(t.trade_date for t in trades) - timedelta(days=HISTORY_LEAD_DAYS)
    # Each stage hits a different Yahoo endpoint, so one failing must not skip the rest.
    try:
        check_metadata(report, ticker)
    except Exception as exc:  # noqa: BLE001 recon script: record any yfinance failure as a finding
        report.add(Status.FAIL, "metadata", f"{type(exc).__name__}: {exc}")
    try:
        check_current(report, ticker, now)
    except Exception as exc:  # noqa: BLE001 recon script: record any yfinance failure as a finding
        report.add(Status.FAIL, "current", f"{type(exc).__name__}: {exc}")
    try:
        history = fetch_history(ticker, start, now.date())
    except Exception as exc:  # noqa: BLE001 recon script: record any yfinance failure as a finding
        report.add(Status.FAIL, "history", f"{type(exc).__name__}: {exc}")
        return report
    if not history.empty and is_intraday(bar_dates(history)[-1], now):
        history = history.iloc[:-1]
    report.history = history
    check_history_shape(report, history)
    check_adjustment(report, history)
    check_trades(report, history, trades)
    check_precision(report, history)
    check_distributions(report, history)
    check_splits(report, history)
    return report


def check_batch(codes: list[str]) -> Finding:
    symbols = [code + ASX_SUFFIX for code in codes]
    try:
        frame = yf.download(
            symbols,
            period="5d",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as exc:  # noqa: BLE001 recon script: record any yfinance failure as a finding
        return Finding(Status.FAIL, "batch", f"{type(exc).__name__}: {exc}")
    if frame is None or frame.empty:
        return Finding(Status.FAIL, "batch", "yf.download returned nothing")
    missing = [
        symbol
        for symbol in symbols
        if symbol not in frame.columns.get_level_values(0)
        or frame[symbol]["Close"].dropna().empty
    ]
    if missing:
        return Finding(Status.FAIL, "batch", f"no closes for {', '.join(missing)}")
    return Finding(
        Status.OK,
        "batch",
        f"one call returned closes for all {len(symbols)} codes, "
        f"latest bar {frame.index[-1].date()}",
    )


def say(message: str) -> None:
    sys.stdout.write(message + "\n")


def dump_history(reports: list[CodeReport], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for report in reports:
        if report.history is not None and not report.history.empty:
            report.history.to_csv(directory / f"{report.code}.csv")


def weekdays_no_code_has(all_dates: set[date]) -> list[date]:
    if not all_dates:
        return []
    first, last = min(all_dates), max(all_dates)
    days = (first + timedelta(days=n) for n in range((last - first).days + 1))
    return [
        d
        for d in days
        if d.weekday() < 5 and d not in all_dates  # noqa: PLR2004 Monday to Friday are 0 to 4
    ]


def print_report(
    reports: list[CodeReport], batch: Finding, all_dates: set[date]
) -> None:
    for report in reports:
        state = "held" if report.held else "closed"
        say(f"\n== {report.code}{ASX_SUFFIX} ({state}) [{report.worst}]")
        for finding in report.findings:
            say(f"  {finding.status:<4} {finding.check:<13} {finding.detail}")
    say(f"\n== batch\n  {batch.status:<4} {batch.check:<13} {batch.detail}")

    absent = weekdays_no_code_has(all_dates)
    say("\n== weekdays no code has (should all be ASX holidays)")
    say("  " + (", ".join(str(d) for d in absent) or "none"))

    say("\n== summary")
    for report in reports:
        say(f"  {report.worst:<4} {report.code}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--trades",
        type=Path,
        default=REAL_TRADES if REAL_TRADES.exists() else FIXTURE_TRADES,
        help="CMC Confirmation.csv (default: real export if present, else fixture)",
    )
    parser.add_argument(
        "--codes",
        nargs="+",
        help="check only these ASX codes (without the .AX suffix)",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help=f"write raw daily history per code to {DEFAULT_DUMP_DIR}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trades = load_trades(args.trades)
    net = net_quantities(trades)
    codes = sorted({c.upper() for c in args.codes} if args.codes else net)
    unknown = [c for c in codes if c not in net]
    if unknown:
        sys.stderr.write(f"no trades in {args.trades} for: {', '.join(unknown)}\n")
        return 2

    now = datetime.now(ASX_TZ)
    say(f"trades: {args.trades}")
    say(f"now (Sydney): {now:%Y-%m-%d %H:%M}, yfinance {yf.__version__}")

    trades_by_code: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        trades_by_code[trade.code].append(trade)

    reports = [
        check_code(code, trades_by_code[code], held=net[code] > 0, now=now)
        for code in codes
    ]
    all_dates = {
        d
        for r in reports
        if r.history is not None and not r.history.empty
        for d in bar_dates(r.history)
    }
    for report in reports:
        check_gaps(report, all_dates)

    batch = check_batch(codes)
    print_report(reports, batch, all_dates)
    if args.dump:
        dump_history(reports, DEFAULT_DUMP_DIR)
        say(f"\nhistory written to {DEFAULT_DUMP_DIR}")

    failed = batch.status is Status.FAIL or any(r.worst is Status.FAIL for r in reports)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
