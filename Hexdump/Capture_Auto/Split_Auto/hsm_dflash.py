import xml.etree.ElementTree as ET


def get_block_line_ranges(xml_file):
    """
    Find start/end line of every MEM_OVERVIEW_BLOCK
    in the original XML file.
    """

    ranges = []
    start_line = None

    with open(xml_file, "r", encoding="utf-8", errors="ignore") as f:

        for line_number, line in enumerate(f, start=1):

            # Start of MEM_OVERVIEW_BLOCK
            if "<MEM_OVERVIEW_BLOCK>" in line:
                start_line = line_number

            # End of MEM_OVERVIEW_BLOCK
            elif "</MEM_OVERVIEW_BLOCK>" in line:

                if start_line is not None:
                    ranges.append({
                        "START_LINE": start_line,
                        "END_LINE": line_number
                    })

                    start_line = None

    return ranges


def parse_mem_overview_blocks(xml_file):

    # -----------------------------------------------
    # Get physical line numbers first
    # -----------------------------------------------

    block_ranges = get_block_line_ranges(xml_file)

    # -----------------------------------------------
    # Parse XML
    # -----------------------------------------------

    tree = ET.parse(xml_file)
    root = tree.getroot()

    result = {}

    blocks = root.findall(".//MEM_OVERVIEW_BLOCK")

    for index, block in enumerate(blocks):

        block_dict = {}

        # -------------------------------------------
        # Read normal child nodes
        # -------------------------------------------

        for child in block:

            # MEM_OVERVIEW_BLOCK_DATA is special
            if child.tag == "MEM_OVERVIEW_BLOCK_DATA":

                page_data = []

                for page in child.findall("MEM_OVERVIEW_PAGE_DATA"):

                    if page.text:
                        page_data.append(
                            page.text.strip()
                        )

                block_dict["MEM_OVERVIEW_BLOCK_DATA"] = page_data

            else:

                block_dict[child.tag] = (
                    child.text.strip()
                    if child.text
                    else None
                )

        # -------------------------------------------
        # Add source line information
        # -------------------------------------------

        if index < len(block_ranges):

            block_dict["START_LINE"] = (
                block_ranges[index]["START_LINE"]
            )

            block_dict["END_LINE"] = (
                block_ranges[index]["END_LINE"]
            )

        # -------------------------------------------
        # Use BLOCK_ID as dictionary key
        # -------------------------------------------

        block_id = block_dict.get(
            "MEM_OVERVIEW_BLOCK_ID"
        )

        if block_id:
            result[block_id] = block_dict

    return result

def find_mem_overview_block(xml_file, block_id):
    mem_blocks = parse_mem_overview_blocks(xml_file)
    if block_id not in mem_blocks:
        raise ValueError(f"Block ID {block_id!r} not found in mem_overview_blocks")
    block = mem_blocks[block_id]
    return block["START_LINE"], block["END_LINE"]

# =================================================
# MAIN
# =================================================

xml_file = r"C:\01_Workspace\Task\Hex_Dump\6WZX\MP0\6WZX_Hexdump_Verification_0261S10BN8\05_DFlash_analysis\0261s109wl_mg1cs022_5100101316675002_hsm_dflash.decrypted.xml"

mem_blocks = parse_mem_overview_blocks(xml_file)


# =================================================
# TEST
# =================================================

block = mem_blocks["0x0703"]

print(block)