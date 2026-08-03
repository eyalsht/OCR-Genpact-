# Chat 1 — Planning conversation (claude.ai)

The first conversation, held on claude.ai before any code existed.

### 📎 [Read the full conversation →](https://claude.ai/share/9925bbb9-a404-4a08-b618-e92a6a23dea5)

`https://claude.ai/share/9925bbb9-a404-4a08-b618-e92a6a23dea5`

This one is a link rather than a committed transcript, because it happened in the claude.ai web
app rather than in Claude Code — there is no session file on disk to export the way
[chat 2](02-build-session.md) and [chat 3](03-first-draft-session.md) were. Its *output* is
committed in full, below.

---

## What this chat produced

Its output is committed in this repository, so the substance is reviewable without leaving it:

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

## What did not survive contact with the code

Worth reading the conversation for, since the plan and the repository disagree in two places:

- The plan predicted the AI first draft would report **only the first reason** on a row with two
  failures. It did not — that was the bug I most expected and it was not there. What the draft
  actually got wrong was subtler and worse: silent miscalculation.
- The plan sketched a LangGraph agent for generating an adversarial corpus. It was cut. Its own
  bail-out condition said a half-finished agent is worse than none, and it would have made CI
  depend on an API key.
