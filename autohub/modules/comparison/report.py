"""Self-contained HTML report of the stored comparison result (no external resources)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape

_STYLE = """
body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#1f2933;background:#fff}
h1{margin:0 0 8px;font-size:26px}
h2{font-size:18px;margin:28px 0 8px}
.meta{color:#52606d;margin:2px 0}.meta b{color:#1f2933;display:inline-block;min-width:130px}
.summary{display:flex;gap:12px;margin:20px 0}
.card{border:1px solid #cbd2d9;border-radius:6px;padding:10px 18px;min-width:110px}
.card b{display:block;font-size:22px}
.card.match b{color:#1b7f3b}.card.deviation b{color:#b42318}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0}
.controls input,.controls select,.controls button{font:inherit;padding:5px 8px;border:1px solid #9aa5b1;border-radius:4px;background:#fff}
.controls input[type=search]{min-width:260px}
.controls button{cursor:pointer;background:#f0f4f8}
#count{color:#52606d;margin:4px 0 8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#243b53;color:#fff;text-align:left;padding:8px;position:sticky;top:0}
td{border-bottom:1px solid #e4e7eb;padding:6px 8px;vertical-align:top;word-break:break-word}
tbody tr:nth-child(even){background:#f7f9fb}
tr.match td.status{background:#e3f6e8;color:#1b7f3b;font-weight:600}
td.manual{font-style:italic;outline:2px dashed #7b61ff;outline-offset:-3px}
td.manual::after{content:" \u270E";font-style:normal}
tbody tr.deviation{background:#fff5f5}
tr.deviation td.status{background:#fde2e1;color:#b42318;font-weight:700}
td.target-deviation{background:#fde2e1;color:#b42318}
tr.hidden{display:none}
.report-info{break-inside:avoid;page-break-inside:avoid;margin-bottom:20px}
.report-info .grid{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:10px 16px;max-width:720px;align-items:center}
.report-info input{box-sizing:border-box;width:100%;font:inherit;color:inherit;padding:5px 8px;border:1px solid #9aa5b1;border-radius:4px;background:#fff}
.print-value{display:none;white-space:pre-wrap;overflow-wrap:anywhere}
.signature{margin-top:20px}
.signature .grid{gap:22px 16px}
.signature .line{border-bottom:1px solid #1f2933;height:20px}
@media print{
@page{margin:15mm}
body{margin:0;font-size:11pt;background:#fff}
.controls{display:none!important}
.report-info input{display:none;border:0;background:transparent}
.print-value{display:block;min-height:1em}
tr.hidden{display:table-row!important}
th{position:static}
thead{display:table-header-group}
tr{break-inside:avoid;page-break-inside:avoid}
table{font-size:10pt}
.card{box-shadow:none}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact;box-shadow:none!important}
}
""".strip()

_SCRIPT = """
(function(){
var info=Array.prototype.slice.call(document.querySelectorAll(".report-info input"));
function syncInfo(){info.forEach(function(input){document.getElementById(input.id+"-print").textContent=input.value;});}
info.forEach(function(input){input.addEventListener("input",syncInfo);input.addEventListener("change",syncInfo);});
window.addEventListener("beforeprint",syncInfo);
syncInfo();
var rows=Array.prototype.slice.call(document.querySelectorAll("#results tbody tr"));
var search=document.getElementById("search"),variant=document.getElementById("variant"),
status=document.getElementById("status"),dev=document.getElementById("deviations"),
count=document.getElementById("count");
function fill(select,index){var seen={};rows.forEach(function(r){seen[r.cells[index].textContent]=1;});
Object.keys(seen).sort().forEach(function(v){var o=document.createElement("option");o.value=o.textContent=v;select.appendChild(o);});}
if(variant)fill(variant,0);fill(status,__STATUS_COLUMN__);
function apply(){var q=search.value.toLowerCase(),shown=0;
rows.forEach(function(r){var ok=(!variant||!variant.value||r.cells[0].textContent===variant.value)
&&(!status.value||r.cells[__STATUS_COLUMN__].textContent===status.value)
&&(!dev.checked||r.classList.contains("deviation"))
&&(!q||r.textContent.toLowerCase().indexOf(q)>=0);
r.classList.toggle("hidden",!ok);if(ok)shown++;});
count.textContent="Showing "+shown+" of "+rows.length+" parameters";}
[search,variant,status,dev].forEach(function(e){if(e){e.addEventListener("input",apply);e.addEventListener("change",apply);}});
document.getElementById("clear").addEventListener("click",function(){search.value="";if(variant)variant.value="";status.value="";dev.checked=false;apply();});
apply();
})();
""".strip()


def _report_information(
    exported_at: datetime, reviewer: str, xml_files: tuple[str, ...] | None = None,
) -> str:
    fields = (
        ("report-date", "Date", f"{exported_at:%Y-%m-%d}"),
        ("report-time", "Time", f"{exported_at:%H:%M:%S}"),
        ("reviewed-by", "Reviewed by", reviewer),
        ("approved-by", "Approved by", ""),
    )
    if xml_files is not None:
        fields += (("base-xml", "Base XML filename", xml_files[0]),)
        fields += tuple(
            ("target-xml" if len(xml_files) == 2 else f"target-xml-{index}",
             "Target XML filename" if len(xml_files) == 2 else f"Target {index} XML filename", filename)
            for index, filename in enumerate(xml_files[1:], 1)
        )
    inputs = "".join(
        f'<label for="{key}">{label}:</label><div>'
        f'<input type="text" id="{key}" value="{escape(value)}">'
        f'<span class="print-value" id="{key}-print">{escape(value)}</span></div>'
        for key, label, value in fields
    )
    return (
        '<section class="report-info"><h2>Report Information / Review &amp; Approval</h2>'
        f'<div class="grid">{inputs}</div>'
        '<div class="signature"><div class="grid">'
        '<div>Reviewer Signature:</div><div class="line"></div>'
        '<div>Approver Signature:</div><div class="line"></div>'
        '</div></div></section>'
    )


def build_report(
    headers: Sequence[str], rows: Sequence[Sequence[str]], deviations: Sequence[bool], variants: Sequence[str],
    exported_at: datetime, calculated: Sequence[str] = (), reviewer: str = "",
    *, xml_files: tuple[str, ...] | None = None, target_statuses: Sequence[Sequence[str]] = (),
) -> str:
    deviation_count = sum(deviations)
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    status_column = headers.index("Status")
    title = "WebFlow XML Comparison Result" if xml_files is not None else "Comparison Result"
    variant_info = (
        f'<p class="meta"><b>Compared Variants:</b>({len(variants)}) {escape(", ".join(variants))}</p>'
        if xml_files is None else ""
    )
    variant_filter = (
        '<select id="variant"><option value="">All part numbers</option></select>'
        if xml_files is None else ""
    )
    calculated = list(calculated) + [""] * (len(rows) - len(calculated))
    target_summary = ""
    if xml_files is not None and len(xml_files) > 2:
        target_summary = "".join(
            f'<p class="meta"><b>Target {index + 1} ({escape(filename)}):</b> '
            f'Match: {matches} | Deviation: {len(rows) - matches}</p>'
            for index, filename in enumerate(xml_files[1:])
            for matches in [sum(statuses[index] == "MATCH" for statuses in target_statuses)]
        )

    def cell(column: int, value: str, original: str, statuses: Sequence[str]) -> str:
        if column != status_column:
            if xml_files is not None and 2 <= column < status_column and statuses:
                status = statuses[column - 2]
                return (
                    f'<td class="{"target-match" if status == "MATCH" else "target-deviation"}" '
                    f'data-status="{escape(status)}" title="Calculated: {escape(status)}">{escape(value)}</td>'
                )
            return f"<td>{escape(value)}</td>"
        note = (
            f' title="Calculated: {escape(original)} | Manually changed" data-calculated="{escape(original)}"'
            if original else ""
        )
        return f'<td class="status{" manual" if original else ""}"{note}>{escape(value)}</td>'

    body = "".join(
        f'<tr class="{"deviation" if deviation else "match"}">'
        + "".join(cell(column, value, original, target_statuses[index] if target_statuses else ())
                  for column, value in enumerate(row))
        + "</tr>"
        for index, (row, deviation, original) in enumerate(zip(rows, deviations, calculated))
    )
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{title}</title>"
        f"<style>{_STYLE}</style></head><body>"
        f"<h1>{title}</h1>"
        f'{_report_information(exported_at, reviewer, xml_files)}'
        f'{variant_info}'
        '<div class="summary">'
        f'<div class="card"><b>{len(rows)}</b>Total</div>'
        f'<div class="card match"><b>{len(rows) - deviation_count}</b>Match</div>'
        f'<div class="card deviation"><b>{deviation_count}</b>Deviation</div></div>'
        f'{target_summary}'
        '<div class="controls">'
        '<input type="search" id="search" placeholder="Search all columns...">'
        f'{variant_filter}'
        '<select id="status"><option value="">All statuses</option></select>'
        '<label><input type="checkbox" id="deviations"> Deviations only</label>'
        '<button type="button" id="clear">Clear Filters</button></div>'
        '<div id="count"></div>'
        f'<table id="results"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
        f'<script>{_SCRIPT.replace("__STATUS_COLUMN__", str(status_column))}</script></body></html>\n'
    )
