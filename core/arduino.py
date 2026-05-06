# -*- coding: utf-8 -*-
import threading
import sys

try:
    import serial
    import serial.tools.list_ports
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False

# 아두이노 시리얼 연결 (전역)
_arduino: "serial.Serial | None" = None
_arduino_lock = threading.Lock()

def arduino_send(cmd: str):
    with _arduino_lock:
        if _arduino and _arduino.is_open:
            try:
                _arduino.write((cmd + "\n").encode())
            except Exception as e:
                print(f"[Arduino 전송 오류] {cmd}: {e}", file=sys.stderr)
