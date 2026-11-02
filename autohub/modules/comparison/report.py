"""Self-contained HTML report of the stored comparison result (no external resources)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape

_STYLE = """
body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#1f2933;background:#fff}
h1{margin:0 0 4px;font-size:26px}
.meta{color:#52606d;margin:2px 0}
.summary{display:flex;gap:12px;margin:20px 0}
.card{border:1px solid #cbd2d9;border-radius:6px;padding:10px 18px;min-width:110px}
.card b{display:block;font-size:22px}
.card.match b{color:#1b7f3b}.card.deviation b{color:#b42318}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#243b53;color:#fff;text-align:left;padding:8px;position:sticky;top:0}
td{border-bottom:1px solid #e4e7eb;padding:6px 8px;vertical-align:top;word-break:break-word}
tr.match td.status{background:#e3f6e8;color:#1b7f3b;font-weight:600}
td.manual{font-style:italic;outline:2px dashed #7b61ff;outline-offset:-3px}
tr.deviation{background:#fff5f5}
tr.deviation td.status{background:#fde2e1;color:#b42318;font-weight:700}
""".strip()


def build_report(
    headers: Sequence[str], rows: Sequence[Sequence[str]], deviations: Sequence[bool], variants: Sequence[str],
    exported_at: datetime, calculated: Sequence[str] = (),
) -> str:
    deviation_count = sum(deviations)
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    status_column = headers.index("Status")
    calculated = list(calculated) + [""] * (len(rows) - len(calculated))

    def cell(column: int, value: str, original: str) -> str:
        if column != status_column:
            return f"<td>{escape(value)}</td>"
        note = f' title="Calculated: {escape(original)} | Manually changed"' if original else ""
        return f'<td class="status{" manual" if original else ""}"{note}>{escape(value)}</td>'

    body = "".join(
        f'<tr class="{"deviation" if deviation else "match"}">'
        + "".join(cell(column, value, original) for column, value in enumerate(row))
        + "</tr>"
        for row, deviation, original in zip(rows, deviations, calculated)
    )
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        "<title>Comparison Result</title>"
        f"<style>{_STYLE}</style></head><body>"
        "<h1>Comparison Result</h1>"
        f'<p class="meta">Exported: {exported_at:%Y-%m-%d %H:%M:%S}</p>'
        f'<p class="meta">Compared variants ({len(variants)}): {escape(", ".join(variants))}</p>'
        '<div class="summary">'
        f'<div class="card"><b>{len(rows)}</b>Total</div>'
        f'<div class="card match"><b>{len(rows) - deviation_count}</b>Match</div>'
        f'<div class="card deviation"><b>{deviation_count}</b>Deviation</div></div>'
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></body></html>\n"
    )
