# Research — OCR error patterns and tool selection

Background reading behind the design choices in `invoice_cleaner.py`. Written before the
repair map was finalised, so the map is sourced rather than guessed.

---

## 1. The formal model

What this module does has a name in the literature: **confusion-matrix-based post-OCR
correction**. The standard framing assumes OCR errors arise from character insertions,
deletions and substitutions, and models them with a noisy channel plus a probabilistic
confusion matrix over character substitutions.

A confusion matrix is a table where rows are the true characters and columns are the engine's
guesses, with each cell holding the probability of that misread. Production OCR engines ship
these — Tesseract's Latin-script language models include character mapping tables that encode
which characters are confusable and assign confidence scores to candidate substitutions.

**What this module implements is a deliberate simplification of that model:** a flat,
unweighted, one-directional map with no probabilities and no language model. That is the right
level for a single numeric field with a hard parse check as the acceptance test — a probability
distribution has nothing to contribute when the only question is "does the result parse as a
number." It would be the wrong level for free-text correction.

Sources:
- Noisy-channel + confusion matrix framing — https://arxiv.org/pdf/1604.06225
- Tesseract Latin-script confusion tables — https://deepwiki.com/tesseract-ocr/tessdata/3.2-latin-script-language-models

---

## 2. Which pairs actually matter

`0/O` and `l/1/I` are the primary pairs, and the reason is physical rather than statistical:
the distinguishing feature between those glyphs lives in the character's *edge profile*, which
is the first thing lost when a scan is blurred or thresholded. Analysis of depth-of-field blur
in document capture finds those two groups producing systematic substitution errors in
blur-affected regions specifically, while sharply-focused characters extract correctly.

This is also settled enough to be a product feature rather than a research topic: enterprise
capture software (Kofax / Tungsten Automation) exposes a configurable substitution table in
its UI, and its documentation calls out O-versus-0 and I-versus-1 by name, noting the feature
is particularly useful for **amount** fields.

The map used here, in priority order:

| Substitution | Tier | Notes |
|---|---|---|
| `O→0`, `o→0` | primary | The sample data's `95O.5` case |
| `l→1`, `I→1`, `|→1` | primary | Pipe included; some engines emit it for `1` |
| `S→5` | secondary | Shape-similar under low resolution |
| `B→8`, `Z→2`, `G→6` | secondary | Included for completeness; not exercised by the sample |

Sources:
- Blur-driven confusion-pair analysis — https://picturetext.org/blog/how-to-fix-mobile-phone-camera-ocr-errors-lens-distortion-depth-of-field-blur-and-motion-blur
- Commercial substitution tables — https://docshield.tungstenautomation.com/KTA/en_US/7.8.0-dpm5ap0jk8/help/TD/ProjectBuilder/150_ProjectBuilder/Recognition/t_SubstitutingCommonOCRMisreads.html

---

## 3. The finding that changed the design

**Substitution direction is a property of the field, not of the string.**

A benchmark study of post-OCR correction on retail bills lists its contextual substitutions as
`'0'→'O'`, `'1'→'I'`, `'S'→'5'` — applied in *non-numeric* contexts. That is the inverse of
what an amount field needs. In a numeric field the letter is the misread; in a text field the
digit is.

So a single global substitution map applied across every field is wrong by construction. It
will either corrupt text or fail to fix numbers, depending on which direction you picked.

The consequence for identifiers is worse than cosmetic. Guidance for numeral normalization in
invoice pipelines is explicit that normalization should run on every field a downstream
consumer expects as numeric — amounts, quantities, tax rates — while identifiers and free-text
fields are left alone, because an identifier's unusual characters may be part of its canonical
form and rewriting them changes the identifier.

Applied here: repairing `INV-1OO1` into `INV-1001` would **silently merge two distinct
invoices**, because dedupe keys on the identifier. The repair would corrupt the key it is
matched on. A cleaner that loses an invoice is worse than one that flags too much.

**Resulting rule:** OCR repair is reachable only from the amount-parsing path. `invoice_id`
and `vendor` pass through untouched. Locked in by `test_dedupe.py::test_ocr_lookalike_id_is_not_a_duplicate`.

The same source independently supports keeping `amount_raw` alongside the parsed value: storing
both the original string and the normalized number gives downstream audits a verification trail
at negligible cost.

Sources:
- Context-dependent substitution direction — https://arxiv.org/pdf/2604.25176
- Field-scoped normalization and identifier safety — https://invoicedataextraction.com/blog/python-ocr-library-arabic-table

---

## 4. Libraries evaluated

Every one of these was rejected. The module has zero runtime dependencies, which is a design
outcome, not an accident.

| Library | Considered for | Rejected because |
|---|---|---|
| `python-dateutil` | Multi-format date parsing | It resolves `01/06/2024` silently via a `dayfirst` flag. Surfacing that ambiguity is the entire point of the date layer here — see §5. Using it would hide the decision this module exists to make explicit. |
| `babel.numbers` | Locale-aware decimal parsing | Correct for genuine multi-locale input, but the sample is single-locale and it costs the zero-dependency property. Noted as the right answer if European separator formats enter scope. |
| `price-parser` | Currency string → number | Built for scraped e-commerce markup. No OCR repair layer, which is the actual hard part. |
| `rapidfuzz` | Fuzzy vendor dedup | Genuinely applicable — `Acme Corp` / `ACME Corp.` / `Acme Corporation` are one vendor. Deliberately deferred: fuzzy matching needs a tuned threshold, and an untuned threshold merges records that shouldn't merge. Listed under future work. |
| `invoice2data` | End-to-end invoice parsing | Out of scope by an order of magnitude. It runs OCR and template extraction; this module's input is already extracted. |

---

## 5. The `01/06/2024` decision

Neither format is detectable from the string — Jan 6 and Jun 1 are both real dates. The batch
resolves it where the string cannot:

| Invoice | Date |
|---|---|
| INV-1001 | 2024-01-05 |
| **INV-1002** | **`01/06/2024`** |
| INV-1003 | 2024-01-07 |
| INV-1004 | Jan 8, 2024 |

Identifiers are sequential and the surrounding dates are monotonically increasing by one day.
INV-1002 is 2024-01-06 — US `MM/DD/YYYY`.

This is an inference from the batch, not a coin flip, but it is still an inference. The record
therefore carries an `ambiguous_date` note recording the alternative reading, so a downstream
consumer can see that a judgment call was made rather than a fact established.

---

## 6. Why there is no LLM in the pipeline

An agent architecture (research pairs → mutate → repair → verify) is a natural fit for OCR
correction in general, and was prototyped separately. It is deliberately absent from this
module:

- **Determinism.** Two runs over the same invoices must produce the same flags. A data cleaner
  that returns different results on Tuesday is not a data cleaner.
- **No credentials to run.** `git clone && pytest` works offline. An API key in the critical
  path means the reviewer can't reproduce the results.
- **Cost and latency** are indefensible for eight records of string parsing.
- **Auditability.** Every flag traces to one named constant and one function. "The model
  decided" is not a reason a finance team can act on.

Where the agent structure *did* earn its place is one layer back, at development time:
generating an adversarial corpus of OCR-damaged records and their expected outputs, checked in
as a static fixture. The agent produced test data; it never produced verdicts. Its output was
reviewed by hand before committing, and the cases where its expected values were wrong were
deleted rather than accommodated.

See `docs/ai-log.md` for the session.

---

## 7. Known gaps

- European separator convention (`1.200,00`) is not supported. Detecting it reliably needs
  either a locale hint or a heuristic on separator position; guessing on money is worse than
  refusing. Currently lands in `AMOUNT_UNPARSEABLE`, which is the honest outcome.
- Vendor names are compared by exact normalized string. See `rapidfuzz` above.
- The confusion map is unweighted. A frequency-weighted matrix derived from the actual OCR
  engine in use would beat it, and would be the correct next step given access to that engine's
  output distribution.
