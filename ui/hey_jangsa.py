# -*- coding: utf-8 -*-
import threading
import time
import random
import os
import json
import re

import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageGrab

import win32gui
import win32con
import win32api

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

from core.constants import _BASE_DIR
import core.arduino as _ar_mod
from core.arduino import _arduino_lock, arduino_send, _SERIAL_OK
import core.ocr_engine as _ocr_mod
from core.ocr_engine import ocr_read, _init_ocr
from core.win32_utils import (
    _SendMessageA, _KEY_CODES, enum_visible_windows, force_foreground,
    _is_admin, _restart_as_admin,
)
from core.icon import _apply_icon
from ui.region_selector import RegionSelector, PointSelector
class AppHeyJangsa(ctk.CTk):
    _MODE_META = {
        "헤이장사_싱글":            ("👤 싱글모드",          "#22C55E"),
        "헤이장사_멀티_호스트":     ("🎯 멀티 · 호스트",     "#F59E0B"),
        "헤이장사_멀티_클라이언트": ("📡 멀티 · 클라이언트", "#3B82F6"),
    }

    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode
        label, _ = self._MODE_META.get(mode, ("헤이장사", "#A855F7"))
        self.title(f"배미유니버스 — 헤이장사  [{label}]")
        self.geometry("720x920")
        self.after(100, lambda: _apply_icon(self))
        self.resizable(False, False)
        self.configure(fg_color="#0A0F1E")

        # 공통 상태
        self.windows_list  = []
        self.hj_combo      = None
        self.ocr_region    = None
        self._ocr_img_ref  = None
        self._run_evt      = threading.Event()
        self._chat_lock    = threading.Lock()   # 채팅 동시 전송 방지
        self._log_box      = None   # 미사용(하위호환)
        self._hj_log_popup  = None
        self._hj_log_box    = None
        self._sales_popup   = None
        self._sales_records = []   # [{"time": str, "amount": int, "shots": int}]

        # 설정 변수
        self._exchange_key_var   = ctk.StringVar(value="F5")
        self._scan_interval_var  = ctk.StringVar(value="1.0")
        self._action_delay_var   = ctk.StringVar(value="0.3")
        self._cooldown_var       = ctk.StringVar(value="3.0")
        # 교환창 확인
        self._money_region       = None   # 돈 텍스트 OCR 영역 bbox (x1,y1,x2,y2)
        self._money_hover_pos    = None   # 커서 이동 위치 (x, y) — 금화 슬롯
        self._ok_pos             = None   # OK 버튼 절대좌표 (x, y)
        self._cancel_pos         = None   # Cancel 버튼 절대좌표
        self._trade_win_region   = None   # 거래창 존재 감지 영역 bbox
        self._trade_win_thr_var  = ctk.StringVar(value="20.0")  # 거래창 어두운 픽셀 기준(%)
        self._trade_gray_region  = None   # 상대방 거래창 회색 감지 영역 bbox
        self._trade_gray_threshold_var = ctk.StringVar(value="80.0")  # 회색 절대값(%) 기준
        self._allowed_prices_var = ctk.StringVar(value="500, 1000")  # 하위호환 보존
        self._price_per_shot_var = ctk.StringVar(value="150")        # 방당 가격(아데나)
        # 엠탐중 (MP 부족 시 대기 알림)
        self._mp_scan_interval_var = ctk.StringVar(value="10")  # MP 스캔 간격(초)
        self._mp_low_enabled_var  = ctk.BooleanVar(value=True)
        self._mp_low_msg_var      = ctk.StringVar(value="엠탐중")
        self._mp_low_interval_var = ctk.StringVar(value="30")
        self._mp_low_rnd_var      = ctk.StringVar(value="5")
        # 평상시 광고 (4번째 슬롯 = MP 연동 {n}방 메시지)
        self._ad_msg_vars     = [ctk.StringVar(value="") for _ in range(3)] + \
                                [ctk.StringVar(value=r"\fF 헤이 {n}방 가능합니다")]
        self._ad_interval_var = ctk.StringVar(value="60")
        self._ad_rnd_var      = ctk.StringVar(value="10")
        self._ad_running      = False
        self._ad_mp_cap       = 6   # 채팅에 표시할 최대 방 수 (내부는 실제값)
        # 거래 완료 후 대기
        self._post_trade_delay_var = ctk.StringVar(value="5.0")
        # MP 관리
        self._mp_region          = None
        self._mp_per_shot_var    = ctk.StringVar(value="20")
        self._mp_max_var         = ctk.StringVar(value="200")   # OCR 이상값 필터 기준
        self._mp_announce_var      = ctk.BooleanVar(value=True)
        self._mp_announce_tmpl     = ctk.StringVar(value="{n}방 가능합니다")
        self._mp_announce_interval = ctk.StringVar(value="30")   # 반복 주기(초)
        self._mp_announce_rnd      = ctk.StringVar(value="5")    # 랜덤 추가(초)
        # MP 3초 폴링 캐시 (백그라운드 스레드가 3초마다 갱신)
        self._cached_mp:  int | None = None
        self._cached_mp2: int | None = None
        # 거래 완료 채팅
        self._thanks_vars = [ctk.StringVar(value="감사합니다"), ctk.StringVar(value=""), ctk.StringVar(value="")]
        self._thanks_en   = [ctk.BooleanVar(value=True), ctk.BooleanVar(value=False), ctk.BooleanVar(value=False)]
        # 마법 시전
        self._shot_pos           = None   # 손님 클릭 위치 (타겟팅)
        self._shot_key_var       = ctk.StringVar(value="F5")
        self._shot_delay_var     = ctk.StringVar(value="1.5")   # 방 사이 딜레이(초)
        self._shots_per_price_var = ctk.StringVar(value="3, 6") # 가격별 방 수 (가격순 대응)
        self._last_trade_amount  = 0      # 마지막 거래 금액 (방 수 계산용)
        self._wait_timeout_var   = ctk.StringVar(value="60")
        # 픽셀 감지
        self._pixel_threshold_var = ctk.StringVar(value="3.0")  # 흰 픽셀 비율(%) 기준
        self._pos_labels = {}  # attr → CTkLabel (로드 후 반영용)
        # 자동 라이트 (밤 어둠 방지)
        self._auto_light_var      = ctk.BooleanVar(value=True)
        self._light_key_var       = ctk.StringVar(value="F6")
        self._light_interval_var  = ctk.StringVar(value="90")   # 분 단위
        # 2대 모드 (서브 클라이언트)
        self._dual_client_var     = ctk.BooleanVar(value=False)
        self._layout_var          = ctk.StringVar(value="좌우")
        self._sub_mp_region       = None
        self._sub_shot_pos        = None
        self._dual_frames         = []   # 2대 모드 전용 위젯 프레임 목록

        self._trade_state    = "IDLE"
        self._worker_threads = []
        self._hj_listener_running = True
        self._build_ui()
        self.refresh_windows()
        self._load_config_hj()
        self._spawn(self._load_ocr_engine, name="ocr-init")
        self._spawn(self._hotkey_listener,  name="hotkey")
        self.protocol("WM_DELETE_WINDOW", self._on_close_hj)

    # ── 프로퍼티 ─────────────────────────
    @property
    def running(self):
        return self._run_evt.is_set()

    # ── 공통 유틸 ────────────────────────
    def log(self, msg, tag=""):
        if not self._hj_log_box:
            return
        ts = time.strftime("%H:%M:%S")
        prefix = f"[{tag}] " if tag else ""
        line = f"[{ts}] {prefix}{msg}\n"
        def _write():
            self._hj_log_box.insert("end", line)
            self._hj_log_box.see("end")
        self.after(0, _write)

    # 4순위: 입력값 검증 헬퍼
    # 3순위: 스레드 헬퍼
    def _spawn(self, target, *args, name=None, **kwargs) -> threading.Thread:
        t = threading.Thread(target=target, args=args, kwargs=kwargs,
                             daemon=True, name=name or target.__name__)
        self._worker_threads.append(t)
        t.start()
        return t

    @staticmethod
    def _fv(var, default: float, lo: float = None, hi: float = None) -> float:
        try:
            v = float(var.get())
        except Exception:
            return default
        if lo is not None: v = max(v, lo)
        if hi is not None: v = min(v, hi)
        return v

    @staticmethod
    def _iv(var, default: int, lo: int = None, hi: int = None) -> int:
        try:
            v = int(float(var.get()))
        except Exception:
            return default
        if lo is not None: v = max(v, lo)
        if hi is not None: v = min(v, hi)
        return v

    # 5순위: 상태 머신
    _STATE_LABEL = {
        "IDLE":       ("● 대기 중",      "#64748B"),
        "WATCHING":   ("● 감시 중",      "#22C55E"),
        "DETECTED":   ("⚡ 손님 감지!",  "#F59E0B"),
        "MP_WAIT":    ("💤 엠탐중",      "#7C3AED"),
        "WAIT_TRADE": ("🔄 거래창 대기", "#F59E0B"),
        "READ_AMT":   ("💰 금액 확인",   "#60A5FA"),
        "GRAY_WAIT":  ("⏳ 상대 확인 대기","#F59E0B"),
        "DONE":       ("✅ 거래 완료",   "#22C55E"),
        "CANCEL":     ("⚠ 거래 취소",   "#EF4444"),
    }
    def _set_state(self, state: str):
        self._trade_state = state
        self.log(f"→ {state}", tag="STATE")
        label, color = self._STATE_LABEL.get(state, (state, "#94A3B8"))
        self.after(0, lambda t=label, c=color: self._status_lbl.configure(text=t, text_color=c))

    def _load_ocr_engine(self):
        self.log("OCR 엔진 로딩 중...")
        _init_ocr()
        if _ocr_mod.OCR_ENGINE:
            self.log(f"OCR 준비: {_ocr_mod.OCR_ENGINE}")
        else:
            self.log(f"OCR 준비: 없음 — {_ocr_mod._init_error}")

    def refresh_windows(self):
        self.windows_list = enum_visible_windows()
        labels = []
        for hwnd, title, exe in self.windows_list:
            if "lineage" not in title.lower() and "lineage" not in exe.lower():
                continue
            m = re.search(r'\[([^\[\]]+@[^\[\]]+)\]', title)
            email_str = f"[{m.group(1)}]  " if m else ""
            t = title[:40] + "…" if len(title) > 40 else title
            e = f"[{exe}]" if exe else ""
            labels.append(f"{email_str}{t}  {e}  #{hwnd}")
        if self.hj_combo:
            self.hj_combo.configure(values=labels)
        if hasattr(self, "hj_combo_sub"):
            self.hj_combo_sub.configure(values=labels)
            if labels:
                self.hj_combo.set(labels[0])

    def _get_hwnd(self):
        try:
            return int(self.hj_combo.get().rsplit("#", 1)[-1].strip())
        except Exception:
            return None

    def _get_sub_hwnd(self):
        try:
            return int(self.hj_combo_sub.get().rsplit("#", 1)[-1].strip())
        except Exception:
            return None

    def _toggle_dual_mode(self):
        """2대 모드 체크박스 콜백 — 관련 프레임 show/hide"""
        on = self._dual_client_var.get()
        for frame in self._dual_frames:
            if on:
                frame.pack(fill="x", pady=(2, 0))
            else:
                frame.pack_forget()

    def _select_sub_mp_region(self):
        self.iconify()
        def _cb(region):
            self.deiconify()
            if region:
                self._sub_mp_region = region
                x1, y1, x2, y2 = region
                self._sub_mp_region_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
                self.log(f"서브 MP 영역: ({x1},{y1})~({x2},{y2})")
                self._save_config_hj()
        self.after(300, lambda: RegionSelector(_cb))

    def _pick_sub_shot_pos(self):
        self.iconify()
        def _cb(result):
            self.deiconify()
            if result:
                x, y = result
                self._sub_shot_pos = (x, y)
                self.after(0, lambda: self._sub_shot_pos_lbl.configure(
                    text=f"({x}, {y})", text_color="#22C55E"))
                self.log(f"서브 손님 위치 저장: ({x}, {y})")
                self._save_config_hj()
        self.after(200, lambda: PointSelector(_cb))

    # ── UI 구성 ──────────────────────────
    def _build_ui(self):
        label, color = self._MODE_META.get(self.mode, ("헤이장사", "#A855F7"))

        hdr = ctk.CTkFrame(self, fg_color="#10061A", corner_radius=0, height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🛒  배미유니버스 — 헤이장사",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#FFFFFF").pack(side="left", padx=20)
        ctk.CTkLabel(hdr, text=label, font=ctk.CTkFont(size=12),
                     fg_color=color, corner_radius=6,
                     text_color="#FFFFFF").pack(side="left", ipadx=8, ipady=2)
        ctk.CTkButton(hdr, text="📋 로그", width=80, height=32,
                      fg_color="transparent", border_width=1, border_color="#334155",
                      text_color="#FFFFFF", font=ctk.CTkFont(size=12),
                      command=self._toggle_hj_log_popup
                      ).pack(side="right", padx=(0, 4))
        ctk.CTkButton(hdr, text="💰 판매기록", width=100, height=32,
                      fg_color="transparent", border_width=1, border_color="#334155",
                      text_color="#FFFFFF", font=ctk.CTkFont(size=12),
                      command=self._toggle_sales_popup
                      ).pack(side="right", padx=(0, 4))

        if self.mode == "헤이장사_싱글":
            self._build_fixed_ctrl_panel()

        s = ctk.CTkScrollableFrame(self, fg_color="#0A0F1E", corner_radius=0)
        s.pack(fill="both", expand=True)

        if self.mode == "헤이장사_싱글":
            self._build_single_ui(s)
        elif self.mode == "헤이장사_멀티_호스트":
            self._build_skeleton(s, "#F59E0B", [
                ("① 윈도우 선택",     "호스트 본인 창 선택"),
                ("② 클라이언트 관리", "접속된 클라이언트 목록 / 제어"),
                ("③ 판매 명령 전송",  "전체 / 개별 클라이언트 명령"),
                ("④ 채팅 광고",       "공동 채팅 광고 전송"),
                ("⑤ 제어 패널",       "시작 / 중지 / 로그"),
            ])
        elif self.mode == "헤이장사_멀티_클라이언트":
            self._build_skeleton(s, "#3B82F6", [
                ("① 호스트 연결",  "호스트 IP / 포트 입력 및 연결"),
                ("② 윈도우 선택",  "이 PC의 Lineage 창 선택"),
                ("③ Arduino 연결", "HID 기판 포트 설정"),
                ("④ 대기 상태",    "호스트 명령 수신 대기 / 로그"),
            ])

    def _card(self, parent, title, color="#22C55E"):
        outer = ctk.CTkFrame(parent, fg_color="#1E293B", corner_radius=12)
        outer.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(outer, text=title,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=color).pack(anchor="w", padx=16, pady=(12, 8))
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 14))
        return inner

    def _build_skeleton(self, s, color, sections):
        for title, desc in sections:
            outer = ctk.CTkFrame(s, fg_color="#1E293B", corner_radius=12)
            outer.pack(fill="x", padx=16, pady=6)
            ctk.CTkLabel(outer, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color).pack(anchor="w", padx=16, pady=(12, 2))
            ctk.CTkLabel(outer, text=desc, font=ctk.CTkFont(size=12),
                         text_color="#64748B").pack(anchor="w", padx=16)
            ctk.CTkLabel(outer, text="🚧  개발 중", font=ctk.CTkFont(size=12),
                         text_color="#374151").pack(pady=(6, 14))

    # ── 고정 제어 패널 (스크롤 밖 상단 고정) ──
    def _build_fixed_ctrl_panel(self):
        G = "#22C55E"
        fixed = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0)
        fixed.pack(fill="x")
        ctk.CTkLabel(fixed, text="자동 판매 제어",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=G).pack(anchor="w", padx=16, pady=(10, 6))
        ctrl = ctk.CTkFrame(fixed, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(0, 10))
        self._start_btn = ctk.CTkButton(
            ctrl, text="▶ 시작", width=160, height=38,
            fg_color=G, hover_color="#16A34A",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start)
        self._start_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = ctk.CTkButton(
            ctrl, text="■ 중지", width=160, height=38,
            fg_color="#374151", hover_color="#374151",
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled", command=self._stop)
        self._stop_btn.pack(side="left")
        ctk.CTkLabel(ctrl, text="[Del]",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left", padx=(6, 0))
        ctk.CTkButton(
            ctrl, text="💾 환경저장", width=110, height=38,
            fg_color="#1E40AF", hover_color="#1D4ED8",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_config_and_notify
        ).pack(side="left", padx=(8, 0))
        self._status_lbl = ctk.CTkLabel(
            ctrl, text="● 대기 중", font=ctk.CTkFont(size=12), text_color="#64748B")
        self._status_lbl.pack(side="left", padx=12)

    # ── 싱글모드 UI ──────────────────────
    def _build_single_ui(self, s):
        G = "#22C55E"

        # ⚡ Arduino HID 연결
        fa = self._card(s, "⚡ Arduino HID 연결", "#F59E0B")
        ra = ctk.CTkFrame(fa, fg_color="transparent"); ra.pack(fill="x")
        ctk.CTkLabel(ra, text="COM:", font=ctk.CTkFont(size=12),
                     text_color="white", width=36).pack(side="left")
        self._hj_com_var = ctk.StringVar(value="COM3")
        _ports = [p.device for p in serial.tools.list_ports.comports()] if _SERIAL_OK else ["COM3"]
        self._hj_com_combo = ctk.CTkComboBox(
            ra, values=_ports, variable=self._hj_com_var,
            width=110, font=ctk.CTkFont(size=12),
            button_color="#F59E0B", button_hover_color="#D97706")
        self._hj_com_combo.pack(side="left", padx=(4, 8))
        self._hj_ard_btn = ctk.CTkButton(
            ra, text="연결", width=80, height=30,
            fg_color="#F59E0B", hover_color="#D97706",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._toggle_arduino_hj)
        self._hj_ard_btn.pack(side="left", padx=(0, 8))
        ctk.CTkButton(ra, text="🔄", width=32, height=30,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=12),
                      command=self._refresh_ports_hj).pack(side="left")
        self._hj_ard_status = ctk.CTkLabel(
            ra, text="● 미연결", font=ctk.CTkFont(size=12), text_color="#64748B")
        self._hj_ard_status.pack(side="left", padx=12)

        # ① 윈도우 선택
        f1 = self._card(s, "① 윈도우 선택", G)
        wr = ctk.CTkFrame(f1, fg_color="transparent"); wr.pack(fill="x")
        ctk.CTkLabel(wr, text="메인:", font=ctk.CTkFont(size=12),
                     text_color="white", width=42).pack(side="left")
        self.hj_combo = ctk.CTkComboBox(
            wr, width=460, state="readonly", font=ctk.CTkFont(size=12),
            button_color=G, button_hover_color="#16A34A",
            dropdown_font=ctk.CTkFont(size=11))
        self.hj_combo.pack(side="left", padx=(4, 6))
        ctk.CTkButton(wr, text="🔄", width=34, height=30,
                      fg_color="#334155", hover_color="#475569",
                      command=self.refresh_windows).pack(side="left")

        # 2대 모드 토글
        dual_toggle_row = ctk.CTkFrame(f1, fg_color="transparent")
        dual_toggle_row.pack(fill="x", pady=(4, 0))
        ctk.CTkCheckBox(dual_toggle_row, text="2대 모드 (서브 클라이언트 사용)",
                        variable=self._dual_client_var,
                        font=ctk.CTkFont(size=12), text_color="white",
                        command=self._toggle_dual_mode).pack(side="left")

        # 서브 창 선택 (2대 모드 전용)
        self._sub_win_frame = ctk.CTkFrame(f1, fg_color="transparent")
        # 처음엔 숨김 — _toggle_dual_mode 가 pack/forget 처리
        ws = ctk.CTkFrame(self._sub_win_frame, fg_color="transparent")
        ws.pack(fill="x")
        ctk.CTkLabel(ws, text="서브:", font=ctk.CTkFont(size=12),
                     text_color="#60A5FA", width=42).pack(side="left")
        self.hj_combo_sub = ctk.CTkComboBox(
            ws, width=460, state="readonly", font=ctk.CTkFont(size=12),
            button_color="#3B82F6", button_hover_color="#2563EB",
            dropdown_font=ctk.CTkFont(size=11))
        self.hj_combo_sub.pack(side="left", padx=(4, 6))
        ctk.CTkButton(ws, text="🔄", width=34, height=30,
                      fg_color="#334155", hover_color="#475569",
                      command=self.refresh_windows).pack(side="left")
        self._dual_frames.append(self._sub_win_frame)

        # ② 평상시 광고
        ORANGE = "#92400E"
        f_ad = self._card(s, "② 평상시 광고", ORANGE)

        for i in range(3):
            ad_row = ctk.CTkFrame(f_ad, fg_color="transparent"); ad_row.pack(fill="x", pady=2)
            ctk.CTkLabel(ad_row, text=f"문구{i+1}:", font=ctk.CTkFont(size=12),
                         text_color="white", width=50).pack(side="left")
            ctk.CTkEntry(ad_row, textvariable=self._ad_msg_vars[i],
                         width=360, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 0))

        # 문구4: MP 연동 슬롯 ({n} 자동 치환, 채팅 최대 6방 표시)
        ad_mp_row = ctk.CTkFrame(f_ad, fg_color="#0F172A", corner_radius=6)
        ad_mp_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(ad_mp_row, text="문구4:", font=ctk.CTkFont(size=12),
                     text_color="#60A5FA", width=50).pack(side="left", padx=(8, 0), pady=4)
        ctk.CTkEntry(ad_mp_row, textvariable=self._ad_msg_vars[3],
                     width=310, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(ad_mp_row, text="← {n}=MP방수(최대6표시)",
                     font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left")

        ad_tim_row = ctk.CTkFrame(f_ad, fg_color="transparent"); ad_tim_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(ad_tim_row, text="전송 주기:", font=ctk.CTkFont(size=12),
                     text_color="white", width=70).pack(side="left")
        ctk.CTkEntry(ad_tim_row, textvariable=self._ad_interval_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(ad_tim_row, text="초  +  랜덤:", font=ctk.CTkFont(size=12),
                     text_color="#94A3B8").pack(side="left")
        ctk.CTkEntry(ad_tim_row, textvariable=self._ad_rnd_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(ad_tim_row, text="초  (순서대로 순환 전송)",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left")

        ad_ctrl = ctk.CTkFrame(f_ad, fg_color="transparent"); ad_ctrl.pack(fill="x", pady=(2, 6))
        self._ad_start_btn = ctk.CTkButton(
            ad_ctrl, text="▶ 광고 시작", width=110, height=30,
            fg_color="#B45309", hover_color="#92400E",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._start_ad)
        self._ad_start_btn.pack(side="left", padx=(0, 6))
        self._ad_stop_btn = ctk.CTkButton(
            ad_ctrl, text="■ 광고 중지", width=110, height=30,
            fg_color="#374151", hover_color="#374151",
            state="disabled",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._stop_ad)
        self._ad_stop_btn.pack(side="left")
        self._ad_status_lbl = ctk.CTkLabel(
            ad_ctrl, text="● 대기", font=ctk.CTkFont(size=11), text_color="#64748B")
        self._ad_status_lbl.pack(side="left", padx=10)

        # ③ 창 정렬 / 크기
        f2a = self._card(s, "③ 창 정렬 / 크기", "#0EA5E9")
        r1 = ctk.CTkFrame(f2a, fg_color="transparent"); r1.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(r1, text="크기:", font=ctk.CTkFont(size=12),
                     text_color="white", width=36).pack(side="left")
        ctk.CTkLabel(r1, text="가로", font=ctk.CTkFont(size=12),
                     text_color="#64748B").pack(side="left")
        self._hj_win_w = ctk.CTkEntry(r1, width=72, font=ctk.CTkFont(size=12))
        self._hj_win_w.insert(0, "800"); self._hj_win_w.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(r1, text="세로", font=ctk.CTkFont(size=12),
                     text_color="#64748B").pack(side="left")
        self._hj_win_h = ctk.CTkEntry(r1, width=72, font=ctk.CTkFont(size=12))
        self._hj_win_h.insert(0, "600"); self._hj_win_h.pack(side="left", padx=(4, 16))
        ctk.CTkButton(r1, text="✔ 창 정렬 적용", width=130, height=30,
                      fg_color="#0F4C81", hover_color="#0D3D6C",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._arrange_window_hj).pack(side="left")

        # 레이아웃 (2대 모드 전용)
        self._layout_frame = ctk.CTkFrame(f2a, fg_color="transparent")
        ctk.CTkLabel(self._layout_frame, text="배치:", font=ctk.CTkFont(size=12),
                     text_color="white", width=36).pack(side="left")
        for lbl in ("좌우", "상하"):
            ctk.CTkRadioButton(self._layout_frame, text=lbl, variable=self._layout_var,
                               value=lbl, font=ctk.CTkFont(size=12),
                               radiobutton_width=16, radiobutton_height=16
                               ).pack(side="left", padx=(4, 12))
        ctk.CTkLabel(self._layout_frame, text="(2대 모드 — 메인 좌상, 서브 우측/하단)",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left")
        self._dual_frames.append(self._layout_frame)

        r2 = ctk.CTkFrame(f2a, fg_color="transparent"); r2.pack(fill="x")
        ctk.CTkLabel(r2, text="프리셋:", font=ctk.CTkFont(size=12),
                     text_color="#64748B", width=36).pack(side="left")
        for label, w, h in [("800×600","800","600"), ("1024×768","1024","768"),
                             ("1280×720","1280","720"), ("1366×768","1366","768")]:
            ctk.CTkButton(r2, text=label, width=88, height=26,
                          fg_color="#334155", hover_color="#475569",
                          font=ctk.CTkFont(size=11),
                          command=lambda ww=w, hh=h: (
                              self._hj_win_w.delete(0, "end"), self._hj_win_w.insert(0, ww),
                              self._hj_win_h.delete(0, "end"), self._hj_win_h.insert(0, hh)
                          )).pack(side="left", padx=3)

        # ④ 교환 설정
        f2 = self._card(s, "④ 교환 설정", G)
        r2 = ctk.CTkFrame(f2, fg_color="transparent"); r2.pack(fill="x")
        _keys = ["F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
                 "1","2","3","4","5","6","7","8","9","0"]

        def _lbl(p, t): ctk.CTkLabel(p, text=t, font=ctk.CTkFont(size=12),
                                      text_color="white").pack(side="left")
        def _dim(p, t): ctk.CTkLabel(p, text=t, font=ctk.CTkFont(size=12),
                                      text_color="#64748B").pack(side="left", padx=(2, 14))
        def _entry(p, var, w=56):
            ctk.CTkEntry(p, textvariable=var, width=w,
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 0))

        _lbl(r2, "교환 키:")
        ctk.CTkComboBox(r2, values=_keys, variable=self._exchange_key_var,
                        width=88, state="readonly", font=ctk.CTkFont(size=12),
                        button_color=G, button_hover_color="#16A34A"
                        ).pack(side="left", padx=(4, 20))
        _lbl(r2, "감지 간격:")
        _entry(r2, self._scan_interval_var)
        _dim(r2, "초")
        _lbl(r2, "키입력 대기:")
        _entry(r2, self._action_delay_var)
        _dim(r2, "초")
        _lbl(r2, "재감지 대기:")
        _entry(r2, self._cooldown_var)
        _dim(r2, "초")
        r2b = ctk.CTkFrame(f2, fg_color="transparent"); r2b.pack(fill="x", pady=(4, 0))
        _lbl(r2b, "거래후 대기:")
        _entry(r2b, self._post_trade_delay_var)
        _dim(r2b, "초  (마법 시전 완료 후 다음 손님 감지까지 쉬는 시간)")

        # ⑤ 교환창 확인 설정
        f3 = self._card(s, "⑤ 교환창 확인 설정", G)

        # 거래창 존재 감지 영역
        tw = ctk.CTkFrame(f3, fg_color="#0F172A", corner_radius=6)
        tw.pack(fill="x", pady=(0, 8), padx=2)
        ctk.CTkLabel(tw, text="①창 열림 감지:",
                     font=ctk.CTkFont(size=12), text_color="white", width=90).pack(side="left", padx=(8,0))
        self._trade_win_lbl = ctk.CTkLabel(tw, text="미지정",
                     font=ctk.CTkFont(size=11), text_color="#64748B")
        self._trade_win_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(tw, text="📐 영역 지정", width=96, height=26,
                      fg_color="#DC2626", hover_color="#B91C1C",
                      font=ctk.CTkFont(size=11),
                      command=self._select_trade_win_region).pack(side="left", padx=(0, 6))
        ctk.CTkButton(tw, text="🔍 테스트", width=72, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=lambda: threading.Thread(
                          target=self._test_trade_win, daemon=True).start()
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(tw, text="어두운픽셀%:", font=ctk.CTkFont(size=11),
                     text_color="#94A3B8").pack(side="left")
        ctk.CTkEntry(tw, textvariable=self._trade_win_thr_var,
                     width=48, height=24, font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 8), pady=4)

        # 방당 가격 / 대기 제한
        pr = ctk.CTkFrame(f3, fg_color="transparent"); pr.pack(fill="x", pady=(0, 8))
        _lbl(pr, "방당 가격:")
        ctk.CTkEntry(pr, textvariable=self._price_per_shot_var, width=80,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        _dim(pr, "아데나/방  (ex: 150 → 300아데나=2방, 450=3방)")
        _lbl(pr, "대기 제한:")
        _entry(pr, self._wait_timeout_var)
        _dim(pr, "초")

        # 커서 이동 위치 (금화 슬롯) — 3초 픽
        hv = ctk.CTkFrame(f3, fg_color="transparent"); hv.pack(fill="x", pady=2)
        ctk.CTkLabel(hv, text="커서 위치:", font=ctk.CTkFont(size=12),
                     text_color="white", width=90).pack(side="left")
        self._money_hover_lbl = ctk.CTkLabel(
            hv, text="미지정", font=ctk.CTkFont(size=11), text_color="#64748B")
        self._money_hover_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(hv, text="🎯 3초후 픽", width=96, height=26,
                      fg_color="#7C3AED", hover_color="#6D28D9",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._pick_pos("_money_hover_pos",
                                                     self._money_hover_lbl)
                      ).pack(side="left")
        ctk.CTkLabel(hv, text="← 금화 슬롯 위에 올려두기",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left", padx=8)

        # 돈 표시 영역 — 드래그로 bbox 지정
        mr = ctk.CTkFrame(f3, fg_color="transparent"); mr.pack(fill="x", pady=2)
        ctk.CTkLabel(mr, text="돈 텍스트 영역:", font=ctk.CTkFont(size=12),
                     text_color="white", width=90).pack(side="left")
        self._money_region_lbl = ctk.CTkLabel(
            mr, text="미지정", font=ctk.CTkFont(size=11), text_color="#64748B")
        self._money_region_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(mr, text="📐 영역 지정", width=96, height=26,
                      fg_color=G, hover_color="#16A34A",
                      font=ctk.CTkFont(size=11),
                      command=self._select_money_region).pack(side="left", padx=(0, 6))
        ctk.CTkButton(mr, text="🔍 테스트", width=72, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=lambda: threading.Thread(
                          target=self._test_money_ocr, daemon=True).start()
                      ).pack(side="left")
        self._money_ocr_lbl = ctk.CTkLabel(
            f3, text="인식: —", font=ctk.CTkFont(size=12), text_color="#64748B")
        self._money_ocr_lbl.pack(anchor="w", pady=(2, 2))

        # 캡처 이미지 프리뷰 (원본 + 전처리)
        prev_row = ctk.CTkFrame(f3, fg_color="transparent"); prev_row.pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(prev_row, text="캡처:", font=ctk.CTkFont(size=11),
                     text_color="#64748B").pack(side="left")
        self._money_raw_lbl = ctk.CTkLabel(prev_row, text="—",
            fg_color="#0F172A", corner_radius=4, width=160, height=36)
        self._money_raw_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkLabel(prev_row, text="OCR용:", font=ctk.CTkFont(size=11),
                     text_color="#64748B").pack(side="left")
        self._money_proc_lbl = ctk.CTkLabel(prev_row, text="—",
            fg_color="#0F172A", corner_radius=4, width=160, height=36)
        self._money_proc_lbl.pack(side="left", padx=(4, 0))

        # OK / Cancel — 3초 카운트다운 픽
        for attr, label_text in [("_ok_pos", "OK 버튼"), ("_cancel_pos", "Cancel 버튼")]:
            br = ctk.CTkFrame(f3, fg_color="transparent"); br.pack(fill="x", pady=2)
            ctk.CTkLabel(br, text=f"{label_text}:", font=ctk.CTkFont(size=12),
                         text_color="white", width=90).pack(side="left")
            pos_lbl = ctk.CTkLabel(br, text="미지정", font=ctk.CTkFont(size=11),
                                   text_color="#64748B")
            pos_lbl.pack(side="left", padx=(4, 8))
            self._pos_labels[attr] = pos_lbl
            ctk.CTkButton(br, text="🎯 3초후 픽", width=96, height=26,
                          fg_color="#7C3AED", hover_color="#6D28D9",
                          font=ctk.CTkFont(size=11),
                          command=lambda a=attr, l=pos_lbl: self._pick_pos(a, l)
                          ).pack(side="left", padx=(0, 4))
            ctk.CTkButton(br, text="🖱 테스트 클릭", width=96, height=26,
                          fg_color="#334155", hover_color="#475569",
                          font=ctk.CTkFont(size=11),
                          command=lambda a=attr: threading.Thread(
                              target=self._test_click_pos, args=(a,), daemon=True).start()
                          ).pack(side="left")

        # 상대방 회색 감지 영역 (상대방이 OK 누르면 해당 구간이 회색으로 변함)
        gr = ctk.CTkFrame(f3, fg_color="transparent"); gr.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(gr, text="②상대방 회색:", font=ctk.CTkFont(size=12),
                     text_color="white", width=100).pack(side="left")
        self._trade_gray_lbl = ctk.CTkLabel(
            gr, text="미지정", font=ctk.CTkFont(size=11), text_color="#64748B")
        self._trade_gray_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(gr, text="📐 영역 지정", width=96, height=26,
                      fg_color=G, hover_color="#16A34A",
                      font=ctk.CTkFont(size=11),
                      command=self._select_trade_gray_region).pack(side="left", padx=(0, 6))
        ctk.CTkButton(gr, text="🔍 테스트", width=72, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=lambda: threading.Thread(
                          target=self._test_trade_gray, daemon=True).start()
                      ).pack(side="left")
        ctk.CTkLabel(gr, text="  ← 손님 창 내부 (OK 누르면 회색 변화)",
                     font=ctk.CTkFont(size=10), text_color="#64748B").pack(side="left")
        gtr = ctk.CTkFrame(f3, fg_color="transparent"); gtr.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(gtr, text="변화량 기준(%):", font=ctk.CTkFont(size=12),
                     text_color="#94A3B8", width=90).pack(side="left")
        ctk.CTkEntry(gtr, textvariable=self._trade_gray_threshold_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(gtr, text="(평상시↓ OK후↑ 중간값, 기본 80)", font=ctk.CTkFont(size=11),
                     text_color="#64748B").pack(side="left")

        # ⑥ OCR 감지 영역 (손님 감지)
        f4 = self._card(s, "⑥ OCR 감지 영역  (손님 감지)", G)
        hr = ctk.CTkFrame(f4, fg_color="transparent"); hr.pack(fill="x", pady=(0, 6))
        self._ocr_region_lbl = ctk.CTkLabel(
            hr, text="미지정", font=ctk.CTkFont(size=11), text_color="#64748B")
        self._ocr_region_lbl.pack(side="left")
        ctk.CTkButton(hr, text="즉시 캡처", width=80, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=self._capture_once).pack(side="right", padx=(0, 6))
        ctk.CTkButton(hr, text="📐 영역 지정", width=96, height=26,
                      fg_color=G, hover_color="#16A34A",
                      font=ctk.CTkFont(size=11),
                      command=self._select_region).pack(side="right")

        self._ocr_preview = ctk.CTkLabel(
            f4, text="영역을 지정하면\n캡처 이미지가 표시됩니다",
            font=ctk.CTkFont(size=11), text_color="#374151",
            fg_color="#0F172A", corner_radius=6, width=340, height=120)
        self._ocr_preview.pack()

        # 픽셀 감지 설정
        pr = ctk.CTkFrame(f4, fg_color="transparent"); pr.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(pr, text="흰 픽셀 기준:", font=ctk.CTkFont(size=12),
                     text_color="white").pack(side="left")
        ctk.CTkEntry(pr, textvariable=self._pixel_threshold_var, width=52,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 2))
        ctk.CTkLabel(pr, text="% 이상 → 감지",
                     font=ctk.CTkFont(size=12), text_color="#64748B").pack(side="left", padx=(0, 14))
        ctk.CTkButton(pr, text="🔍 지금 테스트", width=100, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=self._test_pixel_detect).pack(side="left")
        self._ocr_result_lbl = ctk.CTkLabel(
            f4, text="감지: —", font=ctk.CTkFont(size=12), text_color="#64748B")
        self._ocr_result_lbl.pack(anchor="w", pady=(4, 0))

        # ⑦ 마법 시전 설정
        f6 = self._card(s, "⑦ 거래 완료 후 마법 시전", "#7C3AED")

        # ── 손님 위치 (메인 + 서브 인접 배치) ─
        shot_box = ctk.CTkFrame(f6, fg_color="#0F172A", corner_radius=6)
        shot_box.pack(fill="x", pady=(2, 4), padx=2)

        sr = ctk.CTkFrame(shot_box, fg_color="transparent"); sr.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(sr, text="손님(메인):", font=ctk.CTkFont(size=12),
                     text_color="white", width=80).pack(side="left")
        self._shot_pos_lbl = ctk.CTkLabel(sr, text="미지정", font=ctk.CTkFont(size=11),
                                          text_color="#64748B")
        self._shot_pos_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(sr, text="🖱 클릭으로 선택", width=112, height=26,
                      fg_color="#7C3AED", hover_color="#6D28D9",
                      font=ctk.CTkFont(size=11),
                      command=self._pick_shot_pos).pack(side="left", padx=(0, 4))
        ctk.CTkButton(sr, text="테스트", width=60, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=lambda: threading.Thread(
                          target=lambda: self._test_click_pos("_shot_pos"), daemon=True).start()
                      ).pack(side="left")

        # 서브 손님 위치 (2대 모드 전용) — 메인 바로 아래
        self._sub_shot_frame = ctk.CTkFrame(shot_box, fg_color="transparent")
        ssr = ctk.CTkFrame(self._sub_shot_frame, fg_color="transparent"); ssr.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkLabel(ssr, text="손님(서브):", font=ctk.CTkFont(size=12),
                     text_color="#60A5FA", width=80).pack(side="left")
        self._sub_shot_pos_lbl = ctk.CTkLabel(ssr, text="미지정", font=ctk.CTkFont(size=11),
                                              text_color="#64748B")
        self._sub_shot_pos_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(ssr, text="🖱 클릭으로 선택", width=112, height=26,
                      fg_color="#3B82F6", hover_color="#2563EB",
                      font=ctk.CTkFont(size=11),
                      command=self._pick_sub_shot_pos).pack(side="left", padx=(0, 4))
        ctk.CTkButton(ssr, text="테스트", width=60, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=lambda: threading.Thread(
                          target=lambda: self._test_click_pos("_sub_shot_pos"), daemon=True).start()
                      ).pack(side="left")
        self._dual_frames.append(self._sub_shot_frame)

        kr = ctk.CTkFrame(f6, fg_color="transparent"); kr.pack(fill="x", pady=2)
        ctk.CTkLabel(kr, text="마법 키:", font=ctk.CTkFont(size=12),
                     text_color="white", width=80).pack(side="left")
        ctk.CTkEntry(kr, textvariable=self._shot_key_var,
                     width=60, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 16))
        ctk.CTkLabel(kr, text="방 사이 딜레이:", font=ctk.CTkFont(size=12),
                     text_color="white").pack(side="left")
        ctk.CTkEntry(kr, textvariable=self._shot_delay_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(kr, text="초", font=ctk.CTkFont(size=12),
                     text_color="#64748B").pack(side="left")

        nr = ctk.CTkFrame(f6, fg_color="transparent"); nr.pack(fill="x", pady=2)
        ctk.CTkLabel(nr, text="최대 방수:", font=ctk.CTkFont(size=12),
                     text_color="white", width=80).pack(side="left")
        ctk.CTkLabel(nr, text="6방  (방당 가격 × 방수 = 아데나,  MP 부족 시 MP 기준으로 감소)",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left")

        # ⑦ MP 관리 & 거래 채팅
        BLUE = "#1E40AF"
        f7 = self._card(s, "⑧ MP 관리 & 거래 채팅", BLUE)

        # ── MP 영역 박스 (메인/서브 인접) ────────
        mp_box = ctk.CTkFrame(f7, fg_color="#0F172A", corner_radius=6)
        mp_box.pack(fill="x", pady=(2, 4), padx=2)

        mr = ctk.CTkFrame(mp_box, fg_color="transparent"); mr.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(mr, text="MP영역(메인):", font=ctk.CTkFont(size=12),
                     text_color="white", width=90).pack(side="left")
        self._mp_region_lbl2 = ctk.CTkLabel(mr, text="미지정",
                     font=ctk.CTkFont(size=11), text_color="#64748B")
        self._mp_region_lbl2.pack(side="left", padx=(4, 8))
        ctk.CTkButton(mr, text="📐 영역 지정", width=96, height=26,
                      fg_color=G, hover_color="#16A34A", font=ctk.CTkFont(size=11),
                      command=self._select_mp_region).pack(side="left")
        ctk.CTkLabel(mr, text="스캔간격(초):", font=ctk.CTkFont(size=11),
                     text_color="#94A3B8").pack(side="left", padx=(12, 2))
        ctk.CTkEntry(mr, textvariable=self._mp_scan_interval_var,
                     width=44, font=ctk.CTkFont(size=11)).pack(side="left")

        # 서브 MP 영역 (2대 모드 전용) — 메인 바로 아래
        self._sub_mp_frame = ctk.CTkFrame(mp_box, fg_color="transparent")
        smr = ctk.CTkFrame(self._sub_mp_frame, fg_color="transparent")
        smr.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkLabel(smr, text="MP영역(서브):", font=ctk.CTkFont(size=12),
                     text_color="#60A5FA", width=90).pack(side="left")
        self._sub_mp_region_lbl = ctk.CTkLabel(smr, text="미지정",
                     font=ctk.CTkFont(size=11), text_color="#64748B")
        self._sub_mp_region_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(smr, text="📐 영역 지정", width=96, height=26,
                      fg_color="#3B82F6", hover_color="#2563EB", font=ctk.CTkFont(size=11),
                      command=self._select_sub_mp_region).pack(side="left")
        self._dual_frames.append(self._sub_mp_frame)

        mp2 = ctk.CTkFrame(f7, fg_color="transparent"); mp2.pack(fill="x", pady=2)
        ctk.CTkLabel(mp2, text="1방당 MP:", font=ctk.CTkFont(size=12),
                     text_color="white", width=80).pack(side="left")
        ctk.CTkEntry(mp2, textvariable=self._mp_per_shot_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 8))
        ctk.CTkLabel(mp2, text="최대 MP:", font=ctk.CTkFont(size=12),
                     text_color="white").pack(side="left")
        ctk.CTkEntry(mp2, textvariable=self._mp_max_var,
                     width=60, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(mp2, text="(초과 시 OCR 오류로 무시)",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left", padx=(2, 12))
        ctk.CTkCheckBox(mp2, text="방 수 채팅 알림",
                        variable=self._mp_announce_var,
                        font=ctk.CTkFont(size=12), text_color="white").pack(side="left")

        mp3 = ctk.CTkFrame(f7, fg_color="transparent"); mp3.pack(fill="x", pady=2)
        ctk.CTkLabel(mp3, text="알림 형식:", font=ctk.CTkFont(size=12),
                     text_color="white", width=80).pack(side="left")
        ctk.CTkEntry(mp3, textvariable=self._mp_announce_tmpl,
                     width=180, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(mp3, text="({n}=방수)", font=ctk.CTkFont(size=11),
                     text_color="#64748B").pack(side="left", padx=(0, 12))


        # MP 상태 표시 + 지금 읽기 버튼
        mp4 = ctk.CTkFrame(f7, fg_color="transparent"); mp4.pack(fill="x", pady=2)
        ctk.CTkButton(mp4, text="🔍 지금 읽기", width=96, height=26,
                      fg_color="#374151", hover_color="#4B5563", font=ctk.CTkFont(size=11),
                      command=self._test_read_mp).pack(side="left", padx=(0, 8))
        self._mp_status_lbl = ctk.CTkLabel(mp4, text="MP: —",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color="#60A5FA")
        self._mp_status_lbl.pack(side="left")

        # ── 엠탐중 설정 박스 ───────────────
        em_box = ctk.CTkFrame(f7, fg_color="#0F172A", corner_radius=6)
        em_box.pack(fill="x", pady=(8, 4), padx=2)
        em_hdr = ctk.CTkFrame(em_box, fg_color="transparent"); em_hdr.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkCheckBox(em_hdr, text="0방일 때 엠탐중 메시지 전송",
                        variable=self._mp_low_enabled_var,  # 3방 미만 시 엠탐중
                        font=ctk.CTkFont(size=12), text_color="white").pack(side="left")

        em_msg = ctk.CTkFrame(em_box, fg_color="transparent"); em_msg.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(em_msg, text="메시지:", font=ctk.CTkFont(size=12),
                     text_color="white", width=60).pack(side="left")
        ctk.CTkEntry(em_msg, textvariable=self._mp_low_msg_var,
                     width=220, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 0))

        em_tim = ctk.CTkFrame(em_box, fg_color="transparent"); em_tim.pack(fill="x", padx=8, pady=(2, 6))
        ctk.CTkLabel(em_tim, text="전송 주기:", font=ctk.CTkFont(size=12),
                     text_color="white", width=60).pack(side="left")
        ctk.CTkEntry(em_tim, textvariable=self._mp_low_interval_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(em_tim, text="초  +  랜덤:",
                     font=ctk.CTkFont(size=12), text_color="#94A3B8").pack(side="left")
        ctk.CTkEntry(em_tim, textvariable=self._mp_low_rnd_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(em_tim, text="초  (주기 + 0~랜덤 사이 랜덤 슬립)",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left")

        # ── 자동 라이트 박스 ───────────────────
        lt_box = ctk.CTkFrame(f7, fg_color="#0F172A", corner_radius=6)
        lt_box.pack(fill="x", pady=(8, 4), padx=2)
        lt_hdr = ctk.CTkFrame(lt_box, fg_color="transparent"); lt_hdr.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkCheckBox(lt_hdr, text="자동 라이트 (밤 어둠 방지 — 시작 시 즉시 + 주기적 재시전)",
                        variable=self._auto_light_var,
                        font=ctk.CTkFont(size=12), text_color="white").pack(side="left")
        lt_row = ctk.CTkFrame(lt_box, fg_color="transparent"); lt_row.pack(fill="x", padx=8, pady=(2, 6))
        ctk.CTkLabel(lt_row, text="키:", font=ctk.CTkFont(size=12),
                     text_color="white", width=24).pack(side="left")
        ctk.CTkEntry(lt_row, textvariable=self._light_key_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 12))
        ctk.CTkLabel(lt_row, text="주기:", font=ctk.CTkFont(size=12),
                     text_color="white").pack(side="left")
        ctk.CTkEntry(lt_row, textvariable=self._light_interval_var,
                     width=52, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkLabel(lt_row, text="분  (봇 시작 후 N분마다 재시전)",
                     font=ctk.CTkFont(size=11), text_color="#64748B").pack(side="left")

        # 거래 완료 채팅
        ctk.CTkLabel(f7, text="거래 완료 채팅:", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="white").pack(anchor="w", pady=(8, 2))
        for i in range(3):
            tr = ctk.CTkFrame(f7, fg_color="transparent"); tr.pack(fill="x", pady=2)
            ctk.CTkCheckBox(tr, text="", variable=self._thanks_en[i], width=24,
                            ).pack(side="left")
            ctk.CTkEntry(tr, textvariable=self._thanks_vars[i],
                         width=280, height=26, font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 0))

        # 로그 팝업은 UI 완성 직후 생성
        self.after(200, self._build_hj_log_popup)
        self.after(200, self._build_sales_popup)

    # ── 로그 팝업 ─────────────────────────
    def _build_hj_log_popup(self):
        if self._hj_log_popup is not None:
            return
        popup = ctk.CTkToplevel(self)
        popup.title("헤이장사 로그")
        popup.geometry("720x380")
        popup.configure(fg_color="#0A0F1E")
        popup.protocol("WM_DELETE_WINDOW", self._hide_hj_log_popup)
        # 헤더
        hdr = ctk.CTkFrame(popup, fg_color="#1E293B", corner_radius=0, height=36)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  📋 헤이장사 로그",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color="white").pack(side="left", padx=8)
        ctk.CTkButton(hdr, text="🗑 지우기", width=80, height=26,
                      fg_color="transparent", border_width=1, border_color="#334155",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._hj_log_box.delete("1.0", "end")
                      ).pack(side="right", padx=8)
        # 텍스트박스
        self._hj_log_box = ctk.CTkTextbox(
            popup, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0A0F1E", text_color="#A0AEC0",
            scrollbar_button_color="#334155")
        self._hj_log_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._hj_log_popup = popup
        popup.withdraw()

    def _toggle_hj_log_popup(self):
        if self._hj_log_popup is None:
            return
        if self._hj_log_popup.winfo_viewable():
            self._hide_hj_log_popup()
        else:
            self._hj_log_popup.deiconify()
            self._hj_log_popup.lift()

    def _hide_hj_log_popup(self):
        if self._hj_log_popup:
            self._hj_log_popup.withdraw()

    # ── 판매 기록 팝업 ───────────────────────
    def _build_sales_popup(self):
        if self._sales_popup is not None:
            return
        popup = ctk.CTkToplevel(self)
        popup.title("판매 기록")
        popup.geometry("500x400")
        popup.configure(fg_color="#0A0F1E")
        popup.protocol("WM_DELETE_WINDOW", popup.withdraw)

        hdr = ctk.CTkFrame(popup, fg_color="#1E293B", corner_radius=0, height=36)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  💰 판매 기록",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color="white").pack(side="left", padx=8)
        self._sales_total_lbl = ctk.CTkLabel(hdr, text="합계: 0 아데나",
                     font=ctk.CTkFont(size=12), text_color="#22C55E")
        self._sales_total_lbl.pack(side="left", padx=16)
        ctk.CTkButton(hdr, text="🗑 초기화", width=80, height=26,
                      fg_color="transparent", border_width=1, border_color="#334155",
                      font=ctk.CTkFont(size=11),
                      command=self._clear_sales).pack(side="right", padx=8)

        # 컬럼 헤더
        col_frame = ctk.CTkFrame(popup, fg_color="#1E293B", height=28)
        col_frame.pack(fill="x", padx=4, pady=(4, 0)); col_frame.pack_propagate(False)
        for text, w in [("시각", 100), ("금액 (아데나)", 160), ("방 수", 80), ("누적 (아데나)", 140)]:
            ctk.CTkLabel(col_frame, text=text, width=w, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#94A3B8", anchor="center").pack(side="left", padx=2)

        self._sales_scroll = ctk.CTkScrollableFrame(popup, fg_color="#0A0F1E")
        self._sales_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        self._sales_popup = popup
        popup.withdraw()

    def _toggle_sales_popup(self):
        if self._sales_popup is None:
            self._build_sales_popup()
        if self._sales_popup.winfo_viewable():
            self._sales_popup.withdraw()
        else:
            self._sales_popup.deiconify()
            self._sales_popup.lift()

    def _clear_sales(self):
        self._sales_records.clear()
        for w in self._sales_scroll.winfo_children():
            w.destroy()
        self._sales_total_lbl.configure(text="합계: 0 아데나")

    def _add_sale_record(self, amount: int, shots: int):
        ts = time.strftime("%H:%M:%S")
        self._sales_records.append({"time": ts, "amount": amount, "shots": shots})
        total = sum(r["amount"] for r in self._sales_records)
        cumul = total

        def _ui():
            if self._sales_popup is None:
                self._build_sales_popup()
            row = ctk.CTkFrame(self._sales_scroll,
                               fg_color="#0F1E38" if len(self._sales_records) % 2 == 0 else "#0A0F1E",
                               height=28)
            row.pack(fill="x", pady=1); row.pack_propagate(False)
            for text, w in [(ts, 100), (f"{amount:,}", 160), (f"{shots}", 80), (f"{cumul:,}", 140)]:
                ctk.CTkLabel(row, text=text, width=w, font=ctk.CTkFont(family="Consolas", size=11),
                             text_color="#E2E8F0", anchor="center").pack(side="left", padx=2)
            self._sales_total_lbl.configure(text=f"합계: {total:,} 아데나")
            self._sales_scroll._parent_canvas.yview_moveto(1.0)
        self.after(0, _ui)

    # ── 교환창 확인 설정 헬퍼 ───────────
    def _select_money_region(self):
        self.iconify()
        def _cb(region):
            self.deiconify()
            if region:
                self._money_region = region
                x1, y1, x2, y2 = region
                self._money_region_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
                self._save_config_hj()
                self.log(f"돈 표시 영역 지정: ({x1},{y1})~({x2},{y2})")
        self.after(300, lambda: RegionSelector(_cb))

    def _select_trade_win_region(self):
        self.iconify()
        def _cb(region):
            self.deiconify()
            if region:
                self._trade_win_region = region
                x1, y1, x2, y2 = region
                self._trade_win_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
                self._save_config_hj()
                self.log(f"거래창 감지 영역 지정: ({x1},{y1})~({x2},{y2})")
        self.after(300, lambda: RegionSelector(_cb))

    @staticmethod
    def _dark_ratio(pixels, thr_brightness=90):
        """밝기 ≤ thr_brightness 픽셀 비율(%) 반환"""
        total = len(pixels) or 1
        dark = sum(1 for r, g, b in pixels if (r + g + b) // 3 <= thr_brightness)
        return dark / total * 100

    def _detect_trade_window(self) -> bool:
        """거래창 감지: 영역 내 어두운 픽셀(밝기≤90) 비율로 판정"""
        if not self._trade_win_region:
            return True
        x1, y1, x2, y2 = self._trade_win_region
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
            pixels = list(img.getdata())
            try:
                thr = float(self._trade_win_thr_var.get())
            except Exception:
                thr = 20.0
            ratio = self._dark_ratio(pixels)
            return ratio >= thr
        except Exception:
            return True

    def _test_trade_win(self):
        if not self._trade_win_region:
            self.log("⚠ 거래창 감지 영역 미지정"); return
        x1, y1, x2, y2 = self._trade_win_region
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
            pixels = list(img.getdata())
            try:
                thr = float(self._trade_win_thr_var.get())
            except Exception:
                thr = 20.0
            ratio = self._dark_ratio(pixels)
            found = ratio >= thr
            self.log(f"거래창 감지 테스트: 어두운픽셀(≤90) {ratio:.1f}% / 기준 {thr:.0f}%  →  {'✅ 감지됨' if found else '❌ 없음'}")
        except Exception as e:
            self.log(f"거래창 감지 오류: {e}")

    def _select_trade_gray_region(self):
        self.iconify()
        def _cb(region):
            self.deiconify()
            if region:
                self._trade_gray_region = region
                x1, y1, x2, y2 = region
                self._trade_gray_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
                self._save_config_hj()
                self.log(f"거래확인 영역 지정: ({x1},{y1})~({x2},{y2})")
        self.after(300, lambda: RegionSelector(_cb))

    def _gray_ratio(self) -> float:
        """회색 감지 영역의 회색 픽셀 비율(%) 반환"""
        if not self._trade_gray_region:
            return 0.0
        x1, y1, x2, y2 = self._trade_gray_region
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
            pixels = list(img.getdata())
            total = len(pixels) or 1
            gray_cnt = sum(
                1 for r, g, b in pixels
                if (max(r, g, b) - min(r, g, b)) <= 30
                and 20 <= (r + g + b) // 3 <= 210
            )
            return gray_cnt / total * 100
        except Exception:
            return 0.0

    def _detect_trade_done(self) -> bool:
        """채팅 영역 OCR로 '거래가 완료' 텍스트 감지"""
        if not self._trade_gray_region:
            return False
        x1, y1, x2, y2 = self._trade_gray_region
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
            from core.ocr_engine import ocr_read
            text = ocr_read(img, numbers_only=False)
            return "완료" in text
        except Exception:
            return False

    def _test_trade_gray(self):
        """상대방 회색 감지 영역 현재 비율 테스트"""
        if not self._trade_gray_region:
            self.log("⚠ 상대방 회색 영역 미지정")
            return
        try:
            ratio = self._gray_ratio()
            try:
                thr = float(self._trade_gray_threshold_var.get())
            except Exception:
                thr = 10.0
            self.log(f"회색 테스트: {ratio:.1f}%  (기준 {thr:.0f}% {'→ ⬛ OK 감지' if ratio >= thr else '→ 대기 중'})")
        except Exception as e:
            self.log(f"회색 테스트 오류: {e}")

    def _test_money_ocr(self):
        """교환창 열린 상태에서 수동으로 금액 인식 테스트"""
        amount = self._ocr_money_amount()
        if amount is None:
            self.after(0, lambda: self._money_ocr_lbl.configure(
                text="인식: 실패 (영역 미지정 또는 OCR 오류)", text_color="#EF4444"))
            self.log("💰 금액 인식 실패")
        else:
            try:
                price_per = int(self._price_per_shot_var.get())
            except Exception:
                price_per = 0
            n = amount // price_per if price_per > 0 else 0
            match = n >= 1
            color = "#22C55E" if match else "#EF4444"
            mark  = f"✅ {n}방" if match else "❌ 부족"
            self.after(0, lambda a=amount, c=color, m=mark: self._money_ocr_lbl.configure(
                text=f"인식: {a:,} 아데나  →  {m}", text_color=c))
            self.log(f"💰 금액 인식: {amount:,} 아데나  {mark}")

    def _pick_pos(self, attr: str, lbl):
        """3초 카운트다운 후 현재 커서 위치를 캡처 후 자동 저장"""
        self.iconify()
        def _run():
            for i in range(3, 0, -1):
                self.after(0, lambda n=i: lbl.configure(
                    text=f"준비: {n}초…", text_color="#F59E0B"))
                time.sleep(1)
            x, y = win32api.GetCursorPos()
            setattr(self, attr, (x, y))
            self.after(0, lambda: (
                lbl.configure(text=f"({x}, {y})", text_color="#22C55E"),
                self.deiconify(),
                self._save_config_hj()
            ))
        threading.Thread(target=_run, daemon=True).start()

    def _select_mp_region(self):
        self.iconify()
        def _cb(region):
            self.deiconify()
            if region:
                self._mp_region = region
                x1, y1, x2, y2 = region
                self._mp_region_lbl2.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
                self._save_config_hj()
                self.log(f"MP 영역 지정: ({x1},{y1})~({x2},{y2})")
        self.after(300, lambda: RegionSelector(_cb))

    def _read_mp(self, region=None) -> int | None:
        """MP OCR → 현재 MP 정수 반환 (None=실패). region 미지정 시 self._mp_region 사용.
        최대 MP(self._mp_max_var) 초과 시 OCR 오류로 간주해 None 반환."""
        r = region or self._mp_region
        if not r:
            self.log("MP OCR: region 미설정", tag="OCR")
            return None
        if not _ocr_mod.OCR_ENGINE:
            self.log("MP OCR: OCR 엔진 없음", tag="OCR")
            return None
        try:
            mp_max = int(self._mp_max_var.get())
        except Exception:
            mp_max = 9999
        x1, y1, x2, y2 = r
        try:
            from PIL import ImageEnhance
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
            big = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
            big = ImageEnhance.Contrast(big).enhance(2.5)
            big = ImageEnhance.Sharpness(big).enhance(2.0)
            text = ocr_read(big, numbers_only=False) or ""
            self.log(f"원문: '{text}'", tag="OCR")
            # "N/M" 형식이면 현재값(첫 번째)만
            m = re.search(r'(\d+)\s*/\s*(\d+)', text)
            if m:
                cur, mx = int(m.group(1)), int(m.group(2))
                if cur > mx:
                    cur, mx = mx, cur
                if cur > mp_max:
                    self.log(f"MP OCR 이상값 무시: {cur} > 최대MP {mp_max}", tag="OCR")
                    return None
                self.log(f"MP 현재={cur} / 최대={mx}", tag="OCR")
                return cur
            # '/' 완전 누락 폴백: 4~6자리 숫자를 N/M으로 분해 시도
            nums = re.findall(r'\d+', text)
            if nums:
                raw = nums[0]
                if 4 <= len(raw) <= 6:
                    for sp in range(2, len(raw) - 1):
                        left, right = int(raw[:sp]), int(raw[sp:])
                        if left <= right <= 9999:
                            if left > mp_max:
                                self.log(f"MP OCR 이상값 무시: {left} > 최대MP {mp_max}", tag="OCR")
                                return None
                            self.log(f"MP 분해: {raw} → {left}/{right}", tag="OCR")
                            return left
                val = int(raw)
                if val > mp_max:
                    self.log(f"MP OCR 이상값 무시: {val} > 최대MP {mp_max}", tag="OCR")
                    return None
                return val
        except Exception as e:
            self.log(f"오류: {e}", tag="OCR")
        return None

    def _send_chat_hj(self, text: str):
        """Lineage 채팅 전송 — 메인 앱과 동일한 WM_CHAR CP949 방식
        Lock으로 동시 전송 방지 (메시지 끊김 원인 제거)"""
        hwnd = self._get_hwnd()
        if not hwnd or not text.strip():
            return
        try:
            encoded = text.encode('cp949')
        except UnicodeEncodeError:
            encoded = text.encode('ascii', errors='replace')

        with self._chat_lock:
            force_foreground(hwnd)
            time.sleep(0.15)
            # force_foreground의 ALT 시뮬레이션이 Alt+Enter로 먹히는 것 방지
            import win32con as _wc
            win32api.keybd_event(_wc.VK_MENU, 0, _wc.KEYEVENTF_KEYUP, 0)
            time.sleep(0.15)

            # Enter로 채팅창 열기
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

        self.log(f"💬 채팅: {text}")

    def _announce_shots(self):
        """광고 직전 MP 즉시 캡처 → 가능 방 수 채팅 알림."""
        try:
            per = max(1, int(self._mp_per_shot_var.get()))
        except Exception:
            per = 20
        # 광고 시점에만 캡처 (거래 중에는 이 함수 자체가 호출 안 됨)
        if self._mp_region:
            val = self._read_mp()
            if val is not None:
                self._cached_mp = val
        if self._dual_client_var.get() and self._sub_mp_region:
            val2 = self._read_mp(region=self._sub_mp_region)
            if val2 is not None:
                self._cached_mp2 = val2
        mp1 = self._cached_mp  if self._cached_mp  is not None else None
        mp2 = self._cached_mp2 if (self._dual_client_var.get()
                                    and self._cached_mp2 is not None) else None
        if mp1 is None and mp2 is None:
            self.log("⚠ MP 읽기 실패 — 방 수 알림 스킵")
            return
        n1 = mp1 // per if mp1 is not None else 0
        n2 = mp2 // per if mp2 is not None else 0
        real_n = n1 + n2
        chat_n = min(real_n, self._ad_mp_cap)
        # UI 라벨 — 실제 방 수 표시
        if self._dual_client_var.get() and mp2 is not None:
            lbl_text = f"MP: {mp1 or '?'}+{mp2}  →  총 {real_n}방 (메인{n1}+서브{n2}) / 채팅{chat_n}방"
        else:
            lbl_text = f"MP: {mp1}  →  {real_n}방 가능 (채팅표시 {chat_n}방)"
        self.after(0, lambda t=lbl_text: self._mp_status_lbl.configure(text=t))
        if real_n <= 0:
            return
        tmpl = self._mp_announce_tmpl.get()
        msg  = tmpl.replace("{n}", str(chat_n))
        self._send_chat_hj(msg)

    def _announce_shots_loop(self):
        """봇 실행 중 주기적으로 방 수 알림 전송.
        WATCHING/DETECTED/MP_WAIT 상태에서 interval마다 전송,
        거래 진행 중에는 대기했다가 재개."""
        try:
            interval = float(self._mp_announce_interval.get())
        except Exception:
            interval = 30.0
        try:
            rnd_max = float(self._mp_announce_rnd.get())
        except Exception:
            rnd_max = 5.0
        interval = max(5.0, interval)

        while self.running:
            # 거래 진행 중이면 대기 (종료하지 않고 polling)
            if self._trade_state not in ("WATCHING", "DETECTED", "MP_WAIT"):
                time.sleep(0.5)
                continue

            # interval + 랜덤 대기
            sleep_t = interval + random.uniform(0, rnd_max)
            end_t   = time.time() + sleep_t
            while time.time() < end_t:
                if not self.running:
                    return
                time.sleep(0.2)

            if not self.running:
                return
            if self._trade_state in ("WATCHING", "DETECTED", "MP_WAIT"):
                # 3방 미만이면 엠탐중만 전송
                n = self._get_n_shots_from_mp()
                if self._mp_region and n >= 0 and n < 3:
                    msg = self._mp_low_msg_var.get().strip() or "엠탐중"
                    self.log(f"💤 MP {n}방 (3방 미만) — 엠탐중 전송")
                    threading.Thread(target=lambda: self._send_chat_hj(msg), daemon=True).start()
                else:
                    self._announce_shots()

    def _mp_poll_loop(self):
        """백그라운드에서 MP를 캡처해 _cached_mp / _cached_mp2 갱신."""
        while self.running:
            if self._mp_region:
                val = self._read_mp()
                if val is not None:
                    self._cached_mp = val
            if self._dual_client_var.get() and self._sub_mp_region:
                val2 = self._read_mp(region=self._sub_mp_region)
                if val2 is not None:
                    self._cached_mp2 = val2
            try:
                interval = float(self._mp_scan_interval_var.get())
            except Exception:
                interval = 10.0
            interval = max(3.0, interval)
            end_t = time.time() + interval
            while time.time() < end_t:
                if not self.running:
                    return
                time.sleep(0.2)

    def _get_n_shots_from_mp(self) -> int:
        """캐시된 MP 기반 가능 방 수 반환. 2대 모드 시 합산. 캐시 없으면 -1."""
        try:
            per = max(1, int(self._mp_per_shot_var.get()))
        except Exception:
            per = 20
        mp1 = self._cached_mp
        mp2 = self._cached_mp2 if self._dual_client_var.get() else None
        if mp1 is None and mp2 is None:
            return -1
        return (mp1 // per if mp1 is not None else 0) + \
               (mp2 // per if mp2 is not None else 0)

    def _wait_for_mp(self) -> bool:
        """MP가 0방일 때 엠탐중 메시지를 주기적으로 보내며 MP 회복 대기.
        MP가 1방 이상 회복되면 True, 루프 중지 시 False 반환."""
        if not self._mp_low_enabled_var.get():
            return True  # 기능 꺼져 있으면 바로 통과
        try:
            interval = float(self._mp_low_interval_var.get())
        except Exception:
            interval = 30.0
        try:
            rnd_max = float(self._mp_low_rnd_var.get())
        except Exception:
            rnd_max = 5.0
        msg = self._mp_low_msg_var.get().strip() or "엠탐중"

        self.log(f"💤 MP 0방 — 엠탐중 대기 (주기 {interval:.0f}+0~{rnd_max:.0f}초)")
        self.after(0, lambda: self._status_lbl.configure(
            text="💤 엠탐중", text_color="#7C3AED"))

        # 첫 메시지 즉시 전송
        threading.Thread(target=lambda: self._send_chat_hj(msg), daemon=True).start()

        while self.running:
            sleep_t = interval + random.uniform(0, rnd_max)
            end_t = time.time() + sleep_t
            while time.time() < end_t and self.running:
                time.sleep(0.2)
            if not self.running:
                return False
            n = self._get_n_shots_from_mp()
            lbl = f"MP: {n}방" if n >= 0 else "MP: 읽기 실패"
            self.after(0, lambda t=lbl: self._mp_status_lbl.configure(text=t))
            if n >= 3:
                self.log(f"✅ MP 회복 ({n}방) — 거래 재개")
                return True
            self.log(f"💤 엠탐중 재전송 (현재 {n if n >= 0 else '?'}방)")
            threading.Thread(target=lambda: self._send_chat_hj(msg), daemon=True).start()

        return False

    def _test_read_mp(self):
        """UI 버튼 — MP 한 번 읽고 라벨에 표시 (2대 모드 시 합산)"""
        def _run():
            try:
                per = max(1, int(self._mp_per_shot_var.get()))
            except Exception:
                per = 20
            mp1 = self._read_mp() if self._mp_region else None
            mp2 = self._read_mp(region=self._sub_mp_region) \
                  if self._dual_client_var.get() and self._sub_mp_region else None
            if mp1 is None and mp2 is None:
                self.after(0, lambda: self._mp_status_lbl.configure(text="MP: OCR 실패"))
                return
            n1 = mp1 // per if mp1 is not None else 0
            n2 = mp2 // per if mp2 is not None else 0
            n  = n1 + n2
            if self._dual_client_var.get() and mp2 is not None:
                lbl = f"MP: {mp1 or '?'}+{mp2}  →  총 {n}방 (메인{n1}+서브{n2})"
            else:
                lbl = f"MP: {mp1}  →  {n}방 가능"
            self.after(0, lambda t=lbl: self._mp_status_lbl.configure(text=t))
            self.log(f"[MP 테스트] {lbl}")
        threading.Thread(target=_run, daemon=True).start()

    def _send_thanks(self):
        """거래 완료 후 활성화된 감사 메시지 중 랜덤 1개 전송"""
        candidates = [
            var.get().strip()
            for en, var in zip(self._thanks_en, self._thanks_vars)
            if en.get() and var.get().strip()
        ]
        if not candidates:
            return
        msg = random.choice(candidates)
        time.sleep(0.3)
        self._send_chat_hj(msg)

    def _pick_shot_pos(self):
        self.iconify()
        def _cb(result):
            self.deiconify()
            if result:
                x, y = result
                self._shot_pos = (x, y)
                self.after(0, lambda: self._shot_pos_lbl.configure(
                    text=f"({x}, {y})", text_color="#22C55E"))
                self.log(f"메인 손님 위치 저장: ({x}, {y})")
                self._save_config_hj()
        self.after(200, lambda: PointSelector(_cb))

    def _press_key(self, key: str, hwnd=None):
        """단일 키 입력 (Arduino / win32 공통). hwnd 지정 시 해당 창에 포커스."""
        h = hwnd if hwnd is not None else self._get_hwnd()
        if h and win32gui.GetForegroundWindow() != h:
            force_foreground(h)
            time.sleep(0.08)
        if _ar_mod._arduino and _ar_mod._arduino.is_open:
            arduino_send(f"KEY:{key}:60")
        else:
            vk = _KEY_CODES.get(key, 0x74)
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    def _do_magic_shots(self):
        """거래 완료 후 손님 클릭 → 마법 N방 시전"""
        amount = self._last_trade_amount
        if amount <= 0:
            return

        # 방당 가격 기준으로 방 수 계산 (최대 6방)
        try:
            price_per = int(self._price_per_shot_var.get())
        except Exception:
            price_per = 150
        if price_per <= 0:
            price_per = 150
        n_paid = min(amount // price_per, 6)

        # MP 기반 방 수 계산
        try:
            mp_per = int(self._mp_per_shot_var.get())
        except Exception:
            mp_per = 20
        mp = self._read_mp()
        if mp is not None and mp_per > 0:
            n_mp = mp // mp_per
            lbl_mp = f"MP:{mp}/{mp_per}→{n_mp}방"
        else:
            n_mp = n_paid
            lbl_mp = "MP 미확인"

        # ── 2대 모드 분배 계산 ─────────────────
        import math as _math
        dual = self._dual_client_var.get() and bool(self._sub_shot_pos)
        if dual:
            if self._sub_mp_region:
                # 서브 MP 영역 지정됨 → 실제 MP 읽어서 합산
                mp2 = self._read_mp(region=self._sub_mp_region)
                n_mp2 = mp2 // mp_per if (mp2 is not None and mp_per > 0) else 0
                lbl_mp += f"  서브MP:{mp2 if mp2 is not None else '?'}/{mp_per}→{n_mp2}방"
                n_total = min(n_paid, n_mp + n_mp2)
                n_sub   = min(n_total - min(_math.ceil(n_total / 2), n_mp), n_mp2)
                n_main  = min(n_total - n_sub, n_mp)
            else:
                # 서브 MP 영역 미지정 → n_paid 기준으로 반반 분배 (서브 MP 신뢰)
                mp2 = None
                n_mp2 = None
                lbl_mp += "  서브MP:미설정(신뢰)"
                n_total = n_paid          # MP 제한 없이 결제 금액 기준
                n_sub   = n_total // 2    # 내림 → 서브
                n_main  = n_total - n_sub  # 나머지(홀수 시 1방 더) → 메인
                # 메인 MP 초과 방지
                if n_main > n_mp:
                    n_sub  += n_main - n_mp
                    n_main  = n_mp
        else:
            mp2 = None
            n_mp2 = 0
            n_total = min(n_paid, n_mp)
            n_main  = n_total
            n_sub   = 0

        if dual and n_mp2 is not None:
            split_lbl = f"서브{n_sub}+메인{n_main}"
        elif dual:
            split_lbl = f"서브{n_sub}+메인{n_main}"
        else:
            split_lbl = f"메인{n_main}"
        self.log(f"✨ 결제:{amount:,}아데나÷{price_per}={n_paid}방  {lbl_mp}  →  시전:{n_main+n_sub}방 ({split_lbl})")

        if n_main + n_sub <= 0:
            self.log("⚠ 0방 — MP 없거나 금액 부족, 시전 없음")
            return

        key = self._shot_key_var.get()
        try:
            delay = float(self._shot_delay_var.get())
        except Exception:
            delay = 1.5

        # ── ① 서브 시전 (서브가 먼저) ─────────
        if n_sub > 0:
            if not self._sub_shot_pos:
                self.log("⚠ 손님 위치(서브) 미설정 — 서브 시전 스킵")
            else:
                hwnd2 = self._get_sub_hwnd()
                sx2, sy2 = self._sub_shot_pos
                self.log(f"✨ 서브 시전: [{key}] × {n_sub}방")
                for i in range(n_sub):
                    if not self.running: break
                    self._press_key(key, hwnd=hwnd2)   # 서브 창 포커스 후 키 입력
                    time.sleep(0.15)
                    self._click_abs(sx2, sy2, hwnd=hwnd2)  # 서브 창 포커스 후 클릭
                    self.log(f"  ✨ 서브 {i+1}/{n_sub}방")
                    if i < n_sub - 1:
                        time.sleep(delay)

        # ── ② 메인 시전 (서브 완료 후) ─────────
        if n_main > 0:
            if not self._shot_pos:
                self.log("⚠ 손님 위치(메인) 미설정 — 메인 시전 스킵")
            else:
                sx, sy = self._shot_pos
                self.log(f"✨ 메인 시전: [{key}] × {n_main}방")
                for i in range(n_main):
                    if not self.running: break
                    self._press_key(key)          # 메인 창 포커스 후 키 (hwnd=None → 메인)
                    time.sleep(0.15)
                    self._click_abs(sx, sy)       # 메인 창 포커스 후 클릭
                    self.log(f"  ✨ 메인 {i+1}/{n_main}방")
                    if i < n_main - 1:
                        time.sleep(delay)

        self.log(f"✅ {n_sub+n_main}방 완료  ─ 거래 종료  (서브{n_sub}+메인{n_main})")

    def _test_click_pos(self, attr: str):
        """저장된 좌표로 즉시 테스트 클릭 (좌표 검증용)"""
        pos = getattr(self, attr, None)
        if not pos:
            self.log(f"⚠ {attr} 미지정 — 먼저 픽하세요"); return
        x, y = pos
        self.log(f"🖱 테스트 클릭: ({x}, {y})  ← 실제로 클릭됩니다")
        time.sleep(0.5)   # 로그 확인할 시간
        self._click_abs(x, y)

    def _save_config_and_notify(self):
        self._save_config_hj()
        self.log("💾 환경 저장 완료")
        self._status_lbl.configure(text="💾 저장됨", text_color="#3B82F6")
        self.after(2000, lambda: self._status_lbl.configure(
            text="● 대기 중", text_color="#64748B"))

    def _save_config_hj(self):
        import json, os
        cfg = {
            "hj_com_port":       self._hj_com_var.get(),
            "hj_exchange_key":   self._exchange_key_var.get(),
            "hj_scan_interval":  self._scan_interval_var.get(),
            "hj_action_delay":   self._action_delay_var.get(),
            "hj_cooldown":       self._cooldown_var.get(),
            "hj_allowed_prices": self._allowed_prices_var.get(),
            "hj_price_per_shot": self._price_per_shot_var.get(),
            "hj_ad_msgs":        [v.get() for v in self._ad_msg_vars],
            "hj_ad_interval":    self._ad_interval_var.get(),
            "hj_ad_rnd":         self._ad_rnd_var.get(),
            "hj_mp_low_enabled": self._mp_low_enabled_var.get(),
            "hj_mp_low_msg":     self._mp_low_msg_var.get(),
            "hj_mp_low_interval":self._mp_low_interval_var.get(),
            "hj_mp_low_rnd":     self._mp_low_rnd_var.get(),
            "hj_wait_timeout":   self._wait_timeout_var.get(),
            "hj_pixel_threshold":self._pixel_threshold_var.get(),
            "hj_gray_threshold": self._trade_gray_threshold_var.get(),
            "hj_win_w":          self._hj_win_w.get(),
            "hj_win_h":          self._hj_win_h.get(),
            "hj_money_region":   list(self._money_region)       if self._money_region       else None,
            "hj_money_hover":    list(self._money_hover_pos)    if self._money_hover_pos    else None,
            "hj_ok_pos":         list(self._ok_pos)             if self._ok_pos             else None,
            "hj_cancel_pos":     list(self._cancel_pos)         if self._cancel_pos         else None,
            "hj_trade_win_region":  list(self._trade_win_region)  if self._trade_win_region  else None,
            "hj_trade_win_thr":     self._trade_win_thr_var.get(),
            "hj_trade_gray_region": list(self._trade_gray_region) if self._trade_gray_region else None,
            "hj_ocr_region":     list(self.ocr_region)          if self.ocr_region          else None,
            "hj_shot_pos":       list(self._shot_pos)           if self._shot_pos            else None,
            "hj_shot_key":       self._shot_key_var.get(),
            "hj_shot_delay":     self._shot_delay_var.get(),
            "hj_shots_per_price":self._shots_per_price_var.get(),
            "hj_post_trade_delay":self._post_trade_delay_var.get(),
            "hj_mp_region":      list(self._mp_region) if self._mp_region else None,
            "hj_mp_per_shot":    self._mp_per_shot_var.get(),
            "hj_mp_max":         self._mp_max_var.get(),
            "hj_mp_scan_interval": self._mp_scan_interval_var.get(),
            "hj_mp_announce":    self._mp_announce_var.get(),
            "hj_mp_tmpl":        self._mp_announce_tmpl.get(),
            "hj_mp_ann_interval":self._mp_announce_interval.get(),
            "hj_mp_ann_rnd":     self._mp_announce_rnd.get(),
            "hj_thanks":         [v.get() for v in self._thanks_vars],
            "hj_thanks_en":      [v.get() for v in self._thanks_en],
            "hj_auto_light":     self._auto_light_var.get(),
            "hj_light_key":      self._light_key_var.get(),
            "hj_light_interval": self._light_interval_var.get(),
            "hj_dual_client":    self._dual_client_var.get(),
            "hj_layout":         self._layout_var.get(),
            "hj_sub_mp_region":  list(self._sub_mp_region)  if self._sub_mp_region  else None,
            "hj_sub_shot_pos":   list(self._sub_shot_pos)   if self._sub_shot_pos   else None,
        }
        path = os.path.join(_BASE_DIR, "config_hj.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.log(f"저장 완료: {path}", tag="CONFIG")
        except Exception as e:
            self.log(f"저장 실패: {e}", tag="CONFIG")

    def _load_config_hj(self):
        import json, os
        cfg_path = os.path.join(_BASE_DIR, "config_hj.json")
        if not os.path.exists(cfg_path):
            return
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg.get("hj_com_port"):
                self._hj_com_var.set(cfg["hj_com_port"])
                self._hj_com_combo.set(cfg["hj_com_port"])
            self._exchange_key_var.set(cfg.get("hj_exchange_key",  "F5"))
            self._scan_interval_var.set(cfg.get("hj_scan_interval","1.0"))
            self._action_delay_var.set(cfg.get("hj_action_delay",  "0.3"))
            self._cooldown_var.set(cfg.get("hj_cooldown",          "3.0"))
            self._allowed_prices_var.set(cfg.get("hj_allowed_prices","500, 1000"))
            self._price_per_shot_var.set(cfg.get("hj_price_per_shot", "150"))
            _defaults = ["", "", "", r"\fF 헤이 {n}방 가능합니다"]
            for i, v in enumerate(cfg.get("hj_ad_msgs", _defaults)):
                if i < 4: self._ad_msg_vars[i].set(v)
            self._ad_interval_var.set(cfg.get("hj_ad_interval", "60"))
            self._ad_rnd_var.set(cfg.get("hj_ad_rnd",      "10"))
            self._mp_low_enabled_var.set(cfg.get("hj_mp_low_enabled", True))
            self._mp_low_msg_var.set(cfg.get("hj_mp_low_msg",      "엠탐중"))
            self._mp_low_interval_var.set(cfg.get("hj_mp_low_interval","30"))
            self._mp_low_rnd_var.set(cfg.get("hj_mp_low_rnd",      "5"))
            self._wait_timeout_var.set(cfg.get("hj_wait_timeout",  "60"))
            self._pixel_threshold_var.set(cfg.get("hj_pixel_threshold","3.0"))
            if cfg.get("hj_win_w"):
                self._hj_win_w.delete(0, "end"); self._hj_win_w.insert(0, cfg["hj_win_w"])
            if cfg.get("hj_win_h"):
                self._hj_win_h.delete(0, "end"); self._hj_win_h.insert(0, cfg["hj_win_h"])
            self._trade_gray_threshold_var.set(cfg.get("hj_gray_threshold", "80.0"))
            mr = cfg.get("hj_money_region")
            mh = cfg.get("hj_money_hover")
            ok = cfg.get("hj_ok_pos")
            ca = cfg.get("hj_cancel_pos")
            tw = cfg.get("hj_trade_win_region")
            if tw: self._trade_win_region   = tuple(tw)
            self._trade_win_thr_var.set(cfg.get("hj_trade_win_thr", "40.0"))
            tg = cfg.get("hj_trade_gray_region")
            if mr: self._money_region       = tuple(mr)
            if mh: self._money_hover_pos    = tuple(mh)
            if ok: self._ok_pos             = tuple(ok)
            if ca: self._cancel_pos         = tuple(ca)
            if tg: self._trade_gray_region  = tuple(tg)
            ocrr = cfg.get("hj_ocr_region")
            if ocrr:
                self.ocr_region = tuple(ocrr)
            sp = cfg.get("hj_shot_pos")
            if sp: self._shot_pos = tuple(sp)
            self._shot_key_var.set(cfg.get("hj_shot_key",        "F5"))
            self._shot_delay_var.set(cfg.get("hj_shot_delay",    "1.5"))
            self._shots_per_price_var.set(cfg.get("hj_shots_per_price", "3, 6"))
            self._post_trade_delay_var.set(cfg.get("hj_post_trade_delay", "5.0"))
            mpr = cfg.get("hj_mp_region")
            if mpr: self._mp_region = tuple(mpr)
            self._mp_per_shot_var.set(cfg.get("hj_mp_per_shot",  "20"))
            self._mp_max_var.set(cfg.get("hj_mp_max",            "200"))
            self._mp_scan_interval_var.set(cfg.get("hj_mp_scan_interval", "10"))
            self._mp_announce_var.set(cfg.get("hj_mp_announce",  True))
            self._mp_announce_tmpl.set(cfg.get("hj_mp_tmpl",     "{n}방 가능합니다"))
            self._mp_announce_interval.set(cfg.get("hj_mp_ann_interval", "30"))
            self._mp_announce_rnd.set(cfg.get("hj_mp_ann_rnd",   "5"))
            for i, v in enumerate(cfg.get("hj_thanks", [])):
                if i < 3: self._thanks_vars[i].set(v)
            for i, v in enumerate(cfg.get("hj_thanks_en", [])):
                if i < 3: self._thanks_en[i].set(v)
            self._auto_light_var.set(cfg.get("hj_auto_light",    True))
            self._light_key_var.set(cfg.get("hj_light_key",      "F6"))
            self._light_interval_var.set(cfg.get("hj_light_interval", "90"))
            self._dual_client_var.set(cfg.get("hj_dual_client",  False))
            self._layout_var.set(cfg.get("hj_layout",            "좌우"))
            smr = cfg.get("hj_sub_mp_region")
            if smr: self._sub_mp_region = tuple(smr)
            ssp = cfg.get("hj_sub_shot_pos")
            if ssp: self._sub_shot_pos  = tuple(ssp)
            self.log(f"로드 완료: {cfg_path}", tag="CONFIG")
            # UI 라벨은 빌드 후 적용 (after idle)
            self.after(100, self._apply_pos_labels)
        except Exception as e:
            self.log(f"로드 실패: {e}", tag="CONFIG")
            print(f"헤이장사 설정 로드 실패: {e}")

    def _apply_pos_labels(self):
        """로드된 좌표를 UI 라벨에 반영"""
        try:
            if self._money_hover_pos:
                x, y = self._money_hover_pos
                self._money_hover_lbl.configure(
                    text=f"({x}, {y})", text_color="#22C55E")
            if self._money_region:
                x1, y1, x2, y2 = self._money_region
                self._money_region_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
            if self._trade_win_region:
                x1, y1, x2, y2 = self._trade_win_region
                self._trade_win_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
            if self._trade_gray_region:
                x1, y1, x2, y2 = self._trade_gray_region
                self._trade_gray_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
            if self.ocr_region:
                x1, y1, x2, y2 = self.ocr_region
                self._ocr_region_lbl.configure(
                    text=f"({x1},{y1}) → ({x2},{y2})", text_color="#22C55E")
            if self._shot_pos:
                x, y = self._shot_pos
                self._shot_pos_lbl.configure(text=f"({x}, {y})", text_color="#22C55E")
            if self._mp_region:
                x1, y1, x2, y2 = self._mp_region
                self._mp_region_lbl2.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
            if self._sub_shot_pos:
                x, y = self._sub_shot_pos
                self._sub_shot_pos_lbl.configure(text=f"({x}, {y})", text_color="#22C55E")
            if self._sub_mp_region:
                x1, y1, x2, y2 = self._sub_mp_region
                self._sub_mp_region_lbl.configure(
                    text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
            # 2대 모드 저장값 반영 후 UI 토글
            if self._dual_client_var.get():
                self._toggle_dual_mode()
            for attr in ["_ok_pos", "_cancel_pos"]:
                val = getattr(self, attr, None)
                lbl = self._pos_labels.get(attr)
                if val and lbl:
                    lbl.configure(text=f"({val[0]}, {val[1]})", text_color="#22C55E")
        except Exception as e:
            self.log(f"UI 라벨 반영 오류: {e}", tag="CONFIG")

    def _hotkey_listener(self):
        """Delete → 장사 루프 중지 (전역 단축키)"""
        while self._hj_listener_running:
            try:
                if win32api.GetAsyncKeyState(0x2E) & 0x8000:  # VK_DELETE
                    if self.running:
                        self.after(0, self._stop)
                        self.after(0, lambda: self.log("⌨ Delete → 장사 루프 중지"))
                    time.sleep(0.4)
            except Exception:
                pass
            time.sleep(0.05)

    # ── 평상시 광고 ──────────────────────
    def _start_ad(self):
        msgs = [v.get().strip() for v in self._ad_msg_vars if v.get().strip()]
        if not msgs:
            return  # 문구 없으면 조용히 스킵 (자동 시작 시 로그 불필요)
        if self._ad_running:
            return
        self._ad_running = True
        self._ad_start_btn.configure(state="disabled")
        self._ad_stop_btn.configure(state="normal", fg_color="#EF4444", hover_color="#B91C1C")
        self._ad_status_lbl.configure(text="● 광고 중", text_color="#F59E0B")
        self.log("📢 광고 반복 시작")
        threading.Thread(target=self._ad_loop, daemon=True).start()

    def _stop_ad(self):
        self._ad_running = False
        self.after(0, lambda: (
            self._ad_start_btn.configure(state="normal"),
            self._ad_stop_btn.configure(state="disabled", fg_color="#374151", hover_color="#374151"),
            self._ad_status_lbl.configure(text="● 대기", text_color="#64748B"),
        ))
        self.log("📢 광고 반복 중지")

    _AD_SAFE_STATES = {"IDLE", "WATCHING"}

    def _ad_loop(self):
        idx = 0
        while self._ad_running:
            # 거래 진행 중이면 전송 건너뜀
            if self._trade_state not in self._AD_SAFE_STATES:
                self.log(f"거래 중({self._trade_state}) — 광고 전송 보류", tag="AD")
                time.sleep(2.0)
                continue

            msgs = [v.get().strip() for v in self._ad_msg_vars if v.get().strip()]
            if not msgs:
                time.sleep(1.0)
                continue
            msg = msgs[idx % len(msgs)]
            idx += 1
            # {n} 포함 메시지 → MP 캐시로 방 수 치환 (채팅 최대 _ad_mp_cap, 내부 실제값)
            if "{n}" in msg:
                try:
                    per = max(1, int(self._mp_per_shot_var.get()))
                except Exception:
                    per = 20
                mp1 = self._cached_mp  if self._cached_mp  is not None else 0
                mp2 = self._cached_mp2 if (self._dual_client_var.get()
                                            and self._cached_mp2 is not None) else 0
                real_n = (mp1 // per) + (mp2 // per)
                chat_n = min(real_n, self._ad_mp_cap)
                self.log(f"📢 MP={mp1}+{mp2} → 실제{real_n}방 / 채팅{chat_n}방", tag="AD")
                if real_n <= 0:
                    self.log("📢 0방 — MP 메시지 건너뜀", tag="AD")
                    continue
                msg = msg.replace("{n}", str(chat_n))
            self._send_chat_hj(msg)
            try:
                interval = float(self._ad_interval_var.get())
            except Exception:
                interval = 60.0
            try:
                rnd_max = float(self._ad_rnd_var.get())
            except Exception:
                rnd_max = 10.0
            sleep_t = interval + random.uniform(0, rnd_max)
            self.log(f"📢 광고({idx}/{len(msgs)}) 전송 — 다음까지 {sleep_t:.0f}초")
            end_t = time.time() + sleep_t
            while time.time() < end_t and self._ad_running:
                time.sleep(0.2)
        self.after(0, lambda: (
            self._ad_start_btn.configure(state="normal"),
            self._ad_stop_btn.configure(state="disabled", fg_color="#374151", hover_color="#374151"),
            self._ad_status_lbl.configure(text="● 대기", text_color="#64748B"),
        ))

    def _on_close_hj(self):
        self._hj_listener_running = False
        self._ad_running = False
        self._run_evt.clear()
        self._save_config_hj()
        self.log("종료 중 — 스레드 정리", tag="THREAD")
        for t in self._worker_threads:
            if t.is_alive():
                t.join(timeout=0.5)
        if self._hj_log_popup:
            try:
                self._hj_log_popup.destroy()
            except Exception:
                pass
        self.destroy()

    def _get_allowed_prices(self):
        prices = []
        for p in self._allowed_prices_var.get().split(','):
            p = p.strip().replace(' ', '')
            try:
                prices.append(int(p))
            except ValueError:
                pass
        return prices

    def _ocr_money_amount(self):
        """커서를 금화 슬롯으로 이동 → '아데나 (N)' 텍스트 표시 → bbox OCR
        하단 텍스트 영역만 잘라낸 후 엔진별 전처리 × 3회 → 자릿수 최다 반환"""
        if not self._money_region:
            self.log("돈OCR: money_region 미설정", tag="OCR")
            return None
        if not _ocr_mod.OCR_ENGINE:
            self.log("돈OCR: OCR 엔진 없음", tag="OCR")
            return None
        if self._money_hover_pos:
            hx, hy = self._money_hover_pos
            self.log(f"돈OCR: 커서 이동 → ({hx},{hy})", tag="OCR")
            try:
                for dx in (-5, 5, -5, 5, 0):
                    win32api.SetCursorPos((hx + dx, hy))
                    time.sleep(0.07)
                time.sleep(0.4)
            except Exception as e:
                self.log(f"돈OCR: SetCursorPos 실패 — {e}", tag="OCR")
        else:
            self.log("돈OCR: hover_pos 미설정 — 커서 이동 생략", tag="OCR")
        x1, y1, x2, y2 = self._money_region
        from PIL import ImageEnhance, ImageOps
        candidates = []
        first_raw = None
        first_proc = None

        for attempt in range(3):
            try:
                img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
                if attempt == 0:
                    first_raw = img.copy()

                gray_orig = img.convert("L")
                data = list(gray_orig.getdata())
                avg = sum(data) / len(data)
                dark_bg = avg < 150   # 어두운 배경 여부

                # LANCZOS: easyocr은 부드러운 이미지에서 정확도 높음
                imgs_to_try = []
                for scale in (4, 6):
                    big = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
                    big_enh = ImageEnhance.Contrast(big).enhance(1.8)
                    imgs_to_try.append(big_enh)          # 컬러 원본
                    gray_s = big_enh.convert("L")
                    if dark_bg:
                        imgs_to_try.append(ImageOps.invert(gray_s).convert("RGB"))
                    else:
                        imgs_to_try.append(gray_s.convert("RGB"))

                if attempt == 0:
                    first_proc = imgs_to_try[1].copy()   # 반전/그레이 버전을 OCR용 프리뷰로

                for proc in imgs_to_try:
                    # numbers_only=True 우선 (allowlist 적용), 실패 시 False 폴백
                    for n_only in (True, False):
                        try:
                            text = ocr_read(proc, numbers_only=n_only) or ""
                        except Exception as e:
                            self.log(f"OCR 엔진 오류: {e}", tag="OCR")
                            continue
                        if attempt == 0 and text:
                            self.log(f"OCR 원문 (n_only={n_only}): '{text}'", tag="OCR")
                        # 괄호가 그대로 보이는 경우 (n_only=False)
                        m = re.search(r'[\[\(]\s*(\d+)\s*[\]\)]', text)
                        if m:
                            candidates.append(int(m.group(1))); continue
                        # 1자리 단독(괄호 잔상) 제외 → 2자리 이상만 수집
                        # [ → 1(앞), ] → 0/1/9/…(뒤) 오인식 보정
                        for raw in re.findall(r'\d{2,}', text):
                            rlen = len(raw)
                            if rlen == 3 and raw[0] == '1':
                                val = int(raw[1:])       # 190 → 90
                            elif rlen == 4 and raw[0] == '1':
                                val = int(raw[1:])       # 1450 → 450
                            elif rlen == 5 and raw[0] == '1':
                                val = int(raw[1:-1])     # 14500/14509/14501 → 450
                            elif rlen == 3 and raw[-1] == '1' and raw[0] != '1':
                                val = int(raw[:-1])      # 901 → 90 (회색창)
                            elif rlen == 4 and raw[-1] == '1' and raw[0] != '1':
                                val = int(raw[:-1])      # 4501 → 450 (회색창)
                            else:
                                val = int(raw)
                            candidates.append(val)
                        # n_only=False 도 항상 실행 (break 없음)
            except Exception as e:
                self.log(f"캡처/전처리 오류: {e}", tag="OCR")
            time.sleep(0.1)

        # 프리뷰 업데이트 (UI 스레드로)
        def _update_preview(raw_img, proc_img):
            try:
                if raw_img:
                    rw, rh = raw_img.size
                    scale = min(160 / max(rw, 1), 36 / max(rh, 1), 4.0)
                    r = raw_img.resize((max(1, int(rw * scale)), max(1, int(rh * scale))), Image.LANCZOS)
                    ci = ctk.CTkImage(light_image=r, dark_image=r, size=r.size)
                    self._money_raw_lbl.configure(image=ci, text="")
                    self._money_raw_lbl._ctk_image = ci
                if proc_img:
                    pw, ph = proc_img.size
                    scale = min(160 / max(pw, 1), 36 / max(ph, 1), 1.0)
                    p = proc_img.resize((max(1, int(pw * scale)), max(1, int(ph * scale))), Image.LANCZOS)
                    ci2 = ctk.CTkImage(light_image=p, dark_image=p, size=p.size)
                    self._money_proc_lbl.configure(image=ci2, text="")
                    self._money_proc_lbl._ctk_image = ci2
            except Exception:
                pass
        self.after(0, lambda: _update_preview(first_raw, first_proc))

        if not candidates:
            return None
        from collections import Counter
        # 순수 빈도 투표 (max_digits 필터 제거 — 괄호 오인식 시 짧은 값이 정답)
        cnt = Counter(candidates)
        result = cnt.most_common(1)[0][0]
        freq_str = ", ".join(f"{v}×{n}" for v, n in cnt.most_common())
        self.log(f"💰 OCR 후보: {freq_str} → {result}", tag="OCR")
        return result

    def _click_abs(self, x, y, hwnd=None):
        self.log(f"🖱 클릭 → ({x}, {y})")
        h = hwnd if hwnd is not None else self._get_hwnd()
        if h and win32gui.GetForegroundWindow() != h:
            # 이미 포커스된 창이면 force_foreground 스킵
            # (ALT 시뮬레이션이 라이니지 마법 타겟팅 모드를 취소시키기 때문)
            force_foreground(h)
            time.sleep(0.08)
        win32api.SetCursorPos((x, y))
        time.sleep(0.08)
        if _ar_mod._arduino and _ar_mod._arduino.is_open:
            arduino_send("CLICK")
        else:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)

    def _press_key_y(self):
        hwnd = self._get_hwnd()
        if hwnd:
            force_foreground(hwnd)
            time.sleep(0.1)
        if _ar_mod._arduino and _ar_mod._arduino.is_open:
            arduino_send("KEY:Y:60")
            time.sleep(0.15)
            arduino_send("KEY:Enter:60")
        else:
            win32api.keybd_event(0x59, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(0x59, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)
            win32api.keybd_event(0x0D, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(0x0D, 0, win32con.KEYEVENTF_KEYUP, 0)
        self.log("🔑 Y + Enter 입력 (거래 확인)")

    def _trade_win_open(self) -> bool:
        """거래창 현재 열려있는지 즉시 체크. 영역 미설정 시 True(알 수 없음) 반환"""
        if not self._trade_win_region:
            return True
        return self._detect_trade_window()

    def _wait_and_verify_trade(self):
        """교환창이 열린 후 금액 인식 → OK→Y 또는 Cancel 실행"""
        try:
            timeout = float(self._wait_timeout_var.get())
        except Exception:
            timeout = 60.0

        self.after(0, lambda: self._status_lbl.configure(
            text="🔄 거래창 대기...", text_color="#F59E0B"))

        # ── ① 거래창 열릴 때까지 대기 ──────────────────────────────
        if self._trade_win_region:
            self.log("⏳ 거래창 열림 대기 중...")
            win_found = False
            try:
                thr = float(self._trade_win_thr_var.get())
            except Exception:
                thr = 20.0
            for attempt in range(5):           # 최대 5초
                if not self.running:
                    return False
                try:
                    x1, y1, x2, y2 = self._trade_win_region
                    img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
                    ratio = self._dark_ratio(list(img.getdata()))
                    self.log(f"  거래창 체크 {attempt+1}/5: 어두운픽셀 {ratio:.1f}% (기준 {thr:.0f}%)")
                except Exception:
                    ratio = 0.0
                if self._detect_trade_window():
                    win_found = True
                    self.log(f"✅ 거래창 열림 확인 ({attempt+1}초)")
                    break
                time.sleep(1.0)
            if not win_found:
                self.log("⚠ 거래창 5초 내 미감지 → 대기 상태로 초기화")
                self.after(0, lambda: self._status_lbl.configure(
                    text="⚠ 거래창 없음", text_color="#EF4444"))
                return False
        else:
            self.log("⚠ 거래창 감지 영역 미설정 — 5초 대기 후 초기화")
            for _ in range(5):
                if not self.running:
                    return False
                time.sleep(1.0)
            return False

        # ── ② 돈 영역 미지정 시 타임아웃 대기 ──────────────────────
        if not self._money_region:
            self.log(f"⚠ 돈 표시 영역 미설정 — {timeout:.0f}초 대기")
            end = time.time() + timeout
            while time.time() < end and self.running:
                # 거래창 닫힘 감지 시 즉시 중단
                if not self._trade_win_open():
                    self.log("⚠ 거래창 닫힘 감지 → 중단")
                    self.after(0, lambda: self._status_lbl.configure(
                        text="⚠ 거래창 닫힘", text_color="#EF4444"))
                    return False
                time.sleep(0.5)
            return True

        try:
            price_per = int(self._price_per_shot_var.get())
        except Exception:
            price_per = 150
        start = time.time()
        self.log(f"💰 금액 감지 대기 (최대 {timeout:.0f}초, 방당 {price_per}아데나)...")

        # 5초마다 거래창 존재 독립 감시 스레드
        trade_abort = threading.Event()
        def _win_watcher():
            while not trade_abort.is_set():
                trade_abort.wait(timeout=5.0)
                if trade_abort.is_set():
                    break
                if not self.running:
                    break
                if self._trade_win_region and not self._detect_trade_window():
                    self.log("⚠ [5초 체크] 거래창 없음 → 거래 초기화")
                    self.after(0, lambda: self._status_lbl.configure(
                        text="⚠ 거래창 없음", text_color="#EF4444"))
                    trade_abort.set()
        threading.Thread(target=_win_watcher, daemon=True, name="win-watcher").start()

        while self.running and not trade_abort.is_set() and time.time() - start < timeout:
            # 매 루프마다 거래창 확인 (영역 없을 때도 abort 이벤트로 처리됨)
            if not self._trade_win_open():
                self.log("⚠ 거래창 닫힘 감지 → 손님이 취소함")
                self.after(0, lambda: self._status_lbl.configure(
                    text="⚠ 거래창 닫힘", text_color="#EF4444"))
                trade_abort.set()
                return False

            amount = self._ocr_money_amount()
            if amount is not None and amount > 0:
                n_bought = amount // price_per if price_per > 0 else 0
                match = n_bought >= 1
                mark  = f"✅ {n_bought}방 ({amount:,}아데나)" if match else f"❌ 부족 ({amount:,}아데나 < {price_per})"
                self.log(f"💰 인식: {mark}")
                if match:
                    self._last_trade_amount = amount
                self.after(0, lambda a=amount, m=match: (
                    self._money_ocr_lbl.configure(
                        text=f"인식: {a:,} 아데나  →  {'✅ 일치' if m else '❌ 불일치'}",
                        text_color="#22C55E" if m else "#EF4444"),
                    self._status_lbl.configure(
                        text=f"💰 {a:,} 아데나 {'✅' if m else '❌'}",
                        text_color="#22C55E" if m else "#EF4444")
                ))
                if match:
                    # 상대방 회색 감지 대기 → 봇 OK 클릭 (1초 간격)
                    if self._trade_gray_region:
                        self.after(0, lambda: self._status_lbl.configure(
                            text="⏳ 상대방 OK 대기", text_color="#F59E0B"))
                        self.log("⏳ 상대방 거래창 회색 대기 (1초 간격)...")
                        try:
                            thr = float(self._trade_gray_threshold_var.get())
                        except Exception:
                            thr = 80.0
                        gray_deadline = time.time() + 30.0
                        gray_ok = False
                        while self.running and time.time() < gray_deadline:
                            if not self._trade_win_open():
                                self.log("⚠ 거래창 닫힘 → 손님 취소")
                                return False
                            ratio = self._gray_ratio()
                            self.log(f"  회색: {ratio:.1f}% / 기준: {thr:.0f}%")
                            if ratio >= thr:
                                self.log(f"⬛ 상대방 OK 감지! ({ratio:.1f}%) → 즉시 진행")
                                gray_ok = True
                                break
                            time.sleep(1.0)
                        if not gray_ok:
                            self.log("⏱ 30초 초과 — 상대방 미확인 → Cancel")
                            if self._cancel_pos:
                                self._click_abs(*self._cancel_pos)
                            return False

                    if self._ok_pos:
                        self.log("✅ 거래 확인 → OK 클릭")
                        self._click_abs(*self._ok_pos)
                        time.sleep(1.0)
                        self._press_key_y()
                    else:
                        self.log("⚠ OK 위치 미설정 — Y 키만 입력")
                        time.sleep(1.0)
                        self._press_key_y()
                    trade_abort.set()
                    self._add_sale_record(amount, n_bought)
                    return True
                else:
                    elapsed = time.time() - start
                    self.log(f"❌ 금액 불일치 ({amount:,}) — 재시도 중... ({elapsed:.0f}s/{timeout:.0f}s)")
                    time.sleep(0.5)
                    continue
            time.sleep(0.5)

        trade_abort.set()

        if trade_abort.is_set() and not self.running:
            return False

        # 거래창 감시 스레드가 abort 시킨 경우
        if trade_abort.is_set():
            return False

        # 타임아웃 — 60초 초과 → Cancel 후 초기화
        self.log(f"⏱ {timeout:.0f}초 초과 — 거래 초기화")
        self.after(0, lambda: self._status_lbl.configure(
            text="⏱ 금액 미감지", text_color="#64748B"))
        if self._cancel_pos:
            self._click_abs(*self._cancel_pos)
        return False

    # ── 창 정렬 ──────────────────────────
    def _arrange_window_hj(self):
        hwnd = self._get_hwnd()
        if not hwnd:
            self.log("창을 먼저 선택하세요."); return
        if not _is_admin():
            from tkinter import messagebox
            ans = messagebox.askyesno("관리자 권한 필요",
                "창 정렬은 관리자 권한이 필요합니다.\n관리자 권한으로 재시작하시겠습니까?")
            if ans: _restart_as_admin()
            return
        try:
            w = int(self._hj_win_w.get())
            h = int(self._hj_win_h.get())
        except ValueError:
            self.log("가로/세로는 숫자여야 합니다."); return

        if self._dual_client_var.get():
            hwnd2 = self._get_sub_hwnd()
            if not hwnd2:
                self.log("서브 창을 먼저 선택하세요."); return
            sw = win32api.GetSystemMetrics(0)
            sh = win32api.GetSystemMetrics(1)
            layout = self._layout_var.get()
            if layout == "좌우":
                x2 = min(w, sw - w)
                coords = [(hwnd, 0, 0, w, h), (hwnd2, x2, 0, w, h)]
            else:
                y2 = min(h, sh - h)
                coords = [(hwnd, 0, 0, w, h), (hwnd2, 0, y2, w, h)]
            for hh, x, y, cw, ch in coords:
                try:
                    win32gui.MoveWindow(hh, x, y, cw, ch, True)
                except Exception as e:
                    self.log(f"창 이동 실패: {e}"); return
            self.log(f"창 정렬 완료 [{layout}] {w}×{h}  (메인+서브)")
        else:
            try:
                win32gui.MoveWindow(hwnd, 0, 0, w, h, True)
                self.log(f"창 정렬 완료  {w}×{h}  (0, 0)")
            except Exception as e:
                self.log(f"창 이동 실패: {e}")

    # ── Arduino 연결 (헤이장사) ──────────
    def _refresh_ports_hj(self):
        if not _SERIAL_OK: return
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._hj_com_combo.configure(values=ports if ports else ["COM3"])

    def _toggle_arduino_hj(self):
        with _arduino_lock:
            already_open = _ar_mod._arduino and _ar_mod._arduino.is_open
        if already_open:
            with _arduino_lock:
                _ar_mod._arduino.close()
                _ar_mod._arduino = None
            self._hj_ard_btn.configure(text="연결", fg_color="#F59E0B", hover_color="#D97706")
            self._hj_ard_status.configure(text="● 미연결", text_color="#64748B")
            self.log("연결 해제", tag="SERIAL")
        else:
            if not _SERIAL_OK:
                self.log("pyserial 미설치 — pip install pyserial", tag="SERIAL"); return
            try:
                port = serial.Serial(self._hj_com_var.get(), 115200, timeout=1)
            except Exception as e:
                self.log(f"연결 실패: {e}", tag="SERIAL"); return
            time.sleep(1.5)
            with _arduino_lock:
                _ar_mod._arduino = port
            self._hj_ard_btn.configure(text="해제", fg_color="#EF4444", hover_color="#B91C1C")
            self._hj_ard_status.configure(text="● 연결됨", text_color="#22C55E")
            self.log(f"연결 완료: {self._hj_com_var.get()}", tag="SERIAL")

    # ── OCR 영역 선택 ────────────────────
    def _select_region(self):
        self.iconify()
        def _cb(region):
            self.deiconify()
            if region:
                self.ocr_region = region
                x1, y1, x2, y2 = region
                self._ocr_region_lbl.configure(
                    text=f"({x1},{y1}) → ({x2},{y2})", text_color="#22C55E")
                self.log(f"감지 영역 지정: ({x1},{y1}) ~ ({x2},{y2})")
                self._save_config_hj()
                threading.Thread(target=self._do_capture, daemon=True).start()
        self.after(300, lambda: RegionSelector(_cb))

    def _capture_once(self):
        if not self.ocr_region:
            self.log("영역을 먼저 지정하세요."); return
        threading.Thread(target=self._do_capture, daemon=True).start()

    def _do_capture(self) -> str:
        if not self.ocr_region:
            return ""
        x1, y1, x2, y2 = self.ocr_region
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
        except Exception as e:
            self.log(f"캡처 실패: {e}"); return ""

        # 미리보기
        thumb = img.copy(); thumb.thumbnail((340, 120), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb,
                               size=(thumb.width, thumb.height))
        self._ocr_img_ref = ctk_img
        self.after(0, lambda im=ctk_img: self._ocr_preview.configure(
            image=im, text="", width=340, height=120))

        # 픽셀 밝기 통계 표시
        pixels = list(img.getdata())
        total = len(pixels)
        bright = sum(1 for r, g, b in pixels if r > 200 and g > 200 and b > 200)
        ratio = bright / total * 100 if total else 0
        try:
            thr = float(self._pixel_threshold_var.get())
        except Exception:
            thr = 3.0
        detected = ratio >= thr
        color = "#22C55E" if detected else "#64748B"
        label = f"흰 픽셀: {bright}/{total}  ({ratio:.1f}%)  →  {'✅ 감지됨' if detected else '❌ 없음'}"
        self.after(0, lambda t=label, c=color: self._ocr_result_lbl.configure(
            text=t, text_color=c))
        return ""

    def _test_pixel_detect(self):
        if not self.ocr_region:
            self.log("영역을 먼저 지정하세요."); return
        threading.Thread(target=self._do_capture, daemon=True).start()

    # ── 손님 감지 ────────────────────────
    def _detect_customer(self) -> bool:
        """정면 영역의 흰색 픽셀 비율로 손님 감지 (이름표 = 흰색 텍스트)"""
        if not self.ocr_region:
            return False
        x1, y1, x2, y2 = self.ocr_region
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
            pixels = list(img.getdata())
            total = len(pixels)
            if total == 0:
                return False
            try:
                threshold = float(self._pixel_threshold_var.get())
            except Exception:
                threshold = 3.0
            bright = sum(1 for r, g, b in pixels if r > 200 and g > 200 and b > 200)
            ratio = bright / total * 100
            return ratio >= threshold
        except Exception:
            return False

    # ── 교환 키 입력 ─────────────────────
    def _press_exchange_key(self):
        hwnd = self._get_hwnd()
        if not hwnd:
            self.log("창이 선택되지 않음"); return
        key = self._exchange_key_var.get()
        ard = _ar_mod._arduino and _ar_mod._arduino.is_open
        force_foreground(hwnd)
        time.sleep(0.1)
        if ard:
            arduino_send(f"KEY:{key}:60")
            via = "Arduino"
        else:
            vk = _KEY_CODES.get(key, 0x74)
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            via = "win32"
        self.log(f"🔑 교환 키 [{key}] 입력  [{via}]")

    # ── 시작 / 중지 ──────────────────────
    def _start(self):
        if not self._get_hwnd():
            self.log("창을 먼저 선택하세요."); return
        if not self.ocr_region:
            self.log("OCR 감지 영역을 먼저 지정하세요."); return
        # 로그 팝업 자동 열기
        if self._hj_log_popup and not self._hj_log_popup.winfo_viewable():
            self._hj_log_popup.deiconify()
            self._hj_log_popup.lift()
        self._run_evt.set()
        self._start_btn.configure(state="disabled", fg_color="#374151")
        self._stop_btn.configure(state="normal", fg_color="#EF4444",
                                 hover_color="#B91C1C")
        self._status_lbl.configure(text="● 감시 중", text_color="#22C55E")
        self.log("━━━ 자동 판매 시작 ━━━")
        threading.Thread(target=self._loop, daemon=True).start()
        if self._auto_light_var.get():
            threading.Thread(target=self._auto_light_loop, daemon=True, name="auto-light").start()
        # 평상시 광고 자동 시작
        self._start_ad()

    def _stop(self):
        self._run_evt.clear()
        self._start_btn.configure(state="normal", fg_color="#22C55E",
                                  hover_color="#16A34A")
        self._stop_btn.configure(state="disabled", fg_color="#374151",
                                 hover_color="#374151")
        self._status_lbl.configure(text="● 대기 중", text_color="#64748B")
        self.log("━━━ 자동 판매 중지 ━━━")
        # 평상시 광고 자동 정지
        self._stop_ad()

    def _press_light_key(self):
        """라이트 키 1회 입력 (Arduino 우선, 없으면 win32)"""
        key = self._light_key_var.get().strip() or "F6"
        hwnd = self._get_hwnd()
        if hwnd:
            try:
                from core.win32_utils import force_foreground
                force_foreground(hwnd)
                time.sleep(0.08)
            except Exception:
                pass
        ard = _ar_mod._arduino and _ar_mod._arduino.is_open
        if ard:
            arduino_send(f"KEY:{key}:60")
            via = "Arduino"
        else:
            vk = _KEY_CODES.get(key, 0x77)
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            via = "win32"
        self.log(f"💡 라이트 키 [{key}] 입력 [{via}]", tag="LIGHT")

    def _auto_light_loop(self):
        """봇 실행 중 주기적으로 라이트 키 입력"""
        try:
            interval_min = float(self._light_interval_var.get())
        except Exception:
            interval_min = 90.0
        interval_sec = max(60.0, interval_min * 60)

        # 시작 즉시 1회
        time.sleep(1.0)
        if self.running:
            self._press_light_key()

        while self.running:
            end_t = time.time() + interval_sec
            while time.time() < end_t:
                if not self.running:
                    return
                time.sleep(1.0)
            if self.running:
                self._press_light_key()

    # ── 손님 감지 + 비율 반환 ─────────────
    def _detect_customer_ratio(self):
        """흰 픽셀 비율(%)과 감지 여부를 함께 반환 → (ratio, detected)"""
        if not self.ocr_region:
            return 0.0, False
        x1, y1, x2, y2 = self.ocr_region
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
            pixels = list(img.getdata())
            total = len(pixels)
            if total == 0:
                return 0.0, False
            try:
                threshold = float(self._pixel_threshold_var.get())
            except Exception:
                threshold = 3.0
            bright = sum(1 for r, g, b in pixels if r > 200 and g > 200 and b > 200)
            ratio = bright / total * 100
            return ratio, ratio >= threshold
        except Exception:
            return 0.0, False

    # ── 메인 루프 ────────────────────────
    def _loop(self):
        self._set_state("WATCHING")
        last_ratio_log = 0.0
        while self.running:
            interval     = self._fv(self._scan_interval_var,  1.0, lo=0.1)
            action_delay = self._fv(self._action_delay_var,   0.3, lo=0.0)
            cooldown     = self._fv(self._cooldown_var,       3.0, lo=0.0)
            thr          = self._fv(self._pixel_threshold_var, 3.0, lo=0.1)

            ratio, detected = self._detect_customer_ratio()

            # 상태바 실시간 비율 표시
            color = "#22C55E" if detected else "#64748B"
            self.after(0, lambda r=ratio, t=thr, c=color: self._status_lbl.configure(
                text=f"● 감시 중  흰픽셀: {r:.1f}% / 기준 {t:.1f}%", text_color=c))

            now = time.time()
            if now - last_ratio_log >= 5.0:
                self.log(f"흰 픽셀 {ratio:.1f}% / 기준 {thr:.1f}%  →  {'✅ 감지' if detected else '❌ 없음'}", tag="SCAN")
                last_ratio_log = now

            if detected:
                self._set_state("DETECTED")
                self.log("손님 감지!")

                # MP는 광고용으로만 캡처 — 거래 진입은 MP 무관하게 항상 진행
                if self._mp_announce_var.get():
                    self._spawn(self._announce_shots, name="announce")
                    time.sleep(0.6)

                time.sleep(action_delay)
                if self.running:
                    self._press_exchange_key()
                    time.sleep(0.8)
                    self._set_state("WAIT_TRADE")
                    success = self._wait_and_verify_trade()
                    if success and self.running:
                        self._set_state("DONE")
                        self._do_magic_shots()
                        self._send_thanks()
                        post_delay = self._fv(self._post_trade_delay_var, 5.0, lo=0.0)
                        self.log(f"거래 완료 — {post_delay:.0f}초 대기 후 재감지")
                        end_pt = time.time() + post_delay
                        while time.time() < end_pt and self.running:
                            time.sleep(0.1)
                    else:
                        self._set_state("CANCEL")
                self._set_state("WATCHING")
                last_ratio_log = 0.0
                # 재감지 쿨다운 (오감지 방지)
                end = time.time() + cooldown
                while time.time() < end and self.running:
                    time.sleep(0.1)
            else:
                time.sleep(interval)


# ─────────────────────────────────────────
#  메인 앱 (요정버프)
# ─────────────────────────────────────────