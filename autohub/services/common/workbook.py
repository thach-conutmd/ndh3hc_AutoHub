"""Opening (optionally password-protected) workbooks through Excel COM."""
import logging
import os
import tempfile
from typing import Any, Callable

import msoffcrypto
import win32com.client

from autohub.services.common.sheet_grid import LayoutError, SheetGrid, locate_and_parse

_logger = logging.getLogger(__name__)

#: Password tried for protected workbooks.
DEFAULT_PASSWORD = "hondabosch"


class ExcelDocument:
    """Shared open/close handling; subclasses implement `load_data` on top of `_parse`."""

    document_name = "document"
    #: Readers report problems through `last_error`; a document that gets written must raise instead.
    raise_on_open_error = False

    def __init__(self, file_path: str, password: str = DEFAULT_PASSWORD, quit: bool = False):
        self.file_path = file_path
        self.password = password
        self.quit = quit
        self.excel_app = None
        self.workbook = None
        self.decrypted_path = None
        self.last_error = ""

    def open(self) -> None:
        try:
            with open(self.file_path, "rb") as f:
                office_file = msoffcrypto.OfficeFile(f)
                if office_file.is_encrypted():
                    handle, self.decrypted_path = tempfile.mkstemp(suffix=".xlsx")
                    os.close(handle)
                    office_file.load_key(password=self.password)
                    with open(self.decrypted_path, "wb") as decrypted_file:
                        office_file.decrypt(decrypted_file)

            self.excel_app = win32com.client.DispatchEx("Excel.Application")
            self.workbook = self._open_workbook(self.decrypted_path or self.file_path)
        except Exception as error:
            self.last_error = f"Could not open {self.document_name} '{os.path.basename(self.file_path)}': {error}"
            _logger.error(self.last_error)
            self.close()
            if self.raise_on_open_error:
                raise RuntimeError(f"Error opening Excel file: {error}") from error

    def _open_workbook(self, path: str):
        """Open `path` in the running Excel; subclasses override to set options (must assign self.workbook)."""
        return self.excel_app.Workbooks.Open(path)

    def close(self) -> None:
        try:
            if self.workbook:
                self.workbook.Close(False)
        finally:
            self.workbook = None
            try:
                if self.excel_app and self.quit:
                    self.excel_app.Quit()
            finally:
                self.excel_app = None
                if self.decrypted_path and os.path.exists(self.decrypted_path):
                    os.remove(self.decrypted_path)
                self.decrypted_path = None

    def _parse(self, is_preferred_name: Callable[[str], bool], parse: Callable[[SheetGrid], Any]) -> Any:
        """Parsed data, or None with `last_error` set when the file cannot be read."""
        if not self.workbook:
            self.last_error = self.last_error or f"{self.document_name} workbook is not opened."
            return None
        name = os.path.basename(self.file_path)
        try:
            return locate_and_parse(self.workbook, is_preferred_name, parse)
        except LayoutError as error:
            self.last_error = f"'{name}' is not a readable {self.document_name}: {error}"
        except Exception as error:
            self.last_error = f"Could not read {self.document_name} '{name}': {error}"
        _logger.error(self.last_error)
        return None
