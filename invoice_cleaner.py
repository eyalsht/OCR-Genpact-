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
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, NamedTuple

MAX_OCR_SUBSTITUTIONS = 2

# Tried in order. strptime rather than a hand-rolled regex, because strptime
# rejects 2024-02-30 and 2023-02-29 for free -- a regex that only checks shape
# would accept both, and calendar arithmetic is not worth reimplementing.
DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
)

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

# Two years. Arbitrary, but it has to be some number, and it is one constant
# rather than a literal buried in a condition.
STALE_DAYS = 730

# A misplaced decimal point is a classic OCR failure and it always fails
# upward, so the ceiling is worth more than a floor.
OUTLIER_THRESHOLD = Decimal("1000000")

INVOICE_ID_PATTERN = re.compile(r"INV-\d+")

ERROR = "error"
WARNING = "warning"

# One plain sentence per rule. These are what the reason string is built from,
# and they are deliberately written for someone who has to act on the record
# rather than for someone reading the source.
RULE_MESSAGES = {
    "AMOUNT_MISSING": "no amount was extracted",
    "AMOUNT_UNPARSEABLE": "an amount was extracted but could not be read as a number",
    "AMOUNT_NON_POSITIVE": "amount is zero or negative, which may be a credit note",
    "AMOUNT_OUTLIER": "amount is implausibly large, which usually means a misplaced decimal",
    "DATE_MISSING": "no date was extracted",
    "DATE_INVALID": "date does not match any supported format, or is not a real calendar date",
    "DATE_FUTURE": "date is after the batch reference date",
    "DATE_STALE": "date is far older than the rest of the batch",
    "VENDOR_MISSING": "vendor name is blank or absent",
    "INVOICE_ID_MISSING": "no invoice identifier",
    "INVOICE_ID_MALFORMED": "invoice identifier does not match the expected INV-<digits> form",
    "DUPLICATE_EXACT": "an identical record for this invoice already appeared in the batch",
    "DUPLICATE_CONFLICT": "this invoice already appeared with a different amount, date or vendor",
}


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


class DateResult(NamedTuple):
    """``status`` is one of ``ok``, ``missing`` or ``invalid``.

    ``notes`` carries observations that are worth surfacing but are not
    defects -- an ambiguous slash date is read, not flagged.
    """

    value: date | None
    status: str
    notes: list[str]


def normalize_date(raw: Any) -> DateResult:
    """Parse a date, recording any reading the format left genuinely ambiguous."""
    if raw is None:
        return DateResult(None, "missing", [])
    if not isinstance(raw, str):
        return DateResult(None, "invalid", [])

    text = raw.strip()
    if not text:
        return DateResult(None, "missing", [])

    parsed = _first_matching_format(text)
    if parsed is None:
        return DateResult(None, "invalid", [])

    notes = []
    alternative = _alternative_day_first_reading(text, parsed)
    if alternative is not None:
        notes.append(
            f"ambiguous_date: read as {parsed.isoformat()} under MM/DD/YYYY, "
            f"also valid as {alternative.isoformat()} under DD/MM/YYYY"
        )
    return DateResult(parsed, "ok", notes)


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


def process_records(
    raw_records: list[dict],
    *,
    reference_date: date | None = None,
) -> tuple[list[dict], list[dict]]:
    """Take the raw records and return ``(clean_records, flagged_records)``.

    Flagged records carry a ``reason`` field explaining why they were flagged.

    ``reference_date`` is keyword-only with a default, so the signature the
    brief asked for -- ``process_records(raw_records)`` -- still behaves
    exactly as specified. It exists because "stale" has to be measured against
    something, and measuring against the wall clock means this demo quietly
    destroys itself: run it in 2027 and every row in the sample is stale.
    Freshness is relative to the batch, which is how invoices actually arrive.
    """
    normalized = [_normalize(record) for record in raw_records]
    reference = reference_date or _derive_reference_date(normalized)

    clean: list[dict] = []
    flagged: list[dict] = []
    first_seen: dict[str, tuple[int, tuple]] = {}

    for index, item in enumerate(normalized):
        reasons = _validate(item, reference)
        duplicate_of = None

        # Every identifier is recorded, not just the ones that validated. If
        # only clean records were remembered, a second copy of an already
        # flagged invoice would sail through as the first good one.
        if item.invoice_id:
            content = _content_key(item)
            if item.invoice_id in first_seen:
                duplicate_of, original_content = first_seen[item.invoice_id]
                code = "DUPLICATE_EXACT" if content == original_content else "DUPLICATE_CONFLICT"
                reasons.append(_reason(code, ERROR, f"first seen at index {duplicate_of}"))
            else:
                first_seen[item.invoice_id] = (index, content)

        if reasons:
            flagged.append(_flagged_record(item, reasons, duplicate_of))
        else:
            clean.append(_clean_record(item))

    return clean, flagged


# --------------------------------------------------------------------------
# Date parsing internals
# --------------------------------------------------------------------------


def _first_matching_format(text: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _alternative_day_first_reading(text: str, parsed: date) -> date | None:
    """Return the day-first reading when it differs from the one we took.

    01/06/2024 is Jan 6 and Jun 1, and nothing in the string decides between
    them. 03/03/2024 reads the same either way, so there is no ambiguity to
    report even though both formats match.
    """
    try:
        day_first = datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None
    return day_first if day_first != parsed else None


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


# --------------------------------------------------------------------------
# Pipeline internals
# --------------------------------------------------------------------------


class _Normalized(NamedTuple):
    invoice_id: str
    amount: AmountResult
    date: DateResult
    vendor: str | None
    raw: dict


def _normalize(raw: dict) -> _Normalized:
    invoice_id = raw.get("invoice_id")
    return _Normalized(
        # Stripped, but never character-substituted. See normalize_vendor.
        invoice_id=invoice_id.strip() if isinstance(invoice_id, str) else "",
        amount=normalize_amount(raw.get("amount")),
        date=normalize_date(raw.get("date")),
        vendor=normalize_vendor(raw.get("vendor")),
        raw=raw,
    )


def _derive_reference_date(items: list[_Normalized]) -> date:
    """The batch's own latest date, ignoring anything dated in the future.

    Future dates are excluded because a future date is itself the error being
    looked for -- one 2099 typo would otherwise redefine "recent" for the
    whole batch and mark every genuine record stale.

    The known weakness: if an entire batch is ancient, nothing inside it looks
    stale, because everything is equally old. That is an acceptable trade for
    a batch-oriented cleaner, and callers who disagree can pass the date in.
    """
    today = date.today()
    dates = [item.date.value for item in items if item.date.value and item.date.value <= today]
    return max(dates) if dates else today


def _reason(code: str, severity: str, detail: str) -> dict:
    message = RULE_MESSAGES[code]
    return {
        "code": code,
        "severity": severity,
        "detail": detail,
        "message": f"{message} ({detail})" if detail else message,
    }


def _validate(item: _Normalized, reference: date) -> list[dict]:
    """Run every rule and collect every failure.

    No early return anywhere. A record can be wrong in more than one way at
    once -- INV-1005 in the sample has both a negative amount and an
    impossible date -- and reporting only the first one sends someone back
    round the loop for the second.
    """
    reasons: list[dict] = []
    amount, parsed_date = item.amount, item.date

    if amount.status == "missing":
        reasons.append(_reason("AMOUNT_MISSING", ERROR, _describe(item.raw.get("amount"))))
    elif amount.status == "unparseable":
        reasons.append(_reason("AMOUNT_UNPARSEABLE", ERROR, _describe(item.raw.get("amount"))))
    else:
        if amount.value <= 0:
            reasons.append(_reason("AMOUNT_NON_POSITIVE", WARNING, str(amount.value)))
        if abs(amount.value) > OUTLIER_THRESHOLD:
            reasons.append(_reason("AMOUNT_OUTLIER", WARNING, str(amount.value)))

    if parsed_date.status == "missing":
        reasons.append(_reason("DATE_MISSING", ERROR, _describe(item.raw.get("date"))))
    elif parsed_date.status == "invalid":
        reasons.append(_reason("DATE_INVALID", ERROR, _describe(item.raw.get("date"))))
    elif parsed_date.value > reference:
        reasons.append(
            _reason("DATE_FUTURE", WARNING, f"batch reference is {reference.isoformat()}")
        )
    elif (reference - parsed_date.value).days > STALE_DAYS:
        age = (reference - parsed_date.value).days
        reasons.append(
            _reason("DATE_STALE", WARNING, f"{age} days before {reference.isoformat()}")
        )

    if item.vendor is None:
        reasons.append(_reason("VENDOR_MISSING", ERROR, _describe(item.raw.get("vendor"))))

    if not item.invoice_id:
        reasons.append(_reason("INVOICE_ID_MISSING", ERROR, ""))
    elif not INVOICE_ID_PATTERN.fullmatch(item.invoice_id):
        reasons.append(_reason("INVOICE_ID_MALFORMED", WARNING, item.invoice_id))

    return reasons


def _content_key(item: _Normalized) -> tuple:
    """What "the same invoice" means, compared after normalization.

    Raw strings would not do: "$1,200.00" and "1200" are the same invoice
    written down two different ways, and comparing the strings would let the
    second one through as new.
    """
    return (
        str(item.amount.value) if item.amount.value is not None else None,
        item.date.value.isoformat() if item.date.value else None,
        item.vendor,
    )


def _describe(value: Any) -> str:
    """repr, so that "  " is visibly different from "" in a reason string."""
    return repr(value) if isinstance(value, str) else str(value)


def _clean_record(item: _Normalized) -> dict:
    return {
        "invoice_id": item.invoice_id,
        # float for JSON-serializability; Decimal did the arithmetic.
        "amount": float(item.amount.value),
        "amount_raw": item.raw.get("amount"),
        "date": item.date.value.isoformat(),
        "date_raw": item.raw.get("date"),
        "vendor": item.vendor,
        "repairs": item.amount.repairs,
        "notes": item.date.notes,
    }


def _flagged_record(item: _Normalized, reasons: list[dict], duplicate_of: int | None) -> dict:
    """Original fields preserved verbatim, with the verdict attached.

    Nothing from the input is overwritten -- whoever picks this up needs to
    see what the scanner actually produced, not this module's opinion of it.
    """
    record = dict(item.raw)
    record["reason"] = "; ".join(f"{r['code']}: {r['message']}" for r in reasons)
    record["reasons"] = reasons
    if item.amount.repairs:
        record["repairs"] = item.amount.repairs
    if item.date.notes:
        record["notes"] = item.date.notes
    if duplicate_of is not None:
        record["duplicate_of"] = duplicate_of
    return record


def _report(raw_records: list[dict]) -> str:
    """Human-readable summary of a run. Used by ``python invoice_cleaner.py``."""
    clean, flagged = process_records(raw_records)
    lines = [
        "",
        f"  {len(raw_records)} records in  ->  {len(clean)} clean, {len(flagged)} flagged",
        "",
    ]

    for record in clean:
        lines.append(
            f"  CLEAN    {record['invoice_id']:<10} "
            f"{record['amount']:>12,.2f}   {record['date']}   {record['vendor']}"
        )
        for note in record["repairs"] + record["notes"]:
            lines.append(f"                      -> {note}")

    for record in flagged:
        lines.append(f"  FLAGGED  {record.get('invoice_id') or '<no id>'}")
        for reason in record["reasons"]:
            lines.append(f"                      {reason['code']}: {reason['message']}")

    return "\n".join([*lines, ""])


if __name__ == "__main__":
    from sample_data import RAW_RECORDS

    print(_report(RAW_RECORDS))
