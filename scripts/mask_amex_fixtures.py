"""Mask raw AMEX activity exports into committable test fixtures (S1-17).

Raw exports live in ``data/recon/raw/amex/`` (gitignored, never committed). Masked
copies are written to ``tests/fixtures/amex/`` under the same file names.

    uv run python scripts/mask_amex_fixtures.py

Only the 14-column export is accepted. The 4-column default export has no
``Reference``, which is the only unique key, so a file whose header differs aborts.

What is masked:

- ``Reference``: the shape is kept (``'AT`` + year + day-of-year + 4 digits + 12 digits,
  ``'S000`` + digits, and the 23-digit card-fee form) and so is the part that carries a
  date. The rest becomes fake digits. No two references collide.
- ``Description`` and ``Appears On Your Statement As``, which stay equal: a merchant
  becomes ``MERCHANT xxxx`` (or the name pinned in ``data/recon/mask-config.json``),
  padded to the export's fixed width. Payment, fee and credit wordings are kept; the
  ``W`` number on an online payment is masked.
- ``Amount``: from its absolute value, with the sign put back, so equal amounts stay
  equal and a repeat purchase stays a repeat. On a foreign row ``Commission`` is
  recomputed so it is still 3.00% or 3.50% of the amount before commission, and the
  foreign amount is scaled to match, keeping its currency, decimals and thousands
  separators.
- ``Address``, ``Town/City`` and ``Postcode``: fixed fake values, with any embedded
  line break kept.

Arithmetic here (cents, commission, foreign-amount scaling) only shapes fixture data.
It is not Spend rounding, so the single rounding function in ``domain/`` does not apply.

Kept as they are: dates, ``Country``, the header, the file's quirks (LF endings, quoted
fields with embedded newlines, apostrophe-wrapped references, and whether the file ends
with a line break).

A file with more than 25 rows is cut to a subset chosen by rule: the first row of every
description and reference kind, every foreign row, every row of a same-day repeat, every
row whose posting date differs from a purchase on the 14th, then the earliest remaining
rows up to 25. Rows keep their order.

An unexpected header, a filled ``Exchange Rate`` or ``Additional Information``, an
unknown reference shape, or a commission that fits neither rate aborts the run. After
masking, the output is scanned for every real identifier replaced.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path

from mask_fixtures import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_KEY_PATH,
    MaskConfig,
    Masker,
    MaskError,
    load_config,
    load_key,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "recon" / "raw" / "amex"
DEFAULT_OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "amex"

SUBSET_SIZE = 25
HEADER = [
    "Date",
    "Date Processed",
    "Description",
    "Amount",
    "Foreign Spend Amount",
    "Commission",
    "Exchange Rate",
    "Additional Information",
    "Appears On Your Statement As",
    "Address",
    "Town/City",
    "Postcode",
    "Country",
    "Reference",
]

_BOM = "﻿"
_MIN_LEAK_LENGTH = 4
_DESCRIPTION_WIDTH = 23
_FAKE_TOWN = "TESTVILLE"
_FAKE_PLACE = "TESTTOWN"
_FAKE_STREET = "1 TEST STREET"
# Commission as hundredths of a percent of the amount before commission. Seen: 3.00%
# in 2025 and 3.50% in 2026. Not assumed to be fixed: the importer must store it.
_COMMISSION_RATES = (300, 350)
_RATE_SCALE = 10_000
# Selects fixture rows only. It is not a period rule: periods come from the resolver.
_BOUNDARY_DAY = "14"

_DATE = re.compile(r"\d\d/\d\d/\d{4}")
_AMOUNT = re.compile(r"-?\d+\.\d\d")
_FOREIGN = re.compile(r"(\d[\d,]*(?:\.\d+)?) ([A-Z]{3})")
_ONLINE_PAYMENT = re.compile(r"(ONLINE PAYMENT RECEIVED - THANKYOU )(W\d{4})")
_PURCHASE_REF = re.compile(r"'(AT\d{2}\d{3}\d{4})(\d{12})'")
_PAYID_REF = re.compile(r"'(S000)(\d+)'")
_FEE_REF = re.compile(r"'(1000000001\d{4})(\d{9})'")
_KEPT_DESCRIPTIONS = frozenset(
    {
        "PayID Payment Received, Thank you",
        "MEMBERSHIP FEE",
        "INSUFFICIENT FUNDS FEE",
        "INTEREST CHARGES",
        "CHARGE FOR OVERDUE PAYMENT",
        "Qantas Ultimate Annual Travel Credit",
    }
)
_MUST_BE_EMPTY = ("Exchange Rate", "Additional Information")

Row = dict[str, str]


class RefShape(StrEnum):
    PURCHASE = "purchase"
    PAYID = "payid"
    FEE = "fee"


def parse_cents(text: str) -> int:
    if _AMOUNT.fullmatch(text) is None:
        msg = f"not a plain two-decimal amount: {text!r}"
        raise MaskError(msg)
    return int(text.replace(".", ""))


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _tidy(description: str) -> str:
    return " ".join(description.split())


_REFERENCE_SHAPES = (
    (_PURCHASE_REF, RefShape.PURCHASE),
    (_PAYID_REF, RefShape.PAYID),
    (_FEE_REF, RefShape.FEE),
)


def split_reference(reference: str) -> tuple[RefShape, str, str]:
    """Shape, the part to keep, and the part to mask."""
    for pattern, shape in _REFERENCE_SHAPES:
        match = pattern.fullmatch(reference)
        if match:
            keep, tail = match.groups()
            return shape, keep, tail
    msg = "unknown reference shape: format not yet observed"
    raise MaskError(msg)


def reference_shape(reference: str) -> RefShape:
    return split_reference(reference)[0]


class AmexMasker:
    def __init__(self, key: bytes, config: MaskConfig) -> None:
        self._key = key
        self._config = config
        self._money = Masker(key, config)
        self._known: dict[tuple[str, str], str] = {}
        self._taken: set[tuple[str, str]] = set()
        self.real_values: set[str] = set()

    # -- primitives ---------------------------------------------------------

    def _digest(self, label: str, real: str) -> bytes:
        message = f"{label}\0{real}".encode()
        return hmac.new(self._key, message, hashlib.sha256).digest()

    def _remember(self, real: str) -> None:
        if len(real) >= _MIN_LEAK_LENGTH:
            self.real_values.add(real)

    def digits(self, label: str, real: str) -> str:
        """Fake digits of the same length. Same input, same output; none collide."""
        known = self._known.get((label, real))
        if known is not None:
            return known
        attempt = 0
        while True:
            stream = iter(self._digest(f"{label}#{attempt}", real))
            fake = "".join(str(next(stream) % 10) for _ in real)
            if fake != real and (label, fake) not in self._taken:
                break
            attempt += 1
        self._taken.add((label, fake))
        self._known[(label, real)] = fake
        return fake

    # -- one row ------------------------------------------------------------

    def mask_row(self, row: Row) -> Row:
        for column in _MUST_BE_EMPTY:
            if row[column]:
                msg = f"{column} is filled: format not yet observed"
                raise MaskError(msg)
        for column in ("Date", "Date Processed"):
            if _DATE.fullmatch(row[column]) is None:
                msg = f"{column} is not DD/MM/YYYY: {row[column]!r}"
                raise MaskError(msg)
        if row["Description"] != row["Appears On Your Statement As"]:
            msg = "Description and Appears On Your Statement As differ"
            raise MaskError(msg)
        real_cents = parse_cents(row["Amount"])
        fake_cents = self._money.cents(abs(real_cents))
        description = self._mask_description(row["Description"])
        foreign, commission = self._mask_foreign(row, abs(real_cents), fake_cents)
        return {
            **row,
            "Description": description,
            "Appears On Your Statement As": description,
            "Amount": format_cents(-fake_cents if real_cents < 0 else fake_cents),
            "Foreign Spend Amount": foreign,
            "Commission": commission,
            "Address": self._mask_lines(row["Address"], _FAKE_STREET, "1 TEST\nSTREET"),
            "Town/City": self._mask_lines(
                row["Town/City"], _FAKE_TOWN, f"{_FAKE_TOWN}\nVIC"
            ),
            "Postcode": self._mask_postcode(row["Postcode"]),
            "Reference": self._mask_reference(row["Reference"]),
        }

    # -- fields -------------------------------------------------------------

    def _mask_description(self, description: str) -> str:
        tidy = _tidy(description)
        if tidy in _KEPT_DESCRIPTIONS:
            return description
        online = _ONLINE_PAYMENT.fullmatch(tidy)
        if online:
            wording, number = online.groups()
            self._remember(number)
            return wording + "W" + self.digits("online", number[1:])
        self._remember(description)
        self._remember(tidy)
        pinned = next(
            (
                fake
                for real, fake in self._config.merchants.items()
                if real.lower() in tidy.lower()
            ),
            None,
        )
        fake = pinned or self._money.merchant(tidy)
        return f"{fake.upper():<{_DESCRIPTION_WIDTH}} {_FAKE_PLACE}"

    def _mask_lines(self, real: str, single: str, multiple: str) -> str:
        if not real:
            return real
        for part in real.split("\n"):
            self._remember(part)
        return multiple if "\n" in real else single

    @staticmethod
    def _mask_postcode(real: str) -> str:
        if not real:
            return real
        return {4: "3000", 5: "12345"}.get(len(real), "1" * len(real))

    def _mask_reference(self, real: str) -> str:
        _, keep, tail = split_reference(real)
        self._remember(real.strip("'"))
        return f"'{keep}{self.digits('reference', tail)}'"

    def _mask_foreign(
        self, row: Row, real_total: int, fake_total: int
    ) -> tuple[str, str]:
        text, commission = row["Foreign Spend Amount"], row["Commission"]
        if not text and not commission:
            return "", ""
        match = _FOREIGN.fullmatch(text)
        if match is None or not commission:
            msg = "foreign amount and commission must come together in a known form"
            raise MaskError(msg)
        real_commission = parse_cents(commission)
        rate = self._rate(real_total, real_commission)
        fake_commission = self._commission(fake_total, rate)
        real_base = real_total - real_commission
        fake_base = fake_total - fake_commission
        amount_text, code = match.groups()
        amount = Decimal(amount_text.replace(",", ""))
        places = len(amount_text.partition(".")[2])
        unit = Decimal(1).scaleb(-places)
        scaled = (amount * fake_base / real_base).quantize(unit, ROUND_HALF_UP)
        scaled = max(scaled, unit)
        return f"{scaled:,.{places}f} {code}", format_cents(fake_commission)

    @staticmethod
    def _fits(commission: int, base: int, rate: int) -> bool:
        """Within a cent of ``rate`` of ``base``: AMEX rounds before converting."""
        return abs(commission * _RATE_SCALE - base * rate) <= _RATE_SCALE

    def _rate(self, total: int, commission: int) -> int:
        base = total - commission
        for rate in _COMMISSION_RATES:
            if self._fits(commission, base, rate):
                return rate
        msg = "commission fits neither 3.00% nor 3.50% of the amount before commission"
        raise MaskError(msg)

    def _commission(self, total: int, rate: int) -> int:
        """Commission such that it is ``rate`` of the amount before commission."""
        commission = (total * rate + (_RATE_SCALE + rate) // 2) // (_RATE_SCALE + rate)
        if commission < 1 or not self._fits(commission, total - commission, rate):
            msg = "no commission fits the masked amount"
            raise MaskError(msg)
        return commission


# -- choosing rows ----------------------------------------------------------------


def _kind_key(row: Row) -> str:
    tidy = _tidy(row["Description"])
    if row["Foreign Spend Amount"]:
        return "foreign"
    if tidy in _KEPT_DESCRIPTIONS:
        return tidy
    if _ONLINE_PAYMENT.fullmatch(tidy):
        return "online payment"
    return "purchase"


def _repeat_indexes(rows: list[Row]) -> set[int]:
    """Rows that repeat another on date, posting date, description and amount."""
    groups: dict[tuple[str, ...], list[int]] = {}
    for index, row in enumerate(rows):
        key = (
            row["Date"],
            row["Date Processed"],
            _tidy(row["Description"]),
            row["Amount"],
        )
        groups.setdefault(key, []).append(index)
    return {i for indexes in groups.values() if len(indexes) > 1 for i in indexes}


def _first_of_each_kind(rows: list[Row]) -> set[int]:
    """The first row of every description kind and every reference shape."""
    chosen: set[int] = set()
    seen: set[str] = set()
    for index, row in enumerate(rows):
        for label in (_kind_key(row), reference_shape(row["Reference"]).value):
            if label not in seen:
                seen.add(label)
                chosen.add(index)
    return chosen


def select_rows(rows: list[Row]) -> list[Row]:
    """Rows worth keeping as fixtures, in file order. Short files are kept whole."""
    if len(rows) <= SUBSET_SIZE:
        return rows
    chosen = _first_of_each_kind(rows) | _repeat_indexes(rows)
    for index, row in enumerate(rows):
        boundary = (
            row["Date"].startswith(_BOUNDARY_DAY)
            and row["Date Processed"] != row["Date"]
        )
        if boundary or row["Foreign Spend Amount"]:
            chosen.add(index)
    for index in range(len(rows)):
        if len(chosen) >= SUBSET_SIZE:
            break
        chosen.add(index)
    return [rows[index] for index in sorted(chosen)]


# -- reading and writing ------------------------------------------------------------


def read_export(path: Path) -> tuple[list[Row], bool]:
    """Rows keyed by header name, and whether the file ends with a line break."""
    text = path.read_bytes().decode("utf-8")
    if text.startswith(_BOM) or "\r" in text:
        msg = f"{path.name}: byte-order mark or CRLF: format not yet observed"
        raise MaskError(msg)
    table = list(csv.reader(io.StringIO(text, newline="")))
    if not table or table[0] != HEADER:
        found = table[0] if table else []
        reason = "lacks Reference" if "Reference" not in found else "is unexpected"
        msg = f"{path.name}: header {reason}. Export all 14 columns."
        raise MaskError(msg)
    rows = []
    for cells in table[1:]:
        if len(cells) != len(HEADER):
            msg = f"{path.name}: expected {len(HEADER)} columns, found {len(cells)}"
            raise MaskError(msg)
        rows.append(dict(zip(HEADER, cells, strict=True)))
    return rows, text.endswith("\n")


def render(rows: list[Row], *, final_newline: bool) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows([row[column] for column in HEADER] for row in rows)
    text = buffer.getvalue()
    return text if final_newline else text.removesuffix("\n")


def check_output(texts: dict[str, str], masker: AmexMasker) -> None:
    for name, text in texts.items():
        for real in masker.real_values:
            if re.search(rf"(?<![\w.]){re.escape(real)}(?![\w.])", text):
                msg = f"{name}: a real value survived masking"
                raise MaskError(msg)


def run(
    raw_dir: Path,
    out_dir: Path,
    key_path: Path = DEFAULT_KEY_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> list[Path]:
    """Mask every export in ``raw_dir``. Nothing is written unless all pass."""
    sources = sorted(raw_dir.glob("*.csv"))
    if not sources:
        msg = f"no *.csv in {raw_dir}"
        raise MaskError(msg)
    masker = AmexMasker(load_key(key_path), load_config(config_path))
    texts: dict[str, str] = {}
    for source in sources:
        rows, final_newline = read_export(source)
        masked = [masker.mask_row(row) for row in select_rows(rows)]
        texts[source.name] = render(masked, final_newline=final_newline)
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
