# -*- coding: utf-8 -*-
"""
배미유니버스 원격 서버 — PC2에서 실행
PC1 배미유니버스로부터 TCP 명령을 받아 Lineage 창 2개에 키/클릭 실행
"""

import socket
import json
import threading
import time
import random
import sys
import ctypes
import ctypes.wintypes

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  설정 (여기만 수정)
PORT     = 9999      # PC1과 동일해야 함
COM_PORT = "COM5"    # Arduino COM 포트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

try:
    import serial
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False

import win32gui
import win32api
import win32con
import win32process
import psutil

_arduino = None
_arduino_lock = threading.Lock()

_KEY_CODES = {
    "F1":0x70,"F2":0x71,"F3":0x72,"F4":0x73,"F5":0x74,"F6":0x75,
    "F7":0x76,"F8":0x77,"F9":0x78,"F10":0x79,"F11":0x7A,"F12":0x7B,
    "1":0x31,"2":0x32,"3":0x33,"4":0x34,"5":0x35,
    "6":0x36,"7":0x37,"8":0x38,"9":0x39,"0":0x30,
    "Space":0x20,"Enter":0x0D,
    "A":0x41,"B":0x42,"C":0x43,"D":0x44,"E":0x45,
    "Q":0x51,"R":0x52,"S":0x53,"T":0x54,"W":0x57,
}

# ─── 로그 ────────────────────────────────
def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ─── Arduino ─────────────────────────────
def arduino_send(cmd: str):
    with _arduino_lock:
        if _arduino and _arduino.is_open:
            try:
                _arduino.write((cmd + "\n").encode())
            except Exception as e:
                log(f"Arduino 전송 오류: {e}")

def connect_arduino():
    global _arduino
    if not _SERIAL_OK:
        log("pyserial 없음 — win32 폴백 사용")
        return
    try:
        _arduino = serial.Serial(COM_PORT, 115200, timeout=1)
        time.sleep(1.5)
        log(f"Arduino 연결 완료: {COM_PORT}")
    except Exception as e:
        log(f"Arduino 연결 실패 ({COM_PORT}): {e}  →  win32 폴백 사용")

# ─── Win32 유틸 ──────────────────────────
def find_lineage_windows():
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
        if "lineage" in title.lower() or "lineage" in exe.lower():
            results.append((hwnd, title))
    win32gui.EnumWindows(cb, None)
    return results

def get_window_rect(hwnd):
    try:
        rect = ctypes.wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return win32gui.GetWindowRect(hwnd)

def force_foreground(hwnd):
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass

# ─── 명령 실행 ───────────────────────────
def execute_on_all(cmd_dict: dict) -> dict:
    windows = find_lineage_windows()
    if not windows:
        log("⚠ Lineage 창을 찾을 수 없음")
        return {"status": "error", "msg": "Lineage 창 없음"}

    action = cmd_dict.get("action", "")
    msgs = []
    ard = _arduino and _arduino.is_open

    for hwnd, title in windows:
        label = title[:28]
        try:
            if action == "key":
                key = cmd_dict.get("key", "F9")
                dur = cmd_dict.get("dur", 60)
                force_foreground(hwnd)
                time.sleep(0.1)
                if ard:
                    arduino_send(f"KEY:{key}:{dur}")
                    via = "Arduino"
                else:
                    vk = _KEY_CODES.get(key, 0x78)
                    win32api.keybd_event(vk, 0, 0, 0)
                    time.sleep(0.05)
                    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
                    via = "win32"
                log(f"  → [{via}] {label}  KEY:{key}")
                msgs.append(f"{label} KEY:{key}[{via}]")

            elif action == "dblclick":
                rel_x = cmd_dict.get("x", 0)
                rel_y = cmd_dict.get("y", 0)
                r = get_window_rect(hwnd)
                sx = r[0] + rel_x + random.randint(-2, 2)
                sy = r[1] + rel_y + random.randint(-2, 2)
                force_foreground(hwnd)
                time.sleep(0.1)
                win32api.SetCursorPos((sx, sy))
                time.sleep(0.05)
                if ard:
                    arduino_send("DBLCLICK")
                    via = "Arduino"
                else:
                    for _ in range(2):
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, sx, sy, 0, 0)
                        time.sleep(0.06)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,   sx, sy, 0, 0)
                        time.sleep(0.08)
                    via = "win32"
                log(f"  → [{via}] {label}  DBLCLICK ({sx},{sy})")
                msgs.append(f"{label} DBLCLICK[{via}]")

        except Exception as e:
            log(f"  ✕ {label} 오류: {e}")
            msgs.append(f"{label} ERR:{e}")

        time.sleep(0.3)   # 두 창 사이 간격

    return {"status": "ok", "msg": " | ".join(msgs), "count": len(windows)}

# ─── 클라이언트 처리 ─────────────────────
def handle_client(conn, addr):
    try:
        raw = conn.recv(4096).decode("utf-8")
        cmd = json.loads(raw)
        action = cmd.get("action", "")
        log(f"수신 [{addr[0]}] {cmd}")

        if action == "ping":
            wins = find_lineage_windows()
            ard_ok = bool(_arduino and _arduino.is_open)
            resp = {"status": "pong",
                    "windows": len(wins),
                    "arduino": ard_ok,
                    "titles": [t[:32] for _, t in wins]}
            conn.sendall(json.dumps(resp, ensure_ascii=False).encode())
            return

        result = execute_on_all(cmd)
        conn.sendall(json.dumps(result, ensure_ascii=False).encode())

    except Exception as e:
        log(f"클라이언트 처리 오류: {e}")
        try:
            conn.sendall(json.dumps({"status": "error", "msg": str(e)}).encode())
        except Exception:
            pass
    finally:
        conn.close()

# ─── 메인 ────────────────────────────────
def main():
    log("=" * 50)
    log("  배미유니버스 원격 서버  (PC2)")
    log("=" * 50)

    connect_arduino()

    wins = find_lineage_windows()
    log(f"Lineage 창 {len(wins)}개 감지:")
    for _, title in wins:
        log(f"  • {title}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(10)

    # 내 IP 출력 (PC1에서 입력할 주소)
    try:
        import socket as _s
        my_ip = _s.gethostbyname(_s.gethostname())
    except Exception:
        my_ip = "확인 필요"
    log(f"포트 {PORT} 대기 중")
    log(f"PC1에 입력할 이 PC의 IP: {my_ip}")
    log("-" * 50)

    while True:
        try:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            log("서버 종료")
            break
        except Exception as e:
            log(f"서버 오류: {e}")

if __name__ == "__main__":
    main()
