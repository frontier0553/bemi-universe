# -*- coding: utf-8 -*-
import ctypes
import os
import sys

# ── 중복 실행 방지 ─────────────────────────
_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, True, "배미유니버스_SingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
    import tkinter as tk
    from tkinter import messagebox
    _r = tk.Tk(); _r.withdraw()
    messagebox.showwarning("배미유니버스", "이미 실행 중입니다.\n기존 창을 확인해주세요.")
    _r.destroy()
    sys.exit(0)

# 작업표시줄 아이콘을 Python.exe가 아닌 이 앱 아이콘으로 표시
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bemi.universe.v1")
except Exception:
    pass

# DPI 인식
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from core.win32_utils import _is_admin, _restart_as_admin
from ui.mode_select import ModeSelectWindow
from ui.hey_jangsa import AppHeyJangsa
from ui.yojong_buff import App
from ui.auto_hunt import AppAutoHunt

if __name__ == "__main__":
    import traceback, tempfile
    _log = os.path.join(tempfile.gettempdir(), "bemi_crash.log")
    try:
        if not _is_admin():
            _restart_as_admin()
        sel = ModeSelectWindow()
        sel.mainloop()
        mode = sel.selected_mode
        if mode == "요정버프":
            app = App()
            app.lift()
            app.focus_force()
            app.mainloop()
        elif mode in ("헤이장사_싱글", "헤이장사_멀티_호스트", "헤이장사_멀티_클라이언트"):
            app = AppHeyJangsa(mode)
            app.lift()
            app.focus_force()
            app.mainloop()
        elif mode == "자동사냥":
            app = AppAutoHunt()
            app.lift()
            app.focus_force()
            app.mainloop()
    except Exception:
        with open(_log, "w", encoding="utf-8") as _f:
            traceback.print_exc(file=_f)
        os.startfile(_log)
