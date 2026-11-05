import re


def parse_parameters(container_file):

    parameters = {}

    start_line = None
    parameter_name = None
    parameter_value = None

    with open(container_file, "r", encoding="utf-8", errors="ignore") as f:

        for line_number, line in enumerate(f, start=1):

            # Start of PARAMETER
            if "<PARAMETER>" in line:
                start_line = line_number
                parameter_name = None
                parameter_value = None

            # PARAMETER-NAME
            match = re.search(
                r"<PARAMETER-NAME>(.*?)</PARAMETER-NAME>",
                line
            )

            if match:
                parameter_name = match.group(1).strip()

            # PARAMETER-VALUE
            match = re.search(
                r"<PARAMETER-VALUE>(.*?)</PARAMETER-VALUE>",
                line
            )

            if match:
                parameter_value = match.group(1).strip()

            # End of PARAMETER
            if "</PARAMETER>" in line:

                if parameter_name is not None:

                    parameters[parameter_name] = {
                        "value": parameter_value,
                        "start_line": start_line,
                        "end_line": line_number
                    }

                start_line = None
                parameter_name = None
                parameter_value = None

    return parameters

def find_parameter(container_file, parameter_name):
    parameters = parse_parameters(container_file)
    if parameter_name != "DCM_SIGNALG_KEYID" and parameter_name != "EEPData1":
        if parameter_name not in parameters:
            raise ValueError(f"Parameter {parameter_name!r} not found in container file")
    
    if parameter_name == "DCM_SIGNALG_KEYID":
        tmp = None
        for k,v in parameters.items():
            if v["value"] == "DCM_SIGNALG_KEYID":
                print("haha1")
                if "BLOCK_SHORT_NAME" in k:
                    print("haha")
                    tmp = k.replace("BLOCK_SHORT_NAME", "").strip()
                else:
                    raise ValueError(f"Unexpected parameter format for {k!r}")
                break
        if tmp == None:
            raise ValueError(f"Could not find BLOCK_SHORT_NAME for DCM_SIGNALG_KEYID")
        else:
            param = parameters[tmp + "VALUE"]
    elif parameter_name == "EEPData1":
        tmp = None
        for k,v in parameters.items():
            if v["value"] == "EEPData1":
                if "BLOCK_SHORT_NAME" in k:
                    tmp = k.replace("BLOCK_SHORT_NAME", "").strip()
                elif "VALUE" in k:
                    tmp = k.replace("VALUE", "").strip()
                else:
                    raise ValueError(f"Unexpected parameter format for {k!r}")
                break
        if tmp == None:
            raise ValueError(f"Could not find BLOCK_SHORT_NAME for EEPData1")
        else:
            param = parameters[tmp + "RB_HASH"]
    else:
        param = parameters[parameter_name]

    return param["start_line"], param["end_line"]

# =============================
# Main
# =============================

# container_file = r"C:\01_Workspace\Task\Hex_Dump\6WZX\MP0\6WZX_Hexdump_Verification_0261S10BN8\00_Hex_from_CNT\10SW137784.cnt"

# data = parse_parameters(container_file)

# for key, value in data.items():
#     print(f"{key}: {value}")
    
