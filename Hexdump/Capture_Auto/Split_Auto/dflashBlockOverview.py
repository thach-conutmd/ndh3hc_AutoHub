import json
import re
import sys

# Các trường nằm trong mỗi block: "| Key:   value"
FIELD_RE = re.compile(r"^\|\s*([A-Za-z ]+?):\s*(.*)$")
# Dòng viền: +-----+
BORDER_RE = re.compile(r"^\+-+\+\s*$")


def parse_blocks(path):
    """
    Đọc file và tách thành danh sách block.
    Mỗi block là dict gồm các trường dữ liệu + start_line, end_line (đánh số từ 1).
    start_line = dòng "Id:", end_line = dòng "Info:" (dòng cuối của block).
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    blocks = []
    current = None

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip()

        # Bắt đầu block mới khi gặp trường "Id"
        m = FIELD_RE.match(line)
        if m:
            key, value = m.group(1).strip(), m.group(2).strip()
            if key == "Id":
                if current:  # đóng block cũ phòng khi thiếu Info
                    blocks.append(current)
                current = {"start_line": lineno -1}
            if current is not None:
                current[key] = value
                current["end_line"] = lineno + 1
            continue

        # Dòng viền ngay sau block kết thúc block hiện tại
        if current is not None and BORDER_RE.match(line):
            blocks.append(current)
            current = None

    if current:
        blocks.append(current)
    return blocks


def to_dictionary(blocks):
    """Chuyển list thành dict với key là Name (nếu trùng thì thêm hậu tố)."""
    result = {}
    for b in blocks:
        key = b.get("Name") or f"line_{b['start_line']}"
        orig, n = key, 1
        while key in result:
            n += 1
            key = f"{orig}_{n}"
        result[key] = b
    return result

def find_dflash_block(path, block_name):
    blocks = to_dictionary(parse_blocks(path))
    if block_name not in blocks:
        raise ValueError(f"Block {block_name!r} not found in dflash blocks")
    block = blocks[block_name]
    return block["start_line"], block["end_line"]

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\01_Workspace\Task\Hex_Dump\6WZX\MP0\6WZX_Hexdump_Verification_0261S10BN8\05_DFlash_analysis\0261s109wl_mg1cs022_5100101316675002_dflashBlockOverview.txt"
    data = to_dictionary(parse_blocks(path))

    for block_id, b in data.items():
        print(f"{block_id}  (lines {b['start_line']}-{b['end_line']})  "
              f"ID={b.get('Id')}  Status={b.get('Status')}  "
              f"Blockdata_len={len(b.get('Blockdata', ''))}")

    # with open("parsed_blocks.json", "w", encoding="utf-8") as f:
    #     json.dump(data, f, indent=2, ensure_ascii=False)
    # print("\nĐã lưu parsed_blocks.json")