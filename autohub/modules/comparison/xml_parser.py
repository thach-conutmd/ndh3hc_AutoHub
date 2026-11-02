"""Parse WebFlow Export XML into stable Group/Name parameter paths (no I/O)."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from urllib.parse import quote, unquote
import xml.etree.ElementTree as ET

from autohub.core.settings_keys import DEFAULT_XML_COMPARISON_EXCLUSIONS, XML_COMPARISON_EXCLUSIONS_KEY

ParameterValue = str | tuple[str, ...] | None
ParameterMap = dict[str, ParameterValue]
MAX_XML_BYTES = 10 * 1024 * 1024
_MAX_PARAMETERS = 20000


def normalize_parameter_path(path: str) -> str:
    """Canonicalize path segments using the export parser's escaping convention."""
    return "/".join(quote(unquote(segment.strip()), safe=" _-().[]") for segment in path.strip().split("/"))


def comparison_exclusions(settings: Mapping) -> tuple[str, ...]:
    values = settings.get(XML_COMPARISON_EXCLUSIONS_KEY, DEFAULT_XML_COMPARISON_EXCLUSIONS)
    if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("XML comparison exclusions must be a list of non-empty path prefixes.")
    return tuple(dict.fromkeys(normalize_parameter_path(value) for value in values))


def comparison_parameters(
    parameters: Mapping[str, ParameterValue], exclusions: Sequence[str] = DEFAULT_XML_COMPARISON_EXCLUSIONS,
) -> ParameterMap:
    """Exclude non-comparable hierarchies from normalized parameter maps."""
    prefixes = tuple(normalize_parameter_path(prefix) for prefix in exclusions)
    return {path: value for path, value in parameters.items() if not normalize_parameter_path(path).startswith(prefixes)}


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _segment(text: str) -> str:
    return quote(text, safe=" _-().")


def parse_xml(data: bytes | str) -> ParameterMap:
    """Reject malformed/ambiguous exports; preserve blank values as None and lists as tuples."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > MAX_XML_BYTES:
        raise ValueError("WebFlow XML exceeds the 10 MiB limit.")
    markup = raw.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in markup or b"<!ENTITY" in markup:
        raise ValueError("WebFlow XML must not contain DTD or entity declarations.")
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, LookupError, ValueError) as error:
        raise ValueError(f"Invalid WebFlow XML: {error}") from error
    fields = [child for child in root if _tag(child) == "Fields"]
    if _tag(root) != "Job" or len(fields) != 1 or not len(fields[0]):
        raise ValueError("Expected a WebFlow Export XML document with Job/Fields/Field entries.")

    parameters: ParameterMap = {}
    field_paths: set[str] = set()

    def store(path: str, value: ParameterValue) -> None:
        if path in parameters:
            raise ValueError(f"Duplicate WebFlow XML parameter: {path}")
        if len(parameters) >= _MAX_PARAMETERS:
            raise ValueError("WebFlow XML contains too many parameters.")
        parameters[path] = value

    def flatten(element: ET.Element, path: str, depth: int = 0) -> None:
        if depth > 32:
            raise ValueError("WebFlow XML nesting is too deep.")
        if not len(element):
            store(path, (element.text or "").strip() or None)
            return
        counts = Counter(_tag(child) for child in element)
        seen: Counter[str] = Counter()
        for child in element:
            tag = _tag(child)
            seen[tag] += 1
            name = next(
                ((item.text or "").strip() for item in child if _tag(item) == "Name"),
                "",
            )
            suffix = f"[{_segment(name)}]" if name else f"[{seen[tag]}]" if counts[tag] > 1 else ""
            flatten(child, f"{path}/{_segment(tag)}{suffix}", depth + 1)

    for field in fields[0]:
        name = (field.get("Name") or "").strip()
        if _tag(field) != "Field" or not name:
            raise ValueError("Every WebFlow XML field must have a Name.")
        path = f"{_segment((field.get('Group') or '').strip())}/{_segment(name)}"
        if path in field_paths:
            raise ValueError(f"Duplicate WebFlow XML field: {path}")
        field_paths.add(path)
        kind = field.get("Type", "")
        if kind == "StringList":
            items = [child for child in field if _tag(child) == "Items"]
            if len(field) != 1 or len(items) != 1 or any(_tag(item) != "Item" or len(item) for item in items[0]):
                raise ValueError(f"Invalid WebFlow XML list: {path}")
            values = tuple(sorted({(item.text or "").strip() for item in items[0]} - {""}))
            store(path, values or None)
        elif kind == "Bool":
            value = (field.text or "").strip().casefold()
            if len(field) or value not in ("", "true", "false"):
                raise ValueError(f"Invalid WebFlow XML boolean: {path}")
            store(path, value or None)
        else:
            flatten(field, path)
    return parameters
