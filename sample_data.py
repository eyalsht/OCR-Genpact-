"""Input fixtures.

``RAW_RECORDS`` is the sample from the assignment brief, copied character for
character. ``95O.5`` carries a capital letter O, and ``INV-1006``'s amount is
two literal space characters rather than an empty string -- both of those
distinctions are the whole point of the exercise, so nothing here is tidied up.

``EXTENDED_RECORDS`` is mine. The provided sample never triggers four of the
validation rules, and a rule with no test is a rule nobody has verified.
"""

# --------------------------------------------------------------------------
# Verbatim from the brief. Do not edit.
# --------------------------------------------------------------------------
RAW_RECORDS: list[dict] = [
    {"invoice_id": "INV-1001", "amount": "$1,200.00", "date": "2024-01-05", "vendor": "Acme Corp"},
    {"invoice_id": "INV-1002", "amount": "95O.5", "date": "01/06/2024", "vendor": "Beta LLC"},
    {"invoice_id": "INV-1003", "amount": "N/A", "date": "2024-01-07", "vendor": "Acme Corp"},
    {"invoice_id": "INV-1004", "amount": "2,340", "date": "Jan 8, 2024", "vendor": ""},
    {"invoice_id": "INV-1001", "amount": "$1,200.00", "date": "2024-01-05", "vendor": "Acme Corp"},
    {"invoice_id": "INV-1005", "amount": "-450.00", "date": "2024-13-40", "vendor": "Gamma Inc"},
    {"invoice_id": "INV-1006", "amount": "  ", "date": "2024/01/09", "vendor": "Delta Co"},
    {"invoice_id": "INV-1007", "amount": "3200.00", "date": "2019-01-10", "vendor": "Acme Corp"},
]

# --------------------------------------------------------------------------
# Mine. Covers the rules the sample leaves cold, plus the cases that worry me.
# --------------------------------------------------------------------------
EXTENDED_RECORDS: list[dict] = [
    # Same ID as a record already seen, but a different amount. Not in the
    # sample, and the case that actually costs money in production: one of
    # these two numbers is wrong and no machine can tell you which.
    {"invoice_id": "INV-2001", "amount": "500.00", "date": "2024-03-01", "vendor": "Acme Corp"},
    {"invoice_id": "INV-2001", "amount": "5000.00", "date": "2024-03-01", "vendor": "Acme Corp"},
    # A capital O inside the identifier. This must NOT be repaired into
    # INV-2001, because repairing it would merge two distinct invoices into
    # one and silently delete a payable.
    {"invoice_id": "INV-2OO1", "amount": "750.00", "date": "2024-03-02", "vendor": "Acme Corp"},
    # Dated after the batch reference date.
    {"invoice_id": "INV-2002", "amount": "120.00", "date": "2099-01-01", "vendor": "Acme Corp"},
    # Zero is not a typo but it is not a payable either.
    {"invoice_id": "INV-2003", "amount": "0.00", "date": "2024-03-03", "vendor": "Acme Corp"},
    # Accounting convention for a negative.
    {"invoice_id": "INV-2004", "amount": "(450.00)", "date": "2024-03-04", "vendor": "Acme Corp"},
    # Four substitutions needed. Past two, "repair" is just guessing.
    {"invoice_id": "INV-2005", "amount": "1O0O.OO", "date": "2024-03-05", "vendor": "Acme Corp"},
    # Indian digit grouping. Strips to 1200000, which trips the outlier rule.
    {"invoice_id": "INV-2006", "amount": "12,00,000", "date": "2024-03-06", "vendor": "Acme Corp"},
    # European separators. 1.200,00 means one thousand two hundred, but
    # "1.200" alone could mean 1.2 -- so this is refused, not guessed at.
    {"invoice_id": "INV-2007", "amount": "€1.200,00", "date": "2024-03-07", "vendor": "Acme Corp"},
    # The vendor key is absent entirely rather than empty.
    {"invoice_id": "INV-2008", "amount": "310.00", "date": "2024-03-08"},
    # A real None rather than the string "None".
    {"invoice_id": "INV-2009", "amount": None, "date": "2024-03-09", "vendor": "Acme Corp"},
    # Non-ASCII vendor name; must survive untouched.
    {"invoice_id": "INV-2010", "amount": "88.00", "date": "2024-03-10", "vendor": "Zoë Ltd"},
    # Identifier that does not match the house format.
    {"invoice_id": "2011", "amount": "99.00", "date": "2024-03-11", "vendor": "Acme Corp"},
    # Well-formed and completely impossible. strptime rejects it for free,
    # which is a good reason not to hand-roll a date parser.
    {"invoice_id": "INV-2012", "amount": "45.00", "date": "2024-02-30", "vendor": "Acme Corp"},
]
