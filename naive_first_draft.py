"""
naive_first_draft.py

First-draft module for cleaning/validating messy OCR-extracted invoice records.

Usage:
    from naive_first_draft import process_records, raw_records
    clean, flagged = process_records(raw_records)
"""

from datetime import datetime
import re


raw_records = [
    {"invoice_id": "INV-1001", "amount": "$1,200.00", "date": "2024-01-05", "vendor": "Acme Corp"},
    {"invoice_id": "INV-1002", "amount": "95O.5",     "date": "01/06/2024", "vendor": "Beta LLC"},
    {"invoice_id": "INV-1003", "amount": "N/A",       "date": "2024-01-07", "vendor": "Acme Corp"},
    {"invoice_id": "INV-1004", "amount": "2,340",     "date": "Jan 8, 2024", "vendor": ""},
    {"invoice_id": "INV-1001", "amount": "$1,200.00", "date": "2024-01-05", "vendor": "Acme Corp"},
    {"invoice_id": "INV-1005", "amount": "-450.00",   "date": "2024-13-40", "vendor": "Gamma Inc"},
    {"invoice_id": "INV-1006", "amount": "  ",        "date": "2024/01/09", "vendor": "Delta Co"},
    {"invoice_id": "INV-1007", "amount": "3200.00",   "date": "2019-01-10", "vendor": "Acme Corp"},
]


# Date formats we try to parse, in order.
DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
]


def normalize_amount(raw_amount):
    """
    Try to turn a messy amount string into a float.
    Returns (value, error_reason). If error_reason is not None, parsing failed.
    """
    if raw_amount is None:
        return None, "amount missing"

    text = raw_amount.strip()

    if text == "" or text.upper() == "N/A":
        return None, "amount missing or not available"

    # Common OCR misread: capital letter O in place of digit 0.
    text = text.replace("O", "0").replace("o", "0")

    # Strip currency symbols, commas, and stray whitespace.
    text = text.replace("$", "").replace(",", "").strip()

    # Keep digits, minus sign, and decimal point only.
    cleaned = re.sub(r"[^0-9.\-]", "", text)

    if cleaned == "" or cleaned == "-":
        return None, f"amount '{raw_amount}' could not be parsed"

    try:
        value = float(cleaned)
    except ValueError:
        return None, f"amount '{raw_amount}' could not be parsed"

    if value < 0:
        return value, "amount is negative"

    return value, None


def normalize_date(raw_date):
    """
    Try to turn a messy date string into an ISO format date string (YYYY-MM-DD).
    Returns (value, error_reason). If error_reason is not None, parsing failed.
    """
    if raw_date is None:
        return None, "date missing"

    text = raw_date.strip()
    if text == "":
        return None, "date missing"

    # Normalize slashes to a consistent separator attempt list already covers this.
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%Y-%m-%d"), None
        except ValueError:
            continue

    return None, f"date '{raw_date}' could not be parsed"


def is_date_suspicious(iso_date):
    """
    Basic sanity check on a parsed date - flag things that are technically
    parseable but look wrong (e.g. too far in the past, or in the future).
    """
    try:
        parsed = datetime.strptime(iso_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return True

    now = datetime.now()
    if parsed.year < 2000 or parsed > now:
        return True

    return False


def process_records(raw_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Takes the raw records and returns (clean_records, flagged_records).
    Flagged records should also include a 'reason' field explaining why
    they were flagged.
    """
    clean_records = []
    flagged_records = []
    seen_keys = set()

    for record in raw_records:
        invoice_id = record.get("invoice_id", "")
        vendor_raw = record.get("vendor", "")
        vendor = vendor_raw.strip() if isinstance(vendor_raw, str) else vendor_raw

        # Duplicate detection: same invoice_id we've already processed.
        dedup_key = invoice_id
        if dedup_key in seen_keys:
            flagged = dict(record)
            flagged["reason"] = f"duplicate record for invoice_id '{invoice_id}'"
            flagged_records.append(flagged)
            continue

        reasons = []

        amount_value, amount_error = normalize_amount(record.get("amount", ""))
        if amount_error:
            reasons.append(amount_error)

        date_value, date_error = normalize_date(record.get("date", ""))
        if date_error:
            reasons.append(date_error)
        elif is_date_suspicious(date_value):
            reasons.append(f"date '{record.get('date', '')}' looks suspicious (out of expected range)")

        if not vendor:
            reasons.append("vendor missing")

        if not invoice_id:
            reasons.append("invoice_id missing")

        if reasons:
            flagged = dict(record)
            flagged["reason"] = "; ".join(reasons)
            flagged_records.append(flagged)
            continue

        seen_keys.add(dedup_key)

        clean_record = {
            "invoice_id": invoice_id,
            "amount": amount_value,
            "date": date_value,
            "vendor": vendor,
        }
        clean_records.append(clean_record)

    return clean_records, flagged_records


if __name__ == "__main__":
    clean, flagged = process_records(raw_records)

    print("Clean records:")
    for r in clean:
        print(r)

    print("\nFlagged records:")
    for r in flagged:
        print(r)
