"""Export a Claude Code session transcript to readable Markdown.

    python tools/export_chat.py <session.jsonl> -o docs/ai-chat-log/02-build-session.md

Claude Code stores each session as JSONL under ``~/.claude/projects/``. This
turns one of those into something a human can read: user turns, assistant
replies, the reasoning behind them, and every tool call in order.

Three things are deliberately reduced rather than reproduced verbatim, because
the raw file is several megabytes and most of that is not conversation:

* inline images (screenshots of the charts) become a one-line placeholder
* long tool output is truncated, with the number of dropped lines recorded
* editor/system scaffolding injected around user turns is stripped

Reasoning blocks are kept, folded into <details> so they do not drown the
thread. They are the part that shows the working, which is the point of
submitting a transcript at all.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

MAX_RESULT_LINES = 28
MAX_RESULT_CHARS = 2200
MAX_INPUT_CHARS = 1600

# Belt and braces. Nothing here is expected to appear in a transcript, but an
# exported conversation is a file that gets pushed to a public repository.
SECRET_PATTERNS = [
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,})"),
    re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{16,})"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"(?i)\b(bearer\s+[A-Za-z0-9._-]{20,})"),
]

# Scaffolding the harness wraps around user turns; not authored by anyone.
NOISE = [
    re.compile(r"<system-reminder>.*?</system-reminder>", re.S),
    re.compile(r"<local-command-caveat>.*?</local-command-caveat>", re.S),
    re.compile(r"<command-name>.*?</command-name>", re.S),
    re.compile(r"<command-message>.*?</command-message>", re.S),
    re.compile(r"<command-args>.*?</command-args>", re.S),
    re.compile(r"<local-command-stdout>.*?</local-command-stdout>", re.S),
]


def scrub(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def strip_noise(text: str) -> str:
    for pattern in NOISE:
        text = pattern.sub("", text)
    return text.strip()


def fence(text: str, language: str = "") -> str:
    """Fence a block, widening the fence if the body contains backticks."""
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{language}\n{text}\n{ticks}"


def clip(text: str, max_chars: int, max_lines: int | None = None) -> str:
    dropped_lines = 0
    if max_lines is not None:
        lines = text.splitlines()
        if len(lines) > max_lines:
            dropped_lines = len(lines) - max_lines
            text = "\n".join(lines[:max_lines])
    if len(text) > max_chars:
        text = text[:max_chars]
        dropped_lines = max(dropped_lines, 1)
    if dropped_lines:
        text += f"\n… [{dropped_lines} more line(s) trimmed for readability]"
    return text


def block_text(block: dict) -> str:
    """Flatten one content block to text, replacing images with a placeholder."""
    kind = block.get("type")
    if kind == "text":
        return block.get("text", "")
    if kind == "image":
        return "_[image]_"
    return ""


def render_tool_use(block: dict) -> str:
    name = block.get("name", "tool")
    payload = block.get("input", {}) or {}

    # The single most useful field, inlined, so the log reads as actions.
    for key in ("command", "file_path", "pattern", "query", "url", "prompt", "skill"):
        if key in payload:
            primary = str(payload[key])
            body = clip(primary, MAX_INPUT_CHARS, 40)
            return f"**→ `{name}`**\n\n{fence(body)}"

    body = clip(json.dumps(payload, indent=2, ensure_ascii=False), MAX_INPUT_CHARS, 30)
    return f"**→ `{name}`**\n\n{fence(body, 'json')}"


def render_tool_result(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "image":
                    parts.append("_[image returned — omitted from this export]_")
                else:
                    parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        text = "\n".join(p for p in parts if p)
    elif isinstance(content, str):
        text = content
    else:
        text = ""

    text = text.strip()
    if not text:
        return ""
    if text.startswith("_[image"):
        return f"**← result**  {text}"
    return "**← result**\n\n" + fence(clip(text, MAX_RESULT_CHARS, MAX_RESULT_LINES))


def load(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def convert(path: Path, title: str, intro: str, keep_thinking: bool) -> str:
    records = load(path)
    out: list[str] = [f"# {title}", ""]
    if intro:
        out += [intro, ""]

    stamps = [r.get("timestamp") for r in records if r.get("timestamp")]
    if stamps:
        first, last = min(stamps), max(stamps)
        out += [
            f"`{len(records)}` transcript records · "
            f"{first[:16].replace('T', ' ')} → {last[:16].replace('T', ' ')} UTC",
            "",
        ]
    out += ["---", ""]

    turn = 0
    for record in records:
        if record.get("type") not in ("user", "assistant"):
            continue
        message = record.get("message") or {}
        role = message.get("role")
        content = message.get("content")

        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            continue

        chunks: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")

            if kind == "thinking":
                if not keep_thinking:
                    continue
                thought = clip(block.get("thinking", "").strip(), 3000, 45)
                if thought:
                    chunks.append(
                        "<details><summary><i>reasoning</i></summary>\n\n"
                        + fence(thought)
                        + "\n\n</details>"
                    )
            elif kind == "tool_use":
                chunks.append(render_tool_use(block))
            elif kind == "tool_result":
                rendered = render_tool_result(block)
                if rendered:
                    chunks.append(rendered)
            else:
                text = block_text(block).strip()
                if role == "user":
                    text = strip_noise(text)
                if text:
                    chunks.append(text)

        chunks = [c for c in chunks if c.strip()]
        if not chunks:
            continue

        turn += 1
        label = "🧑 Eyal" if role == "user" else "🤖 Claude"
        out.append(f"### {label}")
        out.append("")
        out.extend("\n".join(chunks).split("\n"))
        out.append("")

    out += ["---", "", f"_{turn} turns. Exported by `tools/export_chat.py`._"]
    return scrub("\n".join(out)) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="path to a session .jsonl")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("-t", "--title", default="Claude Code session")
    parser.add_argument("-i", "--intro", default="")
    parser.add_argument(
        "--no-thinking", action="store_true", help="omit the model's reasoning blocks"
    )
    args = parser.parse_args()

    if not args.session.exists():
        print(f"no such session file: {args.session}")
        return 1

    markdown = convert(args.session, args.title, args.intro, keep_thinking=not args.no_thinking)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(
        f"{args.output}  ({len(markdown) / 1024:.0f} KB, "
        f"generated {datetime.now().strftime('%Y-%m-%d')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
