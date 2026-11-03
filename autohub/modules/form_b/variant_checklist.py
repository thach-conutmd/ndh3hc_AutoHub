"""Form B columns on the shared variant-selection controls."""
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from autohub.core.checksums import normalize_crc32
from autohub.modules.creation.variant_checklist import VariantChecklist
from autohub.ui.link_label import LinkLabel

_logger = logging.getLogger(__name__)
_HEADERS = (
    "Select", "Part Number", "Family Name", "FSWID Project Version",
    "WebFlow Link", "SW Part Number", "CRC", "ECR Number",
)


class FormBVariantChecklist(VariantChecklist):
    def __init__(self):
        super().__init__()
        self._table.setHorizontalHeaderLabels(_HEADERS)

    def _apply_filter(self, *_args) -> None:
        super()._apply_filter(*_args)
        for row in range(self._table.rowCount()):
            self._table.takeItem(row, 4)
            self._table.removeCellWidget(row, 5)
            link = self._links.get(self._table.item(row, 1).text(), "")
            if link:
                label = LinkLabel(link, link)
                label.setAlignment(Qt.AlignCenter)
                self._table.setCellWidget(row, 4, label)
            software = self._table.takeItem(row, 6)
            if software is not None:
                self._table.setItem(row, 5, software)
        self.refresh_checksums()

    def refresh_checksums(self) -> None:
        variants = {variant["part_number"]: variant for variant in self._variants}
        for row in range(self._table.rowCount()):
            part = self._table.item(row, 1).text()
            value = variants[part].get("form_b", {}).get("BA")
            text = "-"
            if value is not None and str(value).strip().strip("*"):
                try:
                    text = normalize_crc32(value) or "-"
                except ValueError:
                    _logger.warning("%s: unavailable Master Sheet Container Checksum from Flow5: %r", part, value)
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 6, item)
        self._table.fit_columns()
