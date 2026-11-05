"""Parses <PARAMETER> blocks of a .cnt container file (legacy: Split_Auto/container_file.py)."""
import re

from autohub.services.HexdumpAnalyzer.exceptions import RangeNotFoundError

_NAME_RE = re.compile(r"<PARAMETER-NAME>(.*?)</PARAMETER-NAME>")
_VALUE_RE = re.compile(r"<PARAMETER-VALUE>(.*?)</PARAMETER-VALUE>")


def parse_parameters(container_file: str) -> dict[str, dict]:
    parameters: dict[str, dict] = {}
    start_line = None
    parameter_name = None
    parameter_value = None

    with open(container_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_number, line in enumerate(f, start=1):
            if "<PARAMETER>" in line:
                start_line = line_number
                parameter_name = None
                parameter_value = None

            match = _NAME_RE.search(line)
            if match:
                parameter_name = match.group(1).strip()

            match = _VALUE_RE.search(line)
            if match:
                parameter_value = match.group(1).strip()

            if "</PARAMETER>" in line:
                if parameter_name is not None:
                    parameters[parameter_name] = {
                        "value": parameter_value,
                        "start_line": start_line,
                        "end_line": line_number,
                    }
                start_line = None
                parameter_name = None
                parameter_value = None

    return parameters


def find_parameter(container_file: str, parameter_name: str) -> tuple[int, int]:
    parameters = parse_parameters(container_file)
    if parameter_name not in ("DCM_SIGNALG_KEYID", "EEPData1") and parameter_name not in parameters:
        raise RangeNotFoundError(f"Parameter {parameter_name!r} not found in container file")

    if parameter_name == "DCM_SIGNALG_KEYID":
        tmp = None
        for k, v in parameters.items():
            if v["value"] == "DCM_SIGNALG_KEYID":
                if "BLOCK_SHORT_NAME" not in k:
                    raise RangeNotFoundError(f"Unexpected parameter format for {k!r}")
                tmp = k.replace("BLOCK_SHORT_NAME", "").strip()
                break
        if tmp is None:
            raise RangeNotFoundError("Could not find BLOCK_SHORT_NAME for DCM_SIGNALG_KEYID")
        param = parameters[tmp + "VALUE"]
    elif parameter_name == "EEPData1":
        tmp = None
        for k, v in parameters.items():
            if v["value"] == "EEPData1":
                if "BLOCK_SHORT_NAME" in k:
                    tmp = k.replace("BLOCK_SHORT_NAME", "").strip()
                elif "VALUE" in k:
                    tmp = k.replace("VALUE", "").strip()
                else:
                    raise RangeNotFoundError(f"Unexpected parameter format for {k!r}")
                break
        if tmp is None:
            raise RangeNotFoundError("Could not find BLOCK_SHORT_NAME for EEPData1")
        param = parameters[tmp + "RB_HASH"]
    else:
        param = parameters[parameter_name]

    return param["start_line"], param["end_line"]
