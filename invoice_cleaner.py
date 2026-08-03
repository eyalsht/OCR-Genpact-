"""Normalize and validate OCR-extracted invoice records.

The entry point is :func:`process_records`, which takes the raw extraction
output and returns ``(clean_records, flagged_records)``.

Two ideas run through the whole module:

*Nothing is discarded silently.* Every input record comes out in exactly one
of the two lists, duplicates included, and every transformation is recorded
alongside the original string. A cleaner that quietly drops an invoice is
worse than one that flags too much.

*A repair is only worth making if it can be refused.* The OCR substitution
map is a fallback, runs only on the amount field, and gives up rather than
guess when it would have to change more than two characters.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, NamedTuple

MAX_OCR_SUBSTITUTIONS = 2

# Strings OCR emits when it found nothing. These mean "absent", which is a
# different thing from a zero amount.
NULL_TOKENS = frozenset(
    {"", "-", "--", "?", "n/a", "n\\a", "na", "none", "null", "nil", "unknown"}
)

# Letter-to-digit only, and only ever applied to a numeric field. The 0/O and
# l/1/I pairs are primary: what separates those glyphs lives in the character's
# edge profile, which is the first thing a blurred or thresholded scan loses.
# The rest are second-tier shape confusions. See docs/RESEARCH.md.
OCR_DIGIT_LOOKALIKES = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",
    "|": "1",
    "S": "5",
    "B": "8",
    "Z": "2",
    "G": "6",
}

CURRENCY_CHARS = frozenset("$€£¥₪₹")

_NUMERIC = re.compile(r"[+-]?\d*\.?\d+")


class AmountResult(NamedTuple):
    """``status`` is one of ``ok``, ``missing`` or ``unparseable``.

    The distinction between the last two is the point: "the scan found no
    amount" and "the scan found something I cannot read" need different
    handling by whoever picks the record up.
    """

    value: Decimal | None
    status: str
    repairs: list[str]


def normalize_amount(raw: Any) -> AmountResult:
    """Turn a raw amount into a :class:`Decimal`, repairing OCR damage if needed."""
    if raw is None:
        return AmountResult(None, "missing", [])

    # OCR output is usually strings, but an upstream change could hand us a
    # real number and that should not be a crash.
    if isinstance(raw, bool):
        return AmountResult(None, "unparseable", [])
    if isinstance(raw, int | float | Decimal):
        return AmountResult(_quantize(Decimal(str(raw))), "ok", [])
    if not isinstance(raw, str):
        return AmountResult(None, "unparseable", [])

    text = raw.strip()
    if text.lower() in NULL_TOKENS:
        return AmountResult(None, "missing", [])

    negative, text = _strip_accounting_parens(text)
    text = "".join(ch for ch in text if ch not in CURRENCY_CHARS and not ch.isspace())

    text, separators_resolved = _resolve_separators(text)
    if not separators_resolved:
        return AmountResult(None, "unparseable", [])

    repairs: list[str] = []
    value = _to_decimal(text)

    if value is None:
        # Only now, having genuinely failed to parse, is the map worth trying.
        repaired, repairs = _repair_ocr(text)
        value = _to_decimal(repaired) if repaired is not None else None
        if value is None:
            return AmountResult(None, "unparseable", [])

    if negative:
        value = -value
    return AmountResult(_quantize(value), "ok", repairs)


def normalize_vendor(raw: Any) -> str | None:
    """Collapse whitespace; return ``None`` for absent or blank names.

    Deliberately does not touch characters. Substitution direction is a
    property of the field: in an amount the letter is the misread, in a name
    the digit is. Running the numeric map here would turn "OOO Vostok" into
    "000 Vostok".
    """
    if not isinstance(raw, str):
        return None
    return " ".join(raw.split()) or None


# --------------------------------------------------------------------------
# Amount parsing internals
# --------------------------------------------------------------------------


def _strip_accounting_parens(text: str) -> tuple[bool, str]:
    """``(450.00)`` is accounting notation for a negative, not decoration."""
    if text.startswith("(") and text.endswith(")"):
        return True, text[1:-1].strip()
    return False, text


def _resolve_separators(text: str) -> tuple[str, bool]:
    """Strip thousands separators, or refuse when the convention is ambiguous.

    Returns ``(text, resolved)``. ``1.200,00`` is one thousand two hundred
    under European convention, but ``1.200`` on its own is equally readable as
    1.2 -- and a cleaner that silently turns 1200 into 1.2 is worse than one
    that admits it cannot tell. So those are refused rather than resolved.
    """
    has_comma, has_dot = "," in text, "." in text

    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            return text, False  # European convention; not supported.
        return text.replace(",", ""), True
    if has_comma:
        return text.replace(",", ""), True
    if text.count(".") > 1:
        return text, False
    return text, True


def _repair_ocr(text: str) -> tuple[str | None, list[str]]:
    """Apply the lookalike map, or give up if it would change too much.

    Returns ``(None, [])`` when nothing was substitutable or when more than
    :data:`MAX_OCR_SUBSTITUTIONS` characters would have to change. Past two,
    a "repair" is not recovering a number so much as inventing one.
    """
    out: list[str] = []
    substitutions: list[str] = []

    for index, char in enumerate(text):
        replacement = OCR_DIGIT_LOOKALIKES.get(char)
        if replacement is None:
            out.append(char)
        else:
            out.append(replacement)
            substitutions.append(f"ocr_substitution: {char!r}->{replacement!r} at index {index}")

    if not substitutions or len(substitutions) > MAX_OCR_SUBSTITUTIONS:
        return None, []
    return "".join(out), substitutions


def _to_decimal(text: str) -> Decimal | None:
    # The regex guard matters: Decimal happily accepts "1e5", "Infinity" and
    # "NaN", none of which are amounts a scanner produced.
    if not text or not _NUMERIC.fullmatch(text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
