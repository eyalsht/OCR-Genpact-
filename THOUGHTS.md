# Thoughts

## Assumptions

**What counts as a normal amount.** Positive, and at most 1,000,000. Zero and negatives are
flagged as *warnings* rather than errors, because `-450.00` is plausibly a credit note and
that is a human's call, not mine. The ceiling exists because a misplaced decimal point — a
classic OCR failure — always fails upward.

**What counts as a normal date.** Anything from the batch period. "Stale" is measured against
the latest date in the batch, not against `date.today()`. The obvious version of that rule
(`today - parsed > 730 days`) means this submission destroys itself as the calendar moves: run
it in 2027 and all eight sample rows are stale. Deriving the reference from the batch makes
the result stable forever and matches how invoices actually arrive. Its weakness, which I would
rather name than hide: if an entire batch is ancient, nothing inside it looks stale.

**Ambiguous formats.** `01/06/2024` is Jan 6 under US convention and Jun 1 under everyone
else's, and nothing in the string decides it. The batch does: INV-1001 is Jan 5, INV-1003 is
Jan 7, INV-1004 is Jan 8, and the IDs run in sequence, so the INV-1002 between them is Jan 6.
I took that reading and attached an `ambiguous_date` note naming the alternative. A note, not a
flag — the value is usable, only its provenance is uncertain.

**European separators are refused.** `1.200,00` is twelve hundred, but `1.200` alone reads
just as well as 1.2. I could have guessed from separator position; I would rather return
`AMOUNT_UNPARSEABLE` than silently turn 1200 into 1.2.

## Edge cases that surprised me, or that I had to handle deliberately

**`INV-1006`'s amount is `"  "`, not `""`.** Two literal spaces. `if amount == ""` misses it;
`if not amount.strip()` catches it. That one is easy once you look at the bytes, and invisible
if you don't.

**`INV-1005` fails twice.** A negative amount *and* an impossible date. This is the case that
decided the architecture: every validator runs and appends to a list, and nothing early-returns.
Reporting only the first problem sends someone round the loop twice.

**`N/A` must stay unreadable.** I checked deliberately that no key in the substitution map
matches `N` or `A`, so the repair layer cannot accidentally rescue it. That the map is
conservative rather than lucky is worth a test of its own.

**`2024-02-30` is the sharp one.** It is well-formed and impossible. `strptime` rejects it for
free — which is the argument against hand-rolling a regex date parser, since a shape check
would accept it.

**The one that changed the design: `INV-1OO1`.** It is not in the sample; I went looking for it.
Repairing a letter `O` inside an *identifier* would merge two distinct invoices and silently
delete a payable — the repair would corrupt the very key that dedupe runs on. So substitution
is scoped to the amount field alone, and identifiers and vendor names pass through untouched.
Mis-flagging costs someone five minutes; that would cost money.

I also changed a test partway through. I had asserted `INV-1OO1` should come out *clean*, and
writing the implementation showed I was conflating two things: it genuinely is a malformed
identifier and someone should look at it. What the test needs to guarantee is only that it is
never treated as a copy of `INV-1001`. That correction is its own commit.

## How I used AI

**A first draft to argue with.** I asked an AI for an implementation from a cold start, given
only the assignment text and nothing else, and committed the reply unedited as
`naive_first_draft.py` before writing a line of my own. That ordering was the point — it is
only evidence if it comes first.

**It was better than I expected, and I want to say so plainly.** It handled the whitespace-only
amount, repaired `95O.5`, parsed all five date formats, and collected multiple reasons per
record. The failure I had assumed I would find — only the first reason surviving — was not
there. Inventing one would have collapsed the moment anyone asked about it.

**What I actually found, by running it.** Its real defects are all silent miscalculations,
which is worse than crashing. `(450.00)` comes back as **+450** — the parentheses are stripped
as punctuation and a credit note becomes a payable. `€1.200,00` comes back as **1.2**. `1O0O.OO`
gets four substitutions and returns `1000.00` with no record that anything changed, because the
map is applied unconditionally as a first pass rather than as a fallback. `N0NE` becomes a real
`0.00`. A non-string amount crashes it outright. And its dedupe only remembers IDs from records
that came out clean, so a duplicate of an already-flagged invoice sails through as new.

Those aren't opinions — each one is a test in `tests/test_naive_regression.py` that runs both
implementations side by side, alongside two tests recording what the draft got right.

**Where I pushed back.** Its freshness rule is `year < 2000 or date > datetime.now()` — two
wall-clock dependencies and an arbitrary cliff. I replaced it with a batch-relative reference.
I also rejected putting an LLM anywhere in the runtime path: the same invoices must produce the
same flags on every run, a fresh clone has to work with no API key, and every flag has to trace
to one named constant and one function. "The model decided" is not a reason a finance team can
act on.

**Where AI earned its place.** Research (the confusion-pair sourcing in `docs/RESEARCH.md`),
the first draft, and the tooling *around* the module — the figure generator and the table
renderer. The module itself is a pure deterministic function. Full detail in `docs/ai-log.md`.
