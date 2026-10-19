"""Tests for the CMC fixture masking script (S1-16)."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from mask_cmc_fixtures import (
    CASH_NAME,
    CONFIRMATION_NAME,
    FAKE_ACCOUNT_NAME,
    parse_cents,
    run,
    trade_cents,
)
from mask_fixtures import MaskError

if TYPE_CHECKING:
    from pathlib import Path

REAL_ACCOUNT = "123456"
REAL_NAME = "MR REAL PERSON"
REAL_BUY_REF, REAL_BUY_REF_2, REAL_SELL_REF = "40000001", "40000002", "40000003"
REAL_JOURNAL, REAL_VRN, REAL_DEP = "5550001", "999888777", "123987"
REAL_RECEIPT = "00555111"

HEADER = (
    "Account Number,Account Name,AsxCode,Confirmation Number,Order Type,As at Date,"
    "Trade Date,Settlement Date,Avg Price,Exch Rate,Price,Quantity,Brokerage,GST,"
    "Stampduty,Application Fee,OtherCharge,Fee,Discount,Consideration,"
    "Reverse Confirmation Number"
)


def confirmation_row(  # noqa: PLR0913 - test data builder, keywords for clarity
    ref: str, code: str, side: str, *, price: str, quantity: int, consideration: str
) -> str:
    fees = ("10.00", "1.00") if side == "Sell" else ("0.00", "0.00")
    return (
        f"{REAL_ACCOUNT},{REAL_NAME},{code},{ref},{side},,2026-01-05,2026-01-07,"
        f'"{price} AUD",1.000000,{price},{quantity}.000000000,{fees[0]},{fees[1]},'
        f"0.00,0.00,0.00,0.00,0.00,{consideration},0,"
    )


_CRLF = "\r\n"
CONFIRMATION_RAW = _CRLF.join(
    [
        HEADER,
        confirmation_row(
            REAL_SELL_REF,
            "IVV",
            "Sell",
            price="70.0000",
            quantity=4,
            consideration="269.0000",
        ),
        confirmation_row(
            REAL_BUY_REF_2,
            "IVV",
            "Buy",
            price="9.9251",
            quantity=51,
            consideration="506.1800",
        ),
        confirmation_row(
            REAL_BUY_REF,
            "NDQ",
            "Buy",
            price="50.0000",
            quantity=2,
            consideration="100.0000",
        ),
        "",
    ]
)

CASH_RAW = "﻿" + _CRLF.join(
    [
        '"Date","Description","Debit $","Credit $","Balance $"',
        '"01/07/2025","OPENING BALANCE","","","0.46"',
        '"11/07/2025","EXTERNAL - DIV IVV PAYMENT TRAN","","6.08","6.54"',
        '"17/07/2025","Statement Balance Alignment","","15.18","21.72"',
        f'"20/07/2025","EXTERNAL - OCT25/{REAL_RECEIPT} TRANS","","9.39","31.11"',
        (
            f'"25/07/2025","JNL{REAL_JOURNAL} ]NPP VRN:{REAL_VRN} DEP:{REAL_DEP}",'
            '"","500.00","531.11"'
        ),
        f'"27/07/2025","Bght 2 NDQ @ 50.0000 AUD {REAL_BUY_REF}","100.00","","431.11"',
        (
            f'"29/07/2025","Bght 51 IVV @ 9.9251 AUD {REAL_BUY_REF_2}",'
            '"506.18","","-75.07"'
        ),
        f'"31/07/2025","Sold 4 IVV @ 70.0000 AUD {REAL_SELL_REF}","","269.00","193.93"',
        '"30/06/2026","CLOSING BALANCE","","","193.93"',
        "",
        '"","TOTALS","606.18","799.65",""',
        "",
    ]
)


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "raw"
    directory.mkdir()
    (directory / CONFIRMATION_NAME).write_bytes(CONFIRMATION_RAW.encode())
    (directory / "CashTransactionSummary-123456-20250701-20260630.csv").write_bytes(
        CASH_RAW.encode()
    )
    return directory


def mask(raw_dir: Path, tmp_path: Path, key: str = "k1") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    key_path = tmp_path / "key"
    key_path.write_text(key)
    out = tmp_path / "out"
    run(raw_dir, out, key_path)
    return out


def confirmations(out: Path) -> list[dict[str, str]]:
    text = (out / CONFIRMATION_NAME).read_bytes().decode()
    return list(csv.DictReader(io.StringIO(text, newline="")))


def cash_rows(out: Path) -> list[list[str]]:
    text = (out / CASH_NAME).read_bytes().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


def test_real_identifiers_do_not_survive(raw_dir: Path, tmp_path: Path) -> None:
    out = mask(raw_dir, tmp_path)

    combined = (out / CONFIRMATION_NAME).read_text() + (out / CASH_NAME).read_text(
        encoding="utf-8-sig"
    )
    for real in (
        REAL_ACCOUNT,
        REAL_NAME,
        REAL_BUY_REF,
        REAL_BUY_REF_2,
        REAL_SELL_REF,
        REAL_JOURNAL,
        REAL_VRN,
        REAL_DEP,
        REAL_RECEIPT,
    ):
        assert real not in combined
    assert {row["Account Name"] for row in confirmations(out)} == {FAKE_ACCOUNT_NAME}


def test_trade_line_in_cash_summary_shares_its_confirmations_fake_number(
    raw_dir: Path, tmp_path: Path
) -> None:
    out = mask(raw_dir, tmp_path)

    confirmation_refs = {row["Confirmation Number"] for row in confirmations(out)}
    cash_refs = {
        row[1].rsplit(" ", 1)[1]
        for row in cash_rows(out)
        if row[1:2] and row[1].startswith(("Bght", "Sold"))
    }
    assert cash_refs == confirmation_refs


def test_quantity_is_scaled_by_one_factor_per_ticker(
    raw_dir: Path, tmp_path: Path
) -> None:
    out = mask(raw_dir, tmp_path)

    ivv = {
        row["Order Type"]: Decimal(row["Quantity"])
        for row in confirmations(out)
        if row["AsxCode"] == "IVV"
    }
    assert ivv["Sell"] % 4 == 0
    assert ivv["Buy"] % 51 == 0
    assert ivv["Sell"] / 4 == ivv["Buy"] / 51
    assert 2 <= ivv["Sell"] / 4 <= 8


def test_masked_confirmations_still_add_up(raw_dir: Path, tmp_path: Path) -> None:
    out = mask(raw_dir, tmp_path)

    for row in confirmations(out):
        gross = trade_cents(Decimal(row["Quantity"]), Decimal(row["Price"]))
        fees = parse_cents(row["Brokerage"]) + parse_cents(row["GST"])
        expected = gross - fees if row["Order Type"] == "Sell" else gross + fees
        assert parse_cents(row["Consideration"]) == expected


def test_sell_proceeds_in_cash_summary_equal_the_confirmations_consideration(
    raw_dir: Path, tmp_path: Path
) -> None:
    out = mask(raw_dir, tmp_path)

    by_ref = {row["Confirmation Number"]: row for row in confirmations(out)}
    for row in cash_rows(out):
        if row[1:2] and row[1].startswith(("Bght", "Sold")):
            confirmation = by_ref[row[1].rsplit(" ", 1)[1]]
            amount = row[3] if row[1].startswith("Sold") else row[2]
            assert parse_cents(amount) == parse_cents(confirmation["Consideration"])


def test_cash_balance_reconciles_and_never_goes_negative(
    raw_dir: Path, tmp_path: Path
) -> None:
    out = mask(raw_dir, tmp_path)

    rows = cash_rows(out)
    opening, closing = rows[1], rows[-3]
    totals = rows[-1]
    body = rows[2:-3]
    balance = parse_cents(opening[4])
    for row in body:
        balance += parse_cents(row[3]) - parse_cents(row[2])
        assert parse_cents(row[4]) == balance >= 0
    assert closing[1] == "CLOSING BALANCE"
    assert parse_cents(closing[4]) == balance
    assert parse_cents(totals[2]) == sum(parse_cents(row[2]) for row in body)
    assert parse_cents(totals[3]) == sum(parse_cents(row[3]) for row in body)


def test_file_quirks_are_preserved(raw_dir: Path, tmp_path: Path) -> None:
    out = mask(raw_dir, tmp_path)

    confirmation = (out / CONFIRMATION_NAME).read_bytes()
    cash = (out / CASH_NAME).read_bytes()
    assert not confirmation.startswith(b"\xef\xbb\xbf")
    assert cash.startswith(b"\xef\xbb\xbf")
    for data in (confirmation, cash):
        assert data.endswith(b"\r\n")
        assert b"\n" not in data.replace(b"\r\n", b"")
    assert b'"70.0000 AUD"' in confirmation
    assert confirmation.startswith(b"Account Number,Account Name,")
    assert b",Avg Price," in confirmation.split(b"\r\n")[0]
    assert b'"11/07/2025","EXTERNAL - DIV IVV PAYMENT TRAN"' in cash
    assert b"\r\n\r\n" in cash  # blank line before TOTALS


def test_dividend_and_alignment_rows_survive_with_masked_amounts(
    raw_dir: Path, tmp_path: Path
) -> None:
    out = mask(raw_dir, tmp_path)

    descriptions = [row[1] for row in cash_rows(out) if len(row) > 1]
    assert "EXTERNAL - DIV IVV PAYMENT TRAN" in descriptions
    assert "Statement Balance Alignment" in descriptions
    assert any(
        d.startswith("EXTERNAL - OCT25/") and d.endswith(" TRANS") for d in descriptions
    )
    dividend = next(
        row for row in cash_rows(out) if row[1:2] == ["EXTERNAL - DIV IVV PAYMENT TRAN"]
    )
    assert 100 <= parse_cents(dividend[3]) <= 999  # still three digits
    assert parse_cents(dividend[3]) != 608


def test_masking_is_deterministic_and_key_dependent(
    raw_dir: Path, tmp_path: Path
) -> None:
    first = mask(raw_dir, tmp_path / "a")
    again = mask(raw_dir, tmp_path / "b")
    other = mask(raw_dir, tmp_path / "c", key="k2")

    assert (first / CASH_NAME).read_bytes() == (again / CASH_NAME).read_bytes()
    assert (first / CASH_NAME).read_bytes() != (other / CASH_NAME).read_bytes()


def test_unrecognised_cash_description_aborts_before_anything_is_written(
    raw_dir: Path, tmp_path: Path
) -> None:
    cash = next(raw_dir.glob("CashTransactionSummary*.csv"))
    cash.write_bytes(
        cash.read_bytes().replace(
            b"Statement Balance Alignment", b"Paid to Some Person"
        )
    )

    with pytest.raises(MaskError, match="unrecognised cash description"):
        mask(raw_dir, tmp_path)

    assert not (tmp_path / "out").exists()


def test_cash_trade_without_a_confirmation_aborts(
    raw_dir: Path, tmp_path: Path
) -> None:
    confirmation = raw_dir / CONFIRMATION_NAME
    lines = confirmation.read_bytes().split(b"\r\n")
    confirmation.write_bytes(
        b"\r\n".join(line for line in lines if REAL_BUY_REF.encode() not in line)
    )

    with pytest.raises(MaskError, match="no confirmation"):
        mask(raw_dir, tmp_path)


def test_confirmation_whose_consideration_does_not_add_up_aborts(
    raw_dir: Path, tmp_path: Path
) -> None:
    confirmation = raw_dir / CONFIRMATION_NAME
    confirmation.write_bytes(
        confirmation.read_bytes().replace(b"269.0000", b"270.0000")
    )

    with pytest.raises(MaskError, match="does not add up"):
        mask(raw_dir, tmp_path)


def test_reversed_confirmation_aborts_because_its_format_is_unknown(
    raw_dir: Path, tmp_path: Path
) -> None:
    confirmation = raw_dir / CONFIRMATION_NAME
    confirmation.write_bytes(
        confirmation.read_bytes().replace(b",269.0000,0,", b",269.0000,777,")
    )

    with pytest.raises(MaskError, match="reversed"):
        mask(raw_dir, tmp_path)


def test_cash_line_that_disagrees_with_its_confirmation_aborts(
    raw_dir: Path, tmp_path: Path
) -> None:
    cash = next(raw_dir.glob("CashTransactionSummary*.csv"))
    cash.write_bytes(cash.read_bytes().replace(b"Bght 2 NDQ", b"Bght 3 NDQ"))

    with pytest.raises(MaskError, match="disagrees"):
        mask(raw_dir, tmp_path)


def test_duplicate_confirmation_number_aborts(raw_dir: Path, tmp_path: Path) -> None:
    confirmation = raw_dir / CONFIRMATION_NAME
    confirmation.write_bytes(
        confirmation.read_bytes().replace(
            REAL_BUY_REF_2.encode(), REAL_BUY_REF.encode()
        )
    )

    with pytest.raises(MaskError, match="duplicate"):
        mask(raw_dir, tmp_path)


def test_sell_keeps_its_brokerage_and_gst(raw_dir: Path, tmp_path: Path) -> None:
    out = mask(raw_dir, tmp_path)

    sell = next(row for row in confirmations(out) if row["Order Type"] == "Sell")
    assert (sell["Brokerage"], sell["GST"]) == ("10.00", "1.00")


def test_a_half_cent_rounds_up() -> None:
    assert trade_cents(Decimal(1), Decimal("0.005")) == 1
    assert trade_cents(Decimal(3), Decimal("0.1650")) == 50
