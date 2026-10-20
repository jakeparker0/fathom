"""Tests for the AMEX fixture masking script (S1-17)."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest
from mask_amex_fixtures import COMMISSION_RATES, RATE_SCALE, SUBSET_SIZE, run
from mask_fixtures import MaskError

FIXTURES = Path(__file__).parent / "fixtures" / "amex"

HEADER = (
    "Date,Date Processed,Description,Amount,Foreign Spend Amount,Commission,"
    "Exchange Rate,Additional Information,Appears On Your Statement As,Address,"
    "Town/City,Postcode,Country,Reference"
)
COLUMNS = HEADER.split(",")

REAL_BAKERY = "ZETABAKERY PTY            BETATOWN"
REAL_STREET = "5 ALPHA RD\nNORTH"
REAL_TOWN = "BETATOWN\nNSW"
REAL_REF = "'AT262450004000099900011'"
REAL_PAYID_REF = "'S0007770000000000000001'"
REAL_FEE_REF = "'10000000010410777700001'"
REAL_ONLINE = "ONLINE PAYMENT RECEIVED - THANKYOU W9990"
PAYID = "PayID Payment Received, Thank you"


def row(  # noqa: PLR0913 - test data builder, keywords for clarity
    date: str,
    processed: str,
    description: str,
    amount: str,
    reference: str,
    *,
    foreign: str = "",
    commission: str = "",
    address: str = "",
    town: str = "",
    postcode: str = "",
    country: str = "",
) -> dict[str, str]:
    return {
        "Date": date,
        "Date Processed": processed,
        "Description": description,
        "Amount": amount,
        "Foreign Spend Amount": foreign,
        "Commission": commission,
        "Exchange Rate": "",
        "Additional Information": "",
        "Appears On Your Statement As": description,
        "Address": address,
        "Town/City": town,
        "Postcode": postcode,
        "Country": country,
        "Reference": reference,
    }


def write_csv(
    path: Path, rows: list[dict[str, str]], *, final_newline: bool = False
) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    text = buffer.getvalue()
    path.write_bytes((text if final_newline else text.rstrip("\n")).encode())


def small_rows() -> list[dict[str, str]]:
    return [
        row(
            "01/09/2026",
            "02/09/2026",
            REAL_BAKERY,
            "31.45",
            REAL_REF,
            address=REAL_STREET,
            town=REAL_TOWN,
            postcode="2999",
            country="AUSTRALIA",
        ),
        row("14/08/2026", "14/08/2026", PAYID, "-1500.25", REAL_PAYID_REF),
        row(
            "22/12/2025",
            "22/12/2025",
            REAL_ONLINE,
            "-640.10",
            "'AT253560004000099900071'",
        ),
        row("10/04/2025", "10/04/2025", "MEMBERSHIP FEE", "450.00", REAL_FEE_REF),
        row(
            "18/11/2025",
            "19/11/2025",
            "SampleWallet Jakarta",
            "103.00",
            "'AT253220004000099900021'",
            foreign="1,500,000 IDR",
            commission="3.00",
            country="INDONESIA",
        ),
        row(
            "16/12/2025",
            "17/12/2025",
            "SAMPLESOFT.COM 555-0100 CALAB",
            "206.00",
            "'AT253500004000099900031'",
            foreign="130.00 USD",
            commission="6.00",
            country="UNITED STATES",
        ),
        row(
            "21/08/2026",
            "22/08/2026",
            "OMEGA LABS OMEGA LABS   PARISVILLE",
            "207.00",
            "'AT262340003000099900041'",
            foreign="133.00 USD",
            commission="7.00",
            country="FRANCE",
        ),
        row(
            "08/06/2025",
            "08/06/2025",
            "ZETA SALON FITZROY",
            "19.99",
            "'AT251590004000099900051'",
        ),
        row(
            "08/06/2025",
            "08/06/2025",
            "ZETA SALON FITZROY",
            "19.99",
            "'AT251590004000099900052'",
        ),
        row(
            "14/12/2025",
            "15/12/2025",
            "ALPHA ST RADIO Sampleton",
            "11.11",
            "'AT253490004000099900061'",
        ),
    ]


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    directory = tmp_path / "raw"
    directory.mkdir()
    write_csv(directory / "activity.csv", small_rows())
    return directory


def masked_bytes(
    raw: Path, tmp_path: Path, key: bytes = b"key-one"
) -> dict[str, bytes]:
    key_path = tmp_path / "key"
    key_path.write_bytes(key)
    out = tmp_path / "out"
    run(raw, out, key_path, tmp_path / "no-config.json")
    return {path.name: path.read_bytes() for path in sorted(out.glob("*.csv"))}


def masked(raw: Path, tmp_path: Path, key: bytes = b"key-one") -> list[dict[str, str]]:
    text = masked_bytes(raw, tmp_path, key)["activity.csv"].decode()
    return list(csv.DictReader(io.StringIO(text, newline="")))


def cents(amount: str) -> int:
    return int(amount.replace(".", ""))


def test_real_identifiers_do_not_survive_masking(raw: Path, tmp_path: Path) -> None:
    text = masked_bytes(raw, tmp_path)["activity.csv"].decode()
    for real in (
        "ZETABAKERY",
        "ALPHA RD",
        REAL_REF.strip("'"),
        REAL_PAYID_REF.strip("'"),
        REAL_FEE_REF.strip("'"),
        "W9990",
        "ZETA SALON",
        "OMEGA LABS",
    ):
        assert real not in text


def test_export_quirks_survive_masking(raw: Path, tmp_path: Path) -> None:
    data = masked_bytes(raw, tmp_path)["activity.csv"]
    assert data.decode().splitlines()[0] == HEADER
    assert b"\r" not in data
    assert not data.endswith(b"\n")
    first = masked(raw, tmp_path)[0]
    assert "\n" in first["Address"]
    assert "\n" in first["Town/City"]
    assert all(r["Reference"].startswith("'") for r in masked(raw, tmp_path))
    assert all(r["Reference"].endswith("'") for r in masked(raw, tmp_path))


def test_a_trailing_newline_is_kept_when_the_export_has_one(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    write_csv(raw / "activity.csv", small_rows(), final_newline=True)
    assert masked_bytes(raw, tmp_path)["activity.csv"].endswith(b"\n")


def test_reference_shapes_and_the_date_inside_them_are_kept(
    raw: Path, tmp_path: Path
) -> None:
    refs = [r["Reference"] for r in masked(raw, tmp_path)]
    assert re.fullmatch(r"'AT26245\d{16}'", refs[0])
    assert re.fullmatch(r"'S000\d{19}'", refs[1])
    assert re.fullmatch(r"'AT25356\d{16}'", refs[2])
    assert re.fullmatch(r"'1000000001\d{4}\d{9}'", refs[3])
    assert refs[0] != REAL_REF
    assert refs[3][:15] == REAL_FEE_REF[:15]


def test_references_stay_unique(raw: Path, tmp_path: Path) -> None:
    refs = [r["Reference"] for r in masked(raw, tmp_path)]
    assert len(set(refs)) == len(refs)


def test_description_and_statement_text_stay_equal_and_padded(
    raw: Path, tmp_path: Path
) -> None:
    rows = masked(raw, tmp_path)
    assert all(r["Description"] == r["Appears On Your Statement As"] for r in rows)
    assert re.fullmatch(r"\S.{22} \S+", rows[0]["Description"])
    assert rows[1]["Description"] == PAYID
    assert rows[3]["Description"] == "MEMBERSHIP FEE"


def test_online_payment_keeps_its_wording_and_masks_the_number(
    raw: Path, tmp_path: Path
) -> None:
    description = masked(raw, tmp_path)[2]["Description"]
    assert re.fullmatch(r"ONLINE PAYMENT RECEIVED - THANKYOU W\d{4}", description)
    assert description != REAL_ONLINE


def test_merchants_pinned_in_the_config_use_the_readable_name(
    raw: Path, tmp_path: Path
) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"merchants": {"zetabakery": "Bakery"}}')
    key = tmp_path / "key"
    key.write_bytes(b"k")
    run(raw, tmp_path / "out", key, config)
    text = (tmp_path / "out" / "activity.csv").read_text()
    assert text.splitlines()[1].split(",")[2].startswith("BAKERY ")


def test_amounts_keep_their_sign_and_shape(raw: Path, tmp_path: Path) -> None:
    amounts = [r["Amount"] for r in masked(raw, tmp_path)]
    assert amounts[1].startswith("-")
    assert amounts[2].startswith("-")
    assert not amounts[0].startswith("-")
    assert amounts[3].endswith(".00")
    assert all(re.fullmatch(r"-?\d+\.\d\d", amount) for amount in amounts)


def test_equal_amounts_stay_equal_so_repeat_purchases_remain_repeats(
    raw: Path, tmp_path: Path
) -> None:
    rows = masked(raw, tmp_path)
    first, second = rows[7], rows[8]
    for column in ("Date", "Date Processed", "Description", "Amount"):
        assert first[column] == second[column]
    assert first["Reference"] != second["Reference"]


def test_commission_stays_a_fixed_share_of_the_amount_before_commission(
    raw: Path, tmp_path: Path
) -> None:
    foreign = [r for r in masked(raw, tmp_path) if r["Commission"]]
    assert len(foreign) == 3
    for r in foreign:
        commission = cents(r["Commission"])
        base = cents(r["Amount"]) - commission
        assert any(
            abs(commission * RATE_SCALE - base * rate) <= RATE_SCALE
            for rate in COMMISSION_RATES
        )


def test_foreign_amounts_keep_their_currency_and_format(
    raw: Path, tmp_path: Path
) -> None:
    foreign = [r["Foreign Spend Amount"] for r in masked(raw, tmp_path)]
    idr, usd, other_usd = foreign[4], foreign[5], foreign[6]
    assert re.fullmatch(r"\d{1,3}(,\d{3})* IDR", idr)
    assert re.fullmatch(r"\d{1,3}(,\d{3})*\.\d\d USD", usd)
    assert other_usd.endswith(" USD")
    assert idr != "1,500,000 IDR"


def test_dates_and_countries_are_kept(raw: Path, tmp_path: Path) -> None:
    rows = masked(raw, tmp_path)
    assert [r["Date"] for r in rows] == [r["Date"] for r in small_rows()]
    assert [r["Date Processed"] for r in rows] == [
        r["Date Processed"] for r in small_rows()
    ]
    assert rows[4]["Country"] == "INDONESIA"


def test_masking_is_repeatable_and_depends_on_the_key(
    raw: Path, tmp_path: Path
) -> None:
    first = masked_bytes(raw, tmp_path)
    assert masked_bytes(raw, tmp_path) == first
    assert masked_bytes(raw, tmp_path, key=b"key-two") != first


def test_a_header_without_reference_aborts(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "activity.csv").write_text(
        "Date,Date Processed,Description,Amount\n01/09/2026,02/09/2026,X,1.00\n"
    )
    with pytest.raises(MaskError, match="Reference"):
        masked_bytes(raw, tmp_path)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("name", "message"),
    [("four_columns.csv", "Reference"), ("missing_reference.csv", "Reference")],
)
def test_the_committed_rejected_layouts_abort(
    tmp_path: Path, name: str, message: str
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "activity.csv").write_bytes((FIXTURES / "handbuilt" / name).read_bytes())
    with pytest.raises(MaskError, match=message):
        masked_bytes(raw, tmp_path)


def test_the_committed_refund_fixture_is_accepted_and_refunds_stay_negative(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = FIXTURES / "handbuilt" / "refunds.csv"
    (raw / "activity.csv").write_bytes(source.read_bytes())
    rows = masked(raw, tmp_path)
    original = list(csv.DictReader(io.StringIO(source.read_text(), newline="")))
    assert [r["Amount"].startswith("-") for r in rows] == [
        r["Amount"].startswith("-") for r in original
    ]
    assert any(r["Description"] == "Qantas Ultimate Annual Travel Credit" for r in rows)


def test_a_filled_exchange_rate_aborts_because_its_format_is_unobserved(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    odd = small_rows()
    odd[0]["Exchange Rate"] = "0.71"
    write_csv(raw / "activity.csv", odd)
    with pytest.raises(MaskError, match="Exchange Rate"):
        masked_bytes(raw, tmp_path)


def test_an_unknown_reference_shape_aborts_and_writes_nothing(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    odd = small_rows()
    odd[0]["Reference"] = "'ZZ1234'"
    write_csv(raw / "activity.csv", odd)
    with pytest.raises(MaskError, match="reference"):
        masked_bytes(raw, tmp_path)
    assert not (tmp_path / "out").exists()


def test_a_commission_that_fits_no_known_rate_aborts(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    odd = small_rows()
    odd[4]["Commission"] = "1.00"
    write_csv(raw / "activity.csv", odd)
    with pytest.raises(MaskError, match="commission"):
        masked_bytes(raw, tmp_path)


def big_rows() -> list[dict[str, str]]:
    plain = [
        row(
            f"{index % 28 + 1:02d}/03/2025",
            f"{index % 28 + 1:02d}/03/2025",
            f"SHOP NUMBER {index}          TOWN",
            f"{index + 1}.50",
            f"'AT25{60 + index % 10:03d}0004{index:012d}'",
        )
        for index in range(60)
    ]
    return [*plain, *small_rows()]


def test_a_long_export_is_cut_to_a_subset_that_keeps_every_special_case(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    write_csv(raw / "activity.csv", big_rows())
    rows = masked(raw, tmp_path)
    assert SUBSET_SIZE <= len(rows) < len(big_rows())
    assert sum(bool(r["Commission"]) for r in rows) == 3
    assert any(r["Description"] == PAYID for r in rows)
    assert any(r["Description"] == "MEMBERSHIP FEE" for r in rows)
    assert any("ONLINE PAYMENT RECEIVED" in r["Description"] for r in rows)
    same_day = [r for r in rows if r["Date"] == "08/06/2025"]
    assert len(same_day) == 2
    assert any(r["Date"] == "14/12/2025" for r in rows)


def test_a_short_export_is_masked_whole(raw: Path, tmp_path: Path) -> None:
    assert len(masked(raw, tmp_path)) == len(small_rows())


def test_a_three_and_a_half_percent_commission_stays_three_and_a_half_percent(
    raw: Path, tmp_path: Path
) -> None:
    row = masked(raw, tmp_path)[6]
    commission = cents(row["Commission"])
    base = cents(row["Amount"]) - commission
    assert abs(commission * RATE_SCALE - base * 350) <= RATE_SCALE


def test_the_same_merchant_masks_the_same_across_files(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    write_csv(raw / "activity.csv", small_rows()[:1])
    write_csv(raw / "second.csv", small_rows()[:1])
    out = tmp_path / "out"
    key = tmp_path / "key"
    key.write_bytes(b"k")
    run(raw, out, key, tmp_path / "no-config.json")
    assert (out / "activity.csv").read_bytes() == (out / "second.csv").read_bytes()
