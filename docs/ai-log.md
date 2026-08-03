# AI log

Deliverable #3. What I asked AI for, what came back, and what I did about it.

Tools used: **Claude** — a planning conversation first, then Claude Code for the build.

---

## 1. Planning, before any code

The first conversation was about the *shape* of the problem rather than the solution. The
output is committed unedited in [`planning/`](planning/):

- [`planning/PLAN.md`](planning/PLAN.md) — the architectural decisions, written as ADRs, and the
  decoded table of what trap each of the eight sample rows contains.
- [`planning/TODO.md`](planning/TODO.md) — the ordered task list, including the honesty
  guardrails I then had to actually hold myself to.
- [`RESEARCH.md`](RESEARCH.md) — background reading on OCR confusion pairs, gathered before the
  substitution map was fixed, so the map is sourced rather than guessed.

The single most useful thing to come out of this stage was **ADR-2, constraint B**: that
substitution direction is a property of the *field*, not of the string. That is what turned a
generic "fix OCR errors" idea into the specific rule that repair is reachable only from the
amount parser, which is the thing the whole module is built around.

## 2. A first draft, deliberately obtained cold

I opened a fresh context and gave it **only the assignment text** — no plan, no hints about
which rows were traps, no follow-up questions — and asked for an implementation. The reply is
committed byte-for-byte as [`../naive_first_draft.py`](../naive_first_draft.py) and has never
been edited.

The ordering mattered: this was captured *before* I wrote any of my own implementation. It is
only evidence if it comes first, and the git history shows it does — the draft is the second
commit in the repository.

Then I ran it. Not read it — ran it, against the eight rows and then against inputs I chose to
probe it.

**What it got right**, which I want on the record because the comparison is otherwise a straw
man: the whitespace-only amount on INV-1006, the `95O.5` repair, all five date formats, and
collecting more than one reason per record. That last one is the classic first-draft bug and I
had fully expected to find it. It wasn't there.

**What it got wrong** — every one of these verified by running it, not by reading it:

| Input | Draft returns | Should be |
|---|---|---|
| `"(450.00)"` | `+450.0` | `-450.00` — a credit note became a payable |
| `"€1.200,00"` | `1.2` | ~1200 — wrong by a factor of a thousand |
| `"1O0O.OO"` | `1000.0` | refused — four substitutions, none recorded |
| `"9X5.5"` | `95.5` | refused — an unknown character was deleted |
| `"N0NE"` | `0.0` | refused — a null token became a real zero |
| `500` (an int) | `AttributeError` | `500.00` |

Plus a structural one: its dedupe only records identifiers from records that came out *clean*,
so a duplicate of an already-flagged invoice is never recognised.

The pattern is what makes it interesting. None of these raise anything. They are all confident
wrong numbers, and in a finance pipeline a wrong number nobody was told to check is worse than
a missing one. Every row of that table is now a test in
[`../tests/test_naive_regression.py`](../tests/test_naive_regression.py), running both
implementations over the same input.

## 3. Where I disagreed with the AI

**Wall-clock staleness.** The draft used `year < 2000 or date > datetime.now()`. Both halves
depend on when you run it, and the year-2000 cliff is arbitrary. I replaced it with a reference
date derived from the batch, so the answer is stable — and made the injection point explicit so
a test can prove it actually works rather than merely existing.

**Repair as a first pass.** The draft applies `O -> 0` unconditionally to every amount before
trying to parse. That is backwards: parse first, repair only on failure, cap the number of
substitutions, and record what changed.

**Stripping unknown characters.** `re.sub(r"[^0-9.\-]", "", text)` is how `9X5.5` becomes
`95.5`. Deleting a character you do not understand is a decision, and it should be a refusal.

**No LLM in the runtime path.** This was the biggest one, and it was a proposal I turned down
rather than one I was handed. An agent pipeline is a natural fit for OCR correction in general.
It is a bad fit here: two runs over the same invoices must produce the same flags, `git clone
&& pytest` has to work offline with no API key, and every flag has to trace to one named
constant and one function. "The model decided" is not a reason a finance team can act on.

## 4. Where AI genuinely earned its place

Research; the first draft to argue with; and the tooling *around* the module —
[`../tools/make_assets.py`](../tools/make_assets.py), which renders the README's figures from a
live run, and [`../render_results.py`](../render_results.py), which generates the results table
and is checked in CI so the README cannot drift from the code.

The module itself is a pure deterministic function with zero runtime dependencies. That
division is the point: AI did the scaffolding, the prose and the pictures. The judgment calls —
which field the repair may touch, what "stale" is measured against, whether an ambiguous date
is a flag or a note — are the parts I had to be able to defend, so they are the parts I made
myself.

## 5. One place I was wrong, kept in the history

I wrote a test asserting that `INV-1OO1` (letter O) should come out **clean**, on the reasoning
that the important thing was that it not be merged with `INV-1001`. Writing the implementation
showed I was conflating two separate things: it really is a malformed identifier, and someone
should look at it. Flagged-and-distinct is the correct outcome; only the *merge* is the failure
worth guarding against.

The correction is its own commit (`test: correct the lookalike-ID expectation`) rather than
being quietly folded into the implementation, because a test that teaches you something is the
part of TDD actually worth showing.

---

## Transcripts

Full conversations are in [`ai-chat-log/`](ai-chat-log/):

| # | Chat | Status |
|---|---|---|
| 1 | [Planning conversation](ai-chat-log/01-planning-chat.md) (claude.ai) | ✅ [public share link](https://claude.ai/share/9925bbb9-a404-4a08-b618-e92a6a23dea5); its output is committed in [`planning/`](planning/) and [`RESEARCH.md`](RESEARCH.md) |
| 2 | [Build session](ai-chat-log/02-build-session.md) (Claude Code) | ✅ full |
| 3 | [Cold first-draft session](ai-chat-log/03-first-draft-session.md) | ✅ full |

Chats 2 and 3 are exported from Claude Code's own session files by
[`../tools/export_chat.py`](../tools/export_chat.py) — images dropped, long tool output
truncated, harness scaffolding stripped, nothing else edited. Reasoning blocks are kept.

The git history is the other transcript: red-then-green commit pairs, including the test
correction above, the empty first render of the rule-matrix chart, and the fresh-clone install
that turned out to be broken.
