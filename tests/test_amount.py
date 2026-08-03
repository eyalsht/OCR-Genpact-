"""Amount normalization, including the OCR repair layer and its limits."""

from decimal import Decimal

import pytest

from invoice_cleaner import normalize_amount, normalize_vendor


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,200.00", Decimal("1200.00")),
        ("2,340", Decimal("2340.00")),
        ("3200.00", Decimal("3200.00")),
        ("-450.00", Decimal("-450.00")),
        ("0.00", Decimal("0.00")),
        # Accounting convention: parentheses mean negative. Dropping them
        # turns a credit note into a payable.
        ("(450.00)", Decimal("-450.00")),
        # Indian digit grouping. Commas are separators wherever they appear.
        ("12,00,000", Decimal("1200000.00")),
        # No decimal point at all.
        ("1200", Decimal("1200.00")),
    ],
)
def test_parses_valid_amounts(raw, expected):
    result = normalize_amount(raw)
    assert result.status == "ok"
    assert result.value == expected
    assert result.repairs == []


def test_ocr_letter_o_is_repaired_and_recorded():
    """The headline case from the brief: 95O.5 carries a letter O."""
    result = normalize_amount("95O.5")
    assert result.status == "ok"
    assert result.value == Decimal("950.50")
    # A silent repair is worse than no repair -- finance needs an audit trail.
    assert len(result.repairs) == 1
    assert "O" in result.repairs[0] and "0" in result.repairs[0]


@pytest.mark.parametrize("raw", ["N/A", "n/a", "  ", "", None, "-", "none", "NULL"])
def test_null_tokens_and_blanks_are_missing_not_zero(raw):
    """Whitespace-only is not an empty string, and neither is a zero amount."""
    result = normalize_amount(raw)
    assert result.status == "missing"
    assert result.value is None
    assert result.repairs == []


@pytest.mark.parametrize(
    "raw",
    [
        # Four substitutions. Past two, "repair" is indistinguishable from
        # inventing a number.
        "1O0O.OO",
        # X is not a digit lookalike; deleting it would fabricate 95.5.
        "9X5.5",
        # Looks like a null token but is not one. Must not become 0.0.
        "N0NE",
        # European separators: 1.200,00 is one thousand two hundred, but
        # 1.200 on its own could be 1.2. Guessing on money is worse than
        # refusing, so this is rejected rather than resolved.
        "€1.200,00",
        "1.200,00",
        # Two decimal points and no way to tell which is which.
        "1.200.000",
        "abc",
    ],
)
def test_unparseable_amounts_are_refused_not_guessed(raw):
    result = normalize_amount(raw)
    assert result.status == "unparseable"
    assert result.value is None


def test_non_string_input_does_not_crash():
    """OCR output is not guaranteed to be a string."""
    assert normalize_amount(500).value == Decimal("500.00")
    assert normalize_amount(12.5).value == Decimal("12.50")
    assert normalize_amount([]).status == "unparseable"


def test_repair_is_a_fallback_never_a_first_pass():
    """A string that already parses must never be run through the map."""
    result = normalize_amount("100.00")
    assert result.repairs == []


# --------------------------------------------------------------------------
# Substitution direction is a property of the field, not of the string. In a
# numeric field the letter is the misread; in a text field the digit is. A
# single global map applied everywhere is wrong by construction.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["Beta LLC", "Zoë Ltd", "OOO Vostok", "Acme Corp"])
def test_vendor_names_are_never_ocr_repaired(raw):
    assert normalize_vendor(raw) == raw


def test_vendor_blank_and_missing_collapse_to_none():
    assert normalize_vendor("") is None
    assert normalize_vendor("   ") is None
    assert normalize_vendor(None) is None
