"""Tests for the Bendigo fixture masking script (S1-17)."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest
from mask_bendigo_fixtures import run
from mask_fixtures import MaskError

FIXTURES = Path(__file__).parent / "fixtures" / "bendigo"

BSB = "633-000"
REAL_EVERYDAY, REAL_SAVER = "111111111", "222222222"
REAL_RECEIPT_OUT, REAL_RECEIPT_IN = "0555000111", "0555000222"
REAL_OSKO_ID, REAL_OSKO_SENT_ID = "900000001", "900000002"
REAL_PAYER = "REAL PERSON NAME"
REAL_BPAY_REF = "2000000001"
REAL_MERCHANT = "REALSHOP ONLINE PAYMEN, KEW"
REAL_DEBIT_NUMBER = "0500000001"
REAL_DEBIT_REF = "300000000000001"
REAL_EVERYDAY_REF, REAL_SAVER_REF = "0011223344NA01", "00112233441401"
CRLF = "\r\n"


def line(account: str, *cells: str) -> str:
    quoted = (f'"{cell}"' for cell in (f"{BSB} {account}", *cells))
    return ",".join(quoted)


def everyday_rows() -> list[str]:
    return [
        line(
            REAL_EVERYDAY,
            "17/09/2026",
            "TDR06",
            "-2000.00",
            "E-BANKING TRANSFER",
            REAL_RECEIPT_OUT,
            REAL_EVERYDAY_REF,
        ),
        line(
            REAL_EVERYDAY,
            "16/08/2026",
            "WDL05",
            "-150.75",
            "RETAIL PURCHASE",
            REAL_MERCHANT,
            "1408 AUD000000015075",
        ),
        line(
            REAL_EVERYDAY,
            "14/08/2026",
            "TCR06",
            "150.75",
            "E-BANKING TRANSFER",
            REAL_RECEIPT_IN,
            REAL_EVERYDAY_REF,
        ),
        line(
            REAL_EVERYDAY,
            "17/07/2026",
            "JDR10",
            "-410.60",
            "DIRECT DEBIT",
            f"AMERICAN EXPRESS    {REAL_DEBIT_NUMBER}",
            REAL_DEBIT_REF,
        ),
    ]


def savings_rows(*, out_leg: str = "2000.00") -> list[str]:
    return [
        line(
            REAL_SAVER,
            "17/09/2026",
            "TCR06",
            out_leg,
            "E-BANKING TRANSFER",
            REAL_RECEIPT_OUT,
            REAL_SAVER_REF,
        ),
        line(
            REAL_SAVER,
            "15/09/2026",
            "DEP52",
            "2500.00",
            "Osko Payment Received",
            f"Savings {REAL_OSKO_ID}",
            REAL_PAYER,
        ),
        line(REAL_SAVER, "01/09/2026", "JCR99", "20.15", "INTEREST", "", ""),
        line(
            REAL_SAVER,
            "01/09/2026",
            "MCR90",
            "0.00",
            "REWARD RECEIVED",
            "BONUS RATE FOR PREVIOUS MONTH",
            "Reward Saver",
        ),
        line(
            REAL_SAVER,
            "14/08/2026",
            "TDR06",
            "-150.75",
            "E-BANKING TRANSFER",
            REAL_RECEIPT_IN,
            REAL_SAVER_REF,
        ),
        line(
            REAL_SAVER,
            "14/08/2026",
            "WDL53",
            "-1000.00",
            "Osko Payment Sent",
            f"Invest {REAL_OSKO_SENT_ID}",
            "CMC",
        ),
        line(
            REAL_SAVER,
            "14/08/2026",
            "WDL40",
            "-120.40",
            "BILL PAYMENT",
            "BPAY TO: TAX OFFICE PAYMENTS",
            REAL_BPAY_REF,
        ),
    ]


def write_raw(raw: Path, everyday: list[str], savings: list[str]) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "transactions_extended.csv").write_bytes(
        (CRLF.join(everyday) + CRLF).encode()
    )
    (raw / "transactions_extended_savings.csv").write_bytes(
        (CRLF.join(savings) + CRLF).encode()
    )


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    directory = tmp_path / "raw"
    write_raw(directory, everyday_rows(), savings_rows())
    return directory


def masked(raw: Path, tmp_path: Path, key: bytes = b"key-one") -> dict[str, str]:
    key_path = tmp_path / "key"
    key_path.write_bytes(key)
    out = tmp_path / "out"
    run(raw, out, key_path, tmp_path / "no-config.json")
    return {path.name: path.read_bytes().decode() for path in sorted(out.glob("*.csv"))}


def cents(amount: str) -> int:
    return int(amount.replace(".", ""))


def parse(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


def test_real_identifiers_do_not_survive_masking(raw: Path, tmp_path: Path) -> None:
    combined = "\n".join(masked(raw, tmp_path).values())
    for real in (
        REAL_EVERYDAY,
        REAL_SAVER,
        REAL_RECEIPT_OUT,
        REAL_RECEIPT_IN,
        REAL_OSKO_ID,
        REAL_OSKO_SENT_ID,
        REAL_PAYER,
        REAL_BPAY_REF,
        REAL_MERCHANT,
        REAL_DEBIT_NUMBER,
        REAL_DEBIT_REF,
        REAL_EVERYDAY_REF,
        REAL_SAVER_REF,
    ):
        assert real not in combined


def test_export_quirks_survive_masking(raw: Path, tmp_path: Path) -> None:
    for text in masked(raw, tmp_path).values():
        assert text.endswith(CRLF)
        body = text.removesuffix(CRLF).split(CRLF)
        assert all(re.fullmatch(r'"[^"]*"(,"[^"]*"){6}', row) for row in body)
        assert re.fullmatch(r"\d\d/\d\d/\d{4}", parse(text)[0][1])


def test_the_bsb_is_kept_and_each_account_gets_its_own_fake_number(
    raw: Path, tmp_path: Path
) -> None:
    files = masked(raw, tmp_path)
    everyday = {row[0] for row in parse(files["transactions_extended.csv"])}
    savings = {row[0] for row in parse(files["transactions_extended_savings.csv"])}
    assert len(everyday) == len(savings) == 1
    assert everyday != savings
    assert all(account.startswith(f"{BSB} ") for account in everyday | savings)


def test_a_transfer_pair_still_matches_on_receipt_amount_and_date(
    raw: Path, tmp_path: Path
) -> None:
    files = masked(raw, tmp_path)
    everyday = parse(files["transactions_extended.csv"])
    savings = parse(files["transactions_extended_savings.csv"])
    for out_row, in_row in ((everyday[0], savings[0]), (everyday[2], savings[4])):
        assert out_row[5] == in_row[5]
        assert out_row[1] == in_row[1]
        assert cents(out_row[3]) == -cents(in_row[3])
    assert everyday[0][5] != everyday[2][5]


def test_a_transfer_pair_that_no_longer_nets_to_zero_aborts(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    write_raw(raw, everyday_rows(), savings_rows(out_leg="1500.00"))
    with pytest.raises(MaskError, match="transfer"):
        masked(raw, tmp_path)
    assert not (tmp_path / "out").exists()


def test_retail_purchase_reference_carries_the_masked_amount(
    raw: Path, tmp_path: Path
) -> None:
    purchase = parse(masked(raw, tmp_path)["transactions_extended.csv"])[1]
    assert purchase[6] == f"1408 AUD{abs(cents(purchase[3])):012d}"
    assert purchase[5] != REAL_MERCHANT


def test_zero_amounts_stay_zero_and_signs_are_kept(raw: Path, tmp_path: Path) -> None:
    savings = parse(masked(raw, tmp_path)["transactions_extended_savings.csv"])
    amounts = [row[3] for row in savings]
    assert amounts[3] == "0.00"
    assert not amounts[2].startswith("-")
    assert amounts[5].startswith("-")
    assert re.fullmatch(r"-?\d+\.\d\d", amounts[2])


def test_payments_to_cmc_keep_the_payee_and_the_nickname(
    raw: Path, tmp_path: Path
) -> None:
    sent = parse(masked(raw, tmp_path)["transactions_extended_savings.csv"])[5]
    assert sent[6] == "CMC"
    assert re.fullmatch(r"Invest \d{9}", sent[5])
    assert sent[5] != f"Invest {REAL_OSKO_SENT_ID}"


def test_fixed_text_rows_are_kept(raw: Path, tmp_path: Path) -> None:
    savings = parse(masked(raw, tmp_path)["transactions_extended_savings.csv"])
    assert savings[2][4:] == ["INTEREST", "", ""]
    assert savings[3][4:] == [
        "REWARD RECEIVED",
        "BONUS RATE FOR PREVIOUS MONTH",
        "Reward Saver",
    ]
    assert savings[6][5] == "BPAY TO: TAX OFFICE PAYMENTS"


def test_masking_is_repeatable_and_depends_on_the_key(
    raw: Path, tmp_path: Path
) -> None:
    first = masked(raw, tmp_path)
    assert masked(raw, tmp_path) == first
    assert masked(raw, tmp_path, key=b"key-two") != first


def test_a_row_of_the_wrong_width_aborts(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    write_raw(raw, [*everyday_rows(), '"633-000 1","17/09/2026","X"'], savings_rows())
    with pytest.raises(MaskError, match="columns"):
        masked(raw, tmp_path)


def test_a_header_row_aborts(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    header = '"Account","Date","Code","Amount","Kind","Detail","Reference"'
    write_raw(raw, [header, *everyday_rows()], savings_rows())
    with pytest.raises(MaskError, match="header"):
        masked(raw, tmp_path)


def test_an_unrecognised_kind_aborts_and_writes_nothing(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    odd = line(
        REAL_EVERYDAY, "01/09/2026", "XXX01", "-1.00", "CHEQUE DEPOSIT", "a", "b"
    )
    write_raw(raw, [*everyday_rows(), odd], savings_rows())
    with pytest.raises(MaskError, match="CHEQUE DEPOSIT"):
        masked(raw, tmp_path)
    assert not (tmp_path / "out").exists()


def test_the_committed_header_fixture_is_rejected(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = FIXTURES / "handbuilt" / "with_header.csv"
    (raw / "transactions_extended.csv").write_bytes(source.read_bytes())
    with pytest.raises(MaskError, match="header"):
        masked(raw, tmp_path)
