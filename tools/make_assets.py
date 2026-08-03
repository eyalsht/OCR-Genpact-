"""Regenerate the images used by README.md.

Everything drawn here comes from calling ``invoice_cleaner`` and
``naive_first_draft`` for real, at build time. No figure in the README contains
a number that was typed in by hand -- if the code changes, the pictures change
with it or the script fails.

    pip install -e ".[assets]"
    python tools/make_assets.py

The outputs are committed, so a reviewer never has to run this.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.offsetbox import AnnotationBbox, HPacker, TextArea  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import naive_first_draft  # noqa: E402
from invoice_cleaner import (  # noqa: E402
    OCR_DIGIT_LOOKALIKES,
    RULE_MESSAGES,
    normalize_amount,
    process_records,
)
from sample_data import EXTENDED_RECORDS, RAW_RECORDS  # noqa: E402

ASSETS = REPO_ROOT / "docs" / "assets"

# --------------------------------------------------------------------------
# Palette
#
# Slots taken from a validated design-system palette rather than picked by eye.
# The three-colour severity set (blue / yellow / red) and the two-colour
# comparison set (blue / red) were both checked with a contrast-and-CVD
# validator in light and dark before anything was drawn: worst all-pairs
# colour-vision-deficiency separation is dE 19.8 light and 10.2 dark against a
# threshold of 8. Yellow sits below 3:1 on the light surface, which is why
# every cell that uses it also carries a text label.
# --------------------------------------------------------------------------

THEMES = {
    "light": {
        "page": "#f9f9f7",
        "surface": "#fcfcfb",
        "text": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "accent": "#2a78d6",
        "warning": "#eda100",
        "error": "#d03b3b",
        "empty": "#eeede8",
    },
    "dark": {
        "page": "#0d0d0d",
        "surface": "#1a1a19",
        "text": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "accent": "#3987e5",
        "warning": "#c98500",
        "error": "#d03b3b",
        "empty": "#242422",
    },
}

MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-{weight}.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono{dejavu}.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-{weight}.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "C:/Windows/Fonts/consola.ttf",
]


def load_mono(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """First monospace font that exists, so this degrades rather than crashes."""
    for template in MONO_CANDIDATES:
        path = template.format(
            weight="Bold" if bold else "Regular",
            dejavu="-Bold" if bold else "",
        )
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


# --------------------------------------------------------------------------
# Terminal-style GIF rendering
# --------------------------------------------------------------------------

SCALE = 2  # render at 2x and downsample, for clean glyph edges


class TerminalCard:
    """Draws a dark terminal window. Text is supplied as coloured spans."""

    def __init__(self, cols: int, rows: int, title: str, font_size: int = 15):
        self.theme = THEMES["dark"]
        self.font = load_mono(font_size * SCALE)
        self.bold = load_mono(font_size * SCALE, bold=True)
        self.char_w = self.font.getlength("M")
        self.line_h = math.ceil(font_size * SCALE * 1.65)
        self.pad = 22 * SCALE
        self.title_h = 34 * SCALE
        self.title = title
        self.width = math.ceil(self.pad * 2 + self.char_w * cols)
        self.height = self.pad * 2 + self.title_h + self.line_h * rows

    def blank(self) -> Image.Image:
        image = Image.new("RGB", (self.width, self.height), self.theme["page"])
        draw = ImageDraw.Draw(image)
        radius = 12 * SCALE

        draw.rounded_rectangle(
            [(0, 0), (self.width - 1, self.height - 1)],
            radius=radius,
            fill=self.theme["surface"],
            outline=self.theme["axis"],
            width=SCALE,
        )
        # Title bar: three dots and a caption.
        for index, colour in enumerate(("#e66767", "#c98500", "#199e70")):
            cx = self.pad + index * 15 * SCALE
            cy = self.title_h // 2 + 6 * SCALE
            r = 5 * SCALE
            draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=colour)
        small = load_mono(11 * SCALE)
        draw.text(
            (self.width // 2, self.title_h // 2 + 6 * SCALE),
            self.title,
            font=small,
            fill=self.theme["muted"],
            anchor="mm",
        )
        draw.line(
            [(SCALE, self.title_h + 12 * SCALE), (self.width - SCALE, self.title_h + 12 * SCALE)],
            fill=self.theme["grid"],
            width=SCALE,
        )
        return image

    def _origin(self, row: int) -> tuple[int, int]:
        return self.pad, self.pad + self.title_h + row * self.line_h

    def draw_spans(self, image: Image.Image, row: int, spans: list[tuple[str, str]]) -> None:
        draw = ImageDraw.Draw(image)
        x, y = self._origin(row)
        for text, colour_key in spans:
            bold = colour_key.endswith("!")
            key = colour_key.rstrip("!")
            font = self.bold if bold else self.font
            draw.text((x, y), text, font=font, fill=self.theme.get(key, key))
            x += self.char_w * len(text)

    def highlight(
        self, image: Image.Image, row: int, col: int, length: int, colour: str, char: str = ""
    ) -> None:
        """Box a run of characters, and optionally overprint replacement text."""
        draw = ImageDraw.Draw(image)
        x, y = self._origin(row)
        x0 = x + self.char_w * col
        box = [
            (x0 - 2 * SCALE, y - 3 * SCALE),
            (x0 + self.char_w * length + 2 * SCALE, y + self.line_h - 5 * SCALE),
        ]
        draw.rounded_rectangle(box, radius=3 * SCALE, fill=self.theme.get(colour, colour))
        if char:
            draw.text((x0, y), char, font=self.bold, fill=self.theme["surface"])

    def finish(self, image: Image.Image) -> Image.Image:
        return image.resize(
            (self.width // SCALE, self.height // SCALE), Image.LANCZOS
        )


def write_gif(path: Path, frames: list[Image.Image], durations: list[int]) -> None:
    """Quantize every frame against one shared palette, so the GIF stays small
    and does not shimmer between frames."""
    master = frames[0].quantize(colors=128, method=Image.MEDIANCUT)
    paletted = [frame.quantize(palette=master, dither=Image.NONE) for frame in frames]
    paletted[0].save(
        path,
        save_all=True,
        append_images=paletted[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=1,
    )
    print(f"  {path.relative_to(REPO_ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")


# --------------------------------------------------------------------------
# GIF 1: the OCR catch, and the OCR repair being refused
# --------------------------------------------------------------------------


def build_ocr_catch_gif() -> None:
    repaired = normalize_amount("95O.5")
    assert repaired.value is not None and repaired.repairs, "expected a repair here"

    card = TerminalCard(cols=64, rows=12, title="invoice_cleaner - OCR repair")
    frames: list[Image.Image] = []
    durations: list[int] = []

    def emit(image: Image.Image, ms: int) -> None:
        frames.append(card.finish(image))
        durations.append(ms)

    header = [
        ([("  amount field", "muted")], None),
        ([('  "95O.5"', "text!")], None),
    ]

    def base() -> Image.Image:
        image = card.blank()
        for row, (spans, _) in enumerate(header):
            card.draw_spans(image, row, spans)
        return image

    # --- Scene A: sweep the amount, find the letter, repair it -------------
    amount = '"95O.5"'
    for index in range(len(amount)):
        image = base()
        card.highlight(image, 1, 2 + index, 1, "accent", amount[index])
        card.draw_spans(image, 3, [("  scanning...", "muted")])
        emit(image, 120)

    image = base()
    card.highlight(image, 1, 4, 1, "error", "O")
    card.draw_spans(image, 3, [("  parse failed", "error!")])
    card.draw_spans(image, 4, [("  'O' is a letter, in a field that must be numeric", "secondary")])
    emit(image, 1100)

    image = base()
    card.highlight(image, 1, 4, 1, "warning", "O")
    card.draw_spans(image, 3, [("  parse failed", "error!")])
    card.draw_spans(image, 4, [("  'O' is a letter, in a field that must be numeric", "secondary")])
    card.draw_spans(image, 5, [("  trying substitution  O -> 0", "warning!")])
    emit(image, 900)

    image = base()
    card.highlight(image, 1, 4, 1, "accent", "0")
    card.draw_spans(image, 3, [("  1 substitution, limit is 2", "secondary")])
    card.draw_spans(image, 5, [("  amount     ", "muted"), ("950.50", "accent!")])
    card.draw_spans(image, 6, [("  amount_raw ", "muted"), ('"95O.5"', "secondary")])
    card.draw_spans(image, 7, [("  repairs    ", "muted"), (repaired.repairs[0], "secondary")])
    emit(image, 2400)

    # --- Scene B: same lookalike, inside an identifier this time -----------
    def base_b() -> Image.Image:
        image = card.blank()
        card.draw_spans(image, 0, [("  invoice_id field", "muted")])
        card.draw_spans(image, 1, [('  "INV-1OO1"', "text!")])
        return image

    identifier = '"INV-1OO1"'
    for index in range(len(identifier)):
        image = base_b()
        card.highlight(image, 1, 2 + index, 1, "accent", identifier[index])
        card.draw_spans(image, 3, [("  scanning...", "muted")])
        emit(image, 110)

    image = base_b()
    card.highlight(image, 1, 8, 2, "warning", "OO")
    card.draw_spans(image, 3, [("  same two letters found", "warning!")])
    emit(image, 1100)

    image = base_b()
    card.highlight(image, 1, 8, 2, "error", "OO")
    card.draw_spans(image, 3, [("  REPAIR REFUSED", "error!")])
    card.draw_spans(image, 4, [("  an identifier is not a numeric field", "secondary")])
    emit(image, 1600)

    # The payoff frame. In a monospace face INV-1001 and INV-1OO1 are all but
    # identical -- which is the whole problem -- so the two characters in
    # question are coloured apart here rather than left to the reader's eye.
    image = base_b()
    card.draw_spans(image, 3, [("  REPAIR REFUSED", "error!")])
    card.draw_spans(image, 4, [("  an identifier is not a numeric field", "secondary")])
    card.draw_spans(
        image,
        6,
        [
            ("  INV-1", "text!"),
            ("00", "accent!"),
            ("1", "text!"),
            ("   digit zeros", "muted"),
        ],
    )
    card.draw_spans(
        image,
        7,
        [
            ("  INV-1", "text!"),
            ("OO", "warning!"),
            ("1", "text!"),
            ("   letter Os", "muted"),
        ],
    )
    card.draw_spans(image, 9, [("  two different invoices, and both are kept", "secondary")])
    card.draw_spans(
        image, 10, [("  repairing the identifier would have merged them", "secondary")]
    )
    emit(image, 3400)

    write_gif(ASSETS / "ocr-catch.gif", frames, durations)


# --------------------------------------------------------------------------
# GIF 2: the whole batch running through
# --------------------------------------------------------------------------


def build_pipeline_gif() -> None:
    clean, flagged = process_records(RAW_RECORDS)
    verdicts = _verdicts_by_index(RAW_RECORDS, clean, flagged)

    card = TerminalCard(cols=90, rows=14, title="python invoice_cleaner.py")
    frames: list[Image.Image] = []
    durations: list[int] = []

    settled: list[list[tuple[str, str]]] = []

    def compose(pending: list[tuple[str, str]] | None = None) -> Image.Image:
        image = card.blank()
        card.draw_spans(image, 0, [("  $ python invoice_cleaner.py", "muted")])
        for offset, spans in enumerate(settled):
            card.draw_spans(image, 2 + offset, spans)
        if pending is not None:
            card.draw_spans(image, 2 + len(settled), pending)
        return image

    for index, record in enumerate(RAW_RECORDS):
        label = _record_spans(record)
        frames.append(card.finish(compose(label)))
        durations.append(260)

        verdict, codes = verdicts[index]
        if verdict == "CLEAN":
            row = [*label, ("  CLEAN", "accent!")]
        else:
            row = [*label, ("  FLAGGED  ", "error!"), (", ".join(codes), "warning")]
        settled.append(row)
        frames.append(card.finish(compose()))
        durations.append(520)

    summary = compose()
    card.draw_spans(
        summary,
        2 + len(settled) + 1,
        [
            (f"  {len(RAW_RECORDS)} in", "muted"),
            ("  ->  ", "muted"),
            (f"{len(clean)} clean", "accent!"),
            ("   ", "muted"),
            (f"{len(flagged)} flagged", "error!"),
            ("     nothing dropped", "muted"),
        ],
    )
    frames.append(card.finish(summary))
    durations.append(4000)

    write_gif(ASSETS / "pipeline.gif", frames, durations)


def _record_spans(record: dict) -> list[tuple[str, str]]:
    """One input row, with digit-lookalike letters picked out in amber.

    Without this, '95O.5' renders as a perfectly ordinary '950.5' -- which is
    precisely why the misread survives a human skim in the first place, but
    makes for a demo that shows nothing.
    """
    spans: list[tuple[str, str]] = [(f"  {record['invoice_id']:<9} ", "secondary")]
    literal = repr(record["amount"])
    buffer = ""
    for char in literal:
        if char in OCR_DIGIT_LOOKALIKES:
            if buffer:
                spans.append((buffer, "secondary"))
                buffer = ""
            spans.append((char, "warning!"))
        else:
            buffer += char
    if buffer:
        spans.append((buffer, "secondary"))
    spans.append((" " * max(1, 13 - len(literal)) + f"{record['date']:<12}", "secondary"))
    return spans


def _verdicts_by_index(
    raw_records: list[dict], clean: list[dict], flagged: list[dict]
) -> dict[int, tuple[str, list[str]]]:
    """Map each input row back to its verdict.

    Flagged records keep their original fields, and duplicates point at the
    index they duplicate, so rows can be matched back without the pipeline
    having to hand out identifiers it does not otherwise need.
    """
    verdicts: dict[int, tuple[str, list[str]]] = {}
    clean_queue, flagged_queue = list(clean), list(flagged)

    for index, record in enumerate(raw_records):
        head = clean_queue[0] if clean_queue else None
        is_clean = (
            head is not None
            and head["invoice_id"] == str(record.get("invoice_id", "")).strip()
            and head["amount_raw"] == record.get("amount")
        )
        if is_clean:
            clean_queue.pop(0)
            verdicts[index] = ("CLEAN", [])
        else:
            entry = flagged_queue.pop(0)
            verdicts[index] = ("FLAGGED", [reason["code"] for reason in entry["reasons"]])

    assert not clean_queue and not flagged_queue, "every record must be accounted for"
    return verdicts


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------


def _figure(theme: dict, width: float, height: float):
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(theme["page"])
    ax.set_facecolor(theme["surface"])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=theme["muted"], length=0, labelsize=9)
    return fig, ax


def _save(fig, name: str, mode: str, theme: dict) -> None:
    path = ASSETS / f"{name}-{mode}.png"
    fig.savefig(path, dpi=200, facecolor=theme["page"], bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"  {path.relative_to(REPO_ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")


def build_rule_matrix(mode: str) -> None:
    """Which rule fired on which of the eight sample rows."""
    theme = THEMES[mode]
    clean, flagged = process_records(RAW_RECORDS)
    verdicts = _verdicts_by_index(RAW_RECORDS, clean, flagged)
    severity = _severity_by_code(flagged)

    rules = sorted({code for _, codes in verdicts.values() for code in codes})
    columns = [f"{i}  {r['invoice_id']}" for i, r in enumerate(RAW_RECORDS)]

    fig, ax = _figure(theme, 10.5, 0.52 * len(rules) + 2.4)
    gap = 0.06

    for col, (_, (verdict, codes)) in enumerate(sorted(verdicts.items())):
        for row, rule in enumerate(rules):
            fired = rule in codes
            colour = theme["error"] if severity.get(rule) == "error" else theme["warning"]
            ax.add_patch(
                FancyBboxPatch(
                    (col + gap, row + gap),
                    1 - 2 * gap,
                    1 - 2 * gap,
                    boxstyle="round,pad=0,rounding_size=0.10",
                    linewidth=0,
                    facecolor=colour if fired else theme["empty"],
                )
            )
        ax.text(
            col + 0.5,
            -0.45,
            "CLEAN" if verdict == "CLEAN" else "FLAGGED",
            ha="center",
            va="center",
            fontsize=8.5,
            weight="bold",
            color=theme["accent"] if verdict == "CLEAN" else theme["error"],
        )

    ax.set_xlim(0, len(columns))
    ax.set_ylim(-0.95, len(rules))
    ax.set_xticks([i + 0.5 for i in range(len(columns))])
    ax.set_xticklabels(columns, fontsize=8.5, color=theme["secondary"])
    ax.set_yticks([i + 0.5 for i in range(len(rules))])
    ax.set_yticklabels(rules, fontsize=9, color=theme["secondary"], family="monospace")
    ax.invert_yaxis()

    ax.set_title(
        f"Every flag on the sample batch  —  {len(clean)} clean, {len(flagged)} flagged",
        color=theme["text"],
        fontsize=13,
        weight="bold",
        loc="left",
        pad=26,
    )
    ax.legend(
        handles=[
            Patch(facecolor=theme["error"], label="error"),
            Patch(facecolor=theme["warning"], label="warning"),
        ],
        loc="upper right",
        bbox_to_anchor=(1.0, 1.13),
        frameon=False,
        ncol=2,
        fontsize=9,
        labelcolor=theme["secondary"],
    )
    _save(fig, "rule-matrix", mode, theme)


def _severity_by_code(flagged: list[dict]) -> dict[str, str]:
    return {
        reason["code"]: reason["severity"] for record in flagged for reason in record["reasons"]
    }


def build_flag_counts(mode: str) -> None:
    """How often each rule fires across both fixture sets."""
    from datetime import date

    theme = THEMES[mode]
    counts: dict[str, int] = {}
    severity: dict[str, str] = {}
    total = 0

    for rows, reference in ((RAW_RECORDS, None), (EXTENDED_RECORDS, date(2024, 3, 11))):
        _, flagged = process_records(rows, reference_date=reference)
        total += len(rows)
        for record in flagged:
            for reason in record["reasons"]:
                counts[reason["code"]] = counts.get(reason["code"], 0) + 1
                severity[reason["code"]] = reason["severity"]

    ordered = sorted(counts.items(), key=lambda item: (item[1], item[0]))
    labels = [code for code, _ in ordered]
    values = [count for _, count in ordered]
    colours = [theme["error"] if severity[c] == "error" else theme["warning"] for c in labels]

    fig, ax = _figure(theme, 9.5, 0.40 * len(labels) + 2.1)
    ax.barh(labels, values, color=colours, height=0.5, zorder=3)
    for index, value in enumerate(values):
        ax.text(
            value + 0.08,
            index,
            str(value),
            va="center",
            fontsize=9.5,
            color=theme["secondary"],
            weight="bold",
        )

    ax.set_xlim(0, max(values) + 0.7)
    ax.xaxis.grid(True, color=theme["grid"], linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    ax.set_xticks(range(max(values) + 1))
    ax.tick_params(axis="y", labelsize=9)
    for label in ax.get_yticklabels():
        label.set_family("monospace")
        label.set_color(theme["secondary"])

    ax.set_title(
        f"Which rules actually fire  —  {total} records across both fixture sets",
        color=theme["text"],
        fontsize=13,
        weight="bold",
        loc="left",
        pad=24,
    )
    ax.legend(
        handles=[
            Patch(facecolor=theme["error"], label="error"),
            Patch(facecolor=theme["warning"], label="warning"),
        ],
        loc="lower right",
        frameon=False,
        ncol=2,
        fontsize=9,
        labelcolor=theme["secondary"],
    )

    missing = sorted(set(RULE_MESSAGES) - set(counts))
    if missing:
        fig.text(
            0.012,
            -0.01,
            "no fixture triggers " + " or ".join(missing) + "; both are covered by a "
            "dedicated test, and a coverage test fails if any rule loses its case.",
            fontsize=8,
            color=theme["muted"],
        )
    _save(fig, "flag-counts", mode, theme)


# The inputs the two implementations disagree about, each with the only answer
# that is defensible. ``None`` means "no reading of this is trustworthy", so
# refusing is the correct outcome and any number at all is the wrong one.
#
# An implementation is judged safe on a row if it produced the correct value or
# declined to answer. Returning a confident wrong number is the failure being
# measured; a crash is also a failure, but at least a loud one.
# Characters in {braces} are drawn in red: they are the ones doing the damage,
# and in a monospace face "1O0O.OO" is otherwise indistinguishable from a
# perfectly ordinary 1000.00 -- which is exactly why it slips through.
ADVERSARIAL = [
    ('"{(}450.00{)}"', "parentheses mean negative", -450.0),
    ('"\u20ac1{.}200{,}00"', "European separators", 1200.0),
    ('"1{O}0{O}.{O}{O}"', "four letter Os, one real zero", None),
    ('"9{X}5.5"', "character not in the repair map", None),
    ('"N{0}NE"', "a digit hiding inside a word", None),
    ("500", "an int, not a string", 500.0),
]


def _draft_outcome(raw, correct):
    try:
        value, _ = naive_first_draft.normalize_amount(raw)
    except Exception as exc:  # noqa: BLE001 - crashing is one of the outcomes
        return type(exc).__name__, False
    if value is None:
        return "refused", True
    return f"{value}", correct is not None and value == correct


def _module_outcome(raw, correct):
    result = normalize_amount(raw)
    if result.status != "ok":
        return "refused", True
    value = float(result.value)
    return f"{value}", correct is not None and value == correct


def _draw_marked_label(ax, x: float, y: float, marked: str, theme: dict, size: int = 10) -> None:
    """Right-aligned monospace label with {braced} characters picked out in red."""
    children = []
    for segment in re.split(r"(\{[^}]\})", marked):
        if not segment:
            continue
        highlighted = segment.startswith("{") and segment.endswith("}")
        children.append(
            TextArea(
                segment[1:-1] if highlighted else segment,
                textprops={
                    "color": theme["error"] if highlighted else theme["text"],
                    "family": "monospace",
                    "size": size,
                    "weight": "bold",
                },
            )
        )
    ax.add_artist(
        AnnotationBbox(
            HPacker(children=children, align="baseline", pad=0, sep=0),
            (x, y),
            xycoords="data",
            box_alignment=(1.0, 0.5),
            frameon=False,
            pad=0,
        )
    )


def build_comparison(mode: str) -> None:
    """The same six inputs through the AI's first draft and through this module."""
    theme = THEMES[mode]
    rows = []
    for marked, note, correct in ADVERSARIAL:
        plain = marked.replace("{", "").replace("}", "")
        raw = 500 if plain == "500" else plain.strip('"')
        rows.append(
            (marked, note, _draft_outcome(raw, correct), _module_outcome(raw, correct))
        )

    fig, ax = _figure(theme, 10.0, 0.62 * len(rows) + 2.2)
    gap = 0.05

    for index, (marked, note, draft, module) in enumerate(rows):
        y = len(rows) - index - 1
        _draw_marked_label(ax, -0.10, y + 0.62, marked, theme)
        ax.text(
            -0.08, y + 0.28, note, ha="right", va="center", fontsize=8.5, color=theme["muted"]
        )
        for col, (text, safe) in enumerate((draft, module)):
            colour = theme["accent"] if safe else theme["error"]
            ax.add_patch(
                FancyBboxPatch(
                    (col + gap, y + gap),
                    1 - 2 * gap,
                    0.9 - 2 * gap,
                    boxstyle="round,pad=0,rounding_size=0.08",
                    linewidth=0,
                    facecolor=colour,
                )
            )
            ax.text(
                col + 0.5,
                y + 0.45,
                text,
                ha="center",
                va="center",
                fontsize=10.5,
                family="monospace",
                weight="bold",
                color=theme["surface"] if mode == "light" else "#ffffff",
            )

    for col, heading in enumerate(("AI first draft", "this module")):
        ax.text(
            col + 0.5,
            len(rows) - 0.08,
            heading,
            ha="center",
            va="bottom",
            fontsize=10.5,
            weight="bold",
            color=theme["secondary"],
        )

    ax.set_xlim(-2.9, 2)
    ax.set_ylim(-0.25, len(rows) + 0.45)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        "Same input, both implementations  —  every red cell is a wrong number, silently returned",
        color=theme["text"],
        fontsize=12.5,
        weight="bold",
        loc="left",
        x=-0.0,
        pad=30,
    )
    ax.legend(
        handles=[
            Patch(facecolor=theme["accent"], label="correct, or safely refused"),
            Patch(facecolor=theme["error"], label="wrong, and reported as success"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.28, 1.10),
        frameon=False,
        ncol=2,
        fontsize=9,
        labelcolor=theme["secondary"],
    )
    _save(fig, "draft-comparison", mode, theme)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    print("rendering assets from a live run:")
    build_ocr_catch_gif()
    build_pipeline_gif()
    for mode in ("light", "dark"):
        build_rule_matrix(mode)
        build_flag_counts(mode)
        build_comparison(mode)


if __name__ == "__main__":
    main()
