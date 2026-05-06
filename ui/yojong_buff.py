# -*- coding: utf-8 -*-
import threading
import time
import random
import ctypes
import os
import json
import re

import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageGrab

import win32gui
import win32con
import win32api
import win32process
import psutil

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

from core.constants import _CONFIG_FILE, BG_MAIN, BG_CARD, TEXT_DIM, ACCENT, SUCCESS, DANGER, PURPLE, DARK, LIGHT
import core.arduino as _ar_mod
from core.arduino import _arduino_lock, arduino_send, _SERIAL_OK
import core.ocr_engine as _ocr_mod
from core.ocr_engine import ocr_read, _init_ocr
from core.win32_utils import (
    _SendMessageA, _KEY_CODES, enum_visible_windows, force_foreground,
    get_window_rect, click_at, _is_admin, _restart_as_admin,
)
from core.icon import _apply_icon
from ui.region_selector import RegionSelector
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("배미유니버스")
        self.geometry("760x1020")
        self.after(100, lambda: _apply_icon(self))
        self.resizable(False, False)
        self.configure(fg_color=BG_MAIN)

        self.windows_list = []
        self.hwnd1 = self.hwnd2 = None
        self.pos1  = self.pos2  = None
        self._run_evt          = threading.Event()   # self.running
        self._click_count      = 0

        self.ocr_region   = [None, None]
        self._ocr_images  = [None, None]
        self._ocr_evt     = threading.Event()        # self._ocr_running
        self._ocr_interval_var = ctk.StringVar(value="2")
        self._ocr_values       = [None, None]   # (current, max) 파싱 결과
        self._auto_loop_var    = ctk.BooleanVar(value=False)   # OCR 자동 루프 시작
        self._win_name_var     = [ctk.StringVar(value=""), ctk.StringVar(value="")]
        self._act_lbl_var      = [ctk.StringVar(value="창1:"), ctk.StringVar(value="창2:")]
        self._chat_win_rb      = [None, None]
        self._pos_active_var   = [ctk.BooleanVar(value=True), ctk.BooleanVar(value=True)]
        self._is_dark           = True
        self._action_key_var    = [ctk.StringVar(value="F9"), ctk.StringVar(value="F9")]
        self._action_mode_var   = [ctk.StringVar(value="mouse"), ctk.StringVar(value="mouse")]
        self._chat_check_vars     = [ctk.BooleanVar(value=(i==0)) for i in range(3)]
        self._chat_interval_var   = ctk.StringVar(value="60")
        self._chat_random_var     = ctk.StringVar(value="10")
        self._chat_evt = threading.Event()           # self._chat_repeat_running

        self._remote_ip_var      = ctk.StringVar(value="192.168.0.")
        self._remote_port_var    = ctk.StringVar(value="9999")
        self._remote_trigkey_var = ctk.StringVar(value="F7")
        self._remote_sendkey_var = ctk.StringVar(value="F9")
        self._remote_enabled_var = ctk.BooleanVar(value=False)

        self._build_ui()
        self.refresh_windows()
        self._start_f12_listener()
        threading.Thread(target=self._load_ocr, daemon=True).start()
        self.after(200, self._load_config)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_ocr(self):
        self.after(0, lambda: self.log("OCR 엔진 로딩 중..."))
        _init_ocr()
        msg = f"OCR 엔진 준비: {_ocr_mod.OCR_ENGINE}" if _ocr_mod.OCR_ENGINE else "OCR 엔진 없음 — easyocr 또는 tesseract 설치 필요"
        self.after(0, lambda: self.log(msg))

    # ─── UI 구성 ───────────────────────────
    def _build_ui(self):
        self._card_frames  = []   # 카드 outer frames
        self._inner_frames = []   # (frame, dark_color, light_color)
        self._text_widgets = []   # (widget, dark_color, light_color) — text_color 추적
        self._hdr_btns     = []   # 헤더 버튼들 (text_color + border_color 변경)

        # 헤더
        self._hdr = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=64)
        self._hdr.pack(fill="x"); self._hdr.pack_propagate(False)
        hdr = self._hdr
        self._rt(ctk.CTkLabel(hdr, text="  ⚡  배미유니버스",
                     font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                     text_color="white"), "#1E293B").pack(side="left", padx=20)
        self._mode_btn = ctk.CTkButton(
            hdr, text="☀ Light", width=90, height=32,
            fg_color="transparent", border_width=1, border_color="#334155",
            text_color="white", font=ctk.CTkFont(size=12), command=self._toggle_mode)
        self._mode_btn.pack(side="right", padx=(0,16))
        self._hdr_btns.append(self._mode_btn)
        _btn_save = ctk.CTkButton(
            hdr, text="💾 저장", width=72, height=32,
            fg_color="transparent", border_width=1, border_color="#334155",
            text_color="white", font=ctk.CTkFont(size=12), command=self._save_config)
        _btn_save.pack(side="right", padx=(0,4))
        self._hdr_btns.append(_btn_save)
        _btn_log = ctk.CTkButton(
            hdr, text="📋 로그", width=72, height=32,
            fg_color="transparent", border_width=1, border_color="#334155",
            text_color="white", font=ctk.CTkFont(size=12), command=self._toggle_log_popup)
        _btn_log.pack(side="right", padx=(0,4))
        self._hdr_btns.append(_btn_log)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_MAIN, scrollbar_button_color="#334155")
        self._scroll.pack(fill="both", expand=True)
        scroll = self._scroll

        self._build_arduino_section(scroll)
        self._build_window_section(scroll)
        self._build_layout_section(scroll)
        self._build_position_section(scroll)
        self._build_delay_section(scroll)
        self._build_control_section(scroll)
        self._build_chat_section(scroll)
        self._build_ocr_section(scroll)
        self._build_remote_section(scroll)
        self._log_popup = None
        self._build_log_popup()

    # ─── 스레드 플래그 프로퍼티 (threading.Event 래핑) ───
    @property
    def running(self):
        return self._run_evt.is_set()

    @running.setter
    def running(self, val):
        self._run_evt.set() if val else self._run_evt.clear()

    @property
    def _chat_repeat_running(self):
        return self._chat_evt.is_set()

    @_chat_repeat_running.setter
    def _chat_repeat_running(self, val):
        self._chat_evt.set() if val else self._chat_evt.clear()

    @property
    def _ocr_running(self):
        return self._ocr_evt.is_set()

    @_ocr_running.setter
    def _ocr_running(self, val):
        self._ocr_evt.set() if val else self._ocr_evt.clear()

    def _reg(self, fr, dark_c, light_c):
        self._inner_frames.append((fr, dark_c, light_c))
        return fr

    def _rt(self, w, light_c="#1E293B"):
        self._text_widgets.append((w, "#FFFFFF", light_c))
        return w

    def _card(self, parent, title, color=None):
        outer = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12)
        outer.pack(fill="x", padx=16, pady=6)
        self._card_frames.append(outer)
        ctk.CTkLabel(outer, text=title,
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=color or ACCENT).pack(anchor="w", padx=16, pady=(12,4))
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=(0,12))
        return inner

    def _build_arduino_section(self, p):
        f = self._card(p, "⚡ Arduino HID 연결", color="#F59E0B")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x")
        self._rt(ctk.CTkLabel(row, text="COM:", font=ctk.CTkFont(size=13), text_color="white", width=44)).pack(side="left")
        self._com_var = ctk.StringVar(value="COM3")
        ports = [p.device for p in serial.tools.list_ports.comports()] if _SERIAL_OK else ["COM3"]
        self._com_combo = ctk.CTkComboBox(row, values=ports, variable=self._com_var,
                                          width=120, font=ctk.CTkFont(size=13),
                                          button_color="#F59E0B", button_hover_color="#D97706")
        self._com_combo.pack(side="left", padx=(4,8))
        self._ard_btn = ctk.CTkButton(row, text="연결", width=80, height=32,
                                      fg_color="#F59E0B", hover_color="#D97706",
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      command=self._toggle_arduino)
        self._ard_btn.pack(side="left", padx=(0,8))
        ctk.CTkButton(row, text="🔄", width=36, height=32,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=13),
                      command=self._refresh_ports).pack(side="left")
        self._ard_status = ctk.CTkLabel(row, text="● 미연결",
                                        font=ctk.CTkFont(size=12), text_color=TEXT_DIM)
        self._ard_status.pack(side="left", padx=12)

    def _refresh_ports(self):
        if not _SERIAL_OK: return
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._com_combo.configure(values=ports if ports else ["COM3"])

    def _toggle_arduino(self):
        with _arduino_lock:
            already_open = _ar_mod._arduino and _ar_mod._arduino.is_open
        if already_open:
            with _arduino_lock:
                _ar_mod._arduino.close()
                _ar_mod._arduino = None
            self._ard_btn.configure(text="연결", fg_color="#F59E0B", hover_color="#D97706")
            self._ard_status.configure(text="● 미연결", text_color=TEXT_DIM)
            self.log("Arduino 연결 해제")
        else:
            if not _SERIAL_OK:
                self.log("pyserial 미설치 — pip install pyserial"); return
            try:
                port = serial.Serial(self._com_var.get(), 115200, timeout=1)
            except Exception as e:
                self.log(f"Arduino 연결 실패: {e}"); return
            time.sleep(1.5)  # 락 밖에서 대기 — arduino_send() 블로킹 방지
            with _arduino_lock:
                _ar_mod._arduino = port
            self._ard_btn.configure(text="해제", fg_color=DANGER, hover_color="#B91C1C")
            self._ard_status.configure(text="● 연결됨", text_color=SUCCESS)
            self.log(f"Arduino 연결 완료: {self._com_var.get()}")

    def _build_window_section(self, p):
        f = self._card(p, "① 윈도우 선택")
        for i, txt in enumerate(["창 1","창 2"]):
            row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", pady=4)
            self._rt(ctk.CTkLabel(row, text=txt, width=44,
                         font=ctk.CTkFont(size=13, weight="bold"), text_color="white")).pack(side="left")
            combo = ctk.CTkComboBox(row, width=510, state="readonly",
                                    font=ctk.CTkFont(size=12),
                                    button_color=ACCENT, button_hover_color="#2563EB",
                                    dropdown_font=ctk.CTkFont(size=11),
                                    command=lambda v, idx=i: self._on_window_select(idx))
            combo.pack(side="left", padx=(6,0))
            if i == 0: self.combo1 = combo
            else:       self.combo2 = combo
        ctk.CTkButton(f, text="🔄  목록 새로고침", width=160, height=32,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=12), command=self.refresh_windows
                      ).pack(anchor="e", pady=(6,0))

    def _on_window_select(self, changed_idx):
        combos = [self.combo1, self.combo2]
        all_vals = list(combos[changed_idx].cget("values"))
        chosen = combos[changed_idx].get()
        other = combos[1 - changed_idx]
        other_vals = [v for v in all_vals if v != chosen]
        current_other = other.get()
        other.configure(values=other_vals)
        if current_other == chosen:
            other.set(other_vals[0] if other_vals else "")
        self._update_win_labels()

    def _build_position_section(self, p):
        f = self._card(p, "③ 클릭 위치 지정  (창 기준 상대 좌표)")
        self._pos_x_var = [ctk.StringVar(value="0"), ctk.StringVar(value="0")]
        self._pos_y_var = [ctk.StringVar(value="0"), ctk.StringVar(value="0")]
        for i in range(1, 3):
            row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", pady=5)
            ctk.CTkCheckBox(row, text="", variable=self._pos_active_var[i-1],
                            width=24, checkbox_width=18, checkbox_height=18
                            ).pack(side="left", padx=(0,4))
            badge = self._reg(ctk.CTkFrame(row, fg_color="#1E3A5F", corner_radius=8, width=44, height=32), "#1E3A5F", "#BFDBFE")
            badge.pack(side="left"); badge.pack_propagate(False)
            ctk.CTkLabel(badge, text=f"창{i}", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=ACCENT).place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(row, textvariable=self._win_name_var[i-1],
                         font=ctk.CTkFont(size=10), text_color=TEXT_DIM).pack(side="left", padx=(4,4))
            ctk.CTkLabel(row, text="X:", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left", padx=(4,2))
            ex = ctk.CTkEntry(row, textvariable=self._pos_x_var[i-1], width=60, font=ctk.CTkFont(size=12))
            ex.pack(side="left", padx=(0,8))
            ex.bind("<Return>",   lambda e, n=i: self._apply_pos_entry(n))
            ex.bind("<FocusOut>", lambda e, n=i: self._apply_pos_entry(n))
            ctk.CTkLabel(row, text="Y:", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left", padx=(0,2))
            ey = ctk.CTkEntry(row, textvariable=self._pos_y_var[i-1], width=60, font=ctk.CTkFont(size=12))
            ey.pack(side="left", padx=(0,8))
            ey.bind("<Return>",   lambda e, n=i: self._apply_pos_entry(n))
            ey.bind("<FocusOut>", lambda e, n=i: self._apply_pos_entry(n))
            ctk.CTkButton(row, text="📍 지정(5초)", width=110, height=32,
                          fg_color=ACCENT, hover_color="#2563EB",
                          font=ctk.CTkFont(size=12), command=lambda n=i: self.pick_position(n)
                          ).pack(side="left", padx=(8,0))

    def _build_delay_section(self, p):
        f = self._card(p, "④ 랜덤 딜레이 (초)")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x")
        self._rt(ctk.CTkLabel(row, text="최소", font=ctk.CTkFont(size=13), text_color="white", width=36)).pack(side="left")
        self.min_delay = ctk.CTkEntry(row, width=80, font=ctk.CTkFont(size=13))
        self.min_delay.insert(0,"1.0"); self.min_delay.pack(side="left", padx=(4,14))
        self._rt(ctk.CTkLabel(row, text="최대", font=ctk.CTkFont(size=13), text_color="white", width=36)).pack(side="left")
        self.max_delay = ctk.CTkEntry(row, width=80, font=ctk.CTkFont(size=13))
        self.max_delay.insert(0,"3.0"); self.max_delay.pack(side="left", padx=(4,0))
        ctk.CTkLabel(row, text="초  사이 랜덤 대기", font=ctk.CTkFont(size=12), text_color=TEXT_DIM
                     ).pack(side="left", padx=8)
        pr = ctk.CTkFrame(f, fg_color="transparent"); pr.pack(fill="x", pady=(6,0))
        ctk.CTkLabel(pr, text="프리셋:", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left")
        for label,mn,mx in [("빠름 0.3~1s","0.3","1.0"),("보통 1~3s","1.0","3.0"),("느림 3~8s","3.0","8.0")]:
            ctk.CTkButton(pr, text=label, width=110, height=28,
                          fg_color="#334155", hover_color="#475569", font=ctk.CTkFont(size=11),
                          command=lambda a=mn,b=mx: self._set_delay(a,b)).pack(side="left", padx=4)
        # 창별 액션 모드 선택
        _key_opts = ["F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
                     "1","2","3","4","5","6","7","8","9","0",
                     "A","B","C","D","E","Q","R","S","T","W","Space","Enter"]
        for i in range(2):
            mr = self._reg(ctk.CTkFrame(f, fg_color="#0F172A", corner_radius=6), "#0F172A", "#E8EDF5")
            mr.pack(fill="x", pady=(8,0))
            ctk.CTkLabel(mr, textvariable=self._act_lbl_var[i],
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=ACCENT, width=88).pack(side="left", padx=(8,4))
            ctk.CTkRadioButton(mr, text="🖱 마우스더블클릭",
                               value="mouse", variable=self._action_mode_var[i],
                               font=ctk.CTkFont(size=12)).pack(side="left", padx=(0,12))
            ctk.CTkRadioButton(mr, text="⌨ 키보드",
                               value="key", variable=self._action_mode_var[i],
                               font=ctk.CTkFont(size=12)).pack(side="left", padx=(0,6))
            ctk.CTkComboBox(mr, values=_key_opts, variable=self._action_key_var[i],
                            width=90, state="readonly", font=ctk.CTkFont(size=12),
                            button_color=ACCENT, button_hover_color="#2563EB",
                            ).pack(side="left", padx=(0,8))

    def _set_delay(self, mn, mx):
        self.min_delay.delete(0,"end"); self.min_delay.insert(0, mn)
        self.max_delay.delete(0,"end"); self.max_delay.insert(0, mx)

    def _set_win_size(self, w, h):
        self.win_w.delete(0,"end"); self.win_w.insert(0, w)
        self.win_h.delete(0,"end"); self.win_h.insert(0, h)

    def _build_layout_section(self, p):
        f = self._card(p, "② 창 정렬 / 크기")
        row1 = ctk.CTkFrame(f, fg_color="transparent"); row1.pack(fill="x", pady=4)
        self._rt(ctk.CTkLabel(row1, text="배치:", font=ctk.CTkFont(size=13), text_color="white", width=44)).pack(side="left")
        self.layout_var = ctk.StringVar(value="좌우")
        for opt,ico in [("좌우","⬛⬛"),("상하","🔲"),("겹침","🗗")]:
            ctk.CTkRadioButton(row1, text=f"{ico} {opt}", value=opt, variable=self.layout_var,
                               font=ctk.CTkFont(size=12), radiobutton_width=16, radiobutton_height=16
                               ).pack(side="left", padx=10)
        row2 = ctk.CTkFrame(f, fg_color="transparent"); row2.pack(fill="x", pady=4)
        self._rt(ctk.CTkLabel(row2, text="크기:", font=ctk.CTkFont(size=13), text_color="white", width=44)).pack(side="left")
        ctk.CTkLabel(row2, text="가로", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left")
        self.win_w = ctk.CTkEntry(row2, width=80, font=ctk.CTkFont(size=12))
        self.win_w.insert(0,"800"); self.win_w.pack(side="left", padx=(4,12))
        ctk.CTkLabel(row2, text="세로", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left")
        self.win_h = ctk.CTkEntry(row2, width=80, font=ctk.CTkFont(size=12))
        self.win_h.insert(0,"600"); self.win_h.pack(side="left", padx=(4,16))
        ctk.CTkButton(row2, text="✔  창 정렬 적용", width=150, height=32,
                      fg_color="#0F4C81", hover_color="#0D3D6C",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self.arrange_windows).pack(side="left")
        row3 = ctk.CTkFrame(f, fg_color="transparent"); row3.pack(fill="x", pady=(0,2))
        ctk.CTkLabel(row3, text="프리셋:", font=ctk.CTkFont(size=12), text_color=TEXT_DIM, width=44).pack(side="left")
        for label, w, h in [("800×600","800","600"),("1024×768","1024","768"),
                             ("1280×720","1280","720"),("1366×768","1366","768"),("1920×1080","1920","1080")]:
            ctk.CTkButton(row3, text=label, width=96, height=26,
                          fg_color="#334155", hover_color="#475569", font=ctk.CTkFont(size=11),
                          command=lambda w=w, h=h: self._set_win_size(w, h)
                          ).pack(side="left", padx=3)

    def _build_control_section(self, p):
        f = ctk.CTkFrame(p, fg_color="transparent"); f.pack(fill="x", padx=16, pady=8)
        self.start_btn = ctk.CTkButton(f, text="▶   시 작", height=48,
                                       fg_color=SUCCESS, hover_color="#16A34A",
                                       font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                                       command=self.start)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0,6))
        self.stop_btn = ctk.CTkButton(f, text="■   중 지   (Backspace)", height=48,
                                      fg_color="#374151", hover_color=DANGER,
                                      font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                                      state="disabled", command=self.stop)
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(6,0))
        sb = self._reg(ctk.CTkFrame(p, fg_color=BG_CARD, corner_radius=8, height=36), BG_CARD, "#FFFFFF")
        sb.pack(fill="x", padx=16, pady=(0,6)); sb.pack_propagate(False)
        self._dot = ctk.CTkLabel(sb, text="●", text_color="#374151", font=ctk.CTkFont(size=14))
        self._dot.pack(side="left", padx=(12,4))
        self.status_lbl = ctk.CTkLabel(sb, text="대기 중", font=ctk.CTkFont(size=12), text_color=TEXT_DIM)
        self.status_lbl.pack(side="left")
        self.count_lbl = ctk.CTkLabel(sb, text="클릭 수: 0", font=ctk.CTkFont(size=12), text_color=TEXT_DIM)
        self.count_lbl.pack(side="right", padx=12)

    # ── 채팅 전송 섹션 ──────────────────────
    def _build_chat_section(self, p):
        f = self._card(p, "💬 채팅 전송 (한글 지원)", color="#F59E0B")

        # 대상 선택
        row1 = ctk.CTkFrame(f, fg_color="transparent"); row1.pack(fill="x", pady=(0,4))
        self._rt(ctk.CTkLabel(row1, text="대상:", font=ctk.CTkFont(size=12), text_color="white", width=44)).pack(side="left")
        self._chat_target_var = ctk.StringVar(value="창1")
        for j, val in enumerate(["창1", "창2", "둘다"]):
            rb = ctk.CTkRadioButton(row1, text=val, value=val, variable=self._chat_target_var,
                                    font=ctk.CTkFont(size=12),
                                    radiobutton_width=16, radiobutton_height=16)
            rb.pack(side="left", padx=8)
            if j < 2: self._chat_win_rb[j] = rb

        # 광고 문구 슬롯 3개 (체크된 것만 반복 전송)
        self._chat_entries = []
        for i in range(3):
            slot = self._reg(ctk.CTkFrame(f, fg_color="#0A0F1E", corner_radius=4), "#0A0F1E", "#EFF6FF")
            slot.pack(fill="x", pady=2)
            ctk.CTkCheckBox(slot, text=f"#{i+1}", variable=self._chat_check_vars[i],
                            width=48, font=ctk.CTkFont(size=12),
                            checkbox_width=16, checkbox_height=16
                            ).pack(side="left", padx=(6,4))
            entry = ctk.CTkEntry(slot, placeholder_text=f"광고 문구 {i+1}  (\\fA한글)",
                                  font=ctk.CTkFont(size=12), height=32)
            entry.pack(side="left", expand=True, fill="x", padx=(0,4))
            entry.bind("<Return>", lambda e, idx=i: self._send_slot(idx))
            ctk.CTkButton(slot, text="전송", width=50, height=28,
                          fg_color="#F59E0B", hover_color="#D97706",
                          font=ctk.CTkFont(size=11, weight="bold"),
                          command=lambda idx=i: self._send_slot(idx)
                          ).pack(side="left", padx=(0,6))
            self._chat_entries.append(entry)

        # 광고 반복 설정
        rr = self._reg(ctk.CTkFrame(f, fg_color="#0F172A", corner_radius=6), "#0F172A", "#E8EDF5")
        rr.pack(fill="x")
        self._chat_start_btn = ctk.CTkButton(
            rr, text="▶ 반복 시작", width=110, height=30,
            fg_color=SUCCESS, hover_color="#16A34A",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._start_chat_repeat)
        self._chat_start_btn.pack(side="left", padx=(8,4), pady=6)
        self._chat_stop_btn = ctk.CTkButton(
            rr, text="■ 반복 중지", width=110, height=30,
            fg_color="#374151", hover_color=DANGER,
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled", command=self._stop_chat_repeat)
        self._chat_stop_btn.pack(side="left", padx=(0,10), pady=6)
        ctk.CTkLabel(rr, text="주기:", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left")
        ctk.CTkEntry(rr, textvariable=self._chat_interval_var, width=52,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4,2))
        ctk.CTkLabel(rr, text="초  ±", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left")
        ctk.CTkEntry(rr, textvariable=self._chat_random_var, width=44,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4,4))
        ctk.CTkLabel(rr, text="초 랜덤", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left")

    def _send_slot(self, idx):
        text = self._chat_entries[idx].get().strip()
        if text:
            self._send_text(text)

    def _send_text(self, text, done_event: "threading.Event | None" = None):
        if not text:
            if done_event: done_event.set()
            return
        target = self._chat_target_var.get()
        hwnds = []
        if target in ("창1", "둘다"):
            h = self._get_hwnd(self.combo1)
            if h: hwnds.append(h)
        if target in ("창2", "둘다"):
            h = self._get_hwnd(self.combo2)
            if h: hwnds.append(h)
        if not hwnds:
            self.log("채팅: 창을 먼저 선택해주세요.")
            if done_event: done_event.set()
            return

        try:
            encoded = text.encode('cp949')
        except UnicodeEncodeError:
            encoded = text.encode('ascii', errors='replace')

        def _do_send(hwnd):
            force_foreground(hwnd)
            time.sleep(0.2)
            # Enter로 채팅창 열기 (Arduino - GameGuard 우회)
            if _ar_mod._arduino and _ar_mod._arduino.is_open:
                arduino_send("KEY:Enter:50")
            else:
                _SendMessageA(hwnd, 0x0102, 0x0D, 0)
            time.sleep(0.35)
            # CP949 바이트 단위 WM_CHAR 전송
            for byte in encoded:
                _SendMessageA(hwnd, 0x0102, byte, 0)
                time.sleep(random.uniform(0.04, 0.07))
            time.sleep(0.2)
            # Enter로 전송
            if _ar_mod._arduino and _ar_mod._arduino.is_open:
                arduino_send("KEY:Enter:50")
            else:
                _SendMessageA(hwnd, 0x0102, 0x0D, 0)

        def _worker():
            for hwnd in hwnds:
                _do_send(hwnd)
                time.sleep(0.3)
            self.after(0, lambda: self.log(f"💬 채팅 전송 [{target}]: {text}"))
            if done_event:
                done_event.set()

        threading.Thread(target=_worker, daemon=True).start()

    def _start_chat_repeat(self):
        active = [self._chat_entries[i].get().strip()
                  for i in range(len(self._chat_entries)) if self._chat_check_vars[i].get()]
        active = [t for t in active if t]
        if not active:
            self.log("채팅: 체크된 광고 문구를 먼저 입력해주세요."); return
        self._chat_repeat_running = True
        self._chat_start_btn.configure(state="disabled")
        self._chat_stop_btn.configure(state="normal", fg_color=DANGER, hover_color="#B91C1C")
        self.log(f"광고 반복 시작 ({len(active)}개 문구) — {self._chat_interval_var.get()}±{self._chat_random_var.get()}초")
        threading.Thread(target=self._chat_repeat_worker, daemon=True).start()

    def _stop_chat_repeat(self):
        self._chat_repeat_running = False
        self._chat_start_btn.configure(state="normal")
        self._chat_stop_btn.configure(state="disabled", fg_color="#374151", hover_color=DANGER)
        self.log("광고 반복 중지")

    def _chat_repeat_worker(self):
        slot_idx = 0
        while self._chat_repeat_running:
            # 체크 + 텍스트 있는 슬롯만 수집
            active = [(i, self._chat_entries[i].get().strip())
                      for i in range(len(self._chat_entries)) if self._chat_check_vars[i].get()]
            active = [(i, t) for i, t in active if t]
            if not active:
                time.sleep(1)
                continue
            _, text = active[slot_idx % len(active)]
            slot_idx += 1
            send_done = threading.Event()
            self.after(0, lambda t=text, ev=send_done: self._send_text(t, done_event=ev))
            send_done.wait(timeout=30)   # 전송 완료 후 카운트다운 시작
            if not self._chat_repeat_running:
                break
            try:
                base = float(self._chat_interval_var.get())
                rnd  = float(self._chat_random_var.get())
            except ValueError:
                base, rnd = 60.0, 10.0
            wait = max(5.0, base + random.uniform(-rnd, rnd))
            self.after(0, lambda w=wait, n=slot_idx, tot=len(active):
                       self.log(f"   └ [{n%tot+1}/{tot}] 다음 광고까지 {w:.1f}초"))
            end = time.time() + wait
            while time.time() < end and self._chat_repeat_running:
                time.sleep(0.5)
        self.after(0, lambda: (
            self._chat_start_btn.configure(state="normal"),
            self._chat_stop_btn.configure(state="disabled", fg_color="#374151", hover_color=DANGER)
        ))

    # ── OCR 섹션 ────────────────────────────
    def _build_ocr_section(self, p):
        f = self._card(p, "⑤ 영역 캡처 & 숫자 읽기 (OCR)", color=PURPLE)

        # 설정 행
        cfg = ctk.CTkFrame(f, fg_color="transparent"); cfg.pack(fill="x", pady=(0,10))
        self._rt(ctk.CTkLabel(cfg, text="갱신:", font=ctk.CTkFont(size=12), text_color="white")).pack(side="left")
        ctk.CTkEntry(cfg, textvariable=self._ocr_interval_var, width=48,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4,2))
        ctk.CTkLabel(cfg, text="초", font=ctk.CTkFont(size=12), text_color=TEXT_DIM).pack(side="left", padx=(0,14))
        self._ocr_toggle_btn = ctk.CTkButton(
            cfg, text="▶ 자동 캡처 시작", width=140, height=30,
            fg_color=PURPLE, hover_color="#7C3AED",
            font=ctk.CTkFont(size=12, weight="bold"), command=self._toggle_ocr)
        self._ocr_toggle_btn.pack(side="left")
        ctk.CTkButton(cfg, text="즉시 캡처", width=90, height=30,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=12), command=self._capture_once
                      ).pack(side="left", padx=(8,0))
        ctk.CTkCheckBox(cfg, text="MP 자동 루프", variable=self._auto_loop_var,
                        font=ctk.CTkFont(size=12), text_color=TEXT_DIM,
                        checkbox_width=18, checkbox_height=18
                        ).pack(side="left", padx=(14, 0))

        # 두 패널
        panels = ctk.CTkFrame(f, fg_color="transparent"); panels.pack(fill="x")
        self._build_ocr_panel(panels, 1)
        self._build_ocr_panel(panels, 2)

    def _build_ocr_panel(self, parent, idx):
        outer = self._reg(ctk.CTkFrame(parent, fg_color="#060D1A", corner_radius=10), "#060D1A", "#F1F5F9")
        outer.pack(side="left", expand=True, fill="both", padx=(0, 6 if idx==1 else 0))

        # 헤더
        hdr = self._reg(ctk.CTkFrame(outer, fg_color="#1E293B", corner_radius=0, height=34), "#1E293B", "#FFFFFF")
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"  화면 {idx}",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=PURPLE).pack(side="left")
        region_lbl = ctk.CTkLabel(hdr, text="영역 미지정",
                                   font=ctk.CTkFont(size=10), text_color=TEXT_DIM)
        region_lbl.pack(side="left", padx=6)
        ctk.CTkButton(hdr, text="📐 영역 지정", width=88, height=24,
                      fg_color=PURPLE, hover_color="#7C3AED", font=ctk.CTkFont(size=11),
                      command=lambda i=idx: self._select_region(i)
                      ).pack(side="right", padx=6, pady=4)

        # 미리보기
        preview = ctk.CTkLabel(outer,
                               text=f"화면{idx} 영역을 지정하면\n캡처 이미지가 표시됩니다",
                               font=ctk.CTkFont(size=11), text_color=TEXT_DIM,
                               fg_color="#0A1628", corner_radius=0, width=340, height=170)
        self._inner_frames.append((preview, "#0A1628", "#EEF2FF"))
        preview.pack(fill="x", padx=0, pady=(4,0))

        # 결과 행
        res = self._reg(ctk.CTkFrame(outer, fg_color="#0A1628", corner_radius=0), "#0A1628", "#EEF2FF")
        res.pack(fill="x", padx=0, pady=(2,4))
        ctk.CTkLabel(res, text="인식:", font=ctk.CTkFont(size=11), text_color=TEXT_DIM
                     ).pack(side="left", padx=(10,4), pady=6)
        result_lbl = ctk.CTkLabel(res, text="—",
                                   font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
                                   text_color=SUCCESS)
        result_lbl.pack(side="left")

        if idx == 1:
            self._ocr_region_lbl1 = region_lbl
            self._ocr_preview1    = preview
            self._ocr_result1     = result_lbl
        else:
            self._ocr_region_lbl2 = region_lbl
            self._ocr_preview2    = preview
            self._ocr_result2     = result_lbl

    # ── 원격 제어 섹션 ──────────────────────
    def _build_remote_section(self, p):
        TEAL = "#0D9488"
        f = self._card(p, "⑥ 원격 PC2 제어", color=TEAL)

        # IP / 포트 행
        row1 = ctk.CTkFrame(f, fg_color="transparent"); row1.pack(fill="x", pady=(0, 6))
        self._rt(ctk.CTkLabel(row1, text="PC2 IP:", font=ctk.CTkFont(size=12),
                              text_color="white", width=56)).pack(side="left")
        ctk.CTkEntry(row1, textvariable=self._remote_ip_var, width=160,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 12))
        self._rt(ctk.CTkLabel(row1, text="포트:", font=ctk.CTkFont(size=12),
                              text_color="white")).pack(side="left")
        ctk.CTkEntry(row1, textvariable=self._remote_port_var, width=64,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 12))
        self._remote_ping_btn = ctk.CTkButton(
            row1, text="연결 테스트", width=100, height=28,
            fg_color="#334155", hover_color="#475569",
            font=ctk.CTkFont(size=12), command=self._remote_ping)
        self._remote_ping_btn.pack(side="left")
        self._remote_ping_lbl = ctk.CTkLabel(
            row1, text="●", font=ctk.CTkFont(size=14), text_color="#374151")
        self._remote_ping_lbl.pack(side="left", padx=(8, 0))

        # 키 설정 행
        _key_opts = ["F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
                     "1","2","3","4","5","6","7","8","9","0","Space"]
        row2 = ctk.CTkFrame(f, fg_color="transparent"); row2.pack(fill="x")
        self._rt(ctk.CTkLabel(row2, text="트리거 키:", font=ctk.CTkFont(size=12),
                              text_color="white", width=72)).pack(side="left")
        ctk.CTkComboBox(row2, values=_key_opts, variable=self._remote_trigkey_var,
                        width=88, state="readonly", font=ctk.CTkFont(size=12),
                        button_color=TEAL, button_hover_color="#0F766E"
                        ).pack(side="left", padx=(4, 16))
        self._rt(ctk.CTkLabel(row2, text="전송 키:", font=ctk.CTkFont(size=12),
                              text_color="white", width=60)).pack(side="left")
        ctk.CTkComboBox(row2, values=_key_opts, variable=self._remote_sendkey_var,
                        width=88, state="readonly", font=ctk.CTkFont(size=12),
                        button_color=TEAL, button_hover_color="#0F766E"
                        ).pack(side="left", padx=(4, 16))
        ctk.CTkCheckBox(row2, text="활성화", variable=self._remote_enabled_var,
                        font=ctk.CTkFont(size=12), text_color="white",
                        checkbox_width=18, checkbox_height=18
                        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(f, text="※ 트리거 키를 누르면 PC2의 모든 Lineage 창에 전송 키를 입력합니다.",
                     font=ctk.CTkFont(size=11), text_color=TEXT_DIM).pack(anchor="w", pady=(6, 0))

    def _remote_ping(self):
        def _ping():
            try:
                ip   = self._remote_ip_var.get().strip()
                port = int(self._remote_port_var.get().strip())
                import socket as _sock
                with _sock.create_connection((ip, port), timeout=3) as s:
                    s.sendall(b'{"action":"ping"}')
                    resp = json.loads(s.recv(4096).decode())
                wins = resp.get("windows", "?")
                ard  = "Arduino O" if resp.get("arduino") else "Arduino X"
                titles = resp.get("titles", [])
                self.after(0, lambda: self._remote_ping_lbl.configure(
                    text="● 연결됨", text_color=SUCCESS))
                self.after(0, lambda: self.log(
                    f"[원격] PC2 연결 OK — Lineage {wins}개 / {ard}"))
                for t in titles:
                    self.after(0, lambda tt=t: self.log(f"  • {tt}"))
            except Exception as e:
                self.after(0, lambda: self._remote_ping_lbl.configure(
                    text="● 실패", text_color=DANGER))
                self.after(0, lambda: self.log(f"[원격] 연결 실패: {e}"))
        threading.Thread(target=_ping, daemon=True).start()

    def _send_remote_cmd(self, action: str, **kwargs):
        def _send():
            try:
                ip   = self._remote_ip_var.get().strip()
                port = int(self._remote_port_var.get().strip())
                cmd  = {"action": action, **kwargs}
                import socket as _sock
                with _sock.create_connection((ip, port), timeout=3) as s:
                    s.sendall(json.dumps(cmd).encode())
                    resp = json.loads(s.recv(4096).decode())
                status = resp.get("status", "?")
                msg    = resp.get("msg", "")
                self.after(0, lambda: self.log(f"[원격] {status} — {msg}"))
            except Exception as e:
                self.after(0, lambda: self.log(f"[원격] 전송 실패: {e}"))
        threading.Thread(target=_send, daemon=True).start()

    def _build_log_popup(self):
        popup = ctk.CTkToplevel(self)
        popup.title("로그")
        popup.geometry("680x320")
        popup.configure(fg_color="#0A0F1E")
        popup.protocol("WM_DELETE_WINDOW", self._hide_log_popup)
        self._log_popup_hdr = ctk.CTkFrame(popup, fg_color="#1E293B", corner_radius=0, height=36)
        self._log_popup_hdr.pack(fill="x"); self._log_popup_hdr.pack_propagate(False)
        hdr = self._log_popup_hdr
        self._log_title_lbl = ctk.CTkLabel(hdr, text="  📋 로그", font=ctk.CTkFont(size=13, weight="bold"),
                                            text_color="white")
        self._log_title_lbl.pack(side="left", padx=8)
        ctk.CTkButton(hdr, text="🗑 지우기", width=80, height=26,
                      fg_color="transparent", border_width=1, border_color="#334155",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self.log_box.delete("1.0", "end")
                      ).pack(side="right", padx=8)
        self.log_box = ctk.CTkTextbox(popup, font=ctk.CTkFont(family="Consolas", size=11),
                                      fg_color="#0A0F1E", text_color="#A0AEC0",
                                      scrollbar_button_color="#334155")
        self.log_box.pack(fill="both", expand=True, padx=4, pady=(0,4))
        self._log_popup = popup
        popup.withdraw()

    def _toggle_log_popup(self):
        if self._log_popup is None:
            return
        if self._log_popup.winfo_viewable():
            self._hide_log_popup()
        else:
            self._log_popup.deiconify()
            self._log_popup.lift()

    def _hide_log_popup(self):
        if self._log_popup:
            self._log_popup.withdraw()

    # ─── 설정 저장/로드 ─────────────────────
    def _on_close(self):
        self._save_config()
        self.destroy()

    def _save_config(self):
        data = {
            "com_port":      self._com_var.get(),
            "appearance":    "dark" if self._is_dark else "light",
            "window1_title": self.combo1.get().rsplit("#", 1)[0].strip(),
            "window2_title": self.combo2.get().rsplit("#", 1)[0].strip(),
            "pos1":          list(self.pos1) if self.pos1 else None,
            "pos2":          list(self.pos2) if self.pos2 else None,
            "pos_active":    [v.get() for v in self._pos_active_var],
            "action_mode":   [v.get() for v in self._action_mode_var],
            "action_key":    [v.get() for v in self._action_key_var],
            "delay_min":     self.min_delay.get(),
            "delay_max":     self.max_delay.get(),
            "layout":        self.layout_var.get(),
            "win_width":     self.win_w.get(),
            "win_height":    self.win_h.get(),
            "chat_target":   self._chat_target_var.get(),
            "chat_entries":  [e.get() for e in self._chat_entries],
            "chat_checks":   [v.get() for v in self._chat_check_vars],
            "chat_interval": self._chat_interval_var.get(),
            "chat_random":   self._chat_random_var.get(),
            "ocr_interval":  self._ocr_interval_var.get(),
            "remote_ip":     self._remote_ip_var.get(),
            "remote_port":   self._remote_port_var.get(),
            "remote_trigkey":self._remote_trigkey_var.get(),
            "remote_sendkey":self._remote_sendkey_var.get(),
        }
        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log(f"설정 저장 완료 → {_CONFIG_FILE}")
        except Exception as e:
            self.log(f"설정 저장 실패: {e}")

    def _load_config(self):
        if not os.path.exists(_CONFIG_FILE):
            return
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.log(f"설정 로드 실패: {e}"); return

        # COM 포트
        if "com_port" in data:
            self._com_var.set(data["com_port"])

        # 다크/라이트 모드
        if data.get("appearance") == "light" and self._is_dark:
            self._toggle_mode()

        # 윈도우 선택 (타이틀 매칭)
        for combo, key in [(self.combo1, "window1_title"), (self.combo2, "window2_title")]:
            saved = data.get(key, "")
            if not saved:
                continue
            vals = list(combo.cget("values"))
            for val in vals:
                if val.rsplit("#", 1)[0].strip() == saved:
                    combo.set(val); break

        # 클릭 위치
        for i, val in enumerate(data.get("pos_active", [])):
            if i < 2: self._pos_active_var[i].set(val)
        if data.get("pos1"):
            self.pos1 = tuple(data["pos1"])
            self._pos_x_var[0].set(str(self.pos1[0]))
            self._pos_y_var[0].set(str(self.pos1[1]))
        if data.get("pos2"):
            self.pos2 = tuple(data["pos2"])
            self._pos_x_var[1].set(str(self.pos2[0]))
            self._pos_y_var[1].set(str(self.pos2[1]))

        # 액션 모드/키
        for i in range(2):
            if "action_mode" in data and i < len(data["action_mode"]):
                self._action_mode_var[i].set(data["action_mode"][i])
            if "action_key" in data and i < len(data["action_key"]):
                self._action_key_var[i].set(data["action_key"][i])

        # 딜레이
        if "delay_min" in data:
            self.min_delay.delete(0, "end"); self.min_delay.insert(0, data["delay_min"])
        if "delay_max" in data:
            self.max_delay.delete(0, "end"); self.max_delay.insert(0, data["delay_max"])

        # 창 정렬
        if "layout" in data:    self.layout_var.set(data["layout"])
        if "win_width" in data:
            self.win_w.delete(0, "end"); self.win_w.insert(0, data["win_width"])
        if "win_height" in data:
            self.win_h.delete(0, "end"); self.win_h.insert(0, data["win_height"])

        # 채팅
        if "chat_target" in data:
            self._chat_target_var.set(data["chat_target"])
        for i, text in enumerate(data.get("chat_entries", [])):
            if i < len(self._chat_entries) and text:
                self._chat_entries[i].delete(0, "end")
                self._chat_entries[i].insert(0, text)
        for i, val in enumerate(data.get("chat_checks", [])):
            if i < len(self._chat_check_vars):
                self._chat_check_vars[i].set(val)
        if "chat_interval" in data: self._chat_interval_var.set(data["chat_interval"])
        if "chat_random"   in data: self._chat_random_var.set(data["chat_random"])

        # OCR
        if "ocr_interval"  in data: self._ocr_interval_var.set(data["ocr_interval"])

        # 원격 제어
        if "remote_ip"      in data: self._remote_ip_var.set(data["remote_ip"])
        if "remote_port"    in data: self._remote_port_var.set(data["remote_port"])
        if "remote_trigkey" in data: self._remote_trigkey_var.set(data["remote_trigkey"])
        if "remote_sendkey" in data: self._remote_sendkey_var.set(data["remote_sendkey"])

        self._update_win_labels()
        self.log("설정 로드 완료")

    # ─── 공통 기능 ──────────────────────────
    def _toggle_mode(self):
        self._is_dark = not self._is_dark
        theme = DARK if self._is_dark else LIGHT
        ctk.set_appearance_mode("dark" if self._is_dark else "light")
        self._mode_btn.configure(text="☀ Light" if self._is_dark else "🌙 Dark")
        self.configure(fg_color=theme["BG_MAIN"])
        self._hdr.configure(fg_color=theme["BG_CARD"])
        self._scroll.configure(fg_color=theme["BG_MAIN"])
        for card in self._card_frames:
            try: card.configure(fg_color=theme["BG_CARD"])
            except Exception: pass
        for fr, dark_c, light_c in self._inner_frames:
            try: fr.configure(fg_color=dark_c if self._is_dark else light_c)
            except Exception: pass
        for w, dark_c, light_c in self._text_widgets:
            try: w.configure(text_color=dark_c if self._is_dark else light_c)
            except Exception: pass
        for btn in self._hdr_btns:
            try: btn.configure(text_color=theme["TEXT_MAIN"], border_color=theme["BORDER"])
            except Exception: pass
        if self._log_popup:
            lp_bg = DARK["BG_MAIN"] if self._is_dark else "#FFFFFF"
            lp_hd = DARK["BG_CARD"] if self._is_dark else "#F1F5F9"
            try:
                self._log_popup.configure(fg_color=lp_bg)
                self._log_popup_hdr.configure(fg_color=lp_hd)
                self.log_box.configure(fg_color=lp_bg)
                self._log_title_lbl.configure(text_color=theme["TEXT_MAIN"])
            except Exception: pass

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")

    def _set_status(self, text, running=False):
        self.status_lbl.configure(text=text, text_color=SUCCESS if running else TEXT_DIM)
        self._dot.configure(text_color=SUCCESS if running else "#374151")

    def _extract_win_short(self, combo):
        raw = combo.get()
        if not raw:
            return ""
        # hwnd로 잘리지 않은 전체 제목에서 이메일 추출
        try:
            hwnd = int(raw.rsplit("#", 1)[-1].strip())
            full = win32gui.GetWindowText(hwnd)
            m = re.search(r'\[([^\[\]]+@[^\[\]]+)\]', full)
            if m:
                return m.group(1)
        except Exception:
            pass
        # 폴백: 콤보 텍스트에서 추출
        title = raw.rsplit("#", 1)[0].strip()
        if "[" in title:
            title = title[:title.rfind("[")].strip()
        return title[:20] if title else ""

    def _update_win_labels(self):
        for i, combo in enumerate([self.combo1, self.combo2]):
            short = self._extract_win_short(combo)
            self._win_name_var[i].set(f"({short})" if short else "")
            self._act_lbl_var[i].set(f"창{i+1}  {short}:" if short else f"창{i+1}:")
            label = f"창{i+1}" + (f"  {short}" if short else "")
            if self._chat_win_rb[i]:
                self._chat_win_rb[i].configure(text=label)

    def refresh_windows(self):
        self.windows_list = enum_visible_windows()
        labels = []
        for hwnd, title, exe in self.windows_list:
            if "lineage" not in title.lower() and "lineage" not in exe.lower():
                continue
            em = re.search(r'\[([^\[\]]+@[^\[\]]+)\]', title)
            email_str = f"[{em.group(1)}]  " if em else ""
            t = title[:40] + "…" if len(title) > 40 else title
            e = f"[{exe}]" if exe else ""
            labels.append(f"{email_str}{t}  {e}  #{hwnd}")
        self.combo1.configure(values=labels)
        self.combo2.configure(values=labels)
        if labels:
            self.combo1.set(labels[0])
            rest = labels[1:]
            self.combo2.configure(values=rest if rest else labels)
            if rest:
                self.combo2.set(rest[0])
            else:
                self.combo2.set("")
                self.log("⚠ 라이니지 창이 1개입니다. 창 2를 수동으로 선택해주세요.")
        self.log(f"창 목록 갱신 (lineage): {len(labels)}개")
        self._update_win_labels()

    def _get_hwnd(self, combo):
        try:
            return int(combo.get().rsplit("#", 1)[-1].strip())
        except Exception:
            return None

    def pick_position(self, which):
        hwnd = self._get_hwnd(self.combo1 if which==1 else self.combo2)
        if not hwnd:
            messagebox.showwarning("알림", f"창 {which}을(를) 먼저 선택해주세요."); return
        self.log(f"창{which} 위치 대기... 5초 안에 해당 창을 클릭하세요.")
        self.iconify()
        def worker():
            time.sleep(0.3)
            deadline = time.time() + 5.0
            captured = False
            while time.time() < deadline:
                if win32api.GetAsyncKeyState(0x01) & 0x8000:
                    cx, cy = win32api.GetCursorPos()
                    try:
                        rect = get_window_rect(hwnd)
                        rx, ry = cx - rect[0], cy - rect[1]
                    except Exception:
                        rx, ry = cx, cy
                    pos = (rx, ry)
                    if which == 1:
                        self.pos1 = pos
                    else:
                        self.pos2 = pos
                    self.after(0, lambda rx_=rx, ry_=ry, w=which: (
                        self._pos_x_var[w-1].set(str(rx_)),
                        self._pos_y_var[w-1].set(str(ry_)),
                        self.log(f"창{w} 위치 저장 X:{rx_}, Y:{ry_}")
                    ))
                    captured = True; break
                time.sleep(0.03)
            if not captured:
                self.after(0, lambda: self.log(f"창{which} 위치 지정 시간 초과"))
            self.after(150, self.deiconify)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_pos_entry(self, which):
        try:
            rx = int(self._pos_x_var[which-1].get())
            ry = int(self._pos_y_var[which-1].get())
            if which == 1: self.pos1 = (rx, ry)
            else:          self.pos2 = (rx, ry)
            self.log(f"창{which} 위치 설정 X:{rx}, Y:{ry}")
        except ValueError:
            pass

    def _nudge_pos(self, which, dy):
        pos = self.pos1 if which == 1 else self.pos2
        if pos is None:
            return
        new_pos = (pos[0], pos[1] + dy)
        if which == 1: self.pos1 = new_pos
        else:          self.pos2 = new_pos
        self._pos_x_var[which-1].set(str(new_pos[0]))
        self._pos_y_var[which-1].set(str(new_pos[1]))
        self.log(f"창{which} Y 조정 {'+' if dy>0 else ''}{dy} → Y:{new_pos[1]}")

    def arrange_windows(self):
        if not _is_admin():
            ans = messagebox.askyesno("관리자 권한 필요",
                "창 정렬은 관리자 권한이 필요합니다.\n관리자 권한으로 재시작하시겠습니까?\n\n"
                "※ 클릭/OCR은 관리자 권한 없이도 동작합니다.")
            if ans: _restart_as_admin()
            return
        h1 = self._get_hwnd(self.combo1); h2 = self._get_hwnd(self.combo2)
        if not h1 or not h2:
            messagebox.showwarning("알림", "창 두 개를 모두 선택해주세요."); return
        try:
            w = int(self.win_w.get()); h = int(self.win_h.get())
        except ValueError:
            messagebox.showwarning("알림", "가로/세로는 숫자여야 합니다."); return
        sw = win32api.GetSystemMetrics(0)   # 전체 화면 가로
        sh = win32api.GetSystemMetrics(1)   # 전체 화면 세로
        layout = self.layout_var.get()
        if layout == "좌우":
            x2 = w if w * 2 <= sw else sw - w   # 화면 밖으로 넘어가지 않게 보정
            coords = {h1:(0,0,w,h), h2:(x2,0,w,h)}
        elif layout == "상하":
            y2 = h if h * 2 <= sh else sh - h
            coords = {h1:(0,0,w,h), h2:(0,y2,w,h)}
        else:
            coords = {h1:(80,80,w,h), h2:(140,140,w,h)}
        for hwnd,(x,y,cw,ch) in coords.items():
            try: win32gui.MoveWindow(hwnd,x,y,cw,ch,True)
            except Exception as e: self.log(f"창 이동 실패: {e}"); return
        self.log(f"창 정렬 완료 [{layout}] {w}x{h}")

    def start(self):
        h1 = self._get_hwnd(self.combo1)
        h2 = self._get_hwnd(self.combo2)
        a1 = self._pos_active_var[0].get()
        a2 = self._pos_active_var[1].get()
        if not a1 and not a2:
            messagebox.showwarning("알림", "최소 하나의 클릭 위치를 체크해주세요."); return
        if a1 and not h1:
            messagebox.showwarning("알림", "창 1을 선택해주세요."); return
        if a2 and not h2:
            messagebox.showwarning("알림", "창 2를 선택해주세요."); return
        if a1 and a2 and h1 == h2:
            messagebox.showwarning("알림", "서로 다른 창을 선택해주세요."); return
        if a1 and not self.pos1:
            messagebox.showwarning("알림", "창 1 클릭 위치를 지정해주세요."); return
        if a2 and not self.pos2:
            messagebox.showwarning("알림", "창 2 클릭 위치를 지정해주세요."); return
        try:
            mn = float(self.min_delay.get()); mx = float(self.max_delay.get())
            assert 0 <= mn <= mx
        except Exception:
            messagebox.showerror("오류", "딜레이 값을 확인해주세요."); return
        self.hwnd1, self.hwnd2 = h1, h2
        self.running = True; self._click_count = 0
        self.start_btn.configure(state="disabled", fg_color="#374151")
        self.stop_btn.configure(state="normal", fg_color=DANGER, hover_color="#B91C1C")
        self._set_status("실행 중...", running=True)
        ocr_mode = " | OCR 만MP 감지 중" if any(self.ocr_region) else ""
        self.log(f"━━━ 시작 (딜레이 {mn}~{mx}초 / Backspace 중지{ocr_mode}) ━━━")
        threading.Thread(target=self._loop, args=(mn,mx), daemon=True).start()

    def stop(self):
        self.running = False
        self.start_btn.configure(state="normal", fg_color=SUCCESS)
        self.stop_btn.configure(state="disabled", fg_color="#374151")
        self._set_status("대기 중", running=False)

    def _loop(self, mn, mx):
        sw = win32api.GetSystemMetrics(0)
        sh = win32api.GetSystemMetrics(1)
        # 체크된 슬롯만 수집
        slots = []
        if self._pos_active_var[0].get() and self.hwnd1 and self.pos1:
            slots.append((self.hwnd1, self.pos1, 0))
        if self._pos_active_var[1].get() and self.hwnd2 and self.pos2:
            slots.append((self.hwnd2, self.pos2, 1))
        if not slots:
            self.after(0, lambda: self.log("⚠ 활성화된 클릭 위치가 없습니다."))
            self.after(0, self.stop); return

        use_ocr = any(self.ocr_region)   # OCR 영역 지정 여부
        slot_idx = 0
        while self.running:
            hwnd, pos, idx = slots[slot_idx % len(slots)]
            slot_idx += 1
            try:
                key  = self._action_key_var[idx].get()
                mode = self._action_mode_var[idx].get()
                sx, sy, via = click_at(hwnd, *pos, key_name=key, mode=mode)
                self._click_count += 1
                self.after(0, lambda c=self._click_count: self.count_lbl.configure(text=f"클릭 수: {c}"))
                warn = " ⚠화면밖!" if sx < 0 or sx > sw or sy < 0 or sy > sh else ""
                self.after(0, lambda v=via, x=sx, y=sy, w=warn, n=idx+1: self.log(
                    f"▶ 창{n} [{v}] 더블클릭  abs:({x},{y}){w}"))
            except Exception as e:
                self.after(0, lambda err=e: self.log(f"⚠ 클릭 오류: {err}"))

            delay = random.uniform(mn, mx)
            self.after(0, lambda d=delay: self.log(f"   └ {d:.2f}초 대기"))
            end = time.time() + delay
            while time.time() < end and self.running:
                time.sleep(0.05)

            # OCR 영역 지정된 경우만 만MP 체크 → 자동 중지
            if use_ocr and self.running:
                ocr_vals = [(i, self._ocr_values[i]) for i in range(2) if self.ocr_region[i]]
                if ocr_vals and all(v is not None and v[0] >= v[1] for _, v in ocr_vals):
                    self.after(0, lambda: self.log("✅ MP 충전 완료 → 자동 중지"))
                    self.running = False
                    self.after(0, self.stop)
                    break

        self.after(0, lambda: self.log("━━━ 종료 ━━━"))
        self.after(0, self.stop)

    # ─── OCR 기능 ───────────────────────────
    def _select_region(self, idx):
        self.iconify()
        time.sleep(0.3)
        def on_done(region):
            self.after(200, self.deiconify)
            if region is None:
                return
            self.ocr_region[idx-1] = region
            x1,y1,x2,y2 = region
            txt = f"({x1},{y1})~({x2},{y2})"
            if idx==1: self.after(0, lambda: self._ocr_region_lbl1.configure(text=txt, text_color=PURPLE))
            else:       self.after(0, lambda: self._ocr_region_lbl2.configure(text=txt, text_color=PURPLE))
            self.log(f"화면{idx} 영역 지정: {txt}")
            threading.Thread(target=lambda: self._do_capture(idx), daemon=True).start()
        self.after(400, lambda: RegionSelector(on_done))

    def _toggle_ocr(self):
        if self._ocr_running:
            self._ocr_running = False
            self._ocr_toggle_btn.configure(text="▶ 자동 캡처 시작", fg_color=PURPLE)
            self.log("OCR 자동 캡처 중지")
        else:
            if not any(self.ocr_region):
                messagebox.showwarning("알림", "화면1 또는 화면2 영역을 먼저 지정해주세요."); return
            self._ocr_running = True
            self._ocr_toggle_btn.configure(text="■ 자동 캡처 중지", fg_color=DANGER)
            self.log("OCR 자동 캡처 시작")
            threading.Thread(target=self._ocr_loop, daemon=True).start()

    def _capture_once(self):
        for i in range(2):
            if self.ocr_region[i]:
                threading.Thread(target=lambda idx=i+1: self._do_capture(idx), daemon=True).start()

    def _ocr_loop(self):
        while self._ocr_running:
            try:
                interval = float(self._ocr_interval_var.get())
            except Exception:
                interval = 2.0
            for i in range(2):
                if self.ocr_region[i] and self._ocr_running:
                    self._do_capture(i+1)
            end = time.time() + interval
            while time.time() < end and self._ocr_running:
                time.sleep(0.1)

    def _do_capture(self, idx):
        region = self.ocr_region[idx-1]
        if not region:
            return
        x1,y1,x2,y2 = region
        try:
            img = ImageGrab.grab(bbox=(x1,y1,x2,y2), all_screens=True)
        except Exception as e:
            self.after(0, lambda: self.log(f"화면{idx} 캡처 실패: {e}")); return

        # 미리보기 썸네일
        thumb = img.copy()
        thumb.thumbnail((340, 170), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb,
                               size=(thumb.width, thumb.height))
        self._ocr_images[idx-1] = None   # 이전 이미지 참조 해제 후 교체
        self._ocr_images[idx-1] = ctk_img
        if idx==1:
            self.after(0, lambda im=ctk_img: self._ocr_preview1.configure(
                image=im, text="", width=340, height=170))
        else:
            self.after(0, lambda im=ctk_img: self._ocr_preview2.configure(
                image=im, text="", width=340, height=170))

        # OCR
        if _ocr_mod.OCR_ENGINE:
            try:
                from PIL import ImageEnhance
                big = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
                big = ImageEnhance.Contrast(big).enhance(2.5)
                big = ImageEnhance.Sharpness(big).enhance(2.0)
                text = ocr_read(big, numbers_only=False) or "—"
                # current/max 파싱 저장 (자동 중지 조건용)
                m = re.search(r'(\d+)/(\d+)', text)
                if m:
                    self._ocr_values[idx-1] = (int(m.group(1)), int(m.group(2)))
                else:
                    nums = re.findall(r'\d+', text)
                    # '/' 누락 폴백: 4~6자리 숫자를 N/M으로 분해
                    if len(nums) == 1 and 4 <= len(nums[0]) <= 6:
                        raw = nums[0]
                        for sp in range(2, len(raw) - 1):
                            left, right = int(raw[:sp]), int(raw[sp:])
                            if left <= right <= 9999:
                                self._ocr_values[idx-1] = (left, right); break
                        else:
                            self._ocr_values[idx-1] = None
                    else:
                        self._ocr_values[idx-1] = (int(nums[0]), int(nums[1])) if len(nums) == 2 else None
                # OCR 영역 지정 + MP 미충전 + 자동 루프 체크 → 루프 자동 시작
                val = self._ocr_values[idx-1]
                if (val is not None and self._auto_loop_var.get()
                        and any(self.ocr_region) and not self.running):
                    if val[0] < val[1]:
                        self.after(0, self.start)
            except Exception as e:
                text = f"오류: {e}"
        else:
            text = "(OCR 없음)"

        if idx==1: self.after(0, lambda t=text: self._ocr_result1.configure(text=t))
        else:       self.after(0, lambda t=text: self._ocr_result2.configure(text=t))
        self.after(0, lambda t=text: self.log(f"화면{idx} OCR → {t}"))

    def _start_f12_listener(self):
        _REMOTE_VK = {
            "F1":0x70,"F2":0x71,"F3":0x72,"F4":0x73,"F5":0x74,"F6":0x75,
            "F7":0x76,"F8":0x77,"F9":0x78,"F10":0x79,"F11":0x7A,"F12":0x7B,
            "1":0x31,"2":0x32,"3":0x33,"4":0x34,"5":0x35,
            "6":0x36,"7":0x37,"8":0x38,"9":0x39,"0":0x30,"Space":0x20,
        }
        def _watch():
            _remote_cooldown = 0.0
            while True:
                if win32api.GetAsyncKeyState(0x08) & 0x8000:  # Backspace
                    if self.running: self.after(0, self.stop)
                    time.sleep(0.4)
                if win32api.GetAsyncKeyState(0x2E) & 0x8000:  # Delete
                    if self._chat_repeat_running: self.after(0, self._stop_chat_repeat)
                    time.sleep(0.4)
                # 원격 트리거 키
                if self._remote_enabled_var.get():
                    trig_vk = _REMOTE_VK.get(self._remote_trigkey_var.get(), 0)
                    now = time.time()
                    if trig_vk and (win32api.GetAsyncKeyState(trig_vk) & 0x8000) \
                            and now > _remote_cooldown:
                        _remote_cooldown = now + 0.6
                        send_key = self._remote_sendkey_var.get()
                        self.after(0, lambda k=send_key: self.log(
                            f"[원격] 트리거 → PC2  KEY:{k}"))
                        self._send_remote_cmd("key", key=send_key, dur=60)
                time.sleep(0.05)
        threading.Thread(target=_watch, daemon=True).start()


# ─────────────────────────────────────────