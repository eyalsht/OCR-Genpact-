"""Duplicate detection.

Duplicates are flagged, never dropped. Dropping a record without a trace is
the wrong default anywhere, and specifically wrong in a finance pipeline where
the missing row is a payable nobody will chase.
"""

from datetime import date

from invoice_cleaner import process_records

REFERENCE = date(2024, 1, 9)


def _row(invoice_id, amount="100.00", day="2024-01-05", vendor="Acme Corp"):
    return {"invoice_id": invoice_id, "amount": amount, "date": day, "vendor": vendor}


def _codes(record):
    return [reason["code"] for reason in record["reasons"]]


def test_exact_duplicate_keeps_the_first_and_flags_the_second():
    clean, flagged = process_records([_row("INV-1"), _row("INV-1")], reference_date=REFERENCE)

    assert len(clean) == 1
    assert len(flagged) == 1
    assert _codes(flagged[0]) == ["DUPLICATE_EXACT"]
    # Point at what it duplicates, so a human can go and compare the two.
    assert flagged[0]["duplicate_of"] == 0


def test_same_id_with_a_different_amount_is_a_conflict_not_a_copy():
    """Same ID, two different numbers. One of them is wrong and no machine
    can say which, so this must not be filed alongside harmless re-scans."""
    clean, flagged = process_records(
        [_row("INV-1", amount="500.00"), _row("INV-1", amount="5000.00")],
        reference_date=REFERENCE,
    )

    assert len(clean) == 1
    assert _codes(flagged[0]) == ["DUPLICATE_CONFLICT"]


def test_duplicates_are_matched_after_normalization():
    """$1,200.00 and 1200 are the same invoice written down two ways.

    This is why dedupe runs on normalized values: comparing raw strings would
    let the same invoice through twice.
    """
    clean, flagged = process_records(
        [_row("INV-1", amount="$1,200.00"), _row("INV-1", amount="1200")],
        reference_date=REFERENCE,
    )

    assert len(clean) == 1
    assert _codes(flagged[0]) == ["DUPLICATE_EXACT"]


def test_ocr_lookalike_id_is_not_a_duplicate():
    """INV-1OO1 (letter O) must stay distinct from INV-1001 (digit zero).

    The single most important test here. OCR repair is scoped to the amount
    field precisely so it can never reach the identifier -- "fixing" INV-1OO1
    would merge two different invoices into one and silently delete a payable.
    Mis-flagging costs someone five minutes; this would cost real money.

    The odd identifier is still worth a human's attention, so it is flagged as
    malformed. Flagged and distinct is the correct outcome; the failure mode
    being guarded against is being merged, not being noticed.
    """
    clean, flagged = process_records(
        [_row("INV-1001"), _row("INV-1OO1")], reference_date=REFERENCE
    )

    assert [record["invoice_id"] for record in clean] == ["INV-1001"]
    assert [record["invoice_id"] for record in flagged] == ["INV-1OO1"]
    assert _codes(flagged[0]) == ["INVOICE_ID_MALFORMED"]
    # The point of the test: it was never treated as a copy of INV-1001.
    assert not any(code.startswith("DUPLICATE") for code in _codes(flagged[0]))


def test_duplicate_of_an_already_flagged_record_is_still_caught():
    """The first occurrence being flagged for some other reason must not stop
    the second occurrence from being recognised as a duplicate."""
    rows = [
        _row("INV-1", vendor=""),  # flagged: no vendor
        _row("INV-1", vendor=""),  # and a duplicate of it
    ]
    clean, flagged = process_records(rows, reference_date=REFERENCE)

    assert clean == []
    assert len(flagged) == 2
    assert "DUPLICATE_EXACT" in _codes(flagged[1])


def test_three_copies_all_point_at_the_first():
    clean, flagged = process_records([_row("INV-1")] * 3, reference_date=REFERENCE)

    assert len(clean) == 1
    assert [record["duplicate_of"] for record in flagged] == [0, 0]


def test_nothing_is_ever_discarded():
    rows = [_row("INV-1"), _row("INV-1"), _row("INV-2"), _row("INV-1OO1")]
    clean, flagged = process_records(rows, reference_date=REFERENCE)

    assert len(clean) + len(flagged) == len(rows)
