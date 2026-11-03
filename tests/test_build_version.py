import re

import pytest

from autohub.config import APP_NAME, APP_VERSION
from build_version_info import four_part_version, version_info_text


def test_version_resource_matches_app_version():
    text = version_info_text()
    expected = ".".join(str(part) for part in four_part_version(APP_VERSION))

    assert f"StringStruct('FileVersion', '{expected}')" in text
    assert f"StringStruct('ProductVersion', '{expected}')" in text
    assert f"filevers=({expected.replace('.', ', ')})" in text


def test_version_resource_has_required_strings():
    text = version_info_text()

    assert f"StringStruct('ProductName', '{APP_NAME}')" in text
    assert f"StringStruct('InternalName', '{APP_NAME}')" in text
    assert "StringStruct('FileDescription', 'AutoHub - Container Automation Tool')" in text
    assert "StringStruct('OriginalFilename', 'AutoHub.exe')" in text
    assert re.search(r"StringStruct\('LegalCopyright', '.+'\)", text)


@pytest.mark.parametrize("bad", ["1.0", "v1.0.0", "1.0.0.0", "1.0.x"])
def test_invalid_app_version_is_rejected(bad):
    with pytest.raises(ValueError):
        four_part_version(bad)
