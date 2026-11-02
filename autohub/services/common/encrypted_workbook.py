"""Helpers for reading password-protected Office workbooks."""
from __future__ import annotations

import io

import msoffcrypto

DEFAULT_PASSWORD = "hondabosch"


def decrypt_workbook(path: str) -> io.BytesIO:
    """Decrypt a protected Office workbook in memory using AutoHub's shared password."""
    with open(path, "rb") as source:
        office_file = msoffcrypto.OfficeFile(source)
        office_file.load_key(password=DEFAULT_PASSWORD)
        decrypted = io.BytesIO()
        office_file.decrypt(decrypted)
    decrypted.seek(0)
    return decrypted
