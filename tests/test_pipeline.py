"""End-to-end behaviour against the eight rows from the brief."""

from datetime import date

import pytest

from invoice_cleaner import process_records
from sample_data import RAW_RECORDS


@pytest.fixture
def result():
    return process_records(RAW_RECORDS)


def _codes(record):
    return [reason["code"] for reason in record["reasons"]]


def _by_id(records, invoice_id):
    return next(record for record in records if record["invoice_id"] == invoice_id)


def test_the_brief_signature_works_unchanged(result):
    """process_records(raw_records) with no keywords, exactly as specified."""
    clean, flagged = result
    assert isinstance(clean, list)
    assert isinstance(flagged, list)


def test_nothing_vanishes(result):
    """The cheapest invariant available and the one that catches the most."""
    clean, flagged = result
    assert len(clean) + len(flagged) == len(RAW_RECORDS)


def test_expected_split(result):
    clean, flagged = result
    assert [record["invoice_id"] for record in clean] == ["INV-1001", "INV-1002"]
    assert len(flagged) == 6


def test_every_flagged_record_has_a_reason_string(result):
    """The literal requirement from the brief."""
    _, flagged = result
    for record in flagged:
        assert isinstance(record["reason"], str)
        assert record["reason"].strip()


@pytest.mark.parametrize(
    ("invoice_id", "expected_codes"),
    [
        ("INV-1003", ["AMOUNT_MISSING"]),  # "N/A" is a sentinel, not a number
        ("INV-1004", ["VENDOR_MISSING"]),  # amount and date are both fine here
        ("INV-1006", ["AMOUNT_MISSING"]),  # "  " is blank, not zero
        ("INV-1007", ["DATE_STALE"]),  # valid, but five years older than the batch
    ],
)
def test_single_failure_rows(result, invoice_id, expected_codes):
    _, flagged = result
    assert _codes(_by_id(flagged, invoice_id)) == expected_codes


def test_row_with_two_independent_failures_reports_both():
    """INV-1005 has a negative amount AND an impossible date.

    Stopping at the first problem sends someone round the loop twice.
    """
    _, flagged = process_records(RAW_RECORDS)
    assert _codes(_by_id(flagged, "INV-1005")) == ["AMOUNT_NON_POSITIVE", "DATE_INVALID"]


def test_repeated_invoice_is_flagged_and_points_at_the_original(result):
    _, flagged = result
    duplicate = next(record for record in flagged if "DUPLICATE_EXACT" in _codes(record))
    assert duplicate["invoice_id"] == "INV-1001"
    assert duplicate["duplicate_of"] == 0


def test_ocr_damaged_amount_survives_with_an_audit_trail(result):
    """INV-1002 is the row the whole exercise is built around."""
    clean, _ = result
    record = _by_id(clean, "INV-1002")

    assert record["amount"] == 950.5
    assert record["amount_raw"] == "95O.5"  # the original is never destroyed
    assert len(record["repairs"]) == 1
    # And its date was ambiguous, which is recorded without flagging the row.
    assert record["date"] == "2024-01-06"
    assert any("ambiguous_date" in note for note in record["notes"])


def test_clean_records_are_json_serializable(result):
    import json

    clean, flagged = result
    json.dumps(clean)
    json.dumps(flagged)


def test_reference_date_actually_changes_the_verdict():
    """Staleness is measured against the batch, and the injection point works.

    Proving this matters: if the argument existed but were ignored, every
    other assertion here would still pass.
    """
    _, flagged = process_records(RAW_RECORDS, reference_date=date(2024, 2, 1))
    assert "DATE_STALE" in _codes(_by_id(flagged, "INV-1007"))

    # Move the reference back to 2019 and the same row is unremarkable.
    clean, _ = process_records(RAW_RECORDS, reference_date=date(2019, 6, 1))
    assert "INV-1007" in [record["invoice_id"] for record in clean]


def test_derived_reference_is_the_batch_not_the_clock():
    """No wall-clock dependency: the answer must not change as time passes."""
    derived_clean, derived_flagged = process_records(RAW_RECORDS)
    explicit_clean, explicit_flagged = process_records(
        RAW_RECORDS, reference_date=date(2024, 1, 9)
    )
    assert derived_clean == explicit_clean
    assert derived_flagged == explicit_flagged


def test_is_deterministic():
    assert process_records(RAW_RECORDS) == process_records(RAW_RECORDS)


def test_input_is_not_mutated():
    before = [dict(record) for record in RAW_RECORDS]
    process_records(RAW_RECORDS)
    assert RAW_RECORDS == before


def test_empty_batch():
    assert process_records([]) == ([], [])
