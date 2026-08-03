"""Where the AI's first draft and this module disagree, and which one is right.

``naive_first_draft.py`` is the unedited first answer from a cold AI context
given only the assignment text. It is genuinely competent -- it handles the
whitespace-only amount, repairs the 95O.5 misread, parses all five date
formats, and collects more than one reason per record. Several things I
expected to be broken were not.

What it gets wrong is narrower and worse: it converts amounts silently. Every
case below produces a confidently wrong number with no flag raised, which in a
finance pipeline is the failure mode that actually costs money -- a wrong
number nobody was told to check is worse than a missing one.

Guarded with importorskip so a draft that fails to import cannot take CI down
with it.
"""

from datetime import date
from decimal import Decimal

import pytest

from invoice_cleaner import normalize_amount, process_records
from sample_data import RAW_RECORDS

naive = pytest.importorskip("naive_first_draft")

REFERENCE = date(2024, 1, 9)


# --------------------------------------------------------------------------
# Silent miscalculation
# --------------------------------------------------------------------------


def test_accounting_negative_has_its_sign_inverted():
    """(450.00) is minus 450. The draft strips the parentheses as punctuation.

    A credit note becomes a payable. Nothing is flagged, so nobody looks.
    """
    assert naive.normalize_amount("(450.00)") == (450.0, None)

    assert normalize_amount("(450.00)").value == Decimal("-450.00")


def test_european_separators_are_misread_by_a_factor_of_a_thousand():
    """1.200,00 is twelve hundred. The draft returns 1.2 and reports success."""
    assert naive.normalize_amount("€1.200,00") == (1.2, None)

    # Refusing to read it is the honest outcome; guessing on money is not.
    assert normalize_amount("€1.200,00").status == "unparseable"


def test_unbounded_repair_invents_a_number():
    """1O0O.OO needs four substitutions before it parses.

    The draft applies the map to everything unconditionally and as a first
    pass, so it returns 1000.00 with no indication that four characters were
    changed. This module caps the repair at two and records each one.
    """
    assert naive.normalize_amount("1O0O.OO") == (1000.0, None)

    assert normalize_amount("1O0O.OO").status == "unparseable"


def test_unknown_characters_are_deleted_rather_than_questioned():
    """The draft's regex strips anything non-numeric, so 9X5.5 becomes 95.5."""
    assert naive.normalize_amount("9X5.5") == (95.5, None)

    assert normalize_amount("9X5.5").status == "unparseable"


def test_a_null_token_it_does_not_recognise_becomes_a_real_zero():
    """N0NE is not in the draft's hard-coded list, so it falls through the
    regex to an empty numeric string and lands as 0.00 -- an amount that
    looks deliberate."""
    assert naive.normalize_amount("N0NE") == (0.0, None)

    assert normalize_amount("N0NE").status == "unparseable"


def test_a_non_string_amount_crashes_the_draft():
    with pytest.raises(AttributeError):
        naive.normalize_amount(500)

    assert normalize_amount(500).value == Decimal("500.00")


# --------------------------------------------------------------------------
# Structural
# --------------------------------------------------------------------------


def test_draft_misses_a_duplicate_of_an_already_flagged_record():
    """The draft only remembers identifiers it has seen on *clean* records.

    So if the first copy of an invoice is flagged for any reason, the second
    copy is not recognised as a duplicate and is emitted as clean.
    """
    rows = [
        {"invoice_id": "INV-9", "amount": "N/A", "date": "2024-01-01", "vendor": "A"},
        {"invoice_id": "INV-9", "amount": "100.00", "date": "2024-01-01", "vendor": "A"},
    ]

    draft_clean, _ = naive.process_records(rows)
    assert [record["invoice_id"] for record in draft_clean] == ["INV-9"]

    # Here the second copy is recognised. It is a CONFLICT rather than an
    # EXACT copy because the two scans really do differ -- one has no readable
    # amount and the other has 100.00 -- and a human should decide which to
    # keep. What matters is that it is not emitted as a fresh clean invoice.
    clean, flagged = process_records(rows, reference_date=REFERENCE)
    assert clean == []
    assert any(
        reason["code"].startswith("DUPLICATE") for reason in flagged[1]["reasons"]
    )


def test_draft_cannot_tell_a_re_scan_from_a_contradiction():
    """Same ID with a different amount is reported as a plain duplicate.

    One of those two numbers is wrong. Filing it alongside harmless re-scans
    loses the only signal that says so.
    """
    rows = [
        {"invoice_id": "INV-8", "amount": "500.00", "date": "2024-01-01", "vendor": "A"},
        {"invoice_id": "INV-8", "amount": "5000.00", "date": "2024-01-01", "vendor": "A"},
    ]

    _, draft_flagged = naive.process_records(rows)
    assert "duplicate" in draft_flagged[0]["reason"]
    assert "5000" not in draft_flagged[0]["reason"]  # no hint that they disagree

    _, flagged = process_records(rows, reference_date=REFERENCE)
    assert flagged[0]["reasons"][0]["code"] == "DUPLICATE_CONFLICT"


def test_staleness_verdicts_diverge_on_the_2019_record():
    """The draft's freshness rule is `year < 2000 or date > datetime.now()`.

    Both halves are wall-clock dependent, and the year-2000 cliff is arbitrary
    -- INV-1007 is five years older than everything else in its batch and the
    draft passes it as clean. Measuring against the batch instead makes the
    answer stable and makes that record stand out.
    """
    draft_clean, _ = naive.process_records(RAW_RECORDS)
    assert [record["invoice_id"] for record in draft_clean] == [
        "INV-1001",
        "INV-1002",
        "INV-1007",
    ]

    clean, flagged = process_records(RAW_RECORDS)
    assert [record["invoice_id"] for record in clean] == ["INV-1001", "INV-1002"]
    stale = next(record for record in flagged if record["invoice_id"] == "INV-1007")
    assert stale["reasons"][0]["code"] == "DATE_STALE"


# --------------------------------------------------------------------------
# Credit where it is due
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("95O.5", 950.5), ("$1,200.00", 1200.0), ("2,340", 2340.0), ("  ", None)],
)
def test_the_draft_got_these_right(raw, expected):
    """Recorded so the comparison is not a straw man.

    The whitespace-only amount and the headline OCR misread were both handled
    correctly on the first attempt.
    """
    assert naive.normalize_amount(raw)[0] == expected


def test_the_draft_also_collects_more_than_one_reason():
    """I expected this to be broken -- it is the classic first-draft bug --
    and it was not. INV-1005 comes back with both of its problems."""
    _, draft_flagged = naive.process_records(RAW_RECORDS)
    row = next(record for record in draft_flagged if record["invoice_id"] == "INV-1005")
    assert "negative" in row["reason"]
    assert "could not be parsed" in row["reason"]
