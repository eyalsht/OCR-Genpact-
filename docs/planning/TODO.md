# TODO — Invoice OCR Cleaner

Ordered for `git log` to read as a story. Each TDD pair is **two commits**: the failing test,
then the code that passes it. That history is graded evidence — it's the only proof that the
tests came first.

`(P0)` ship-blocker · `(P1)` strong differentiator · `(P2)` cut without regret

---

## Phase 0 — Scaffold (~15 min)

- [ ] (P0) `git init`; first commit is empty scaffold only — **no logic yet**
- [ ] (P0) `pyproject.toml`: `pytest`, `ruff`. Nothing else. Zero runtime dependencies is a
      selling point — say so in the README.
- [ ] (P0) `.gitignore` — `__pycache__/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`
- [ ] (P0) `sample_data.py` with `RAW_RECORDS` copied **byte-for-byte** from the brief.
      Verify `95O.5` still has the capital O after paste. This is the one place a silent
      typo destroys the whole submission.
- [ ] (P0) `ruff` config: line-length 100, rules `E,F,W,I,N,UP,B,C4,SIM`. No `--strict` typing.
- [ ] `chore: scaffold project with sample data and tooling`

---

## Phase 1 — Capture the naive baseline FIRST (~15 min)

Do this **before** writing your own implementation. The value is entirely in it being genuine.

- [ ] (P1) Open a fresh AI chat. Paste the assignment. Ask for an implementation, nothing more.
- [ ] (P1) Save the reply verbatim as `naive_first_draft.py`. Do not fix it. Do not touch it again.
- [ ] (P1) Run it against the 8 rows. Record the actual output.
- [ ] (P1) Note precisely where it fails. Expected, based on how these drafts usually go:
      - only the first reason survives on row 5
      - `" "` on row 6 slips through as `0.0` or crashes
      - `95O.5` is dropped rather than repaired
      - `date.today()` used directly → stale logic is non-deterministic
- [ ] (P1) If the draft is actually *good* — say so honestly in THOUGHTS.md and pivot the
      section to what you still changed and why. A fabricated failure is worse than no
      failure, and it collapses the moment they ask about it in the interview.
- [ ] `docs: preserve unmodified AI first draft as baseline`

---

## Phase 2 — TDD cycles (~70 min)

Four cycles. Run `pytest` after every single step and watch it go red before it goes green.

### Cycle 1 — `normalize_amount`

- [ ] (P0) RED — `tests/test_amount.py`, parametrized:
      `"$1,200.00"→1200.00` · `"2,340"→2340.00` · `"3200.00"→3200.00` · `"-450.00"→-450.00`
      · `"95O.5"→950.50` + repair recorded · `"N/A"→None` · `" "→None` · `""→None`
      · `"(450.00)"→-450.00` · `"1O0O.OO"→None` (too many substitutions — rejected)
- [ ] (P0) RED — **repair is scoped to amounts.** `normalize_vendor("Beta LLC")` and the
      invoice-id path must pass through with zero substitutions. See ADR-2 Constraint B.
- [ ] (P0) `test: amount normalization incl. OCR digit substitution`
- [ ] (P0) GREEN — implement. Order: strip → null-token check → symbol/separator strip →
      paren-negative → `Decimal` → on failure, repair map → retry → quantize.
- [ ] (P0) GREEN — the repair map is reachable **only** from the amount path. If it's a
      module-level helper that any field can call, that's the bug — keep the call site single.
- [ ] (P0) `feat: normalize amounts with conservative OCR repair`

### Cycle 2 — `normalize_date`

- [ ] (P0) RED — all five sample formats + `"2024-13-40"→None` + `"2024-02-30"→None`
- [ ] (P0) RED — assert `"01/06/2024"` returns Jan 6 **and** carries an `ambiguous_date` note.
      One test, two assertions — the note is the whole point.
- [ ] (P0) `test: date parsing across five formats, incl. ambiguity detection`
- [ ] (P0) GREEN — ordered `strptime` attempts per ADR-3. Do **not** hand-roll a regex parser;
      `strptime` rejecting Feb 30 for free is a feature you'd lose.
- [ ] (P0) `feat: parse dates with format precedence and ambiguity notes`

### Cycle 3 — `deduplicate`

- [ ] (P0) RED — exact dup keeps first, flags second with the source index
- [ ] (P0) RED — same id + different amount → `DUPLICATE_CONFLICT`, not `DUPLICATE_EXACT`
- [ ] (P0) RED — dedupe happens post-normalization: `"$1,200.00"` and `"1200"` on the same id
      must collide. This test is the reason ADR-7 exists.
- [ ] (P0) RED — **`INV-1OO1` must NOT collide with `INV-1001`.** If OCR repair ever leaks into
      the identifier, two distinct invoices silently merge into one. This is the highest-value
      test in the suite: it's the only one guarding against *losing money*, not just
      mis-flagging it.
- [ ] (P0) `test: duplicate detection on normalized values`
- [ ] (P0) GREEN — implement
- [ ] (P0) `feat: flag duplicates without discarding records`

### Cycle 4 — `process_records` end-to-end

- [ ] (P0) RED — `len(clean) + len(flagged) == len(raw_records)`. Nothing vanishes. Assert
      this on every fixture set; it's the cheapest invariant in the suite and catches the
      most bugs.
- [ ] (P0) RED — row 5 returns **both** `AMOUNT_NON_POSITIVE` and `DATE_INVALID`
- [ ] (P0) RED — exact clean/flagged split for the 8 sample rows: `{1001, 1002}` clean
- [ ] (P0) RED — every flagged record has a non-empty `reason` string (literal brief requirement)
- [ ] (P0) RED — `reference_date=date(2024,2,1)` → 1007 stale; `reference_date=date(2019,6,1)`
      → 1007 no longer stale. Proves the injection actually works rather than just existing.
- [ ] (P0) `test: end-to-end pipeline against the provided sample`
- [ ] (P0) GREEN — wire it together
- [ ] (P0) `feat: implement process_records pipeline`

---

## Phase 3 — The regression that proves the point (~20 min)

- [ ] (P1) `tests/test_naive_regression.py` — import `naive_first_draft`, assert it produces
      the *wrong* answer on the rows Phase 1 identified, then assert `invoice_cleaner` gets
      them right. Same input, side by side.
- [ ] (P1) Guard with `pytest.importorskip` / try-except so a crashing draft doesn't take CI
      down with it — if the draft raises, that *is* the assertion.
- [ ] (P1) `test: regression suite documenting first-draft failures`
- [ ] (P0) `python -m pytest -q` → all green. `ruff check .` → zero.
- [ ] (P0) Run against the 8 rows. **Read the output line by line.** Does every flag make
      sense to you, out loud, in one sentence? If not, the rule is wrong — not the record.
- [ ] (P0) Extended fixtures pass too
- [ ] (P0) `test: extended fixture coverage for untriggered rules`

---

## Phase 4 — Docs (~40 min) — the actual differentiator

- [ ] (P1) `render_results.py` — imports the module, runs it, prints the README results table
      as markdown. Docs generated from a real run cannot drift. Mention in the README that
      the table is generated; that sentence *is* the proof you ran your code.
- [ ] (P0) `README.md` per `README_SPEC.md`
- [ ] (P0) `THOUGHTS.md` — assumptions, surprises, AI usage. Half a page as requested; going
      long here reads as padding.
- [ ] (P1) `docs/RESEARCH.md` — the confusion-pair sourcing and the tools you evaluated.
      **Open every source URL before committing this.** It carries your name; a citation you
      haven't read is a liability in the follow-up interview, not an asset.
- [ ] (P1) `docs/ai-log.md` — the transcript, lightly curated for readability. Keep the parts
      where you were wrong.
- [ ] (P1) `.github/workflows/ci.yml` — ruff + pytest on push. Wait for the green check, then
      add the badge. A broken badge is worse than no badge.
- [ ] `docs: README, thoughts, and AI log`

---

## Phase 5 — Optional polish (~20 min) — cut all of this without guilt

- [ ] (P2) Mermaid decision-flow diagram in the README (renders natively on GitHub)
- [ ] (P2) `--report` CLI flag printing an aligned terminal table
- [ ] (P2) One Hypothesis property test: any `Decimal` rendered with `$`/commas round-trips
- [ ] (P2) `pytest --cov` locally to find dead branches — report the number, don't gate on it

---

## Phase 6 — Agent-generated corpus (~45 min) — only if Phases 0–4 are fully done

Per ADR-8. **The hard rule: this produces test data, never verdicts.** The moment an LLM
decides whether a record is clean, the submission stops being deterministic and the whole
thing is worth less than the plain version.

- [ ] (P2) `generate_corpus.py` — LangGraph, three nodes:
      - `researcher` → confusion pairs + provenance comment per pair
      - `adversary` → mutate known-good invoices into OCR-damaged variants, emitting
        `(damaged_input, expected_output)` pairs
      - `verifier` → run `invoice_cleaner` over them, report unrecoverable mutations
- [ ] (P2) Output → `tests/fixtures/generated_corpus.py` as a plain committed Python literal.
      **Read it before committing.** The adversary will produce some cases whose "expected"
      value is wrong; those get deleted, not accommodated. Curating the output is the part
      that demonstrates judgment — accepting it wholesale demonstrates the opposite.
- [ ] (P2) Confirm `invoice_cleaner.py` imports nothing from this file. Check with
      `grep -r "langgraph\|generate_corpus" invoice_cleaner.py` → must be empty.
- [ ] (P2) Confirm CI still passes with no API key present in the environment
- [ ] (P2) `.env` in `.gitignore`; no key anywhere in the history
- [ ] (P2) README: one line only, under "what I'd do with more time." Do not lead with this.
      It's supporting evidence, not the headline — the headline is that the cleaner is a pure
      deterministic function.
- [ ] (P2) `test: add generated adversarial OCR corpus`

**Bail-out condition:** if this isn't working within ~45 minutes, delete the branch and ship
Phases 0–4. A half-finished agent in the repo is strictly worse than no agent.

---

## Honesty guardrails

Two failure modes here are unrecoverable in an interview, and both are tempting:

1. **Staging the AI failure.** They said "be honest here — this is genuinely part of what
   we're evaluating, not a trick." If your first draft was solid, the honest version
   ("it was mostly right; here's the one thing I disagreed with and why") is a *better*
   answer than a manufactured disaster.
2. **Retro-fitting the git history.** Don't write everything then split it into fake
   red/green commits. Interviewers who care about TDD read timestamps.

## Final check

```bash
ruff check . && python -m pytest -q && python render_results.py
```

- [ ] Fresh clone → `pip install -e ".[dev]"` → tests pass. Test this. Broken setup
      instructions are the most common way a good submission dies.
- [ ] Repo is public, or the reviewer's account has access
- [ ] Submit the **GitHub link only** — the brief says email submissions are not reviewed
