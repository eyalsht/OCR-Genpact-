"""Coverage for the rules the provided sample never exercises.

Four validation rules -- AMOUNT_OUTLIER, DATE_FUTURE, DUPLICATE_CONFLICT and
INVOICE_ID_MALFORMED -- are never triggered by the eight given rows. A rule
with no test is a rule nobody has verified, so these fixtures exist to fire
each one at least once.
"""

from datetime import date

import pytest

from invoice_cleaner import process_records
from sample_data import EXTENDED_RECORDS

REFERENCE = date(2024, 3, 11)


@pytest.fixture
def result():
    return process_records(EXTENDED_RECORDS, reference_date=REFERENCE)


def _codes(record):
    return [reason["code"] for reason in record["reasons"]]


def _by_id(records, invoice_id):
    return next(record for record in records if record.get("invoice_id") == invoice_id)


def test_nothing_vanishes(result):
    clean, flagged = result
    assert len(clean) + len(flagged) == len(EXTENDED_RECORDS)


def test_expected_split(result):
    clean, _ = result
    assert [record["invoice_id"] for record in clean] == ["INV-2001", "INV-2010"]


@pytest.mark.parametrize(
    ("invoice_id", "expected_codes"),
    [
        # The four the sample leaves cold.
        ("INV-2002", ["DATE_FUTURE"]),
        ("INV-2006", ["AMOUNT_OUTLIER"]),  # 12,00,000 strips to 1200000
        ("INV-2OO1", ["INVOICE_ID_MALFORMED"]),  # letter O, not digit zero
        ("2011", ["INVOICE_ID_MALFORMED"]),  # no INV- prefix
        # And the rest of the awkward squad.
        ("INV-2003", ["AMOUNT_NON_POSITIVE"]),  # exactly zero
        ("INV-2004", ["AMOUNT_NON_POSITIVE"]),  # (450.00) is minus 450
        ("INV-2005", ["AMOUNT_UNPARSEABLE"]),  # 1O0O.OO needs four repairs
        ("INV-2007", ["AMOUNT_UNPARSEABLE"]),  # European separators, refused
        ("INV-2008", ["VENDOR_MISSING"]),  # the key is absent entirely
        ("INV-2009", ["AMOUNT_MISSING"]),  # a real None, not the string
        ("INV-2012", ["DATE_INVALID"]),  # 2024-02-30 is not a day
    ],
)
def test_each_rule_fires(result, invoice_id, expected_codes):
    _, flagged = result
    assert _codes(_by_id(flagged, invoice_id)) == expected_codes


def test_same_id_different_amount_is_a_conflict(result):
    _, flagged = result
    conflict = next(record for record in flagged if "DUPLICATE_CONFLICT" in _codes(record))
    assert conflict["invoice_id"] == "INV-2001"
    assert conflict["amount"] == "5000.00"
    assert conflict["duplicate_of"] == 0


def test_lookalike_id_did_not_merge_into_the_real_one(result):
    """INV-2OO1 is flagged as malformed, but it is still its own invoice."""
    _, flagged = result
    record = _by_id(flagged, "INV-2OO1")
    assert not any(code.startswith("DUPLICATE") for code in _codes(record))
    assert "duplicate_of" not in record


def test_parenthesised_negative_keeps_its_sign(result):
    """The record is flagged, but the number underneath is still minus 450."""
    from invoice_cleaner import normalize_amount

    assert float(normalize_amount("(450.00)").value) == -450.0


def test_unicode_vendor_survives_untouched(result):
    clean, _ = result
    assert _by_id(clean, "INV-2010")["vendor"] == "Zoë Ltd"


def test_outputs_are_json_serializable(result):
    import json

    clean, flagged = result
    json.dumps(clean)
    json.dumps(flagged)


def test_records_with_no_id_or_no_date_are_caught():
    """Neither fixture set contains these, which is exactly why they are here."""
    rows = [
        {"invoice_id": "", "amount": "10.00", "date": "2024-03-01", "vendor": "A"},
        {"invoice_id": "INV-3001", "amount": "10.00", "date": "", "vendor": "A"},
    ]
    _, flagged = process_records(rows, reference_date=REFERENCE)

    assert _codes(flagged[0]) == ["INVOICE_ID_MISSING"]
    assert _codes(flagged[1]) == ["DATE_MISSING"]


def test_every_declared_rule_is_exercised_by_the_test_suite():
    """A rule with no test is a rule nobody has verified.

    Adding a code to RULE_MESSAGES without a fixture that triggers it fails
    here, which keeps the rule table and the fixtures honest about each other.
    """
    from invoice_cleaner import RULE_MESSAGES
    from sample_data import RAW_RECORDS

    batches = [
        (RAW_RECORDS, None),
        (EXTENDED_RECORDS, REFERENCE),
        (
            [
                {"invoice_id": "", "amount": "10.00", "date": "2024-03-01", "vendor": "A"},
                {"invoice_id": "INV-3001", "amount": "10.00", "date": "", "vendor": "A"},
            ],
            REFERENCE,
        ),
    ]

    fired = set()
    for rows, reference in batches:
        _, flagged = process_records(rows, reference_date=reference)
        for record in flagged:
            fired.update(_codes(record))

    assert fired == set(RULE_MESSAGES)
