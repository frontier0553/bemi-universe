# -*- coding: utf-8 -*-
import ctypes
import sys
import time
import random

import win32gui
import win32con
import win32api
import win32process
import psutil

from tkinter import messagebox
import core.arduino as _ar_mod
from core.arduino import arduino_send

# ─────────────────────────────────────────
#  관리자 권한
# ─────────────────────────────────────────
def _is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def _restart_as_admin():
    try:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("오류", f"관리자 권한 재시작 실패:\n{e}")

# ─────────────────────────────────────────
#  Win32 유틸
# ─────────────────────────────────────────
def enum_visible_windows():
    results = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return
        exe = ""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = psutil.Process(pid).name()
        except Exception:
            pass
        results.append((hwnd, title, exe))
    win32gui.EnumWindows(cb, None)
    return results

def force_foreground(hwnd):
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass

def get_window_rect(hwnd):
    """Windows 10 invisible border 보정 — DWM 실제 가시 영역 반환"""
    try:
        import ctypes.wintypes
        rect = ctypes.wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return win32gui.GetWindowRect(hwnd)

# ─ 키코드 테이블 ────────────────────────────
# SendMessageA — 모듈 수준에서 한 번만 argtypes 설정
_SendMessageA = ctypes.windll.user32.SendMessageA
_SendMessageA.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulong, ctypes.c_long]
_SendMessageA.restype  = ctypes.c_long

_KEY_CODES = {
    "F1":0x70,"F2":0x71,"F3":0x72,"F4":0x73,"F5":0x74,"F6":0x75,
    "F7":0x76,"F8":0x77,"F9":0x78,"F10":0x79,"F11":0x7A,"F12":0x7B,
    "1":0x31,"2":0x32,"3":0x33,"4":0x34,"5":0x35,
    "6":0x36,"7":0x37,"8":0x38,"9":0x39,"0":0x30,
    "Space":0x20,"Enter":0x0D,"Tab":0x09,
    "A":0x41,"B":0x42,"C":0x43,"D":0x44,"E":0x45,
    "Q":0x51,"R":0x52,"S":0x53,"T":0x54,"W":0x57,
}

def smooth_move(tx, ty, steps=20):
    """현재 위치에서 목표까지 사람처럼 부드럽게 이동 (smoothstep)"""
    cx, cy = win32api.GetCursorPos()
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)
        win32api.SetCursorPos((int(cx + (tx - cx) * t), int(cy + (ty - cy) * t)))
        time.sleep(random.uniform(0.008, 0.014))

def click_at(hwnd, rel_x, rel_y, key_name="F9", mode="mouse"):
    """포커스 이동 → 커서 이동(SetCursorPos) → 클릭(Arduino HID) / 키(Arduino HID)
    GameGuard: 커서 이동은 감지 안 함, 클릭/키 이벤트만 감지 → Arduino로 우회.
    반환: (절대x, 절대y, 사용경로문자열)"""
    force_foreground(hwnd)
    time.sleep(0.07)
    rect = get_window_rect(hwnd)
    sx = rect[0] + rel_x + random.randint(-2, 2)
    sy = rect[1] + rel_y + random.randint(-2, 2)
    smooth_move(sx, sy)
    win32api.SetCursorPos((sx, sy))
    if win32gui.GetForegroundWindow() != hwnd:
        force_foreground(hwnd)
        time.sleep(0.07)
    time.sleep(0.05)

    ard = _ar_mod._arduino and _ar_mod._arduino.is_open

    if mode == "mouse":
        if ard:
            arduino_send("DBLCLICK")
            return sx, sy, "Arduino"
        else:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, sx, sy, 0, 0)
            time.sleep(random.uniform(0.04, 0.08))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, sx, sy, 0, 0)
            time.sleep(0.08)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, sx, sy, 0, 0)
            time.sleep(random.uniform(0.04, 0.08))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, sx, sy, 0, 0)
            return sx, sy, "win32"
    else:
        dur = random.randint(40, 90)
        if ard:
            arduino_send(f"KEY:{key_name}:{dur}")
            return sx, sy, f"Arduino:{key_name}"
        else:
            vk = _KEY_CODES.get(key_name, 0x78)
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            return sx, sy, f"win32:{key_name}"
