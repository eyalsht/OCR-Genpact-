"""Date parsing across the formats the extractor emits, and the ambiguity it can't resolve."""

from datetime import date

import pytest

from invoice_cleaner import normalize_date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-01-05", date(2024, 1, 5)),
        ("2024/01/09", date(2024, 1, 9)),
        ("Jan 8, 2024", date(2024, 1, 8)),
        ("January 8, 2024", date(2024, 1, 8)),
        ("08-Jan-2024", date(2024, 1, 8)),
        # Only readable as DD/MM -- there is no month 13.
        ("13/06/2024", date(2024, 6, 13)),
    ],
)
def test_parses_each_format(raw, expected):
    result = normalize_date(raw)
    assert result.status == "ok"
    assert result.value == expected


def test_ambiguous_slash_date_picks_us_order_and_says_so():
    """01/06/2024 is Jan 6 and Jun 1. No parser can tell from the string alone.

    US order is chosen because the batch settles it -- INV-1001 is Jan 5,
    INV-1003 is Jan 7, INV-1004 is Jan 8, and the IDs run in sequence, so the
    sequential INV-1002 sitting between them is Jan 6. That is an inference
    from the data, but it is still an inference, so it gets recorded.
    """
    result = normalize_date("01/06/2024")
    assert result.status == "ok"
    assert result.value == date(2024, 1, 6)
    assert len(result.notes) == 1
    assert "ambiguous_date" in result.notes[0]
    assert "2024-06-01" in result.notes[0]


@pytest.mark.parametrize("raw", ["2024-01-05", "Jan 8, 2024", "13/06/2024", "2024/01/09"])
def test_unambiguous_dates_carry_no_note(raw):
    assert normalize_date(raw).notes == []


def test_same_date_under_both_orders_is_not_ambiguous():
    """03/03/2024 reads identically either way, so there is nothing to warn about."""
    result = normalize_date("03/03/2024")
    assert result.value == date(2024, 3, 3)
    assert result.notes == []


@pytest.mark.parametrize(
    "raw",
    [
        "2024-13-40",  # no such month, no such day
        "2024-02-30",  # well-formed and impossible; strptime rejects it for free
        "2023-02-29",  # not a leap year
        "05.01.2024",  # separator we do not claim to support
        "yesterday",
    ],
)
def test_invalid_dates_are_refused(raw):
    result = normalize_date(raw)
    assert result.status == "invalid"
    assert result.value is None


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_absent_dates_are_missing_not_invalid(raw):
    result = normalize_date(raw)
    assert result.status == "missing"
    assert result.value is None
