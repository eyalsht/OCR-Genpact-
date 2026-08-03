# PLAN — Invoice OCR Cleaner

> Home assignment, Junior Software Engineer. Target effort: 2.5–3h.
> **Scope discipline:** one flat module, one test package, three docs. No `src/` layout,
> no SDK layer, no config files, no coverage gate. Over-engineering reads *worse* than
> under-engineering on a task this size — the reviewer wants judgment, not scaffolding.

---

## 1. What is actually being graded

Their "What We're Evaluating" section names three things, and only one is about code:

| Their criterion | The artifact that proves it |
|---|---|
| "Whether you actually ran your code against the sample data" | README results table generated *from a real run*, not hand-typed |
| "Whether you questioned an AI-generated first draft" | `naive_first_draft.py` + a test that proves where it breaks |
| "Whether you can explain why a record is flagged, in your own words" | `THOUGHTS.md` + a `reason` code on every flagged record |

Everything below serves those three rows. If a task doesn't, cut it.

---

## 2. Repository layout

```
invoice-ocr-cleaner/
├── README.md                    ← the showpiece (see README_SPEC.md)
├── THOUGHTS.md                  ← deliverable #2
├── invoice_cleaner.py           ← the module (~180 lines, flat, no packages)
├── sample_data.py               ← the 8 given rows, verbatim + extended fixtures
├── naive_first_draft.py         ← the AI's untouched first attempt, preserved
├── render_results.py            ← regenerates README's results table from a live run
├── generate_corpus.py           ← OPTIONAL, dev-time only. Never imported by the module.
├── tests/
│   ├── test_amount.py
│   ├── test_date.py
│   ├── test_dedupe.py
│   ├── test_pipeline.py
│   └── test_naive_regression.py ← proves the first draft was wrong
├── docs/
│   ├── ai-log.md                ← deliverable #3
│   └── RESEARCH.md              ← sourced confusion-pair research, tools evaluated & rejected
├── .github/workflows/ci.yml
├── pyproject.toml
└── .gitignore
```

Flat on purpose. The brief literally says *"a single script is fine"* — beating that by a
little (module + tests + CI) is confident; beating it by a lot looks like you can't judge scope.

---

## 3. The eight rows, decoded

This table is the spec. Every row here becomes at least one test.

| # | `invoice_id` | Raw amount | Raw date | The trap |
|---|---|---|---|---|
| 0 | INV-1001 | `$1,200.00` | `2024-01-05` | Baseline. Currency symbol + thousands separator. |
| 1 | INV-1002 | `95O.5` | `01/06/2024` | OCR letter-for-digit **and** an ambiguous date. Two traps in one row. |
| 2 | INV-1003 | `N/A` | `2024-01-07` | Sentinel null string, not an empty string. |
| 3 | INV-1004 | `2,340` | `Jan 8, 2024` | Month-name date. Empty vendor. Amount is fine — the problem is elsewhere. |
| 4 | INV-1001 | `$1,200.00` | `2024-01-05` | Exact duplicate of row 0. |
| 5 | INV-1005 | `-450.00` | `2024-13-40` | **Two independent failures.** Naive code returns one reason and stops. |
| 6 | INV-1006 | `" "` | `2024/01/09` | Whitespace-only ≠ empty string. `if not amount` catches it; `if amount == ""` does not. |
| 7 | INV-1007 | `3200.00` | `2019-01-10` | Perfectly valid, but stale. Stale *relative to what?* → see ADR-4. |

**Expected verdict:** 2 clean (rows 0, 1) / 6 flagged. A 25% pass rate is a legitimate
result for OCR output and worth one honest sentence in `THOUGHTS.md` — resist the urge to
loosen the rules just to make the demo look prettier.

---

## 4. Architectural decisions

### ADR-1 — Keep the exact signature, extend with keyword-only args

The brief says *"this exact signature"*. So:

```python
def process_records(
    raw_records: list[dict],
    *,
    reference_date: date | None = None,
) -> tuple[list[dict], list[dict]]:
```

`process_records(raw_records)` still works identically. A keyword-only argument with a
default is a strict superset of the required contract. **Call this out explicitly in
THOUGHTS.md** — a reviewer skimming for "did they follow instructions" should find your
reasoning before they find the deviation.

### ADR-2 — OCR repair is a *fallback*, and is scoped to the amount field only

Two constraints, and the second is the one most implementations miss. Full sourcing in
`docs/RESEARCH.md`.

**Constraint A — fallback, never a first pass.** Applying `O→0` to every string mangles
legitimate text.

1. Try to parse the cleaned string as a number.
2. Only on failure, apply the substitution map and retry.
3. Only accept the repair if the result parses **and** ≤ 2 characters were substituted.
4. Always record what was changed in a `repairs` field.

Map (letter→digit, for numeric fields): `O→0  o→0  l→1  I→1  |→1  S→5  B→8  Z→2  G→6`

The `0/O` and `l/1/I` pairs are the documented core — they degrade first under blur because
the confusion is in the character's edge profile. The rest are second-tier.

Check the map against `"N/A"`: no key matches `N` or `A`, so nothing is substituted, so it
stays unparseable. Correct behaviour, and worth a test asserting exactly that — it proves the
repair layer is conservative rather than lucky.

**Constraint B — substitution direction is a property of the field, not the string.** In a
numeric field you want letter→digit. In a *text* field the correct direction is the inverse
(`0→O`, `1→I`), because there the digit is the misread. A single global map applied
everywhere is therefore wrong by construction.

The sharp consequence is for identifiers. Repairing `INV-1OO1` into `INV-1001` **silently
merges two different invoices** — the repair corrupts the key that dedupe runs on. The
standard guidance for OCR post-processing is to normalize every field a consumer expects as
numeric and leave identifiers and free-text alone, precisely because an identifier's odd
characters may be part of its canonical form.

**Rule: repair runs on `amount` only. `invoice_id` and `vendor` are passed through
untouched.** One test locks this in (`INV-1OO1` must NOT dedupe against `INV-1001`), and it's
one of the better sentences available for THOUGHTS.md — it reads as domain awareness rather
than string manipulation.

### ADR-3 — Date format precedence, and the `01/06/2024` problem

Try in order: `%Y-%m-%d`, `%m/%d/%Y`, `%d/%m/%Y`, `%Y/%m/%d`, `%b %d, %Y`, `%B %d, %Y`, `%d-%b-%Y`.

`01/06/2024` parses under *both* slash formats — Jan 6 and Jun 1 are both real dates. No
parser can resolve this from the string alone. But the batch can:

> INV-1001 = Jan 5 · INV-1003 = Jan 7 · INV-1004 = Jan 8

The IDs are sequential and the dates are monotonic, so INV-1002 is **Jan 6** — US format.
That's evidence from the data, not a coin flip, and it's the single best paragraph you can
put in `THOUGHTS.md`.

Implementation: pick US order, and when a value parses under both orders, attach an
`ambiguous_date` entry to the record's `notes`. Note ≠ flag — the record stays clean, but
the ambiguity is visible downstream.

### ADR-4 — Reference date is derived from the batch, not from the clock

The obvious implementation of "stale" is `date.today() - parsed > 730 days`. Two problems:
the test suite starts failing on a future calendar date, and **run this in 2026 and all
eight rows are stale** — the demo destroys itself.

Rule:

```
reference_date = explicit argument
              ↳ else: latest successfully-parsed date in the batch
              ↳ else: date.today()
```

Justification: invoices arrive in batches, and freshness is naturally relative to the batch
period. For this data the reference becomes 2024-01-09, so the 2024 rows are fresh and
INV-1007 (2019) is ~5 years stale. Deterministic forever.

**State the weakness too:** if an entire batch is ancient, nothing inside it looks stale.
That's an acceptable trade for a batch-oriented cleaner, and naming the flaw yourself is
worth more than pretending it isn't there. Tests pass `reference_date` explicitly regardless.

### ADR-5 — `Decimal` in, `float` out

Parse with `Decimal` (no binary artifacts on money), quantize to 2dp, emit `float` so the
output dicts stay JSON-serializable. Keep the original string in `amount_raw` so nothing is
destroyed. Three lines in THOUGHTS.md, not three paragraphs — this is a footnote, not a thesis.

### ADR-6 — Collect *all* reasons; never early-return

Row 5 has a bad amount and a bad date. Every validator runs and appends to a list; the
record is flagged if the list is non-empty. This is the specific behaviour most first drafts
get wrong, so it's the assertion `test_naive_regression.py` is built around.

### ADR-7 — Duplicates are flagged, not silently dropped

Dropping data without a trace is the wrong default in a finance pipeline. First occurrence
wins and stays clean; later occurrences move to `flagged` with the index of the row they
duplicate. Two distinct cases:

- `DUPLICATE_EXACT` — same id, same normalized content (row 4).
- `DUPLICATE_CONFLICT` — same id, *different* amount or date. Not in the sample data. Add
  it to the extended fixtures, because "same ID, different amount" is the case that actually
  hurts in production and noticing its absence from the sample is itself a signal.

Dedupe runs **after** normalization — otherwise `"$1,200.00"` and `"1200"` look like
different invoices.

### ADR-8 — No LLM or agent in the runtime path; agents generate test data instead

An agent pipeline (research → mutate → fix → verify) is an appealing fit for OCR repair and
a poor fit for *this deliverable*:

- **Non-deterministic.** The reviewer runs it twice and gets different flags. For a data
  cleaner that isn't a quirk, it's a disqualification.
- **Needs credentials.** Fresh clone fails, CI fails — and "did you actually run this" is
  their first stated criterion.
- **Inverts the rubric.** They want evidence you questioned AI output. Delegating the
  judgment to an agent answers the opposite question.
- An LLM call to decide whether `" "` is empty is not engineering.

But the agent structure is genuinely useful one layer back, at **dev time**, where its output
is a static committed artifact:

```
researcher → confusion pairs from literature ──┐
                                               ↓
adversary  → mutate clean invoices ──→ tests/fixtures/generated_corpus.py  (committed)
                                               ↓
verifier   → run parser over corpus ──→ report of unrecoverable mutations
```

The agent produces **test data, never verdicts**. `invoice_cleaner.py` stays a pure function
with zero runtime dependencies; the corpus is a checked-in Python literal that runs offline
forever. The agent session then becomes content for `docs/ai-log.md` — deliverable #3 — which
is the one place in this assignment where sophisticated AI tooling is explicitly rewarded.

Strictly optional (TODO Phase 5). The submission is complete and defensible without it.

---

## 5. Pipeline

```
raw record
    │
    ├─→ normalize_amount()  → value | None  + repairs[]
    ├─→ normalize_date()    → date  | None  + notes[]
    ├─→ normalize_vendor()  → str   | None
    │
    ↓
validate()  ── runs every rule, collects every reason ──┐
    │                                                    │
    ↓                                                    ↓
deduplicate()  ────────────────────────────────→  reasons[] non-empty?
    │                                                    │
    ↓                                              yes ──┴──→ flagged[]
  clean[]                                           no  ─────→ clean[]
```

## 6. Validation rules

| Code | Trigger | Severity | Hits row |
|---|---|---|---|
| `AMOUNT_MISSING` | empty, whitespace-only, or null-token (`N/A`, `-`, `none`) | error | 2, 6 |
| `AMOUNT_UNPARSEABLE` | non-empty but no numeric reading survives repair | error | — |
| `AMOUNT_NON_POSITIVE` | ≤ 0 — possibly a credit note, needs a human | warning | 5 |
| `AMOUNT_OUTLIER` | > 1,000,000 — misplaced decimal is a classic OCR failure | warning | — |
| `DATE_INVALID` | no format matches | error | 5 |
| `DATE_FUTURE` | later than reference date | warning | — |
| `DATE_STALE` | > 730 days before reference date | warning | 7 |
| `VENDOR_MISSING` | empty or whitespace-only | error | 3 |
| `INVOICE_ID_MALFORMED` | doesn't match `INV-\d+` | warning | — |
| `DUPLICATE_EXACT` | id + content already seen | error | 4 |
| `DUPLICATE_CONFLICT` | id seen, content differs | error | — |

Rows with no trigger in the sample (`AMOUNT_OUTLIER`, `DATE_FUTURE`, `DUPLICATE_CONFLICT`,
`INVOICE_ID_MALFORMED`) are exactly why extended fixtures exist. A rule with no test is a
rule you haven't verified.

Thresholds live in module-level constants (`STALE_DAYS = 730`, `OUTLIER_THRESHOLD = 1_000_000`),
not scattered magic numbers. No config file — that's a step too far for one module.

## 7. Output shape

```python
# clean record
{
    "invoice_id": "INV-1002",
    "amount": 950.5,
    "amount_raw": "95O.5",
    "date": "2024-01-06",           # ISO string, serializable
    "vendor": "Beta LLC",
    "repairs": ["ocr_substitution: 'O'→'0' at index 2"],
    "notes": ["ambiguous_date: also valid as 2024-06-01 under DD/MM"],
}

# flagged record — original fields preserved, plus:
{
    ...,
    "reason": "AMOUNT_NON_POSITIVE; DATE_INVALID",   # required by the brief
    "reasons": [                                      # structured, for machines
        {"code": "AMOUNT_NON_POSITIVE", "severity": "warning", "detail": "-450.00"},
        {"code": "DATE_INVALID",        "severity": "error",   "detail": "2024-13-40"},
    ],
}
```

The brief asks for *"a 'reason' field"* — singular. Ship that as a joined human-readable
string so the literal requirement is met, and carry the structured list alongside it.

## 8. Extended fixtures

The sample has 8 rows and leaves 4 rules untested. Add ~12 in `sample_data.py`, clearly
separated from the verbatim originals:

conflicting duplicate (same id, different amount) · future date · zero amount ·
`(450.00)` parenthesised negative · `1O0O.OO` (multi-substitution, should be rejected as
too-aggressive) · `12,00,000` (Indian grouping) · `€1.200,00` (European separators —
document as out of scope rather than half-supporting it) · missing `vendor` key entirely ·
`None` amount · unicode vendor · trailing-whitespace id · `2024-02-30` (well-formed but
impossible date).

Plus one for ADR-2 Constraint B: **`INV-1OO1` (letter O in the identifier)**, which must stay
distinct from `INV-1001` rather than being repaired into a false duplicate.

`2024-02-30` is the sharp one: `strptime` rejects it, so it lands in `DATE_INVALID` for free —
but only if you didn't write your own regex date parser. Worth a test to lock that in.

If Phase 5 runs, the generated corpus lands in `tests/fixtures/generated_corpus.py` as a
committed literal. It supplements these hand-written fixtures rather than replacing them —
hand-picked cases encode intent, generated cases encode volume.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Over-engineering past the 3h budget | Phases 4–5 in TODO.md are explicitly optional. Ship after Phase 3 if time runs out. |
| Repair map corrupts good data | Fallback-only + ≤2 substitutions + always logged. Test that `N/A` survives untouched. |
| Reviewer disagrees with a rule | Every rule is one constant and one function — trivially arguable in THOUGHTS.md. Disagreement is fine; unexplained choices are not. |
| AI-log looks staged | Capture it live. See the honesty note in TODO.md Phase 5. |
