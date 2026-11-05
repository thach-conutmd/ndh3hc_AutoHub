CÔNG CỤ CHỤP DÒNG TRONG NOTEPAD / NOTEPAD++
===========================================
Cài:   pip install pyautogui pillow pygetwindow pywin32 numpy      (Windows, Python 3.11+ hoặc cài thêm tomli)
Chạy:  python capture.py                       (dùng settings.toml cạnh script)
       python capture.py a.toml b.toml         (nhiều file .toml; hỗ trợ cfg\*.toml)

3 FILE CHÍNH
  get_input.py   Đọc & kiểm tra .toml, ghi thông số vào cfg; Call(mode, path, key) -> (start, end)
                 (THÊM LOGIC TÌM RANGE vào find_block / find_cnt, đăng ký MODE mới trong FINDERS)
  calib.py       Tiện ích cửa sổ/màn hình/ảnh dùng chung + calib (đo line_y, line_h; lưu/nạp theo màn hình)
  capture.py     File chạy chính: đọc dòng cần chụp, cuộn, tính khung cắt, lưu ảnh, điều phối các job

settings.toml    Nơi nhập thông số (khối [common] và các khối [[job]])
calib_cache.json (tự sinh) calib đã lưu          out/  (tự sinh) ảnh kết quả

KHI NÀO SỬA FILE NÀO
  Đổi thông số chụp                  -> settings.toml
  Báo lỗi nhập liệu / thêm thông số / logic tìm range, NPP_EXE, CALIB_FILE -> get_input.py
  Ảnh lệch dòng, ảnh đen khi đổi màn hình, đo line_h sai, đóng/mở cửa sổ -> calib.py
  Cuộn sai dòng, khung cắt sai, đặt tên ảnh, thêm xuất Excel              -> capture.py

