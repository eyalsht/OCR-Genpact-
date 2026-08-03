"""Generate the results table in README.md from an actual run.

    python render_results.py           # print the table and write it into README.md
    python render_results.py --check   # exit non-zero if README.md is out of date

The table lives between two HTML comment markers in the README. Because CI runs
``--check``, a README that disagrees with the code fails the build -- which is
the only way "these are the real results" stays true after the first week.
"""

from __future__ import annotations

import sys
from pathlib import Path

from invoice_cleaner import process_records
from sample_data import RAW_RECORDS

README = Path(__file__).parent / "README.md"
START = "<!-- results:start -->"
END = "<!-- results:end -->"


def verdicts_by_index(
    raw_records: list[dict], clean: list[dict], flagged: list[dict]
) -> dict[int, tuple[str, dict]]:
    """Match each input row back to the record the pipeline produced for it.

    Both output lists preserve input order, so walking them as queues recovers
    the mapping without ``process_records`` having to hand out row numbers it
    does not otherwise need.
    """
    verdicts: dict[int, tuple[str, dict]] = {}
    clean_queue, flagged_queue = list(clean), list(flagged)

    for index, record in enumerate(raw_records):
        head = clean_queue[0] if clean_queue else None
        if (
            head is not None
            and head["invoice_id"] == str(record.get("invoice_id", "")).strip()
            and head["amount_raw"] == record.get("amount")
        ):
            verdicts[index] = ("clean", clean_queue.pop(0))
        else:
            verdicts[index] = ("flagged", flagged_queue.pop(0))

    assert not clean_queue and not flagged_queue, "every record must be accounted for"
    return verdicts


def render_table() -> str:
    clean, flagged = process_records(RAW_RECORDS)
    verdicts = verdicts_by_index(RAW_RECORDS, clean, flagged)

    lines = [
        "| # | `invoice_id` | raw `amount` | raw `date` | verdict | what happened |",
        "|---|---|---|---|---|---|",
    ]

    for index, record in enumerate(RAW_RECORDS):
        state, result = verdicts[index]
        raw_amount = f"`{record['amount']!r}`"
        raw_date = f"`{record['date']}`"

        if state == "clean":
            detail = f"`{result['amount']:.2f}` · `{result['date']}`"
            extras = [note.split(":")[0] for note in result["repairs"] + result["notes"]]
            if extras:
                detail += "  — " + ", ".join(f"_{extra}_" for extra in extras)
            verdict = "**clean**"
        else:
            detail = "<br>".join(
                f"`{reason['code']}` — {reason['message']}" for reason in result["reasons"]
            )
            verdict = "flagged"

        lines.append(
            f"| {index} | `{record['invoice_id']}` | {raw_amount} | {raw_date} "
            f"| {verdict} | {detail} |"
        )

    summary = (
        f"\n**{len(RAW_RECORDS)} records in — {len(clean)} clean, {len(flagged)} flagged.** "
        "Nothing is dropped: every input row appears in exactly one of the two lists.\n"
    )
    return "\n".join(lines) + "\n" + summary


def main() -> int:
    table = render_table()
    check = "--check" in sys.argv

    if not README.exists():
        print(table)
        return 0

    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print(table)
        return 0

    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    updated = f"{head}{START}\n{table}\n{END}{tail}"

    if check:
        if updated != text:
            print("README.md results table is out of date. Run: python render_results.py")
            return 1
        print("README.md results table matches a live run.")
        return 0

    README.write_text(updated, encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
