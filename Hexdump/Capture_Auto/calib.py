"""calib.py - CALIB + tiện ích cửa sổ/màn hình/ảnh dùng chung.

Phần 1: tiện ích dùng chung (tìm chữ trong ảnh, màn hình, mở/đóng cửa sổ Notepad / Notepad++).
Phần 2: calib - tự đo vị trí dòng đầu (line_y) và chiều cao dòng (line_h), lưu/nạp lại theo cấu hình màn hình.

Lưu ý: capture.py là file chạy chính và phải bật DPI-aware TRƯỚC khi file này import pyautogui.
"""
import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import time

import numpy as np
import pyautogui
import pygetwindow as gw
import win32api
import win32con
import win32gui
from PIL import ImageGrab

from get_input import BASE_DIR, cfg, dbg


# ============================================================================
# PHẦN 1: TIỆN ÍCH DÙNG CHUNG - XỬ LÝ ẢNH
# ============================================================================

def ink_mask(img):
    """True ở pixel là chữ (khác màu nền nhiều). Chạy được cả nền sáng lẫn nền tối."""
    a = np.asarray(img.convert("RGB")).astype(int)
    bg = np.median(a.reshape(-1, 3), axis=0)
    return np.abs(a - bg).sum(axis=2) > 150


def bands(flags):
    """Gom các hàng pixel liên tiếp có chữ thành từng dải (= từng dòng chữ)."""
    out, start = [], None
    for y, v in enumerate(flags):
        if v and start is None:
            start = y
        if not v and start is not None:
            out.append((start, y - 1)); start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


# ============================================================================
# PHẦN 1: TIỆN ÍCH DÙNG CHUNG - MÀN HÌNH & CHỤP ẢNH
# ============================================================================

def visible_rect(win):
    """(left, top, right, bottom) của cửa sổ, cắt theo MÀN HÌNH (monitor) chứa nó. Cửa sổ maximize có viền
    âm vài pixel, và khi dùng nhiều màn hình thì tọa độ có thể âm hoặc vượt chiều rộng màn hình chính."""
    hwnd = win._hWnd
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    mon = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    ml, mt, mr, mb = win32api.GetMonitorInfo(mon)["Monitor"]
    return max(l, ml), max(t, mt), min(r, mr), min(b, mb)


def window_monitor_rect(win):
    """(left, top, right, bottom) của màn hình mà cửa sổ đang nằm trên."""
    mon = win32api.MonitorFromWindow(win._hWnd, win32con.MONITOR_DEFAULTTONEAREST)
    return tuple(win32api.GetMonitorInfo(mon)["Monitor"])


def screen_layout_key():
    """Chuỗi mô tả cấu hình màn hình: vị trí/kích thước + tỷ lệ phóng (DPI) của từng màn hình.
    Đổi màn hình, đổi độ phân giải, đổi scale hoặc cắm/rút màn hình phụ -> chuỗi đổi."""
    parts = []
    for hmon, _, rect in win32api.EnumDisplayMonitors():
        dx, dy = ctypes.c_uint(), ctypes.c_uint()
        try:
            ctypes.windll.shcore.GetDpiForMonitor(int(hmon), 0, ctypes.byref(dx), ctypes.byref(dy))
        except Exception:
            pass
        parts.append(f"{tuple(rect)}@{dx.value}")
    return ";".join(sorted(parts))


def grab_window(win):
    """Chụp vùng nhìn thấy của cửa sổ (trên đúng màn hình chứa nó). Cảnh báo + lưu ảnh nếu ảnh bị đen."""
    l, t, r, b = visible_rect(win)
    img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)      # all_screens: chụp được cả màn hình phụ
    # Vùng nằm NGOÀI ảnh chụp bị Pillow tô đen (0,0,0) tuyệt đối. Nền Notepad (kể cả dark mode) không bao giờ đen tuyệt đối.
    a = np.asarray(img.convert("RGB"))
    black = float((a.sum(axis=2) == 0).mean())
    if black > 0.3:
        os.makedirs(cfg.OUT_DIR, exist_ok=True)
        img.save(os.path.join(cfg.OUT_DIR, "grab_black.png"))
        try:
            awareness = ctypes.c_int()
            ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
            aw = {0: "Unaware", 1: "System", 2: "Per-Monitor"}.get(awareness.value, awareness.value)
        except Exception:
            aw = "?"
        mon = win32api.MonitorFromWindow(win._hWnd, win32con.MONITOR_DEFAULTTONEAREST)
        print(f"[WARNING] {black:.0%} of the captured image is black -> the capture region is outside the screen. "
              f"Window={win32gui.GetWindowRect(win._hWnd)}, containing monitor={win32api.GetMonitorInfo(mon)['Monitor']}, "
              f"capture region={(l, t, r, b)}, DPI awareness={aw} (set at startup: {cfg.DPI_RESULT}). "
              f"Saved out\\grab_black.png")
    return img


def grab_stable(win, tries=8, wait=0.4):
    """Chụp cửa sổ sau khi phần HEADER (thanh tab, menu File/Edit/View...) đã vẽ xong và không còn đổi.
    Notepad Win11 vẽ menu chậm sau khi phóng to; chụp sớm sẽ thiếu menu. So 2 lần chụp liên tiếp phần phía trên vùng soạn
    thảo (không so vùng chữ vì con trỏ nhấp nháy). Hết số lần thử thì dùng lần chụp cuối."""
    prev = grab_window(win)
    for n in range(tries):
        time.sleep(wait)
        cur = grab_window(win)
        et = editor_top(win) or 150
        if np.array_equal(np.asarray(prev.convert("RGB"))[:et], np.asarray(cur.convert("RGB"))[:et]):
            dbg(f"[INFO] header stable after {n + 1} check(s)")
            return cur
        prev = cur
    print("[WARNING] the window header kept changing; using the last capture")
    return prev


# ============================================================================
# PHẦN 1: TIỆN ÍCH DÙNG CHUNG - CỬA SỔ NOTEPAD / NOTEPAD++
# ============================================================================

def launch(path):
    if cfg.APP == "npp":
        subprocess.Popen([cfg.NPP_EXE, "-multiInst", "-nosession", path])
    else:
        subprocess.Popen(["notepad.exe", path])


def find_app_windows(name):
    """Cửa sổ có tiêu đề chứa `name` VÀ đúng loại app đang dùng (tránh bắt nhầm cửa sổ khác
    như Notepad cũ còn mở, Explorer, VS Code... cùng có tên file trong tiêu đề)."""
    out = []
    for w in gw.getWindowsWithTitle(name):
        cls = win32gui.GetClassName(w._hWnd)
        is_npp = (cls == "Notepad++")
        if (cfg.APP == "npp") == is_npp:
            out.append(w)
    return out


BORROWED_HWNDS = set()        # cửa sổ có sẵn đang hiển thị đúng file cần chụp: dùng tạm để chụp, KHÔNG đóng
SHARED_HWNDS = set()          # cửa sổ Notepad có sẵn (của người dùng) mà file mới chỉ mở thành 1 tab bên trong


def _notepad_hwnds():
    """Tất cả cửa sổ Notepad thường đang mở (để biết file mới có mở thành tab trong cửa sổ có sẵn hay không)."""
    return {w._hWnd for w in gw.getAllWindows() if win32gui.GetClassName(w._hWnd) == "Notepad"}


def close_all_notepad():
    """Tắt MỌI cửa sổ Notepad thường đang mở, KHÔNG lưu (nội dung chưa lưu sẽ mất). Chờ tới khi cửa sổ biến mất."""
    if not _notepad_hwnds():
        return
    n = len(_notepad_hwnds())
    print(f"[INFO] closing {n} open Notepad window(s) without saving")
    subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
    for _ in range(25):                                    # chờ tối đa ~5 giây
        if not _notepad_hwnds():
            break
        time.sleep(0.2)
    else:
        print("[WARNING] some Notepad windows are still open")
    time.sleep(0.5)


def close_other_tabs(win, name):
    """Notepad Win11 tự khôi phục các tab của phiên trước. Đóng mọi tab KHÁC `name` (không lưu), chỉ để lại tab của file cần chụp.
    Cách làm: Ctrl+Tab sang tab kế; nếu tiêu đề cửa sổ không chứa `name` thì Ctrl+W đóng tab đó. Hai lần Ctrl+Tab liên tiếp
    vẫn ra đúng tab của mình nghĩa là chỉ còn 1 tab."""
    hwnd = win._hWnd
    closed, same = 0, 0
    for _ in range(30):
        if not win32gui.IsWindow(hwnd):
            break
        pyautogui.hotkey("ctrl", "tab"); time.sleep(0.35)
        if name in win32gui.GetWindowText(hwnd):
            same += 1
            if same >= 2:
                break                                       # chỉ còn tab của mình
        else:
            same = 0
            pyautogui.hotkey("ctrl", "w"); time.sleep(0.35)
            closed += 1
    if closed:
        print(f"[INFO] closed {closed} other Notepad tab(s) restored from the previous session")
    else:
        dbg("[INFO] no other Notepad tabs to close")


def open_window(path):
    """Mở file bằng app đang dùng, chờ cửa sổ MỚI xuất hiện rồi phóng to full màn hình.
    Chỉ nhận cửa sổ mới sinh ra sau khi launch: nếu file đã mở sẵn trong cửa sổ của bạn thì không đụng tới cửa sổ đó
    (không chụp nhầm và không đóng nhầm)."""
    name = os.path.basename(path)
    if cfg.APP == "notepad":
        close_all_notepad()                                 # dọn sạch các file khác đang mở trong Notepad trước khi mở
    before = {w._hWnd for w in find_app_windows(name)}      # cửa sổ đã có sẵn trước khi mở
    existing = _notepad_hwnds() if cfg.APP == "notepad" else set()
    launch(path)
    for _ in range(15 if before else 50):     # chờ tối đa ~10 giây (~3 giây nếu file đã mở sẵn: app sẽ không mở cửa sổ mới)
        wins = [w for w in find_app_windows(name) if w._hWnd not in before]
        if wins:
            break
        time.sleep(0.2)
    else:
        old = [w for w in find_app_windows(name) if w._hWnd in before]
        if not old:
            seen = [(w.title, win32gui.GetClassName(w._hWnd)) for w in gw.getWindowsWithTitle(name)]
            raise RuntimeError(f"No {cfg.APP} window named {name} appeared. Windows matching the title: {seen}")
        wins = old[:1]                        # file đã mở sẵn và đang hiển thị: dùng luôn cửa sổ đó
        BORROWED_HWNDS.add(wins[0]._hWnd)
        print(f"[INFO] {name} is already open in an existing window; using it and leaving it open afterwards")
    win = wins[0]
    if win._hWnd in existing:                 # Notepad Win11 mở file thành TAB trong cửa sổ của người dùng
        SHARED_HWNDS.add(win._hWnd)
        print("[INFO] Notepad opened the file as a tab in an existing window; only that tab will be closed afterwards")
    win.maximize(); win.activate()
    time.sleep(0.8)
    if cfg.APP == "notepad" and win._hWnd not in BORROWED_HWNDS and win._hWnd not in SHARED_HWNDS:
        close_other_tabs(win, name)                         # bỏ các tab cũ được Notepad khôi phục
    return win


def close_window(win):
    """Đóng hẳn cửa sổ. Notepad Win11 có nhiều tab nên Ctrl+W từng tab (tab cuối đóng luôn cửa sổ);
    Notepad++ chạy -multiInst nên chỉ cần đóng cửa sổ."""
    hwnd = win._hWnd
    if hwnd in BORROWED_HWNDS:                        # cửa sổ của người dùng: không đóng
        BORROWED_HWNDS.discard(hwnd)
        return
    shared = hwnd in SHARED_HWNDS
    SHARED_HWNDS.discard(hwnd)
    try:
        if cfg.APP == "notepad" and shared:
            win.activate(); time.sleep(0.2)
            pyautogui.hotkey("ctrl", "w"); time.sleep(0.3)      # chỉ đóng tab vừa mở, giữ nguyên các tab khác
            return
        if cfg.APP == "notepad":
            win.activate(); time.sleep(0.2)
            for _ in range(20):
                if not win32gui.IsWindow(hwnd):
                    break
                pyautogui.hotkey("ctrl", "w"); time.sleep(0.3)
        else:
            win.close()
    except Exception:
        pass
    time.sleep(0.5)
    if win32gui.IsWindow(hwnd):                       # còn sót thì gửi WM_CLOSE
        win32gui.PostMessage(hwnd, 0x0010, 0, 0)
        time.sleep(0.5)


def find_child(hwnd, classes):
    """Control con đầu tiên có tên lớp (class) nằm trong `classes`."""
    found = []
    win32gui.EnumChildWindows(
        hwnd, lambda h, _: found.append(h) if win32gui.GetClassName(h) in classes else None, None)
    if not found:
        raise RuntimeError(f"Control not found: {classes}")
    return found[0]


def editor_classes():
    """Tên lớp control soạn thảo của app đang dùng."""
    return ("Scintilla",) if cfg.APP == "npp" else ("RichEditD2DPT", "RICHEDIT50W", "Edit")


def editor_top(win):
    """y (pixel, tính trong ảnh chụp cửa sổ) của mép trên vùng soạn thảo; None nếu không tìm thấy control."""
    try:
        ctrl = find_child(win._hWnd, editor_classes())
    except RuntimeError:
        return None
    return win32gui.GetWindowRect(ctrl)[1] - visible_rect(win)[1]


def editor_text_left(win):
    """Notepad++: x (pixel, trong ảnh chụp cửa sổ) nơi cột đầu tiên của chữ bắt đầu.
    Hỏi thẳng Scintilla vị trí x của đầu dòng đang hiển thị (SCI_POINTXFROMPOSITION, đã gồm mọi lề: số dòng,
    bookmark, fold, lịch sử thay đổi... và phần cuộn ngang); nếu không được thì cộng bề rộng các lề.
    Notepad thường không có lề nên trả 0."""
    if cfg.APP != "npp":
        return 0
    try:
        sci = find_child(win._hWnd, ("Scintilla",))
    except RuntimeError:
        return 0
    ctrl_left = win32gui.GetWindowRect(sci)[0] - visible_rect(win)[0]
    first_vis = win32gui.SendMessage(sci, 2152, 0, 0)                  # SCI_GETFIRSTVISIBLELINE
    doc_line = win32gui.SendMessage(sci, 2221, first_vis, 0)           # SCI_DOCLINEFROMVISIBLE
    pos = win32gui.SendMessage(sci, 2167, doc_line, 0)                 # SCI_POSITIONFROMLINE
    x = win32gui.SendMessage(sci, 2164, 0, pos)                        # SCI_POINTXFROMPOSITION
    margins = sum(win32gui.SendMessage(sci, 2243, i, 0) for i in range(5))      # SCI_GETMARGINWIDTHN
    dbg(f"[DEBUG] text_left: control_left={ctrl_left}, POINTXFROMPOSITION={x}, sum margins={margins}")
    return ctrl_left + (x if x > 0 else margins)


def min_text_x(win, first, last):
    """Notepad++: x (pixel, trong ảnh chụp cửa sổ) của ký tự đầu tiên KHÔNG phải khoảng trắng, nhỏ nhất trong các dòng
    first..last (số dòng của file, từ 1, bỏ qua dòng trống). Đã tính tab, thụt đầu dòng và cuộn ngang vì lấy từ Scintilla.
    Trả về None nếu không xác định được."""
    try:
        sci = find_child(win._hWnd, ("Scintilla",))
    except RuntimeError:
        return None
    ctrl_left = win32gui.GetWindowRect(sci)[0] - visible_rect(win)[0]
    xs = []
    for ln in range(first - 1, last):
        indent_pos = win32gui.SendMessage(sci, 2128, ln, 0)        # SCI_GETLINEINDENTPOSITION: ký tự đầu không phải trắng
        if indent_pos >= win32gui.SendMessage(sci, 2136, ln, 0):   # SCI_GETLINEENDPOSITION: dòng trống / chỉ có khoảng trắng
            continue
        xs.append(win32gui.SendMessage(sci, 2164, 0, indent_pos))  # SCI_POINTXFROMPOSITION
    return ctrl_left + min(xs) if xs else None


def editor_bottom(win):
    """y (pixel, trong ảnh chụp cửa sổ) của mép dưới vùng soạn thảo (trên thanh trạng thái); None nếu không có."""
    try:
        ctrl = find_child(win._hWnd, editor_classes())
    except RuntimeError:
        return None
    return win32gui.GetWindowRect(ctrl)[3] - visible_rect(win)[1]


# ============================================================================
# PHẦN 2: CALIB
# ============================================================================

_RECAL_DONE = set()         # các cấu hình đã đo lại trong lần chạy này
CALIB_MONITOR = None        # màn hình (left, top, right, bottom) lúc calib; phát hiện cửa sổ nhảy sang màn hình khác


class CalibMismatch(Exception):
    """Cửa sổ mở trên màn hình khác với lúc calib -> calib đã lưu không còn đúng."""


def ensure_no_wrap_notepad(win):
    """Notepad thường: tự tắt Word wrap nếu đang bật (Alt+Z). Nhận biết bằng file mẫu có dòng RẤT dài:
    khi KHÔNG wrap, mọi hàng chữ đều chạy tới sát mép phải; khi wrap, hàng cuối của mỗi dòng ngắn hơn.
    Cài đặt Word wrap của Notepad được nhớ lại nên các cửa sổ sau cũng tắt wrap."""
    for attempt in range(2):
        m = ink_mask(grab_window(win))
        W = m.shape[1]
        et, eb = editor_top(win), editor_bottom(win)
        region = m[(et or 0):(eb or m.shape[0]), : W - cfg.SCROLL_W]
        bs = bands(region.sum(axis=1) >= 2)
        short = [b for b in bs if not region[b[0]:b[1] + 1, int(W * 0.8):].any()]   # hàng không chạm mép phải
        if bs and not short:
            return True                                    # mọi hàng chạm mép phải -> Word wrap đã tắt
        if attempt == 0:
            print("[INFO] Notepad has Word wrap on -> turning it off (Alt+Z)")
            pyautogui.click(win.left + win.width // 2, win.top + win.height // 2)
            pyautogui.hotkey("alt", "z"); time.sleep(0.8)
    print("[WARNING] Could not turn off Word wrap automatically. Turn it off manually (View -> Word wrap) and run again.")
    return False


def calibrate():
    """Mở file mẫu (80 dòng toàn chữ H), đo line_y (dòng đầu) và line_h (khoảng cách 2 dòng)."""
    global CALIB_MONITOR
    calib_dir = tempfile.mkdtemp()
    tmp = os.path.join(calib_dir, f"calib_{int(time.time())}.txt")
    with open(tmp, "w") as f:
        # Bình thường dùng dòng NGẮN (không bị wrap dù Word wrap bật) để đo line_h/line_y ổn định.
        # Chỉ khi FORCE_NO_WRAP mới dùng dòng rất dài để nhận biết wrap đang bật hay tắt.
        f.write("\n".join(["H" * (400 if cfg.FORCE_NO_WRAP else 100)] * 80))
    win = open_window(tmp)
    if cfg.APP == "notepad" and cfg.FORCE_NO_WRAP:
        ensure_no_wrap_notepad(win)
    cal_img = grab_window(win)
    m = ink_mask(cal_img)
    W = m.shape[1]
    sub = m[:, int(W * 0.25): int(W * 0.45)]      # cột chữ (né lề số dòng của Notepad++)
    tops = [b[0] for b in bands(sub.sum(axis=1) >= 5)]
    diffs = np.diff(tops)
    h = float(np.median(diffs))
    i = next((k for k in range(len(diffs) - 1)
              if abs(diffs[k] - h) <= 1.5 and abs(diffs[k + 1] - h) <= 1.5), None)
    if i is None:
        os.makedirs(cfg.OUT_DIR, exist_ok=True)
        cal_img.save(os.path.join(cfg.OUT_DIR, "calib_fail.png"))       # lưu ảnh để xem script thấy gì
        print(f"[DEBUG] calibration failed: text bands={len(tops)}, tops={tops[:15]}, median h={h}")
        close_window(win)
        shutil.rmtree(calib_dir, ignore_errors=True)
        raise RuntimeError(f"Could not measure line_h. Saved image {os.path.join(cfg.OUT_DIR, 'calib_fail.png')} for inspection")
    j = i + 2
    while j < len(diffs) and abs(diffs[j] - h) <= 1.5:
        j += 1
    line_h = (tops[j] - tops[i]) / (j - i)
    line_y = tops[i]
    CALIB_MONITOR = window_monitor_rect(win)          # màn hình mà cửa sổ calib nằm trên
    close_window(win)
    shutil.rmtree(calib_dir, ignore_errors=True)      # xóa file calib
    return line_y, line_h


# ---------- Lưu / nạp calib ----------
def profile_key():
    """Khóa nhận dạng calib: app + cấu hình màn hình."""
    return f"{cfg.APP}|{screen_layout_key()}"


def _calib_path():
    return os.path.join(BASE_DIR, cfg.CALIB_FILE)


def _load_cache():
    try:
        with open(_calib_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_calibration(force=False):
    """Trả về (line_y, line_h). Dùng bản đã lưu nếu cùng cấu hình màn hình, ngược lại đo mới rồi lưu."""
    global CALIB_MONITOR
    key = profile_key()
    cache = _load_cache()
    # RECALIBRATE chỉ ép đo lại MỘT lần cho mỗi cấu hình trong 1 lần chạy (nhiều job cùng app không đo lại nhiều lần)
    if not (force or (cfg.RECALIBRATE and key not in _RECAL_DONE)) and key in cache:
        c = cache[key]
        CALIB_MONITOR = tuple(c["monitor"]) if c.get("monitor") else None
        print(f"[CALIB] using saved calibration ({c.get('saved_at', '?')}): line_y={c['line_y']}, line_h={c['line_h']:.2f}")
        return c["line_y"], c["line_h"]
    line_y, line_h = calibrate()
    _RECAL_DONE.add(key)
    cache[key] = {"line_y": line_y, "line_h": line_h,
                  "monitor": list(CALIB_MONITOR) if CALIB_MONITOR else None,
                  "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with open(_calib_path(), "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        print(f"[CALIB] measured and saved to {_calib_path()}")
    except OSError as e:
        print(f"[WARNING] could not save calibration: {e}")
    return line_y, line_h