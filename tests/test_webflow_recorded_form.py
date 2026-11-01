"""Verify panel mappings against the captured browser DOM and both filled-job exports."""
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from autohub.core.webflow_fields import HARDWARE_FIELDS
from autohub.services.WebFlow.HardwareFields import _FIELD_PANELS, _FIELDS

_ROOT = Path(__file__).resolve().parents[1]
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class RecordedPanels(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.panels = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        panel = self.stack[-1]["panel"] if self.stack else None
        if tag == "app-uigroupbox":
            panel = {"title": "", "labels": set(), "buttons": set()}
            self.panels.append(panel)
        if tag not in _VOID_TAGS:
            self.stack.append({"tag": tag, "attrs": attrs, "text": [], "panel": panel})

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"].append(data)

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i]["tag"] == tag), None)
        if index is None:
            return
        frame = self.stack[index]
        del self.stack[index:]
        panel = frame["panel"]
        if panel is None:
            return
        text = " ".join("".join(frame["text"]).split())
        classes = frame["attrs"].get("class", "").split()
        if tag == "span" and "groupbox-title" in classes:
            panel["title"] = text
        if tag == "div" and "control-label" in classes:
            panel["labels"].add(text)
        if tag == "span" and "p-button-label" in classes:
            panel["buttons"].add(text)


@pytest.fixture(scope="module")
def recorded_panels():
    trace = _ROOT / "logs/webflow_trace/20261030_161609"
    capture = next(trace.glob("037_*Hardware_part_number*.html"))
    parser = RecordedPanels()
    parser.feed(capture.read_text(encoding="utf-8"))
    return {panel["title"]: panel["labels"] for panel in parser.panels}


@pytest.mark.parametrize("column,key,label,kind", HARDWARE_FIELDS)
def test_field_exists_in_its_actual_recorded_panel(recorded_panels, column, key, label, kind):
    assert label in recorded_panels[_FIELD_PANELS[key]]
    assert label not in recorded_panels["Hardware/Plant information"]


def test_race_import_button_is_in_recorded_classification_panel():
    capture = next((_ROOT / "logs/webflow_trace/20261030_161609").glob("037_*Hardware_part_number*.html"))
    parser = RecordedPanels()
    parser.feed(capture.read_text(encoding="utf-8"))
    panel = next(panel for panel in parser.panels if panel["title"] == "Classification")
    assert "Import from Race" in panel["buttons"]


@pytest.mark.parametrize("key", ["change_engineer", "cost_allocation", "change_reason", "ecr_notes"])
def test_configured_ecr_field_matches_recorded_panel(recorded_panels, key):
    label, _kind = _FIELDS[key]
    assert label in recorded_panels[_FIELD_PANELS[key]]
    assert _FIELD_PANELS[key] == "ECR Information"


@pytest.mark.parametrize("sample", ["WF225949_export (1).xml", "WF225950_export (1).xml"])
def test_filled_exports_confirm_labels_and_control_types(sample):
    fields = ET.parse(_ROOT / "datas/WebFlowXmlSample" / sample).getroot().find("Fields")
    by_label = {field.get("Description", "").strip(): field for field in fields}
    for _, _, label, kind in HARDWARE_FIELDS:
        field = by_label[label]
        assert field.get("Type") == ("StringList" if kind == "multi" else "String")
