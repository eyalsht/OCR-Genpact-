# AI chat log

Deliverable #3 — the conversations behind this repository, in the order they happened.

| # | Chat | Where | Status |
|---|---|---|---|
| 1 | [Planning conversation](01-planning-chat.md) | claude.ai | ⚠️ transcript still to be added — its output is committed |
| 2 | [Build session](02-build-session.md) | Claude Code | ✅ full transcript, 128 KB |
| 3 | [Cold first-draft session](03-first-draft-session.md) | Claude Code sub-agent | ✅ full transcript |

[`../ai-log.md`](../ai-log.md) is the written summary: what I asked for, what came back, where I
disagreed, and the one place I was wrong. These files are the raw material behind it.

## How to read them

Chats 2 and 3 are exported straight from Claude Code's own session files by
[`../../tools/export_chat.py`](../../tools/export_chat.py):

```bash
python tools/export_chat.py ~/.claude/projects/<project>/<session>.jsonl \
    -o docs/ai-chat-log/02-build-session.md \
    -t "Chat 2 — Build session (Claude Code)"
```

They are close to verbatim, with three reductions, all made by that script rather than by hand:

- **Images are dropped.** Chart screenshots I looked at during review become `_[image]_`.
- **Long tool output is truncated**, with the number of trimmed lines recorded inline.
- **Harness scaffolding is stripped** — `<system-reminder>` blocks and similar wrappers that
  were injected around turns rather than written by anyone.

Nothing else is edited. The reasoning blocks are kept and folded into `<details>` elements —
including the passages where I got something wrong, which are the interesting ones.

## The parts worth skipping to

**Chat 3** is the shortest and the most load-bearing. It is the cold context that produced
[`../../naive_first_draft.py`](../../naive_first_draft.py): given only the assignment text, told
to write the file in one pass and not to run, test or revise it. That constraint is what makes
the comparison in [`../../tests/test_naive_regression.py`](../../tests/test_naive_regression.py)
mean anything.

**In chat 2**, four moments:

- The assignment PDF uses subset CID fonts, so the sample data could not simply be copied out.
  It took a custom ToUnicode pass to read `95O.5` and the two-space amount correctly — worth it,
  because a silent typo there would have invalidated everything downstream.
- A test I had written asserted the wrong thing, and writing the implementation is what showed
  it. The correction is its own commit.
- The first render of the rule-matrix chart came out **completely empty** — a tuple unpacked
  wrongly, so the membership test never matched. Only looking at the image caught it.
- `pip install -e ".[dev]"`, the first command in the README, **failed on a fresh clone**. My
  own environment had hidden it. Found by actually running the setup instructions rather than
  trusting them.

The last two are the honest argument for the reviewer's first criterion: both were invisible
until something was actually run and looked at.
