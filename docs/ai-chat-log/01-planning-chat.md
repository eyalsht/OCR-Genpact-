# Chat 1 — Planning conversation (claude.ai)

The first conversation, held on claude.ai before any code existed:

**https://claude.ai/chat/c5fee4d4-2d55-4000-87a5-9c443a5cb9e1**

> **⚠️ This is a private conversation URL, not a share link.**
>
> `claude.ai/chat/…` is the author's own address for a conversation — opening it while signed
> in as anyone else gives a login prompt, not the transcript. A public share link looks like
> `claude.ai/share/…` instead.
>
> **To make this reviewable, do one of:**
>
> 1. **Publish a share link** — open the conversation → *Share* → *Create public link*, then
>    replace the URL above with the `claude.ai/share/…` one it gives you.
> 2. **Paste the transcript** below the divider at the end of this file, keeping the
>    `### 🧑 Eyal` / `### 🤖 Claude` heading style used in
>    [`02-build-session.md`](02-build-session.md) so all three read the same way.
>
> Option 2 is the more durable of the two: a share link can be revoked, and the repository is
> the thing being submitted. Chats 2 and 3 are already committed in full, so doing the same
> here makes deliverable #3 self-contained.

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
