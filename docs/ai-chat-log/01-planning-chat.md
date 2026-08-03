# Chat 1 — Planning conversation (claude.ai)

> **⚠️ PLACEHOLDER — this transcript still needs to be pasted in.**
>
> This was the first conversation, held on claude.ai before any code existed. Its output is
> already committed (see *What this chat produced* below), but the conversation itself is not
> yet here.
>
> **To fill this in, do one of:**
>
> 1. **Share link** — open the conversation on claude.ai → *Share* → copy link, and replace
>    this whole block with it.
> 2. **Exported transcript** — copy the conversation text and paste it below the divider,
>    keeping the `### 🧑 Eyal` / `### 🤖 Claude` heading style used in
>    [`02-build-session.md`](02-build-session.md) so all three read the same way.
>
> The brief asks for "a shared link **or** exported transcript", so either is sufficient.
> Until then this file is the one incomplete part of deliverable #3.

---

## What this chat produced

Everything below is already committed, so the artifacts are reviewable even before the
transcript lands:

| Artifact | What it is |
|---|---|
| [`../planning/PLAN.md`](../planning/PLAN.md) | Architecture as ADRs, plus a decoded table of the trap in each of the eight sample rows |
| [`../planning/TODO.md`](../planning/TODO.md) | The ordered task list, including the honesty guardrails |
| [`../RESEARCH.md`](../RESEARCH.md) | Background reading on OCR confusion pairs, gathered before the substitution map was fixed |

## Why it mattered

The decision that shaped the whole module came out of this conversation rather than the build:
**substitution direction is a property of the field, not of the string.** In a numeric field the
letter is the misread; in a text field the digit is. That is what turned a vague "fix OCR
errors" idea into the specific rule that repair is reachable only from the amount parser — and
therefore that `INV-1OO1` must never be repaired into `INV-1001`, because doing so would merge
two distinct invoices and silently delete a payable.

It also set two things that survived unchanged into the final code: that duplicates are flagged
rather than dropped, and that "stale" is measured against the batch rather than the wall clock.

---

<!-- paste the transcript below this line -->
