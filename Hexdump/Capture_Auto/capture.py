"""capture.py - CHỤP ẢNH (file chạy chính):  python capture.py [đường dẫn settings.toml]

Luồng: get_input (đọc settings) -> với mỗi job: calib (nạp/đo calib) -> với mỗi file: mở file, đưa đoạn cần chụp
lên top, tính khung cắt, lưu ảnh -> tổng kết lỗi.

Cài thư viện:  pip install pyautogui pillow pygetwindow pywin32 numpy
"""
import ctypes
import glob
import os
import re
import sys
import time
import traceback

# PHẢI bật DPI-aware TRƯỚC khi import pyautogui/pygetwindow/PIL (trong calib.py): pyautogui tự bật chế độ
# "System DPI aware" ngay lúc import và sau đó không đổi lại được. Khi đó màn hình có tỷ lệ phóng (scale) khác
# màn hình chính sẽ bị Windows "ảo hóa" tọa độ -> vùng chụp lệch (ảnh đen/sai). PER_MONITOR_AWARE_V2 = -4.
_DPI_RESULT = "?"
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    _DPI_RESULT = "Per-Monitor V2"
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        _DPI_RESULT = "Per-Monitor"
    except Exception:
        _DPI_RESULT = "FAILED to set"

import numpy as np                                                   # noqa: E402  (các import dưới phải đứng SAU đoạn DPI)
import pyautogui                                                     # noqa: E402
import win32api                                                      # noqa: E402
import win32gui                                                      # noqa: E402
from PIL import Image, ImageDraw                                   # noqa: E402

import calib                                                         # noqa: E402
from calib import (CalibMismatch, bands, close_window, editor_bottom, editor_text_left, editor_top, find_child, min_text_x,   # noqa: E402
                   get_calibration, grab_stable, grab_window, ink_mask, open_window, window_monitor_rect)
from get_input import BASE_DIR, Call, apply_common, apply_file, apply_shot, cfg, dbg, load_settings   # noqa: E402

cfg.DPI_RESULT = _DPI_RESULT


# ============================================================================
# ĐỌC FILE VÀ XÁC ĐỊNH ĐOẠN DÒNG CẦN CHỤP
# ============================================================================

def read_lines(path):
    """Đọc file thành danh sách dòng; in thống kê kiểu xuống dòng thật trong file (để chẩn đoán lệch số dòng)."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()
    with open(path, "rb") as f:
        raw = f.read()
    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    lone_cr = raw.count(b"\r") - crlf
    crcrlf = raw.count(b"\r\r\n")
    non_ascii = sum(1 for b in raw if b > 127)
    dbg(f"[INFO] file: {len(raw)} bytes, CRLF={crlf}, lone LF={lone_lf}, lone CR={lone_cr}, "
          f"CRCRLF={crcrlf}, bytes>127={non_ascii}, Python line count={len(lines)}")
    return lines


def plan_range(path, lines):
    """Xác định đoạn cần chụp của shot hiện tại: gọi Call(MODE, path, key) để tìm (start, end).
    Trả về (lineA, first, n_lines) = (dòng mốc, dòng đầu tiên chụp, số dòng của file cần chụp).
    Ném ValueError nếu không tìm ra hoặc range không hợp lệ."""
    start, end = Call(cfg.MODE, path, cfg.KEY)
    if not (1 <= start <= end <= len(lines)):
        raise ValueError(f"find range for key {cfg.KEY!r} returned an invalid range ({start}, {end}); "
                         f"the file has {len(lines)} lines")
    dbg(f"[RANGE] MODE={cfg.MODE}, key={cfg.KEY!r} -> lines {start}..{end}")
    return start, start, end - start + 1


# ============================================================================
# CUỘN: ĐƯA DÒNG CẦN CHỤP LÊN ĐẦU VÙNG SOẠN THẢO (CÓ TÍNH WORD WRAP)
# ============================================================================

# Thông báo của control soạn thảo Notepad (RichEdit)
EM_LINESCROLL = 0x00B6
EM_GETFIRSTVISIBLELINE = 0x00CE
EM_GETLINECOUNT = 0x00BA
EM_LINEINDEX = 0x00BB
EM_LINEFROMCHAR = 0x00C9
WM_GETTEXTLENGTH = 0x000E


def put_line_on_top(win, first, last):
    """Notepad++: đặt dòng `first` (số dòng của file, từ 1) lên top. Trả về số dòng HIỂN THỊ của đoạn first..last
    (nhiều hơn last-first+1 nếu có dòng bị wrap). Scintilla tự quy đổi dòng file -> dòng hiển thị."""
    pyautogui.click(win.left + win.width // 2, win.top + win.height // 2)  # lấy focus vào vùng soạn thảo
    pyautogui.hotkey("ctrl", "home"); time.sleep(0.3)
    sci = find_child(win._hWnd, ("Scintilla",))
    if cfg.FORCE_NO_WRAP:
        win32gui.SendMessage(sci, 2268, 0, 0)          # SCI_SETWRAPMODE = SC_WRAP_NONE (chỉ cửa sổ này)
    d_first = win32gui.SendMessage(sci, 2220, first - 1, 0)           # SCI_VISIBLEFROMDOCLINE
    n_doc = win32gui.SendMessage(sci, 2154, 0, 0)                     # SCI_GETLINECOUNT
    if last < n_doc:
        d_end = win32gui.SendMessage(sci, 2220, last, 0)              # dòng hiển thị bắt đầu của dòng last+1
    else:
        d_end = (win32gui.SendMessage(sci, 2220, n_doc - 1, 0)
                 + win32gui.SendMessage(sci, 2235, n_doc - 1, 0))     # SCI_WRAPCOUNT của dòng cuối file
    win32gui.SendMessage(sci, 2277, 0, 0)              # SCI_SETENDATLASTLINE = 0: cho cuộn quá dòng cuối (nếu không, dòng gần cuối file không lên top được)
    win32gui.SendMessage(sci, 2613, d_first, 0)        # SCI_SETFIRSTVISIBLELINE (dòng hiển thị, tuyệt đối)
    time.sleep(0.3)
    top = win32gui.SendMessage(sci, 2152, 0, 0)        # SCI_GETFIRSTVISIBLELINE: kiểm tra dòng đã thật sự lên top
    if top != d_first:
        win32gui.SendMessage(sci, 2613, d_first, 0); time.sleep(0.5)
        top = win32gui.SendMessage(sci, 2152, 0, 0)
        if top != d_first:
            raise RuntimeError(f"Could not scroll line {first} to the top in Notepad++ (top row is {top}, wanted {d_first})")
    return d_end - d_first


def map_logical_to_rows(edit, lines, first, last):
    """Notepad: đổi số dòng của FILE (first..last, từ 1) sang số dòng HIỂN THỊ khi có Word wrap.
    Cách làm: tính vị trí ký tự bắt đầu mỗi dòng trong file, rồi hỏi Notepad (EM_LINEFROMCHAR) ký tự đó nằm ở
    dòng hiển thị nào. Tự dò kiểu xuống dòng (1 hay 2 ký tự) bằng cách khớp tổng độ dài văn bản (WM_GETTEXTLENGTH).
    Trả về (dòng hiển thị đầu, số dòng hiển thị của đoạn) hoặc None nếu không khớp được."""
    total = win32gui.SendMessage(edit, WM_GETTEXTLENGTH, 0, 0)
    texts = list(lines)
    if texts:
        texts[0] = texts[0].lstrip("﻿")                       # BOM không hiển thị trong Notepad
    u16 = [len(t.encode("utf-16-le", errors="ignore")) // 2 for t in texts]
    n = len(u16)
    brk = trailing = None
    for b in (1, 2):                                               # xuống dòng tính 1 hay 2 ký tự
        for tr in (0, 1):                                          # file có/không kết thúc bằng xuống dòng
            if brk is None and sum(u16) + b * (n - 1 + tr) == total:
                brk, trailing = b, tr
    if brk is None:
        dbg(f"[DEBUG] map: WM_GETTEXTLENGTH={total}, total chars per file={sum(u16)}, file line count={n} "
              f"(matches when total + line breaks*(n-1[+1]) = {total}), EM_GETLINECOUNT="
              f"{win32gui.SendMessage(edit, EM_GETLINECOUNT, 0, 0)}")
        return None
    # Chỉ số ký tự của EM_LINEINDEX/EM_LINEFROMCHAR tính MỖI chỗ xuống dòng là 1 ký tự (RichEdit lưu '\r'),
    # dù WM_GETTEXTLENGTH có thể báo CRLF là 2. Nên bước tính vị trí dùng +1, không dùng `brk`.
    starts = [0]
    for u in u16:
        starts.append(starts[-1] + u + 1)
    d_first = win32gui.SendMessage(edit, EM_LINEFROMCHAR, starts[first - 1], 0)
    idx_first = win32gui.SendMessage(edit, EM_LINEINDEX, d_first, 0)
    if idx_first != starts[first - 1]:
        dbg(f"[DEBUG] map: line {first} starts at char {starts[first - 1]}, EM_LINEFROMCHAR={d_first}, "
              f"EM_LINEINDEX({d_first})={idx_first} (mismatch), line break={brk} chars")
        return None                                                # vị trí dòng đầu không khớp đầu dòng hiển thị
    if last < n:
        d_end = win32gui.SendMessage(edit, EM_LINEFROMCHAR, starts[last], 0)
        idx_end = win32gui.SendMessage(edit, EM_LINEINDEX, d_end, 0)
        if idx_end != starts[last]:
            dbg(f"[DEBUG] map: line {last + 1} starts at char {starts[last]}, EM_LINEFROMCHAR={d_end}, "
                  f"EM_LINEINDEX({d_end})={idx_end} (mismatch)")
            return None
    else:
        d_end = win32gui.SendMessage(edit, EM_GETLINECOUNT, 0, 0) - trailing   # trừ dòng trống cuối nếu có
    return d_first, d_end - d_first


def scroll_notepad(win, first, last, lines):
    """Notepad thường: đưa dòng `first` của file lên top (có tính tới Word wrap). Cuộn bằng EM_LINESCROLL
    (tương đối) từ đầu file, kiểm tra bằng EM_GETFIRSTVISIBLELINE.
    Trả về (ok, n_rows): ok=True nếu dòng đã ở top; n_rows = số dòng hiển thị của đoạn first..last."""
    try:
        edit = find_child(win._hWnd, ("RichEditD2DPT", "RICHEDIT50W", "Edit"))
    except RuntimeError:
        return False, None
    pyautogui.click(win.left + win.width // 2, win.top + win.height // 2)   # lấy focus
    pyautogui.hotkey("ctrl", "home"); time.sleep(0.3)                       # về mốc 0 rồi mới cuộn
    mapped = map_logical_to_rows(edit, lines, first, last)
    if mapped is None:
        print("[WARNING] Could not convert file lines to Notepad display rows (unusual line endings?). "
              "Assuming no Word wrap; if Word wrap is on, the image may be misaligned.")
        d_first, n_rows = first - 1, last - first + 1
    else:
        d_first, n_rows = mapped
    win32gui.SendMessage(edit, EM_LINESCROLL, 0, d_first)
    time.sleep(0.3)
    ok = win32gui.SendMessage(edit, EM_GETFIRSTVISIBLELINE, 0, 0) == d_first
    return ok, n_rows


# ============================================================================
# LƯU ẢNH KẾT QUẢ VÀ ẢNH DEBUG
# ============================================================================

def result_stem(path):
    """Tên (không đuôi) của ảnh kết quả: <tên file>[_<tên job>]. Nhiều job trên 1 file -> tên khác nhau."""
    return os.path.splitext(os.path.basename(path))[0] + (f"_{cfg.JOB_NAME}" if cfg.JOB_NAME else "")


TEXT_INK = 260      # ngưỡng độ đậm (tổng chênh RGB so với nền) coi là chữ khi cắt sát trái; đường kẻ mờ thấp hơn ngưỡng này
PAD_LEFT = 4        # lề trái (px) chừa lại khi cắt sát theo chữ đầu tiên


def save_results(win, img, m, path, first, n_lines, n_rows, line_y, line_h, crop_w, crop_top, bottom):
    """Lưu ảnh đã cắt (<stem>.png); khi DEBUG bật còn lưu ảnh debug cả cửa sổ (<stem>_debug.png). Trả về đường dẫn ảnh kết quả."""
    os.makedirs(cfg.OUT_DIR, exist_ok=True)
    stem = result_stem(path)
    out = os.path.join(cfg.OUT_DIR, stem + ".png")
    if cfg.DEBUG:                                    # ảnh debug: chỉ lưu khi bật DEBUG trong settings.toml
        # Ảnh debug (cả cửa sổ): vạch đỏ = đỉnh mỗi dòng script tính, kèm số dòng của file; vạch xanh = mép cắt dưới
        dbg_img = img.copy()
        d = ImageDraw.Draw(dbg_img)
        for k in range(n_rows):
            y = round(line_y + k * line_h)
            d.line([(0, y), (crop_w, y)], fill="red")
            d.text((2, y + 1), str(first + k) if n_rows == n_lines else f"r{k + 1}", fill="red")   # r = dòng hiển thị
        d.line([(0, bottom), (crop_w, bottom)], fill="blue", width=2)
        dbg_img.save(os.path.join(cfg.OUT_DIR, stem + "_debug.png"))
    left = 0 if cfg.INCLUDE_MARGIN else editor_text_left(win)
    if not cfg.INCLUDE_HEADER and not cfg.INCLUDE_MARGIN:   # không header, không lề: cắt sát bên trái theo chữ đầu tiên
        new_left = None
        if cfg.APP == "npp" and n_rows == n_lines:
            # Notepad++: lấy x của ký tự đầu tiên không phải khoảng trắng từ Scintilla (tính cả tab/thụt đầu dòng);
            # không dùng ảnh vì ký hiệu fold nhỏ ở đầu vùng chữ bị nhận nhầm là chữ. Có dòng bị wrap thì giữ cột 0.
            x = min_text_x(win, first, first + n_lines - 1)
            if x is not None:
                new_left = max(x - PAD_LEFT, left)
        elif cfg.APP == "notepad":
            # Notepad thường: dùng ảnh, ngưỡng "đậm" cao hơn ink_mask để bỏ qua các đường kẻ mờ
            a = np.asarray(img.convert("RGB")).astype(int)
            strong = np.abs(a - np.median(a.reshape(-1, 3), axis=0)).sum(axis=2) > TEXT_INK
            cols = np.where(strong[crop_top:bottom, left:crop_w].any(axis=0))[0]
            if len(cols):
                new_left = max(left + int(cols.min()) - PAD_LEFT, 0)
        if new_left is not None and new_left > left:
            print(f"[INFO] left crop: removed {new_left}px on the left")
            left = new_left
    if left <= 0:
        res = img.crop((0, crop_top, crop_w, bottom))
    else:                                            # bỏ lề trái (số dòng, fold): chỉ cắt phần nội dung, giữ nguyên thanh tab phía trên
        hdr = editor_top(win) if (cfg.INCLUDE_HEADER and crop_top == 0) else None     # chiều cao phần header
        if hdr:
            body = img.crop((left, hdr, crop_w, bottom))
            W = max(body.width, cfg.MIN_W)
            res = Image.new("RGB", (W, hdr + body.height), "white")
            res.paste(img.crop((0, 0, W, hdr)), (0, 0))
            res.paste(body, (0, hdr))
        else:
            res = img.crop((left, crop_top, crop_w, bottom))
        dbg(f"[INFO] left margin removed: {left}px")
    res = fit_image(res)
    res.save(out)
    return out


def fit_image(im):
    """Thu nhỏ ảnh cho vừa khung FIT_W x FIT_H (giữ tỉ lệ, chỉ thu nhỏ, không phóng to). 0 = không giới hạn chiều đó."""
    w, h = im.size
    k = min(cfg.FIT_W / w if cfg.FIT_W else 1.0, cfg.FIT_H / h if cfg.FIT_H else 1.0, 1.0)
    if k >= 1.0:
        return im
    new = (max(1, round(w * k)), max(1, round(h * k)))
    dbg(f"[INFO] scaling image {w}x{h} -> {new[0]}x{new[1]} (x{k:.3f})")
    return im.resize(new, Image.LANCZOS)


# ============================================================================
# CHỤP 1 FILE
# ============================================================================

def measure_line_y(win, m, window_lines, line_h):
    """Notepad thường: đo y thật của dòng đầu trong CHÍNH ảnh vừa chụp (thay cho line_y của calib).
    Dải chữ đầu tiên trong vùng soạn thảo là dòng không rỗng đầu tiên của vùng cần chụp."""
    et = editor_top(win)
    f = next((i for i, ln in enumerate(window_lines) if ln.strip()), None)   # dòng rỗng không có chữ
    if et is None or f is None:
        return None
    W = m.shape[1]
    bs = bands(m[et:, : W - cfg.SCROLL_W].sum(axis=1) >= 2)
    if not bs:
        return None
    return et + bs[0][0] - f * line_h


def compute_crop(win, m, name, line_y, line_h, n_rows, n_lines):
    """Tính khung cắt. Trả về (crop_w, crop_top, bottom); in cảnh báo nếu không đủ chỗ / dòng chạm mép phải."""
    H, W = m.shape
    top = max(int(line_y) - 2, 0)
    want_bottom = round(line_y + n_rows * line_h) - 3
    et, eb = editor_top(win), editor_bottom(win)     # mép trên/dưới vùng soạn thảo (dưới = trên thanh trạng thái)
    limit = min(H, eb) if eb is not None else H
    capacity = int((limit - line_y) / line_h)        # số dòng tối đa hiển thị được trong 1 màn hình
    dbg(f"[INFO] need {n_rows} display rows, editor shows at most ~{capacity} rows")
    dbg(f"[DEBUG] image height H={H}px, editor_top={et}, editor_bottom={eb}, "
          f"line_y={line_y:.1f}, line_h={line_h:.2f}, limit={limit}")
    if want_bottom > limit:
        print(f"[WARNING] {name}: {n_rows} rows is more than the ~{capacity} rows that fit, "
              f"the image will miss ~{n_rows - capacity} last row(s). Reduce the line count or zoom out (Ctrl + minus).")
    bottom = min(limit, want_bottom)

    cols = np.where(m[top:bottom, : W - cfg.SCROLL_W].any(axis=0))[0]
    right = int(cols.max()) if len(cols) else 0
    if right >= W - cfg.SCROLL_W - 3 and n_rows == n_lines:   # có dòng bị wrap thì chạm mép phải là bình thường
        print(f"[WARNING] {name}: a long line reaches the right edge and may be cut off "
              f"(zoom out: Ctrl + minus)")
    crop_w = min(W, max(cfg.MIN_W if cfg.INCLUDE_HEADER else 0, right + cfg.PAD_X))   # MIN_W: để thấy đủ tên file trên tab

    crop_top = 0                                     # có header: cắt từ mép trên cửa sổ (thấy tên file trên tab)
    if not cfg.INCLUDE_HEADER:                       # không header: cắt từ mép trên vùng soạn thảo
        crop_top = max(min(et, int(line_y) - 2), 0) if et is not None else top
    return crop_w, crop_top, bottom


def capture(path, shots, line_y, line_h):
    """Chụp 1 file: mở cửa sổ MỘT lần, chụp lần lượt từng shot. Ném CalibMismatch nếu cửa sổ mở ở màn hình khác
    với lúc calib. Trả về danh sách (tên shot, lỗi) của các shot bị lỗi (shot lỗi không làm dừng các shot sau)."""
    lines = read_lines(path)
    errors = []
    win = None
    try:                                             # luôn đóng cửa sổ dù có lỗi giữa chừng
        for shot in shots:
            apply_shot(shot)
            try:
                plan = plan_range(path, lines)
            except Exception as e:                   # không tìm ra range: bỏ qua shot này, các shot khác vẫn chụp
                print(f"[ERROR] {path} [{cfg.JOB_NAME}]: {e}")
                errors.append((cfg.JOB_NAME, str(e)))
                continue
            if win is None:
                win = open_window(path)
                cur_mon = window_monitor_rect(win)
                if calib.CALIB_MONITOR is not None and cur_mon != calib.CALIB_MONITOR:
                    raise CalibMismatch(f"window opened on monitor {cur_mon}, calibration was saved for {calib.CALIB_MONITOR}")
            try:
                capture_shot(win, path, lines, plan, line_y, line_h)
            except CalibMismatch:
                raise
            except Exception as e:
                print(f"[ERROR] {path} [{cfg.JOB_NAME}]: {e}")
                traceback.print_exc()
                errors.append((cfg.JOB_NAME, str(e)))
    finally:
        if win is not None:
            close_window(win)
    return errors


def capture_shot(win, path, lines, plan, line_y, line_h):
    """Chụp 1 shot (cfg đã được apply_shot) trên cửa sổ đã mở."""
    lineA, first, n_lines = plan
    last = first + n_lines - 1
    dbg(f"[RANGE] line {first}: {lines[first - 1][:70]!r}")
    dbg(f"[RANGE] line {last}: {lines[last - 1][:70]!r}   (total {n_lines} lines)")

    # n_rows = số dòng HIỂN THỊ của đoạn cần chụp. Bằng n_lines khi không có dòng nào bị wrap;
    # lớn hơn khi Word wrap bật và có dòng dài bị gập thành nhiều dòng.
    if cfg.APP == "npp":
        n_rows = put_line_on_top(win, first, last)   # Notepad++: Scintilla tự quy đổi dòng file -> dòng hiển thị
    else:
        ok, rows = scroll_notepad(win, first, last, lines)
        if not ok:
            raise RuntimeError(f"Could not scroll to line {first} in Notepad")
        n_rows = rows if rows is not None else n_lines
    if n_rows != n_lines:
        dbg(f"[INFO] Word wrap: {n_lines} file lines = {n_rows} display rows")

    img = grab_stable(win)                           # đợi header (tab, menu) vẽ xong rồi mới chụp
    m = ink_mask(img)

    if cfg.APP == "notepad":
        # Đo y thật của dòng đầu cần chụp trong ảnh này để khung chụp bám theo dòng đầu thật,
        # không phụ thuộc line_y của calib.
        measured = measure_line_y(win, m, lines[first - 1: first - 1 + n_lines], line_h)
        if measured is not None:
            dbg(f"[INFO] calibrated line_y={line_y}, measured line_y={measured:.1f}")
            line_y = measured

    name = os.path.basename(path)
    crop_w, crop_top, bottom = compute_crop(win, m, name, line_y, line_h, n_rows, n_lines)
    out = save_results(win, img, m, path, first, n_lines, n_rows, line_y, line_h, crop_w, crop_top, bottom)
    print(f"{name}: START line={lineA}, captured from line {first}, {n_lines} lines ({n_rows} display rows), "
          f"image {crop_w}x{bottom - crop_top} -> {out}")


# ============================================================================
# ĐIỀU PHỐI: MỖI FILE -> NẠP CALIB -> MỞ MỘT LẦN, CHỤP TỪNG SHOT
# ============================================================================

def expand_args(args):
    """Danh sách file .toml từ tham số dòng lệnh (hỗ trợ ký tự đại diện *); mặc định settings.toml cạnh script."""
    if not args:
        return [os.path.join(BASE_DIR, "HSM_DFlash.toml")]
    out = []
    for a in args:
        out += sorted(glob.glob(a)) if any(ch in a for ch in "*?[") else [a]
    return out


def main():
    settings_paths = expand_args(sys.argv[1:])
    sw, sh = pyautogui.size()
    print(f"Primary screen: {sw}x{sh}, DPI awareness: {cfg.DPI_RESULT}")

    failed = []
    for sp in settings_paths:
        common, files = load_settings(sp)
        apply_common(common)
        dbg(f"All monitors (left, top, right, bottom): {[m[2] for m in win32api.EnumDisplayMonitors()]}")
        print(f"\n########## {sp} ##########")
        for n, f in enumerate(files, 1):
            apply_file(f)
            shots = f["shots"]
            print(f"\n===== File {n}/{len(files)}: {os.path.basename(f['FILE'])} | APP={cfg.APP} | MODE={cfg.MODE} "
                  f"| {len(shots)} shot(s) =====")
            line_y, line_h = get_calibration()       # nạp calib đã lưu, hoặc đo mới nếu chưa có / đổi màn hình
            print(f"Calib: line_y={line_y}px, line_h={line_h:.2f}px, "
                  f"~{(sh - line_y) / line_h:.0f} visible rows when maximized")
            try:
                try:
                    errs = capture(f["FILE"], shots, line_y, line_h)
                except CalibMismatch as e:
                    print(f"[CALIB] {e} -> re-calibrating and capturing again")
                    line_y, line_h = get_calibration(force=True)
                    errs = capture(f["FILE"], shots, line_y, line_h)
                failed += [(name, f["FILE"], msg) for name, msg in errs]
            except Exception as e:                   # 1 file lỗi không làm dừng cả đợt
                print(f"[ERROR] {f['FILE']}: {e}")
                traceback.print_exc()
                failed.append(("(file)", f["FILE"], str(e)))

    print(f"\nDone. {len(failed)} error(s)." if failed else "\nDone, no errors.")
    for name, fp, err in failed:
        print(f"  - [{name}] {fp}: {err}")


if __name__ == "__main__":
    main()