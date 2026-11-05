"""get_input.py - ĐỌC THÔNG SỐ ĐẦU VÀO + TÌM RANGE CẦN CHỤP.

1) Đọc & kiểm tra các file .toml ([common], [[file]], [[file.shot]]), báo lỗi nhập liệu, ghi thông số vào `cfg`
   (trạng thái cấu hình dùng chung cho calib.py và capture.py).
2) Call(mode, path, key): theo MODE của file, gọi hàm tìm range tương ứng và trả về (start_line, end_line).
   >>> Thêm logic tìm range của bạn vào các hàm find_* ở phần "TÌM RANGE" bên dưới. <<<
Không phụ thuộc Windows.
"""
import os
import sys
from types import SimpleNamespace
from Split_Auto.container_file import find_parameter
from Split_Auto.hsm_dflash import find_mem_overview_block
from Split_Auto.secumgr_fee_export import find_key_secumgr_fee
from Split_Auto.dflashBlockOverview import find_dflash_block

try:
    import tomllib                                    # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib                       # pip install tomli (cho Python < 3.11)
    except ModuleNotFoundError:
        tomllib = None

# Thư mục chứa các file script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# cfg: thông số đang chạy (apply_* ghi vào). calib.py và capture.py chỉ ĐỌC:  from get_input import cfg
cfg = SimpleNamespace(
    # --- cố định trong code (không nhập trong .toml) ---
    NPP_EXE=r"C:\Program Files\Notepad++\notepad++.exe",
    CALIB_FILE="calib_cache.json",
    # --- thông số của file / shot đang chụp ---
    APP="npp", MODE="", JOB_NAME="", KEY="",
    INCLUDE_HEADER=True, INCLUDE_MARGIN=True, FORCE_NO_WRAP=False,
    FIT_W=0, FIT_H=0,
    FILE_FIT_W=0, FILE_FIT_H=0,                       # mặc định cấp file (apply_file ghi)
    DPI_RESULT="?",                                   # do capture.py đặt lúc khởi động (chỉ để in log)
    # --- thông số chung ([common]) ---
    OUT_DIR="out", RECALIBRATE=False, DEBUG=False,
    PAD_X=20, MIN_W=400, SCROLL_W=30,
    COMMON_FIT_W=0, COMMON_FIT_H=0,
)


def dbg(*args, **kwargs):
    """In dòng chẩn đoán chi tiết; chỉ in khi DEBUG = true trong [common]."""
    if cfg.DEBUG:
        print(*args, **kwargs)


# ============================================================================
# TÌM RANGE: Call(mode, path, key) -> (start_line, end_line)
# ============================================================================
# Mỗi MODE có 1 hàm find_<mode>(path, key). Hàm nhận đường dẫn file và key của shot, trả về
# (start_line, end_line): số dòng bắt đầu từ 1, gồm cả hai đầu. Không tìm ra thì ném ValueError("lý do").
# Thêm MODE mới: viết hàm find_xxx rồi thêm vào FINDERS.

# def find_block(path, key):
#     """MODE = "block": (ví dụ _dflashBlockOverview.txt, _dflash_Layout.txt, Fee_ContentDetails.txt)."""
#     raise NotImplementedError("find_block is not implemented yet: add your logic in get_input.py")


# def find_cnt(path, key):
#     """MODE = "cnt": (file .cnt)."""
#     raise NotImplementedError("find_cnt is not implemented yet: add your logic in get_input.py")


FINDERS = {
    "block": find_dflash_block,
    "cnt": find_parameter,
    "mem_block" : find_mem_overview_block,
    "fee": find_key_secumgr_fee
}


def Call(mode, path, key):
    """Gọi hàm tìm range của `mode`. Trả về (start, end). Ném lỗi (ValueError/NotImplementedError) nếu không tìm ra."""
    if mode not in FINDERS:
        raise ValueError(f"unknown MODE {mode!r} (available: {', '.join(sorted(FINDERS))})")
    res = FINDERS[mode](path, key)
    if not (isinstance(res, tuple) and len(res) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in res)):
        raise ValueError(f"find_{mode} must return (start_line, end_line) as two integers, got {res!r}")
    return res


# ============================================================================
# ĐỌC & KIỂM TRA .toml
# ============================================================================

COMMON_KEYS = {"OUT", "PAD_X", "MIN_W", "SCROLL_W", "FIT_W", "FIT_H", "RECALIBRATE", "DEBUG"}
FILE_KEYS = {"FILE", "APP", "MODE", "FORCE_NO_WRAP", "INCLUDE_HEADER", "INCLUDE_MARGIN", "FIT_W", "FIT_H",
             "enabled", "shot"}
SHOT_KEYS = {"name", "key", "FIT_W", "FIT_H", "enabled"}
FIXED_IN_CODE = {"NPP_EXE", "CALIB_FILE"}


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_ints(errs, where, d, keys):
    for k in keys:
        if k in d and not (_is_int(d[k]) and d[k] >= 0):
            errs.append(f"{where}: {k} must be an integer >= 0")


def load_settings(path):
    """Đọc 1 file .toml. Trả về (common, files). Nếu có lỗi nhập liệu: in TẤT CẢ lỗi rồi thoát."""
    if tomllib is None:
        sys.exit("Python 3.11+ is required (built-in tomllib), or run: pip install tomli")
    if not os.path.isfile(path):
        sys.exit(f"Settings file not found: {path}")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"Settings file {path} has invalid TOML syntax: {e}\n"
                 f"Hint: paths containing \\ must be written in SINGLE quotes '...' (not double quotes).")

    errs = []
    common = data.get("common", {})
    files_raw = data.get("file", [])
    for k in data:
        if k not in ("common", "file"):
            errs.append(f"Section [{k}] is not valid (only [common] and [[file]] with [[file.shot]] are allowed)")

    # ---- [common] ----
    for k in common:
        if k in FIXED_IN_CODE:
            errs.append(f"[common]: {k} is fixed in the code (get_input.py) and cannot be set here")
        elif k not in COMMON_KEYS:
            errs.append(f"[common]: unknown parameter '{k}' (valid: {', '.join(sorted(COMMON_KEYS))})")
    _check_ints(errs, "[common]", common, ("PAD_X", "MIN_W", "SCROLL_W", "FIT_W", "FIT_H"))
    if "OUT" in common and not (isinstance(common["OUT"], str) and common["OUT"]):
        errs.append("[common]: OUT must be a non-empty string")
    for k in ("RECALIBRATE", "DEBUG"):
        if k in common and not isinstance(common[k], bool):
            errs.append(f"[common]: {k} must be true or false")

    # ---- [[file]] / [[file.shot]] ----
    if not isinstance(files_raw, list) or not files_raw:
        errs.append("Nothing to capture: add at least one [[file]] block with [[file.shot]] blocks")
        files_raw = []
    files = []
    for fi, f in enumerate(files_raw, 1):
        where = f"[[file]] #{fi}" + (f" ({f['FILE']})" if isinstance(f.get("FILE"), str) else "")
        if f.get("enabled", True) is False:
            continue
        for k in f:
            if k not in FILE_KEYS:
                errs.append(f"{where}: unknown parameter '{k}' (valid: {', '.join(sorted(FILE_KEYS))})")
        fpath = f.get("FILE")
        if not (isinstance(fpath, str) and fpath):
            errs.append(f"{where}: FILE is required (path of the file to capture)")
        elif not os.path.isfile(fpath):
            errs.append(f"{where}: file not found: {fpath}")
        if f.get("APP") not in ("notepad", "npp"):
            errs.append(f"{where}: APP must be \"notepad\" or \"npp\" (got {f.get('APP')!r})")
        if f.get("MODE") not in FINDERS:
            errs.append(f"{where}: MODE must be one of {sorted(FINDERS)} (got {f.get('MODE')!r})")
        for k in ("INCLUDE_HEADER", "INCLUDE_MARGIN", "FORCE_NO_WRAP"):
            if k in f and not isinstance(f[k], bool):
                errs.append(f"{where}: {k} must be true or false (without quotes)")
        _check_ints(errs, where, f, ("FIT_W", "FIT_H"))

        shots_raw = f.get("shot", [])
        if not (isinstance(shots_raw, list) and shots_raw):
            errs.append(f"{where}: needs at least one [[file.shot]] block")
            continue
        shots, names = [], set()
        for si, sh in enumerate(shots_raw, 1):
            swhere = f"{where} shot #{si}" + (f" ({sh['name']})" if isinstance(sh.get("name"), str) else "")
            if sh.get("enabled", True) is False:
                continue
            for k in sh:
                if k not in SHOT_KEYS:
                    errs.append(f"{swhere}: unknown parameter '{k}' (valid: {', '.join(sorted(SHOT_KEYS))})")
            name = sh.get("name")
            if not (isinstance(name, str) and name):
                errs.append(f"{swhere}: name is required (it is used in the image file name)")
            elif any(c in name for c in '\\/:*?"<>|'):
                errs.append(f"{swhere}: name must not contain any of \\ / : * ? \" < > |")
            elif name in names:
                errs.append(f"{swhere}: duplicate name '{name}' in this file")
            else:
                names.add(name)
            if not (isinstance(sh.get("key"), str) and sh["key"]):
                errs.append(f"{swhere}: key is required (a non-empty string)")
            _check_ints(errs, swhere, sh, ("FIT_W", "FIT_H"))
            shots.append({k: v for k, v in sh.items() if k != "enabled"})
        if shots:
            files.append(dict({k: v for k, v in f.items() if k not in ("shot", "enabled")}, shots=shots))

    if any(f.get("APP") == "npp" for f in files) and not os.path.isfile(cfg.NPP_EXE):
        errs.append(f"Notepad++ not found: {cfg.NPP_EXE} (NPP_EXE is fixed in get_input.py; edit it there)")
    if not files and not errs:
        errs.append("All files are disabled (enabled = false)")
    if errs:
        print(f"Settings file has {len(errs)} error(s) ({path}):")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    return common, files


def apply_common(common):
    """Ghi các thông số chung ([common]) vào cfg; thông số không khai báo về mặc định."""
    cfg.OUT_DIR = common.get("OUT", "out")
    cfg.PAD_X = common.get("PAD_X", 20)
    cfg.MIN_W = common.get("MIN_W", 400)
    cfg.SCROLL_W = common.get("SCROLL_W", 30)
    cfg.COMMON_FIT_W = common.get("FIT_W", 0)
    cfg.COMMON_FIT_H = common.get("FIT_H", 0)
    cfg.RECALIBRATE = common.get("RECALIBRATE", False)
    cfg.DEBUG = common.get("DEBUG", False)


def apply_file(f):
    """Ghi thông số cấp file ([[file]]) vào cfg; FIT_W/FIT_H của file là mặc định cho các shot."""
    cfg.APP = f["APP"]
    cfg.MODE = f["MODE"]
    cfg.FORCE_NO_WRAP = f.get("FORCE_NO_WRAP", False)
    cfg.INCLUDE_HEADER = f.get("INCLUDE_HEADER", True)
    cfg.INCLUDE_MARGIN = f.get("INCLUDE_MARGIN", True)
    cfg.FILE_FIT_W = f.get("FIT_W", cfg.COMMON_FIT_W)
    cfg.FILE_FIT_H = f.get("FIT_H", cfg.COMMON_FIT_H)


def apply_shot(shot):
    """Ghi thông số của 1 shot vào cfg (FIT_W/FIT_H không khai báo lấy từ file, rồi từ [common])."""
    cfg.JOB_NAME = shot["name"]
    cfg.KEY = shot["key"]
    cfg.FIT_W = shot.get("FIT_W", cfg.FILE_FIT_W)
    cfg.FIT_H = shot.get("FIT_H", cfg.FILE_FIT_H)