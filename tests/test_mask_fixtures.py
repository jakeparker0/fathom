"""Tests for the fixture masking script (S1-13)."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

import pytest
from mask_fixtures import Json, MaskConfig, Masker, MaskError, run

if TYPE_CHECKING:
    from pathlib import Path

REAL_ACCOUNT = "2093c23a-9af7-4a28-83c1-2049a73ca5e5"
REAL_OTHER_ACCOUNT = "1c8b6841-e8d1-4d50-afe6-46382fac6155"
REAL_TXN = "375c5f3e-e06f-4c6c-be4a-c966202a9c42"
REAL_LINK_NUMBER = "2906299893"
REAL_LINK = base64.b64encode(f"Transaction-{REAL_LINK_NUMBER}".encode()).decode()


def amount(units: int) -> dict[str, Json]:
    sign = "-" if units < 0 else ""
    value = f"{sign}{abs(units) // 100}.{abs(units) % 100:02d}"
    return {"currencyCode": "AUD", "value": value, "valueInBaseUnits": units}


def transaction(**attributes: Json) -> dict[str, Json]:
    base: dict[str, Json] = {
        "status": "SETTLED",
        "rawText": None,
        "description": "Good Heavens",
        "message": None,
        "note": None,
        "transactionType": "Purchase",
        "cardPurchaseMethod": None,
        "performingCustomer": {"displayName": "$jakeparker0"},
        "amount": amount(-1118),
        "deepLinkURL": f"up://transaction/{REAL_LINK}",
    }
    return {
        "type": "transactions",
        "id": REAL_TXN,
        "attributes": {**base, **attributes},
        "relationships": {
            "account": {
                "data": {"type": "accounts", "id": REAL_ACCOUNT},
                "links": {
                    "related": f"https://api.up.com.au/api/v1/accounts/{REAL_ACCOUNT}"
                },
            },
        },
    }


@pytest.fixture
def masker() -> Masker:
    return Masker(b"test-key", MaskConfig(handles={"$jakeparker0": "$me"}))


def attributes(node: Json) -> dict[str, Json]:
    assert isinstance(node, dict)
    attrs = node["attributes"]
    assert isinstance(attrs, dict)
    return attrs


def test_same_uuid_masks_to_same_value_everywhere_it_appears(masker: Masker) -> None:
    masked = masker.mask(transaction())
    text = json.dumps(masked)

    assert REAL_ACCOUNT not in text
    assert REAL_TXN not in text
    fake_account = masker.uuid(REAL_ACCOUNT)
    assert fake_account in text
    assert text.count(fake_account) == 2  # the id and the related link


def test_masking_is_stable_for_a_key_and_differs_between_keys() -> None:
    first = Masker(b"key-one", MaskConfig())
    again = Masker(b"key-one", MaskConfig())
    other = Masker(b"key-two", MaskConfig())

    assert first.uuid(REAL_TXN) == again.uuid(REAL_TXN)
    assert first.uuid(REAL_TXN) != other.uuid(REAL_TXN)


def test_transfer_legs_stay_equal_and_opposite(masker: Masker) -> None:
    out = attributes(masker.mask(transaction(amount=amount(-35000))))["amount"]
    back = attributes(masker.mask(transaction(amount=amount(35000))))["amount"]

    assert isinstance(out, dict)
    assert isinstance(back, dict)
    assert out["valueInBaseUnits"] == -back["valueInBaseUnits"]
    assert out["valueInBaseUnits"] != -35000


@pytest.mark.parametrize("units", [-1118, 35000, 7, -123456, 100])
def test_masked_amount_keeps_shape_and_value_matches_base_units(
    masker: Masker, units: int
) -> None:
    masked = masker.mask(amount(units))

    assert isinstance(masked, dict)
    fake = masked["valueInBaseUnits"]
    assert isinstance(fake, int)
    assert (fake < 0) == (units < 0)
    assert len(str(abs(fake))) == len(str(abs(units)))
    assert (fake % 100 == 0) == (units % 100 == 0)
    assert (
        masked["value"]
        == f"{'-' if fake < 0 else ''}{abs(fake) // 100}.{abs(fake) % 100:02d}"
    )


def test_zero_amount_stays_zero(masker: Masker) -> None:
    assert masker.mask(amount(0)) == amount(0)


def test_configured_handle_is_used_and_unknown_handle_is_hashed(masker: Masker) -> None:
    mine = attributes(masker.mask(transaction()))["performingCustomer"]
    other = attributes(
        masker.mask(transaction(performingCustomer={"displayName": "$alexglew"}))
    )["performingCustomer"]

    assert mine == {"displayName": "$me"}
    assert isinstance(other, dict)
    assert other["displayName"] != "$alexglew"
    assert str(other["displayName"]).startswith("$user")


def test_card_purchase_keeps_its_merchant_but_not_its_raw_text(masker: Masker) -> None:
    node = transaction(
        cardPurchaseMethod={"method": "CONTACTLESS", "cardNumberSuffix": "3134"},
        rawText="Good Heavens, Melbourne",
    )
    attrs = attributes(masker.mask(node))

    assert attrs["description"] == "Good Heavens"
    assert attrs["rawText"] == "Masked rawText"
    assert attrs["cardPurchaseMethod"] != node["attributes"]["cardPurchaseMethod"]  # type: ignore[index]
    assert "Good Heavens" in masker.kept_merchants


def test_payer_name_and_message_are_masked_on_a_non_card_transaction(
    masker: Masker,
) -> None:
    node = transaction(
        transactionType="Osko Payment Received",
        description="MR JANE CITIZEN",
        rawText="MR JANE CITIZEN",
        message="thanks for dinner",
        note="split",
    )
    text = json.dumps(masker.mask(node))

    for leaked in ("JANE", "dinner", "split"):
        assert leaked not in text


def test_cover_description_keeps_its_prefix_and_masks_the_account_name(
    masker: Masker,
) -> None:
    node = transaction(transactionType="Transfer", description="Cover to Clothes")
    description = attributes(masker.mask(node))["description"]

    assert isinstance(description, str)
    assert description.startswith("Cover to ")
    assert "Clothes" not in description


def test_default_account_name_is_kept(masker: Masker) -> None:
    node = transaction(transactionType="Transfer", description="Transfer from Spending")

    assert attributes(masker.mask(node))["description"] == "Transfer from Spending"


def test_deep_link_is_rewritten_to_a_same_length_number(masker: Masker) -> None:
    link = attributes(masker.mask(transaction()))["deepLinkURL"]

    assert isinstance(link, str)
    payload = base64.b64decode(link.removeprefix("up://transaction/")).decode()
    label, _, number = payload.partition("-")
    assert label == "Transaction"
    assert number != REAL_LINK_NUMBER
    assert len(number) == len(REAL_LINK_NUMBER)


def test_pagination_cursor_and_tag_filter_are_masked(masker: Masker) -> None:
    page: Json = {
        "data": [{"type": "tags", "id": "Yamba"}],
        "links": {
            "next": "https://api.up.com.au/api/v1/transactions?page%5Bsize%5D=30&page%5Bafter%5D=WyIyMDI2Il0%3D",
            "related": "https://api.up.com.au/api/v1/transactions?filter%5Btag%5D=Yamba",
        },
    }
    text = json.dumps(masker.mask(page))

    assert "Yamba" not in text
    assert "WyIyMDI2" not in text
    assert "page%5Bsize%5D=30" in text


def test_token_shaped_value_aborts_the_run(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    (raw / "leaky.json").write_text(json.dumps({"extra": "up:yeah:abc123"}))

    with pytest.raises(MaskError, match="Up token"):
        run(raw, out, key_path=tmp_path / "key", config_path=tmp_path / "cfg.json")

    assert not out.exists()


def test_run_writes_masked_files_and_skips_empty_captures(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    (raw / "transaction_settled_purchase.json").write_text(json.dumps(transaction()))
    (raw / "TD_empty.json").write_text("")

    written = run(
        raw, out, key_path=tmp_path / "key", config_path=tmp_path / "cfg.json"
    )

    assert written == [out / "transaction_settled_purchase.json"]
    content = written[0].read_text()
    assert content.endswith("\n")
    assert REAL_TXN not in content
    assert not (out / "TD_empty.json").exists()
