"""Mask raw CMC Markets exports into committable test fixtures (S1-16).

Raw exports live in ``data/recon/cmc/`` (gitignored, never committed). Masked copies are
written to ``tests/fixtures/cmc/`` as ``Confirmation.csv`` and
``CashTransactionSummary.csv``.

    uv run python scripts/mask_cmc_fixtures.py

The two files describe the same trades, so they are masked together and stay consistent:

- Confirmation Numbers are remapped, and a trade's cash-summary line carries the same
  fake number as its confirmation.
- Each ticker's quantity is multiplied by a fixed factor (2 to 8) derived from the
  secret key in ``data/recon/.mask-key`` (shared with ``mask_fixtures.py``). Unit prices
  are public market data and are kept.
- Every figure that depends on a quantity is recomputed: consideration, the cash line's
  debit or credit, running balances, the closing balance and the totals. A sell keeps
  its brokerage and GST. The fixtures therefore still pass the checks the importer will
  run.
- Deposit and dividend amounts are perturbed (same digit count, whole dollars stay
  whole dollars). The opening balance is raised if needed so the balance never goes
  negative.
- Account number, account name, journal, VRN and DEP numbers are replaced.

Kept as they are: dates, tickers, order types, prices, fees, and the file's quirks
(byte-order mark, CRLF line endings, which fields are quoted).

A description the script does not recognise aborts the run, because it could carry
free text. After masking, the output is scanned for every real identifier replaced.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import re
import sys
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from mask_fixtures import DEFAULT_KEY_PATH, MaskConfig, Masker, MaskError, load_key

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "recon" / "cmc"
DEFAULT_OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "cmc"

CONFIRMATION_NAME = "Confirmation.csv"
CASH_NAME = "CashTransactionSummary.csv"
FAKE_ACCOUNT_NAME = "MR TEST INVESTOR"

_BOM = "﻿"
_CRLF = "\r\n"
_CONFIRMATION_QUOTED = frozenset({"Avg Price"})
_FEE_COLUMNS = (
    "Brokerage",
    "GST",
    "Stampduty",
    "Application Fee",
    "OtherCharge",
    "Fee",
)
_QUANTITY_FACTORS = range(2, 9)
_CENTS_PER_DOLLAR = 100
_MIN_LEAK_LENGTH = 4

_TRADE_LINE = re.compile(r"(Bght|Sold) (\S+) ([A-Z0-9]+) @ (\S+) AUD (\d+)")
_JOURNAL = re.compile(r"JNL(\d+) \]NPP VRN:(\d+) DEP:(\d+)")
_DIVIDEND = re.compile(r"EXTERNAL - DIV [A-Z0-9 ]*")
_UNNAMED_RECEIPT = re.compile(r"(EXTERNAL - [A-Z]{3}\d{2}/)(\d+)([A-Z0-9 ]*)")
_ALIGNMENT = "Statement Balance Alignment"
_STRUCTURE = ("OPENING BALANCE", "CLOSING BALANCE", "TOTALS")


class Side(StrEnum):
    BUY = "Buy"
    SELL = "Sell"


_SIDE_BY_VERB = {"Bght": Side.BUY, "Sold": Side.SELL}


@dataclass(frozen=True)
class MaskedTrade:
    """What a trade became, so its cash-summary line can follow it."""

    side: Side
    code: str
    quantity: Decimal
    cents: int
    reference: str
    price: Decimal
    real_quantity: Decimal


@dataclass(frozen=True)
class CashEntry:
    """One movement in the cash summary, in whole cents."""

    date: str
    description: str
    debit: int
    credit: int


def parse_cents(text: str) -> int:
    """Whole cents from a dollar string. A fractional cent is an error, not rounded."""
    if not text:
        return 0
    try:
        value = Decimal(text) * _CENTS_PER_DOLLAR
    except InvalidOperation as exc:
        msg = f"not an amount: {text!r}"
        raise MaskError(msg) from exc
    if value != value.to_integral_value():
        msg = f"amount is not whole cents: {text!r}"
        raise MaskError(msg)
    return int(value)


def trade_cents(quantity: Decimal, price: Decimal) -> int:
    """Quantity times price in cents.

    Dev-script stand-in for the single rounding function in ``domain/`` (ADR-004
    Amendment), which does not exist yet. Swap this for it when it lands.
    """
    exact = quantity * price * _CENTS_PER_DOLLAR
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return (
        f"{sign}{abs(cents) // _CENTS_PER_DOLLAR}.{abs(cents) % _CENTS_PER_DOLLAR:02d}"
    )


def _amount_cell(cents: int) -> str:
    return format_cents(cents) if cents else ""


class CmcMasker:
    def __init__(self, key: bytes) -> None:
        self._key = key
        self._money = Masker(key, MaskConfig())
        self._numbers: dict[tuple[str, str], str] = {}
        self._taken: set[tuple[str, str]] = set()
        self.real_values: set[str] = set()

    # -- primitives ---------------------------------------------------------

    def _digest(self, label: str, real: str) -> bytes:
        message = f"{label}\0{real}".encode()
        return hmac.new(self._key, message, hashlib.sha256).digest()

    def number(self, label: str, real: str) -> str:
        """Fake digits of the same length. Same input, same output; no two collide."""
        known = self._numbers.get((label, real))
        if known is not None:
            return known
        low = 10 ** (len(real) - 1)
        fake = str(low + int.from_bytes(self._digest(label, real)[:8]) % (9 * low))
        if (label, fake) in self._taken:
            msg = f"two different {label} values masked to the same number"
            raise MaskError(msg)
        self._taken.add((label, fake))
        self._numbers[(label, real)] = fake
        if len(real) >= _MIN_LEAK_LENGTH:
            self.real_values.add(real)
        return fake

    def factor(self, code: str) -> int:
        digest = self._digest("quantity", code)
        return _QUANTITY_FACTORS[digest[0] % len(_QUANTITY_FACTORS)]

    # -- Confirmation.csv ---------------------------------------------------

    def mask_confirmations(
        self, rows: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], dict[str, MaskedTrade]]:
        masked: list[dict[str, str]] = []
        trades: dict[str, MaskedTrade] = {}
        for row in rows:
            fake_row, trade = self._mask_confirmation(row)
            masked.append(fake_row)
            if row["Confirmation Number"] in trades:
                msg = "duplicate Confirmation Number in Confirmation.csv"
                raise MaskError(msg)
            trades[row["Confirmation Number"]] = trade
        return masked, trades

    def _mask_confirmation(
        self, row: dict[str, str]
    ) -> tuple[dict[str, str], MaskedTrade]:
        code = row["AsxCode"]
        try:
            side = Side(row["Order Type"])
        except ValueError as exc:
            msg = f"unknown Order Type {row['Order Type']!r}"
            raise MaskError(msg) from exc
        if row["Reverse Confirmation Number"] not in {"", "0"} or row["As at Date"]:
            msg = "reversed or back-dated confirmation: format not yet observed"
            raise MaskError(msg)
        price = Decimal(row["Price"])
        fees = sum(parse_cents(row[column]) for column in _FEE_COLUMNS)
        self._check_consideration(row, side, price, fees)
        quantity = Decimal(row["Quantity"]) * self.factor(code)
        gross = trade_cents(quantity, price)
        cents = gross - fees if side is Side.SELL else gross + fees
        reference = self.number("reference", row["Confirmation Number"])
        self.real_values.add(row["Account Name"])
        fake_row = {
            **row,
            "Account Number": self.number("account", row["Account Number"]),
            "Account Name": FAKE_ACCOUNT_NAME,
            "Confirmation Number": reference,
            "Quantity": format(quantity, "f"),
            "Consideration": f"{Decimal(cents).scaleb(-2):.4f}",
        }
        return fake_row, MaskedTrade(
            side,
            code,
            quantity,
            cents,
            reference,
            price,
            Decimal(row["Quantity"]),
        )

    @staticmethod
    def _check_consideration(
        row: dict[str, str], side: Side, price: Decimal, fees: int
    ) -> None:
        """Refuse a row whose own numbers don't add up: the fixture would be invalid."""
        gross = trade_cents(Decimal(row["Quantity"]), price)
        expected = gross - fees if side is Side.SELL else gross + fees
        if (
            parse_cents(row["Discount"])
            or parse_cents(row["Consideration"]) != expected
        ):
            ref = row["Confirmation Number"]
            msg = f"confirmation {ref}: consideration does not add up"
            raise MaskError(msg)

    # -- CashTransactionSummary.csv ----------------------------------------

    def mask_cash(
        self, rows: list[list[str]], trades: dict[str, MaskedTrade]
    ) -> list[list[str]]:
        header, opening, entries, closing_date, has_totals = _split_cash(rows)
        masked = [self._mask_entry(entry, trades) for entry in entries]
        deltas = [entry.credit - entry.debit for entry in masked]
        lowest = min(0, *_running(deltas))
        start = max(self._money.cents(opening), -lowest)
        balance = start
        out = [header, [rows[1][0], _STRUCTURE[0], "", "", format_cents(start)]]
        for entry in masked:
            balance += entry.credit - entry.debit
            out.append(
                [
                    entry.date,
                    entry.description,
                    _amount_cell(entry.debit),
                    _amount_cell(entry.credit),
                    format_cents(balance),
                ]
            )
        out.append([closing_date, _STRUCTURE[1], "", "", format_cents(balance)])
        if has_totals:
            debits = sum(entry.debit for entry in masked)
            received = sum(entry.credit for entry in masked)
            out += [
                [],
                ["", _STRUCTURE[2], format_cents(debits), format_cents(received), ""],
            ]
        return out

    def _mask_entry(
        self, entry: CashEntry, trades: dict[str, MaskedTrade]
    ) -> CashEntry:
        trade_line = _TRADE_LINE.fullmatch(entry.description)
        if trade_line:
            return self._mask_trade_line(entry, trade_line, trades)
        description = self._mask_description(entry.description)
        return CashEntry(
            entry.date,
            description,
            self._money.cents(entry.debit),
            self._money.cents(entry.credit),
        )

    def _mask_description(self, text: str) -> str:
        journal = _JOURNAL.fullmatch(text)
        if journal:
            number, vrn, dep = journal.groups()
            return (
                f"JNL{self.number('journal', number)} ]NPP "
                f"VRN:{self.number('vrn', vrn)} DEP:{self.number('dep', dep)}"
            )
        receipt = _UNNAMED_RECEIPT.fullmatch(text)
        if receipt:
            prefix, number, rest = receipt.groups()
            return prefix + self.number("receipt", number) + rest
        if text == _ALIGNMENT or _DIVIDEND.fullmatch(text):
            return text
        msg = f"unrecognised cash description {text!r}"
        raise MaskError(msg)

    def _mask_trade_line(
        self,
        entry: CashEntry,
        line: re.Match[str],
        trades: dict[str, MaskedTrade],
    ) -> CashEntry:
        verb, quantity_text, code, price_text, reference = line.groups()
        trade = trades.get(reference)
        if trade is None:
            msg = f"cash line references a trade with no confirmation: {reference}"
            raise MaskError(msg)
        if (
            trade.side is not _SIDE_BY_VERB[verb]
            or trade.code != code
            or Decimal(quantity_text) != trade.real_quantity
            or Decimal(price_text) != trade.price
        ):
            msg = f"cash line for {reference} disagrees with its confirmation"
            raise MaskError(msg)
        masked_quantity = format(trade.quantity.normalize(), "f")
        description = (
            f"{verb} {masked_quantity} {code} @ {price_text} AUD {trade.reference}"
        )
        debit, credit = (trade.cents, 0) if verb == "Bght" else (0, trade.cents)
        return CashEntry(entry.date, description, debit, credit)


def _running(deltas: list[int]) -> list[int]:
    total, totals = 0, []
    for delta in deltas:
        total += delta
        totals.append(total)
    return totals


def _split_cash(
    rows: list[list[str]],
) -> tuple[list[str], int, list[CashEntry], str, bool]:
    """Header, opening balance, movements, closing date, whether a TOTALS row exists."""
    if len(rows) < 3 or rows[1][1:2] != [_STRUCTURE[0]]:  # noqa: PLR2004 - header, opening, closing
        msg = "cash summary does not start with an OPENING BALANCE row"
        raise MaskError(msg)
    opening = parse_cents(rows[1][4])
    entries: list[CashEntry] = []
    closing_date, has_totals = "", False
    for row in rows[2:]:
        if not row:
            continue
        if row[1] == _STRUCTURE[1]:
            closing_date = row[0]
        elif row[1] == _STRUCTURE[2]:
            has_totals = True
        else:
            entries.append(
                CashEntry(row[0], row[1], parse_cents(row[2]), parse_cents(row[3]))
            )
    if not closing_date:
        msg = "cash summary has no CLOSING BALANCE row"
        raise MaskError(msg)
    return rows[0], opening, entries, closing_date, has_totals


# -- reading and writing ------------------------------------------------------


@dataclass(frozen=True)
class RawText:
    body: str
    bom: bool


def read_text(path: Path) -> RawText:
    text = path.read_bytes().decode("utf-8")
    return RawText(text.removeprefix(_BOM), text.startswith(_BOM))


def render(
    rows: list[list[str]],
    *,
    bom: bool,
    quote: frozenset[int] | None,
    quote_header: bool,
) -> str:
    """Join rows with CRLF. ``quote`` lists data columns to quote; None quotes all."""
    lines = []
    for number, row in enumerate(rows):
        cells = [
            f'"{cell}"'
            if (quote_header if number == 0 else quote is None or index in quote)
            else cell
            for index, cell in enumerate(row)
        ]
        lines.append(",".join(cells) if row else "")
    return (_BOM if bom else "") + _CRLF.join(lines) + _CRLF


def check_output(texts: dict[str, str], masker: CmcMasker) -> None:
    for name, text in texts.items():
        for real in masker.real_values:
            if re.search(rf"(?<![\w.]){re.escape(real)}(?![\w.])", text):
                msg = f"{name}: a real value survived masking"
                raise MaskError(msg)


def find_cash_summary(raw_dir: Path) -> Path:
    found = sorted(raw_dir.glob("CashTransactionSummary*.csv"))
    if len(found) != 1:
        msg = (
            f"expected one CashTransactionSummary*.csv in {raw_dir}, found {len(found)}"
        )
        raise MaskError(msg)
    return found[0]


def run(
    raw_dir: Path,
    out_dir: Path,
    key_path: Path = DEFAULT_KEY_PATH,
) -> list[Path]:
    """Mask both exports. Nothing is written unless both pass. Returns files written."""
    masker = CmcMasker(load_key(key_path))
    confirmation = read_text(raw_dir / CONFIRMATION_NAME)
    cash = read_text(find_cash_summary(raw_dir))

    reader = csv.DictReader(io.StringIO(confirmation.body, newline=""))
    fieldnames = list(reader.fieldnames or [])
    masked_rows, trades = masker.mask_confirmations(list(reader))
    confirmation_rows = [fieldnames] + [
        [row[name] for name in fieldnames] for row in masked_rows
    ]
    quoted = frozenset(
        index for index, name in enumerate(fieldnames) if name in _CONFIRMATION_QUOTED
    )
    cash_rows = masker.mask_cash(
        list(csv.reader(io.StringIO(cash.body, newline=""))), trades
    )

    texts = {
        CONFIRMATION_NAME: render(
            confirmation_rows,
            bom=confirmation.bom,
            quote=quoted,
            quote_header=False,
        ),
        CASH_NAME: render(cash_rows, bom=cash.bom, quote=None, quote_header=True),
    }
    check_output(texts, masker)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in texts.items():
        destination = out_dir / name
        destination.write_bytes(text.encode("utf-8"))
        written.append(destination)
    return written


def _say(message: str) -> None:
    sys.stdout.write(message + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    if not args.raw.is_dir():
        _say(f"No raw exports at {args.raw}")
        return 1
    try:
        written = run(args.raw, args.out)
    except (MaskError, OSError) as exc:
        _say(f"ABORTED: {exc}")
        return 1
    _say(f"Masked {len(written)} file(s) into {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
