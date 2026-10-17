"""Mask raw Up API captures into committable test fixtures (S1-13).

Raw captures live in ``data/recon/raw/up/`` (gitignored, never committed). Masked
copies are written to ``tests/fixtures/up/`` under the same relative name.

    uv run python scripts/mask_fixtures.py

Masking is deterministic: the same real value always becomes the same fake value,
across files and across runs, so a Transfer's two legs, an account's id in a
transaction's ``relationships`` and in a URL all still line up. The mapping is keyed by
a random secret in ``data/recon/.mask-key`` (created on first run, gitignored), so the
real values cannot be recovered or checked from the committed fixtures.

What is masked:

- Every UUID, wherever it appears (ids, ``links``, ``relationships``).
- Money: ``value`` and ``valueInBaseUnits`` of every amount and balance. The sign, the
  digit count and whole-dollar-ness are kept, and equal amounts stay equal, so a
  Transfer's legs still net to zero. Balances no longer reconcile to transactions.
- Customer handles (``$name``), card suffixes, Up deep links, pagination cursors,
  Tag ids, account display names.
- Free text: ``message``, ``note`` and ``rawText``; ``description`` on anything that
  is not a card purchase (Osko payer names and the like). Up-generated transfer
  descriptions ("Cover to Clothes") keep their prefix and mask the account name.

What is kept: dates, currency codes, statuses, transaction types, category ids (Up's
public taxonomy) and card-purchase merchant names. The merchants kept are listed after
each run so they can be checked by eye before committing.

Optional ``data/recon/mask-config.json`` (gitignored) pins readable fake values::

    {"handles": {"$myhandle": "$me", "$partner": "$partner"},
     "names": {"Clothes": "Saver Clothes"},
     "keep_names": ["Spending"], "keep_tags": [], "keep_descriptions": []}

After masking, the output is scanned for every real value that was replaced and for
anything shaped like an Up token. A hit aborts the run before that file is written.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import sys
import uuid
from pathlib import Path
from urllib.parse import quote, unquote

from pydantic import BaseModel, ConfigDict, Field

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "recon" / "raw" / "up"
DEFAULT_OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "up"
DEFAULT_KEY_PATH = REPO_ROOT / "data" / "recon" / ".mask-key"
DEFAULT_CONFIG_PATH = REPO_ROOT / "data" / "recon" / "mask-config.json"

_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_CURSOR = re.compile(
    r"(page(?:%5B|\[)(?:after|before)(?:%5D|\])=)[^&\s\"]+", re.IGNORECASE
)
_TAG_FILTER = re.compile(r"(filter(?:%5B|\[)tag(?:%5D|\])=)([^&\s\"]+)", re.IGNORECASE)
_UP_TOKEN = re.compile(r"up:(?:yeah|test):[A-Za-z0-9_-]+")
_DEEP_LINK_PREFIX = "up://transaction/"
_DEEP_LINK_PAYLOAD = re.compile(r"(\D*)(\d+)")

# Up writes these itself; what follows the prefix is an account name or a handle.
_TRANSFER_PREFIXES = (
    "Auto Transfer from ",
    "Auto Transfer to ",
    "Transfer from ",
    "Transfer to ",
    "Cover from ",
    "Cover to ",
    "Forward from ",
    "Forward to ",
)
_AMOUNT_KEYS = {"currencyCode", "value", "valueInBaseUnits"}
_MIN_LEAK_LENGTH = 4  # shorter literals would match inside unrelated numbers
_CENTS_PER_DOLLAR = 100


class MaskError(Exception):
    """A capture could not be masked safely."""


class MaskConfig(BaseModel):
    """Optional readable overrides, from ``data/recon/mask-config.json``."""

    model_config = ConfigDict(extra="forbid")

    handles: dict[str, str] = Field(default_factory=dict)
    names: dict[str, str] = Field(default_factory=dict)
    keep_names: frozenset[str] = frozenset({"Spending"})
    keep_tags: frozenset[str] = frozenset()
    keep_descriptions: frozenset[str] = frozenset()


class Masker:
    def __init__(self, key: bytes, config: MaskConfig) -> None:
        self._key = key
        self._config = config
        self.replaced: set[str] = set()
        self.kept_merchants: set[str] = set()

    # -- primitives ---------------------------------------------------------

    def _digest(self, label: str, real: str) -> bytes:
        message = f"{label}\0{real}".encode()
        return hmac.new(self._key, message, hashlib.sha256).digest()

    def _replace(self, real: str, fake: str) -> str:
        if real != fake and len(real) >= _MIN_LEAK_LENGTH:
            self.replaced.add(real)
        return fake

    def uuid(self, real: str) -> str:
        fake = str(uuid.UUID(bytes=self._digest("uuid", real.lower())[:16], version=4))
        return self._replace(real, fake)

    def handle(self, real: str) -> str:
        fake = self._config.handles.get(real)
        if fake is None:
            fake = "$user" + self._digest("handle", real)[:3].hex()
        return self._replace(real, fake)

    def account_name(self, real: str) -> str:
        if real in self._config.keep_names:
            return real
        fake = self._config.names.get(real)
        if fake is None:
            fake = "Account " + self._digest("name", real)[:2].hex()
        return self._replace(real, fake)

    def tag(self, real: str) -> str:
        if real in self._config.keep_tags:
            return real
        return self._replace(real, "tag-" + self._digest("tag", real)[:3].hex())

    def card_suffix(self, real: str) -> str:
        number = int.from_bytes(self._digest("card", real)[:4]) % 10_000
        return f"{number:04d}"

    def cents(self, real: int) -> int:
        """Same digit count and whole-dollar-ness; equal inputs give equal outputs."""
        if real == 0:
            return 0
        whole_dollars = real % _CENTS_PER_DOLLAR == 0
        source = real // _CENTS_PER_DOLLAR if whole_dollars else real
        digits = len(str(source))
        low = 10 ** (digits - 1)
        span = 9 * low
        fake = low + int.from_bytes(self._digest("cents", str(real))[:8]) % span
        if whole_dollars:
            return fake * _CENTS_PER_DOLLAR
        if fake % _CENTS_PER_DOLLAR == 0:
            fake += 7  # a fractional amount must not turn into a whole-dollar one
        return fake

    # -- strings ------------------------------------------------------------

    def text(self, value: str) -> str:
        """Mask the identifiers embedded in a string (ids, cursors, tag filters)."""
        value = _UUID.sub(lambda m: self.uuid(m.group(0)), value)
        value = _CURSOR.sub(r"\1masked-cursor", value)
        return _TAG_FILTER.sub(
            lambda m: m.group(1) + quote(self.tag(unquote(m.group(2))), safe=""),
            value,
        )

    def deep_link(self, value: str) -> str:
        if not value.startswith(_DEEP_LINK_PREFIX):
            msg = "unrecognised deepLinkURL"
            raise MaskError(msg)
        encoded = value.removeprefix(_DEEP_LINK_PREFIX)
        try:
            payload = base64.b64decode(encoded, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError) as exc:
            msg = "undecodable deepLinkURL"
            raise MaskError(msg) from exc
        match = _DEEP_LINK_PAYLOAD.fullmatch(payload)
        if match is None:
            msg = "unrecognised deepLinkURL payload"
            raise MaskError(msg)
        label, number = match.groups()
        low = 10 ** (len(number) - 1)
        fake_number = low + int.from_bytes(self._digest("link", number)[:8]) % (9 * low)
        fake = base64.b64encode(f"{label}{fake_number}".encode()).decode()
        self._replace(encoded, fake)
        self._replace(number, str(fake_number))
        return _DEEP_LINK_PREFIX + fake

    def label(self, value: str) -> str:
        return self.handle(value) if value.startswith("$") else self.account_name(value)

    def description(self, value: str, *, card_purchase: bool) -> str:
        if card_purchase:
            self.kept_merchants.add(value)
            return self.text(value)
        if value in self._config.keep_descriptions:
            return value
        for prefix in _TRANSFER_PREFIXES:
            if value.startswith(prefix):
                return prefix + self.label(value.removeprefix(prefix))
        return "Masked description"

    # -- structure ----------------------------------------------------------

    def mask(self, node: Json) -> Json:
        if isinstance(node, dict):
            return self._mask_dict(node)
        if isinstance(node, list):
            return [self.mask(item) for item in node]
        if isinstance(node, str):
            return self.text(node)
        return node

    def _mask_amount(self, node: dict[str, Json]) -> dict[str, Json]:
        units, value = node["valueInBaseUnits"], node["value"]
        if not isinstance(units, int) or not isinstance(value, str):
            msg = "amount has an unexpected shape"
            raise MaskError(msg)
        decimals = len(value.partition(".")[2])
        fake = (-1 if units < 0 else 1) * self.cents(abs(units))
        digits = f"{abs(fake):0{decimals + 1}d}"
        split = len(digits) - decimals
        formatted = digits[:split] + ("." + digits[split:] if decimals else "")
        return {
            **node,
            "valueInBaseUnits": fake,
            "value": ("-" if fake < 0 else "") + formatted,
        }

    def _mask_dict(self, node: dict[str, Json]) -> dict[str, Json]:
        if node.keys() >= _AMOUNT_KEYS:
            return self._mask_amount(node)
        is_transaction = "transactionType" in node and "status" in node
        card_purchase = node.get("cardPurchaseMethod") is not None
        return {
            key: self._mask_field(
                key,
                value,
                node,
                is_transaction=is_transaction,
                card_purchase=card_purchase,
            )
            for key, value in node.items()
        }

    def _mask_field(
        self,
        key: str,
        value: Json,
        parent: dict[str, Json],
        *,
        is_transaction: bool,
        card_purchase: bool,
    ) -> Json:
        if not isinstance(value, str):
            return self.mask(value)
        if key == "id" and parent.get("type") == "tags":
            return self.tag(value)
        simple = self._simple_field(key, value)
        if simple is not None:
            return simple
        if is_transaction and key == "description":
            return self.description(value, card_purchase=card_purchase)
        if is_transaction and key == "rawText":
            return "Masked rawText"  # carries store numbers and suburbs
        return self.text(value)

    def _simple_field(self, key: str, value: str) -> str | None:
        """Fields masked the same way wherever they appear."""
        if key == "deepLinkURL":
            return self.deep_link(value)
        if key == "cardNumberSuffix":
            return self.card_suffix(value)
        if key == "displayName":
            return self.label(value)
        if key in {"message", "note"}:
            return f"Masked {key}" if value else value
        return None


def load_key(path: Path) -> bytes:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip().encode()


def load_config(path: Path) -> MaskConfig:
    if not path.exists():
        return MaskConfig()
    return MaskConfig.model_validate_json(path.read_text())


def check_output(text: str, masker: Masker, name: str) -> None:
    if _UP_TOKEN.search(text):
        msg = f"{name}: output contains something shaped like an Up token"
        raise MaskError(msg)
    leaked = [real for real in masker.replaced if real in text]
    if leaked:
        msg = (
            f"{name}: {len(leaked)} real value(s) survived masking. "
            "Check for a free-text field that embeds them."
        )
        raise MaskError(msg)


def mask_file(source: Path, destination: Path, masker: Masker) -> bool:
    raw = source.read_text()
    if not raw.strip():
        return False
    data: Json = json.loads(raw)
    masked = masker.mask(data)
    text = json.dumps(masked, indent=2, ensure_ascii=False) + "\n"
    check_output(text, masker, source.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)
    return True


def run(
    raw_dir: Path,
    out_dir: Path,
    key_path: Path = DEFAULT_KEY_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> list[Path]:
    """Mask every ``*.json`` under ``raw_dir``. Returns the files written."""
    masker = Masker(load_key(key_path), load_config(config_path))
    written: list[Path] = []
    for source in sorted(raw_dir.rglob("*.json")):
        destination = out_dir / source.relative_to(raw_dir)
        if mask_file(source, destination, masker):
            written.append(destination)
        else:
            _say(f"skipped (empty): {source.relative_to(raw_dir)}")
    if masker.kept_merchants:
        _say("Merchant names kept as-is (check before committing):")
        for merchant in sorted(masker.kept_merchants):
            _say(f"  {merchant}")
    return written


def _say(message: str) -> None:
    sys.stdout.write(message + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    if not args.raw.is_dir():
        _say(f"No raw captures at {args.raw}")
        return 1
    try:
        written = run(args.raw, args.out)
    except MaskError as exc:
        _say(f"ABORTED: {exc}")
        return 1
    _say(f"Masked {len(written)} file(s) into {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
