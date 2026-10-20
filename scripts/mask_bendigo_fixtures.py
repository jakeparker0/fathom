"""Mask raw Bendigo extended exports into committable test fixtures (S1-17).

Raw exports live in ``data/recon/raw/bendigo/`` (gitignored, never committed). Masked
copies are written to ``tests/fixtures/bendigo/`` under the same file names.

    uv run python scripts/mask_bendigo_fixtures.py

Every ``transactions_extended*.csv`` in the raw directory is masked together, because
the two accounts' files describe the same transfers and must stay consistent:

- The E-Banking receipt number is shared by the two legs of a transfer. It is masked
  by a keyed function of the real value, so both legs get the same fake receipt.
- An amount is masked from its absolute value, with the sign put back. Equal and
  opposite legs therefore stay equal and opposite, and a transfer still nets to zero.
- After masking, every receipt that appears twice must be a pair on the same date
  that nets to zero. If not, the run aborts.

What is masked: the account number (the BSB is public and kept), receipt numbers,
account references, Osko payment ids, payer and payee names (``CMC`` is kept), BPAY
and direct-debit reference numbers, and retail-purchase merchants. A retail purchase's
reference carries its amount, which is rewritten to match the masked amount.

Kept as they are: dates, type codes, kind labels, Osko nicknames, the BPAY biller, the
direct-debit biller name, ``INTEREST`` and ``REWARD RECEIVED`` rows, and the file's
quirks (no header, CRLF line endings, every field quoted).

A file with a header row, a row that is not 7 columns, or a transaction kind the
script does not recognise aborts the run, because it could carry free text. After
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
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "recon" / "raw" / "bendigo"
DEFAULT_OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "bendigo"
RAW_GLOB = "transactions_extended*.csv"

_COLUMNS = 7
_CRLF = "\r\n"
_BOM = "﻿"
_CENTS_PER_DOLLAR = 100
_MIN_LEAK_LENGTH = 4
_DATE = re.compile(r"\d\d/\d\d/\d{4}")
_ACCOUNT = re.compile(r"(\d{3}-\d{3}) (\d+)")
_OSKO_DETAIL = re.compile(r"(.+) (\d{9})")
_DEBIT_DETAIL = re.compile(r"(.+?)(\s+)(\d+)")
_PURCHASE_REF = re.compile(r"(\d{4}) AUD(\d{12})")
_REFERENCE = re.compile(r"[0-9A-Z]+")
_DIGITS = re.compile(r"\d+")
_BPAY_PREFIX = "BPAY TO: "
_REWARD_DETAIL = "BONUS RATE FOR PREVIOUS MONTH"
_REWARD_REF = "Reward Saver"
_KEPT_PAYEE = "CMC"


class Kind(StrEnum):
    TRANSFER = "E-BANKING TRANSFER"
    OSKO_RECEIVED = "Osko Payment Received"
    OSKO_SENT = "Osko Payment Sent"
    BPAY = "BILL PAYMENT"
    INTEREST = "INTEREST"
    REWARD = "REWARD RECEIVED"
    PURCHASE = "RETAIL PURCHASE"
    DIRECT_DEBIT = "DIRECT DEBIT"


@dataclass(frozen=True)
class MaskedRow:
    """A masked row plus what the transfer-pair check needs."""

    cells: list[str]
    kind: Kind
    cents: int


def parse_cents(text: str) -> int:
    """Whole cents, signed, from a dollar string. A fractional cent is an error."""
    try:
        value = Decimal(text) * _CENTS_PER_DOLLAR
    except InvalidOperation as exc:
        msg = f"not an amount: {text!r}"
        raise MaskError(msg) from exc
    if value != value.to_integral_value():
        msg = f"amount is not whole cents: {text!r}"
        raise MaskError(msg)
    return int(value)


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return (
        f"{sign}{abs(cents) // _CENTS_PER_DOLLAR}.{abs(cents) % _CENTS_PER_DOLLAR:02d}"
    )


class BendigoMasker:
    def __init__(self, key: bytes, config: MaskConfig) -> None:
        self._key = key
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

    def shaped(self, label: str, real: str) -> str:
        """Fake of the same shape: digits replaced, other characters kept.

        Same input, same output. Two different inputs never share an output.
        """
        known = self._known.get((label, real))
        if known is not None:
            return known
        attempt = 0
        while True:
            stream = self._digest(f"{label}#{attempt}", real)
            digits = iter(stream)
            fake = "".join(
                str(next(digits) % 10) if char.isdigit() else char for char in real
            )
            if fake != real and (label, fake) not in self._taken:
                break
            attempt += 1
        self._taken.add((label, fake))
        self._known[(label, real)] = fake
        self._remember(real)
        return fake

    def signed_cents(self, cents: int) -> int:
        """Mask an amount from its absolute value, so opposite legs stay opposite."""
        masked = self._money.cents(abs(cents))
        return -masked if cents < 0 else masked

    # -- one row ------------------------------------------------------------

    def mask_row(self, row: list[str]) -> MaskedRow:
        account, date, code, amount, kind_text, detail, reference = row
        try:
            kind = Kind(kind_text)
        except ValueError as exc:
            msg = f"unrecognised transaction kind {kind_text!r}"
            raise MaskError(msg) from exc
        cents = self.signed_cents(parse_cents(amount))
        fake_detail, fake_reference = self._mask_detail(
            kind, detail, reference, abs(parse_cents(amount)), abs(cents)
        )
        cells = [
            self._mask_account(account),
            date,
            code,
            format_cents(cents),
            kind_text,
            fake_detail,
            fake_reference,
        ]
        return MaskedRow(cells, kind, cents)

    def _mask_account(self, cell: str) -> str:
        match = _ACCOUNT.fullmatch(cell)
        if match is None:
            msg = "account column is not 'BSB account-number'"
            raise MaskError(msg)
        bsb, number = match.groups()
        return f"{bsb} {self.shaped('account', number)}"

    def _mask_detail(
        self,
        kind: Kind,
        detail: str,
        reference: str,
        real_cents: int,
        fake_cents: int,
    ) -> tuple[str, str]:
        if kind is Kind.PURCHASE:
            return self._mask_purchase(detail, reference, real_cents, fake_cents)
        handlers = {
            Kind.TRANSFER: self._mask_transfer,
            Kind.OSKO_RECEIVED: self._mask_osko,
            Kind.OSKO_SENT: self._mask_osko,
            Kind.BPAY: self._mask_bpay,
            Kind.INTEREST: self._mask_interest,
            Kind.REWARD: self._mask_reward,
            Kind.DIRECT_DEBIT: self._mask_direct_debit,
        }
        return handlers[kind](detail, reference)

    def _mask_transfer(self, detail: str, reference: str) -> tuple[str, str]:
        self._expect(_DIGITS, detail, Kind.TRANSFER)
        self._expect(_REFERENCE, reference, Kind.TRANSFER)
        return self.shaped("receipt", detail), self.shaped("transfer-ref", reference)

    def _mask_osko(self, detail: str, reference: str) -> tuple[str, str]:
        osko = _OSKO_DETAIL.fullmatch(detail)
        if osko is None:
            msg = "Osko detail is not '<nickname> <payment id>'"
            raise MaskError(msg)
        nickname, payment_id = osko.groups()
        return f"{nickname} {self.shaped('osko', payment_id)}", self._payee(reference)

    def _mask_bpay(self, detail: str, reference: str) -> tuple[str, str]:
        if not detail.startswith(_BPAY_PREFIX):
            msg = f"BILL PAYMENT detail does not start with {_BPAY_PREFIX!r}"
            raise MaskError(msg)
        self._expect(_DIGITS, reference, Kind.BPAY)
        return detail, self.shaped("bpay", reference)

    @staticmethod
    def _mask_interest(detail: str, reference: str) -> tuple[str, str]:
        if detail or reference:
            msg = "INTEREST row carries text: format not yet observed"
            raise MaskError(msg)
        return detail, reference

    @staticmethod
    def _mask_reward(detail: str, reference: str) -> tuple[str, str]:
        if detail != _REWARD_DETAIL or reference != _REWARD_REF:
            msg = "REWARD RECEIVED row is not the known bonus-rate marker"
            raise MaskError(msg)
        return detail, reference

    def _mask_direct_debit(self, detail: str, reference: str) -> tuple[str, str]:
        debit = _DEBIT_DETAIL.fullmatch(detail)
        if debit is None:
            msg = "DIRECT DEBIT detail is not '<biller> <number>'"
            raise MaskError(msg)
        biller, spacing, number = debit.groups()
        self._expect(_DIGITS, reference, Kind.DIRECT_DEBIT)
        return (
            f"{biller}{spacing}{self.shaped('debit', number)}",
            self.shaped("debit-ref", reference),
        )

    @staticmethod
    def _expect(pattern: re.Pattern[str], text: str, kind: Kind) -> None:
        if pattern.fullmatch(text) is None:
            msg = f"{kind}: unexpected value shape: format not yet observed"
            raise MaskError(msg)

    def _payee(self, real: str) -> str:
        if real == _KEPT_PAYEE:
            return real
        self._remember(real)
        return "PERSON " + self._digest("payee", real)[:4].hex().upper()

    def _mask_purchase(
        self, merchant: str, reference: str, real_cents: int, fake_cents: int
    ) -> tuple[str, str]:
        match = _PURCHASE_REF.fullmatch(reference)
        if match is None:
            msg = "RETAIL PURCHASE reference is not 'DDMM AUD<12 digits>'"
            raise MaskError(msg)
        day_month, amount = match.groups()
        if int(amount) != real_cents:
            msg = "RETAIL PURCHASE reference amount disagrees with the amount column"
            raise MaskError(msg)
        self._remember(merchant)
        return (
            self._money.merchant(merchant),
            f"{day_month} AUD{fake_cents:012d}",
        )


# -- checks ---------------------------------------------------------------------


def check_transfer_pairs(files: dict[str, list[MaskedRow]]) -> None:
    """Every receipt seen twice is one transfer: same date, amounts net to zero."""
    legs: dict[str, list[tuple[str, int]]] = {}
    for rows in files.values():
        for row in rows:
            if row.kind is Kind.TRANSFER:
                legs.setdefault(row.cells[5], []).append((row.cells[1], row.cents))
    for receipt, found in legs.items():
        if len(found) == 1:
            continue
        dates = {date for date, _ in found}
        total = sum(cents for _, cents in found)
        if len(found) != 2 or len(dates) != 1 or total != 0:  # noqa: PLR2004 - a pair
            msg = f"transfer {receipt} is not a pair that nets to zero"
            raise MaskError(msg)


def check_output(texts: dict[str, str], masker: BendigoMasker) -> None:
    for name, text in texts.items():
        for real in masker.real_values:
            if re.search(rf"(?<![\w.]){re.escape(real)}(?![\w.])", text):
                msg = f"{name}: a real value survived masking"
                raise MaskError(msg)


# -- reading and writing ----------------------------------------------------------


def read_rows(path: Path) -> tuple[list[list[str]], bool]:
    """Data rows, and whether the file ends with a line break."""
    text = path.read_bytes().decode("utf-8")
    if text.startswith(_BOM):
        msg = f"{path.name}: has a byte-order mark: format not yet observed"
        raise MaskError(msg)
    rows = [row for row in csv.reader(io.StringIO(text, newline="")) if row]
    for row in rows:
        if len(row) != _COLUMNS:
            msg = f"{path.name}: expected {_COLUMNS} columns, found {len(row)}"
            raise MaskError(msg)
    if rows and not _DATE.fullmatch(rows[0][1]):
        msg = f"{path.name}: first row looks like a header, which is not expected"
        raise MaskError(msg)
    return rows, text.endswith(_CRLF)


def render(rows: list[list[str]], *, final_newline: bool) -> str:
    lines = [",".join(f'"{cell}"' for cell in row) for row in rows]
    return _CRLF.join(lines) + (_CRLF if final_newline else "")


def run(
    raw_dir: Path,
    out_dir: Path,
    key_path: Path = DEFAULT_KEY_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> list[Path]:
    """Mask every extended export. Nothing is written unless all pass."""
    sources = sorted(raw_dir.glob(RAW_GLOB))
    if not sources:
        msg = f"no {RAW_GLOB} in {raw_dir}"
        raise MaskError(msg)
    masker = BendigoMasker(load_key(key_path), load_config(config_path))
    masked: dict[str, list[MaskedRow]] = {}
    endings: dict[str, bool] = {}
    for source in sources:
        rows, endings[source.name] = read_rows(source)
        masked[source.name] = [masker.mask_row(row) for row in rows]
    check_transfer_pairs(masked)
    texts = {
        name: render([row.cells for row in rows], final_newline=endings[name])
        for name, rows in masked.items()
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
