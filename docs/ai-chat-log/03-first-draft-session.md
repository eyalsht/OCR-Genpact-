# Chat 3 — Cold first-draft session

The sub-session that produced `naive_first_draft.py`. It was given **only** the assignment text — no plan, no hints about which rows were traps, no follow-up — and told to write the file in one pass without running or revising it. The reply is committed unedited.

`10` transcript records · 2026-08-03 11:34 → 2026-08-03 11:35 UTC

---

### 🧑 Eyal

Home Assignment — Junior Software Engineer

Scenario: Our system extracts structured data from scanned invoices using OCR. The extraction step isn't perfect — it sometimes garbles characters, misses fields, or produces inconsistent formats. Your task is to write a small Python module that takes this raw, messy output and turns it into clean, validated data.

The Data. Below is a real-looking sample of what comes out of the extraction step. Use exactly this data to build and test your solution. (Note: "95O.5" contains a capital letter O where a zero should be — a common OCR misread.)

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

Your Task. Write a Python module (a single script is fine) that exposes a function with this exact signature:

def process_records(raw_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Takes the raw records and returns (clean_records, flagged_records).
    Flagged records should also include a 'reason' field explaining why
    they were flagged.
    """

Within process_records, your solution should:
1. Normalize the amount field to a proper numeric value.
2. Normalize the date field.
3. Handle possible records duplication.
4. Flag records that look suspicious or invalid, along with a short reason for each flag.
5. Produce two outputs: a cleaned list of valid records, and a separate list of flagged records with reasons.

There's no single "correct" set of rules for what counts as suspicious — use your judgment.

---

Please write the implementation and save it to the file /home/user/OCR-Genpact-/naive_first_draft.py

Important constraints on how you work:
- Write the file in ONE pass. This is a first draft and it is being captured as-is.
- Do NOT run the code. Do NOT test it. Do NOT iterate on it or revise it after writing.
- Do NOT create any other files.
- Do NOT read any other files in the repository.
- Just write your implementation to that path and then stop and report that you're done.

### 🤖 Claude

**→ `Bash`**

```
test -f /home/user/OCR-Genpact-/naive_first_draft.py && echo EXISTS || echo NOTEXISTS
```

### 🧑 Eyal

**← result**

```
NOTEXISTS
```

### 🤖 Claude

Good, the file doesn't exist yet. Writing the first draft now in a single pass.

### 🤖 Claude

**→ `Write`**

```
/home/user/OCR-Genpact-/naive_first_draft.py
```

### 🧑 Eyal

**← result**

```
File created successfully at: /home/user/OCR-Genpact-/naive_first_draft.py (file state is current in your context — no need to Read it back)
```

### 🤖 Claude

Done. I wrote the implementation to `/home/user/OCR-Genpact-/naive_first_draft.py` in a single pass, per the constraints — no execution, no testing, no other files touched.

What it contains:
- `raw_records` — the sample data, copied exactly as given.
- `normalize_amount()` — strips `$`/commas/whitespace, fixes the OCR `O`→`0` misread, parses to float, flags negatives, missing values, and unparseable strings.
- `normalize_date()` — tries several `strptime` formats (`YYYY-MM-DD`, `MM/DD/YYYY`, `YYYY/MM/DD`, `Mon D, YYYY`, `Month D, YYYY`), returns ISO format on success, flags unparseable dates.
- `is_date_suspicious()` — flags dates before year 2000 or in the future (catches the `2019-01-10` case as suspicious, and would catch `2024-13-40` at the parse-failure stage since month 13/day 40 aren't valid).
- `process_records()` — the required entry point: dedupes by `invoice_id` (flagging repeats as duplicates), normalizes amount/date, flags missing vendor/invoice_id, and returns `(clean_records, flagged_records)` with a `reason` string joined from all applicable issues on each flagged record.
- A `__main__` block that prints both lists (not run by me, just included as a usage convenience for whoever runs the file next).

No other files were created or modified, and the script was not executed or read back.

---

_7 turns. Exported by `tools/export_chat.py`._
