import re
from datetime import datetime

from autohub.modules.comparison.report import build_report

HEADERS = ("Part Number", "Parameter", "Master", "Base", "Target", "Status", "Comment")
ROWS = [
    ("P1", "General/Power", "93", "", "93", "MATCH", ""),
    ("P1", "General/Model", "<A>", "", "B", "MATCHES_BASE", "checked & ok"),
    ("P2", "General/Power", "90", "", "91", "VALUE_MISMATCH", ""),
]


def report(**kwargs):
    return build_report(HEADERS, ROWS, [False, False, True], ["P1", "P2"], datetime(2026, 11, 2, 9, 30, 5),
                        ["", "VALUE_MISMATCH", ""], **kwargs)


def test_header_summary_and_table_are_present():
    html = report(reviewer="A. Reviewer")
    for text in ("Comparison Result", "2026-11-02", "09:30:05", "A. Reviewer", "(2) P1, P2"):
        assert text in html
    assert "<b>3</b>Total" in html and "<b>2</b>Match" in html and "<b>1</b>Deviation" in html
    assert html.count("<tr class=") == 3 and html.count("<th>") == 7
    assert "&lt;A&gt;" in html and "checked &amp; ok" in html


def test_controls_script_and_count_are_embedded_without_external_resources():
    html = report()
    for marker in ('id="search"', 'id="variant"', 'id="status"', 'id="deviations"', 'id="clear"',
                   "Showing ", " parameters", "<script>"):
        assert marker in html
    assert not re.search(r"https?://|<link |src=", html)


def test_manual_review_is_marked_and_calculated_status_is_kept():
    html = report()
    assert html.count('data-calculated="VALUE_MISMATCH"') == 1
    assert "Calculated: VALUE_MISMATCH | Manually changed" in html


def test_signature_section_and_print_rules():
    html = report()
    assert "Review &amp; Approval" in html
    for label in ("Reviewed by:", "Approved by:"):
        assert label in html
    assert html.count("Signature:") == 2
    assert html.count("Review &amp; Approval") == 1
    assert html.index("Review &amp; Approval") < html.index("Compared Variants:") < html.index('<div class="summary">')
    for rule in ("@media print", "table-header-group", "break-inside:avoid", "print-color-adjust:exact",
                 ".controls{display:none!important}"):
        assert rule in html


def test_review_information_uses_initialized_inputs_and_print_values():
    html = report(reviewer='A. "Reviewer" <User>')
    for key, value in (
        ("report-date", "2026-11-02"), ("report-time", "09:30:05"),
        ("reviewed-by", 'A. &quot;Reviewer&quot; &lt;User&gt;'), ("approved-by", ""),
    ):
        assert f'<input type="text" id="{key}" value="{value}">' in html
        assert f'id="{key}-print">{value}</span>' in html
    assert "contenteditable" not in html
    assert 'window.addEventListener("beforeprint",syncInfo)' in html
    assert ".print-value{display:block;min-height:1em}" in html
    assert html.index("</section>") < html.index('<table id="results">')


def test_manual_xml_report_reuses_filters_reviews_and_print_layout():
    html = build_report(
        ("Parameter", "Base", "Target", "Status", "Comment"),
        [("General/Power", "93", "94", "MATCH", "approved <value>")],
        [False], [], datetime(2026, 11, 2, 9, 30, 5), ["VALUE_MISMATCH"], "Reviewer",
        xml_files=('base "one".xml', "target <two>.xml"),
    )
    assert "<title>WebFlow XML Comparison Result</title>" in html
    assert "<h1>WebFlow XML Comparison Result</h1>" in html
    assert "Base XML filename:" in html and "Target XML filename:" in html
    assert 'base &quot;one&quot;.xml' in html and "target &lt;two&gt;.xml" in html
    assert "Compared Variants:" not in html and 'id="variant"' not in html
    assert html.count("<th>") == 5 and "<th>Part Number</th>" not in html
    assert "fill(status,3)" in html and "r.cells[3].textContent" in html
    assert "__STATUS_COLUMN__" not in html
    assert 'data-calculated="VALUE_MISMATCH"' in html
    assert "approved &lt;value&gt;" in html
    assert "<b>1</b>Total" in html and "<b>1</b>Match" in html and "<b>0</b>Deviation" in html
    assert "Reviewer Signature:" in html and "@media print" in html
