# -*- coding: utf-8 -*-
"""
자동사냥 모듈
──────────────────────────────────────────────────────
섹션 구성:
  ① 창 선택     — 사냥할 라이니지 창 hwnd
  ② 감지 영역   — 사냥 화면 스캔 범위 / 툴팁 / HP·MP / 사망
  ③ 커서 감지   — 검 커서 핸들 등록 (몬스터 확인)
  ④ 공격 설정   — 드래그 거리 / 대기 / 사망 확인
  ⑤ HP·MP 관리  — 포션 키 / 임계값
  ⑥ 루팅        — 루팅 키 / 대기
  ⑦ 이동 패턴   — 좌표 리스트 순환 / 랜덤
  ⑧ 탈출 조건   — 사망 감지 / 시간 제한
  자동사냥 제어 — 시작 / 중지 (상단 고정)

몬스터 감지 흐름:
  1. hunt_region 격자 스캔 — SetCursorPos 이동
  2. 각 포인트에서 커서 핸들 확인 → 검 커서면 몬스터
  3. 드래그 다운 → 자동공격 시작
  4. 마우스 좌우 이동 + 커서 확인 → 검 사라지면 사망
  5. F4 루팅
"""
import os
import json
import time
import random
import ctypes
import threading
from datetime import datetime

import customtkinter as ctk
import win32gui
import win32api
import win32con
from PIL import ImageGrab

import core.arduino as _ar_mod
from core.arduino import arduino_send
from core.win32_utils import (
    enum_visible_windows, force_foreground,
    smooth_move, _KEY_CODES,
)
from core.icon import _apply_icon
from ui.region_selector import RegionSelector, PointSelector

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CFG_PATH = os.path.join(_BASE_DIR, "..", "config_hunt.json")


# ─────────────────────────────────────────────────────
#  자동사냥 앱
# ─────────────────────────────────────────────────────
class AppAutoHunt(ctk.CTk):
    W, H = 520, 900

    def __init__(self):
        super().__init__()
        self.title("배미유니버스 — 자동사냥")
        self.geometry(f"{self.W}x{self.H}")
        self.resizable(False, True)
        self.configure(fg_color="#0A0F1E")
        self.after(100, lambda: _apply_icon(self))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.running  = False
        self._run_evt = threading.Event()

        # ① 창 선택
        self._hwnd_var = ctk.StringVar(value="")

        # ② 감지 영역
        # - hunt_region: 화면 스캔 범위 (이미지 인식 대상)
        # - tooltip_region: 마우스 올렸을 때 이름 툴팁이 뜨는 위치
        # - my_hp/mp_region: 포션 판단용 내 캐릭터 바
        # - dead_region: 사망 판별용 픽셀 영역
        self._hunt_region:    tuple | None = None
        self._tooltip_region: tuple | None = None
        self._my_hp_region:   tuple | None = None
        self._my_mp_region:   tuple | None = None
        self._dead_region:    tuple | None = None

        # ③ 커서 감지
        # 인식 흐름: 이미지로 후보 찾기 → 마우스 이동 → 커서 핸들 비교
        # sword_handle: 몬스터 위에 올렸을 때의 커서 핸들 (등록 필요)
        self._sword_handle:    int | None = None
        self._sword_handle_lbl_var = ctk.StringVar(value="미등록")

        # ④ 공격 설정
        self._drag_distance  = ctk.StringVar(value="60")   # 드래그 다운 픽셀
        self._attack_wait    = ctk.StringVar(value="3.0")  # 공격 대기(초)
        self._death_check_t  = ctk.StringVar(value="0.5")  # 사망 확인 체크 간격(초)
        self._death_wiggle   = ctk.StringVar(value="10")   # 사망 확인용 마우스 이동(px)

        # ⑤ HP·MP 관리
        self._hp_potion_key    = ctk.StringVar(value="")
        self._hp_threshold_var = ctk.StringVar(value="50")
        self._mp_potion_key    = ctk.StringVar(value="")
        self._mp_threshold_var = ctk.StringVar(value="30")
        self._potion_cooldown  = ctk.StringVar(value="3.0")

        # ⑥ 루팅
        self._loot_key       = ctk.StringVar(value="F4")
        self._loot_wait      = ctk.StringVar(value="0.8")  # 루팅 후 대기(초)

        # ⑦ 이동 패턴
        self._waypoints: list[tuple[int, int]] = []
        self._move_mode  = ctk.StringVar(value="순환")
        self._move_delay = ctk.StringVar(value="5.0")

        # ⑦ 탈출 조건
        self._escape_on_death = ctk.BooleanVar(value=True)
        self._escape_on_time  = ctk.BooleanVar(value=False)
        self._escape_time_min = ctk.StringVar(value="60")

        self._build_ui()
        self._load_config()
        self.refresh_windows()

    # ── 헬퍼 ───────────────────────────────────────
    def _fv(self, var: ctk.StringVar, default: float, lo=0.0) -> float:
        try:
            return max(lo, float(var.get()))
        except Exception:
            return default

    def _card(self, parent, title: str, color: str = "#7C3AED"):
        outer = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=10,
                             border_width=1, border_color="#1E293B")
        outer.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(outer, text=title,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=color).pack(anchor="w", padx=12, pady=(8, 4))
        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(fill="x", padx=8, pady=(0, 8))
        return body

    def log(self, msg: str, tag: str = ""):
        prefix = f"[{tag}] " if tag else ""
        ts   = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {prefix}{msg}"
        def _do():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", full + "\n")
            self._log_box.configure(state="disabled")
            self._log_box.see("end")
        self.after(0, _do)

    # ── UI 빌드 ────────────────────────────────────
    def _build_ui(self):
        self._build_fixed_ctrl()
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True)
        self._build_window_section(scroll)   # ① 창 선택
        self._build_region_section(scroll)   # ② 감지 영역
        self._build_cursor_section(scroll)   # ③ 커서 감지 (검 커서 등록)
        self._build_attack_section(scroll)   # ④ 공격 설정
        self._build_potion_section(scroll)   # ⑤ HP·MP 관리
        self._build_loot_section(scroll)     # ⑥ 루팅
        self._build_move_section(scroll)     # ⑦ 이동 패턴
        self._build_escape_section(scroll)   # ⑧ 탈출 조건
        self._build_log_section(scroll)

    # ─── 상단 고정: 제어 패널 ─────────────────────
    def _build_fixed_ctrl(self):
        G = "#22C55E"
        fixed = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0)
        fixed.pack(fill="x")
        ctk.CTkLabel(fixed, text="자동사냥 제어",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=G).pack(anchor="w", padx=16, pady=(10, 4))
        ctrl = ctk.CTkFrame(fixed, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(0, 10))

        self._start_btn = ctk.CTkButton(
            ctrl, text="▶ 시작", width=110, height=38,
            fg_color=G, hover_color="#16A34A",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start)
        self._start_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            ctrl, text="■ 중지", width=110, height=38,
            fg_color="#374151", hover_color="#374151",
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled", command=self._stop)
        self._stop_btn.pack(side="left")

        self._status_lbl = ctk.CTkLabel(
            ctrl, text="● 대기 중",
            font=ctk.CTkFont(size=12), text_color="#64748B")
        self._status_lbl.pack(side="left", padx=(12, 0))

        # 실시간 상태 표시
        self._state_lbl = ctk.CTkLabel(
            ctrl, text="",
            font=ctk.CTkFont(size=11), text_color="#F59E0B")
        self._state_lbl.pack(side="left", padx=(8, 0))

    def _set_state_lbl(self, text: str):
        self.after(0, lambda: self._state_lbl.configure(text=text))

    # ─── ① 창 선택 ────────────────────────────────
    def _build_window_section(self, parent):
        f = self._card(parent, "① 창 선택", "#60A5FA")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", pady=2)
        self._win_combo = ctk.CTkComboBox(row, variable=self._hwnd_var,
                                          values=[], width=300, height=30)
        self._win_combo.pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="🔄", width=34, height=30,
                      fg_color="#334155", hover_color="#475569",
                      command=self.refresh_windows).pack(side="left")

    def refresh_windows(self):
        wins  = enum_visible_windows()
        items = [f"{t}  #{h}" for h, t, _ in wins]
        self._win_combo.configure(values=items)
        if items and not self._hwnd_var.get():
            self._win_combo.set(items[0])

    def _get_hwnd(self) -> int | None:
        try:
            return int(self._hwnd_var.get().rsplit("#", 1)[-1].strip())
        except Exception:
            return None

    # ─── ② 감지 영역 ──────────────────────────────
    def _build_region_section(self, parent):
        f = self._card(parent, "② 감지 영역", "#F59E0B")

        # 사냥 화면 영역 (이미지 인식 스캔 범위)
        hunt_row = ctk.CTkFrame(f, fg_color="#0F172A", corner_radius=6)
        hunt_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(hunt_row, text="사냥 화면:",
                     font=ctk.CTkFont(size=12), text_color="#F59E0B",
                     width=72).pack(side="left", padx=(8,0), pady=4)
        self._hunt_lbl = ctk.CTkLabel(hunt_row, text="미지정",
                                       font=ctk.CTkFont(size=11), text_color="#64748B")
        self._hunt_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(hunt_row, text="영역 지정", width=80, height=26,
                      fg_color="#78350F", hover_color="#92400E",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._pick_region("_hunt_region", self._hunt_lbl)
                      ).pack(side="left")
        ctk.CTkLabel(hunt_row, text="← 이미지 인식이 스캔할 전체 사냥 화면",
                     font=ctk.CTkFont(size=10), text_color="#475569"
                     ).pack(side="left", padx=6)

        # 툴팁 영역 (마우스 올렸을 때 이름 뜨는 위치)
        tip_row = ctk.CTkFrame(f, fg_color="#0F172A", corner_radius=6)
        tip_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(tip_row, text="이름 툴팁:",
                     font=ctk.CTkFont(size=12), text_color="#F59E0B",
                     width=72).pack(side="left", padx=(8,0), pady=4)
        self._tooltip_lbl = ctk.CTkLabel(tip_row, text="미지정",
                                          font=ctk.CTkFont(size=11), text_color="#64748B")
        self._tooltip_lbl.pack(side="left", padx=(4, 8))
        ctk.CTkButton(tip_row, text="영역 지정", width=80, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._pick_region("_tooltip_region", self._tooltip_lbl)
                      ).pack(side="left")
        ctk.CTkLabel(tip_row, text="← 마우스 올렸을 때 몬스터 이름 뜨는 위치",
                     font=ctk.CTkFont(size=10), text_color="#475569"
                     ).pack(side="left", padx=6)

        # 내 HP·MP·사망 감지
        self._region_lbls: dict[str, ctk.CTkLabel] = {}
        sub_regions = [
            ("내 HP바",  "_my_hp_region",  "포션 판단용"),
            ("내 MP바",  "_my_mp_region",  "포션 판단용"),
            ("사망감지", "_dead_region",   "어두움 픽셀 감지"),
        ]
        for label, attr, hint in sub_regions:
            row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{label}:", font=ctk.CTkFont(size=12),
                         text_color="white", width=72).pack(side="left")
            lbl = ctk.CTkLabel(row, text="미지정", font=ctk.CTkFont(size=11),
                               text_color="#64748B")
            lbl.pack(side="left", padx=(4, 8))
            self._region_lbls[attr] = lbl
            ctk.CTkButton(row, text="영역 지정", width=80, height=26,
                          fg_color="#334155", hover_color="#475569",
                          font=ctk.CTkFont(size=11),
                          command=lambda a=attr, lb=lbl: self._pick_region(a, lb)
                          ).pack(side="left")
            ctk.CTkButton(row, text="테스트", width=56, height=26,
                          fg_color="#1E3A5F", hover_color="#1E4A7F",
                          font=ctk.CTkFont(size=11),
                          command=lambda a=attr: threading.Thread(
                              target=self._test_region, args=(a,), daemon=True).start()
                          ).pack(side="left", padx=(4, 0))
            ctk.CTkLabel(row, text=hint, font=ctk.CTkFont(size=10),
                         text_color="#475569").pack(side="left", padx=6)

    def _pick_region(self, attr: str, lbl: ctk.CTkLabel):
        self.iconify()
        def _cb(result):
            self.deiconify()
            if result:
                setattr(self, attr, result)
                x1, y1, x2, y2 = result
                lbl.configure(text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
                self._save_config()
        self.after(200, lambda: RegionSelector(_cb))

    def _test_region(self, attr: str):
        region = getattr(self, attr, None)
        if not region:
            self.log(f"[테스트] {attr} 미지정"); return
        if attr in ("_my_hp_region", "_my_mp_region"):
            name  = "HP" if "hp" in attr else "MP"
            color = "red" if "hp" in attr else "blue"
            ratio = self._bar_ratio(region, color)
            self.log(f"[테스트] 내 {name}바 채워진 비율 {ratio*100:.1f}%", tag="감지")
        elif attr == "_dead_region":
            dark = self._is_dark(region)
            self.log(f"[테스트] 사망감지 → {'어두움(사망?)' if dark else '밝음(생존)'}", tag="감지")

    # ─── ③ 커서 감지 ──────────────────────────────
    def _build_cursor_section(self, parent):
        f = self._card(parent, "③ 커서 감지 — 몬스터 확인 방법", "#F97316")

        info = ctk.CTkLabel(f,
            text="몬스터 위에 마우스를 올리면 커서가 화살표 → 검 모양으로 변합니다.\n"
                 "아래 버튼으로 '검 커서' 핸들을 등록하면 이후 자동으로 구분합니다.",
            font=ctk.CTkFont(size=11), text_color="#94A3B8", justify="left")
        info.pack(anchor="w", pady=(0, 6))

        row1 = ctk.CTkFrame(f, fg_color="transparent"); row1.pack(fill="x", pady=2)
        ctk.CTkButton(row1, text="⚔ 검 커서 등록", width=120, height=32,
                      fg_color="#78350F", hover_color="#92400E",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=lambda: threading.Thread(
                          target=self._register_sword_cursor, daemon=True).start()
                      ).pack(side="left", padx=(0, 10))
        self._sword_lbl = ctk.CTkLabel(row1, textvariable=self._sword_handle_lbl_var,
                                        font=ctk.CTkFont(size=11), text_color="#64748B")
        self._sword_lbl.pack(side="left")

        row2 = ctk.CTkFrame(f, fg_color="transparent"); row2.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(row2, text="커서 확인 테스트", width=120, height=28,
                      fg_color="#1E3A5F", hover_color="#1E4A7F",
                      font=ctk.CTkFont(size=11),
                      command=lambda: threading.Thread(
                          target=self._test_cursor, daemon=True).start()
                      ).pack(side="left")
        ctk.CTkLabel(row2, text="현재 커서가 검인지 확인",
                     font=ctk.CTkFont(size=10), text_color="#475569").pack(side="left", padx=8)

    def _register_sword_cursor(self):
        """3초 카운트다운 후 현재 커서 핸들을 검 커서로 등록"""
        for i in range(3, 0, -1):
            self.after(0, lambda n=i: self._sword_handle_lbl_var.set(
                f"⏳ {n}초 후 등록 — 지금 몬스터 위에 마우스를 올려두세요"))
            time.sleep(1.0)
        self._sword_handle = self._get_cursor_handle()
        if self._sword_handle:
            self.after(0, lambda: self._sword_handle_lbl_var.set(
                f"✅ 등록완료  핸들: {self._sword_handle}"))
            self.after(0, lambda: self._sword_lbl.configure(text_color="#22C55E"))
            self.log(f"⚔ 검 커서 등록: {self._sword_handle}", tag="커서")
            self._save_config()
        else:
            self.after(0, lambda: self._sword_handle_lbl_var.set("❌ 등록 실패"))

    def _test_cursor(self):
        handle = self._get_cursor_handle()
        is_sword = (self._sword_handle is not None and handle == self._sword_handle)
        self.log(f"현재 커서 핸들: {handle}  → {'⚔ 검 (몬스터 있음)' if is_sword else '↖ 화살표 (없음)'}", tag="커서")

    def _get_cursor_handle(self) -> int | None:
        """현재 커서 핸들 반환 (Win32 GetCursorInfo)."""
        try:
            class _POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            class _CURSORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize",      ctypes.c_uint32),
                    ("flags",       ctypes.c_uint32),
                    ("hCursor",     ctypes.c_void_p),
                    ("ptScreenPos", _POINT),
                ]
            ci = _CURSORINFO()
            ci.cbSize = ctypes.sizeof(ci)
            if ctypes.windll.user32.GetCursorInfo(ctypes.byref(ci)):
                return ci.hCursor
        except Exception:
            pass
        return None

    def _is_sword_cursor(self) -> bool:
        """현재 커서가 등록된 검 커서인지 확인."""
        if self._sword_handle is None:
            return False
        return self._get_cursor_handle() == self._sword_handle

    # ─── ④ 공격 설정 ──────────────────────────────
    def _build_attack_section(self, parent):
        f = self._card(parent, "④ 공격 설정", "#A855F7")

        info = ctk.CTkLabel(f,
            text="몬스터 위에서 아래로 드래그 → 자동공격\n"
                 "마우스 좌우 이동 후 커서 확인 → 검 사라지면 사망",
            font=ctk.CTkFont(size=11), text_color="#94A3B8", justify="left")
        info.pack(anchor="w", pady=(0, 6))

        row1 = ctk.CTkFrame(f, fg_color="transparent"); row1.pack(fill="x", pady=2)
        for label, var, unit in [
            ("드래그 거리(px):", self._drag_distance,  ""),
            ("공격 대기(초):",    self._attack_wait,    ""),
            ("사망확인 간격(초):", self._death_check_t,  ""),
            ("확인 이동(px):",   self._death_wiggle,   ""),
        ]:
            ctk.CTkLabel(row1, text=label, font=ctk.CTkFont(size=11),
                         text_color="#94A3B8").pack(side="left")
            ctk.CTkEntry(row1, textvariable=var, width=50, height=26
                         ).pack(side="left", padx=(2, 10))

    # ─── ⑤ HP·MP 포션 ─────────────────────────────
    def _build_potion_section(self, parent):
        f = self._card(parent, "⑤ HP·MP 관리", "#EF4444")

        for label, key_var, thr_var, color in [
            ("HP 포션", self._hp_potion_key, self._hp_threshold_var, "#EF4444"),
            ("MP 포션", self._mp_potion_key, self._mp_threshold_var, "#3B82F6"),
        ]:
            row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{label}:", font=ctk.CTkFont(size=12),
                         text_color=color, width=64).pack(side="left")
            ctk.CTkEntry(row, textvariable=key_var,
                         width=60, height=26, placeholder_text="키").pack(side="left", padx=4)
            ctk.CTkLabel(row, text="임계값(%):", font=ctk.CTkFont(size=11),
                         text_color="#94A3B8").pack(side="left")
            ctk.CTkEntry(row, textvariable=thr_var,
                         width=50, height=26).pack(side="left", padx=4)

        row3 = ctk.CTkFrame(f, fg_color="transparent"); row3.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(row3, text="포션 쿨다운(초):", font=ctk.CTkFont(size=11),
                     text_color="#94A3B8").pack(side="left")
        ctk.CTkEntry(row3, textvariable=self._potion_cooldown,
                     width=60, height=26).pack(side="left", padx=4)

    # ─── ⑥ 루팅 ──────────────────────────────────
    def _build_loot_section(self, parent):
        f = self._card(parent, "⑥ 루팅", "#F59E0B")

        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text="루팅 키:", font=ctk.CTkFont(size=12),
                     text_color="white", width=72).pack(side="left")
        ctk.CTkEntry(row, textvariable=self._loot_key,
                     width=70, height=26, placeholder_text="F4").pack(side="left", padx=4)
        ctk.CTkLabel(row, text="루팅 후 대기(초):", font=ctk.CTkFont(size=11),
                     text_color="#94A3B8").pack(side="left", padx=(12, 0))
        ctk.CTkEntry(row, textvariable=self._loot_wait,
                     width=60, height=26).pack(side="left", padx=4)

    # ─── ⑦ 이동 패턴 ──────────────────────────────
    def _build_move_section(self, parent):
        f = self._card(parent, "⑦ 이동 패턴", "#10B981")

        row1 = ctk.CTkFrame(f, fg_color="transparent"); row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="모드:", font=ctk.CTkFont(size=12),
                     text_color="white", width=48).pack(side="left")
        ctk.CTkSegmentedButton(row1, values=["순환", "랜덤"],
                                variable=self._move_mode,
                                width=120, height=26).pack(side="left", padx=4)
        ctk.CTkLabel(row1, text="이동 간격(초):", font=ctk.CTkFont(size=11),
                     text_color="#94A3B8").pack(side="left", padx=(8, 0))
        ctk.CTkEntry(row1, textvariable=self._move_delay,
                     width=60, height=26).pack(side="left", padx=4)

        self._wp_display = ctk.CTkTextbox(f, height=70, font=ctk.CTkFont(size=11),
                                           fg_color="#0F172A", text_color="#94A3B8",
                                           state="disabled")
        self._wp_display.pack(fill="x", pady=(4, 2))

        row2 = ctk.CTkFrame(f, fg_color="transparent"); row2.pack(fill="x")
        ctk.CTkButton(row2, text="+ 좌표 추가", width=90, height=26,
                      fg_color="#334155", hover_color="#475569",
                      font=ctk.CTkFont(size=11),
                      command=self._add_waypoint).pack(side="left", padx=(0, 4))
        ctk.CTkButton(row2, text="전체 삭제", width=80, height=26,
                      fg_color="#7F1D1D", hover_color="#991B1B",
                      font=ctk.CTkFont(size=11),
                      command=self._clear_waypoints).pack(side="left")

    def _add_waypoint(self):
        self.iconify()
        def _cb(result):
            self.deiconify()
            if result:
                self._waypoints.append(result)
                self._refresh_wp_display()
                self._save_config()
        self.after(200, lambda: PointSelector(_cb))

    def _clear_waypoints(self):
        self._waypoints.clear()
        self._refresh_wp_display()
        self._save_config()

    def _refresh_wp_display(self):
        self._wp_display.configure(state="normal")
        self._wp_display.delete("1.0", "end")
        if self._waypoints:
            for i, (x, y) in enumerate(self._waypoints):
                self._wp_display.insert("end", f"  {i+1}. ({x}, {y})\n")
        else:
            self._wp_display.insert("end", "  (좌표 없음 — + 버튼으로 추가)")
        self._wp_display.configure(state="disabled")

    # ─── ⑧ 탈출 조건 ──────────────────────────────
    def _build_escape_section(self, parent):
        f = self._card(parent, "⑧ 탈출 조건", "#64748B")

        row1 = ctk.CTkFrame(f, fg_color="transparent"); row1.pack(fill="x", pady=2)
        ctk.CTkCheckBox(row1, text="사망 감지 시 중지",
                        variable=self._escape_on_death,
                        font=ctk.CTkFont(size=12)).pack(side="left")

        row2 = ctk.CTkFrame(f, fg_color="transparent"); row2.pack(fill="x", pady=2)
        ctk.CTkCheckBox(row2, text="시간 제한(분):",
                        variable=self._escape_on_time,
                        font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(row2, textvariable=self._escape_time_min,
                     width=60, height=26).pack(side="left", padx=6)

    # ─── 로그 ─────────────────────────────────────
    def _build_log_section(self, parent):
        f = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=10,
                         border_width=1, border_color="#1E293B")
        f.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(f, text="로그", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#64748B").pack(anchor="w", padx=12, pady=(6, 2))
        self._log_box = ctk.CTkTextbox(
            f, height=130, font=ctk.CTkFont(size=11, family="Consolas"),
            fg_color="#0F172A", text_color="#94A3B8", state="disabled")
        self._log_box.pack(fill="x", padx=8, pady=(0, 8))

    # ══════════════════════════════════════════════
    #  픽셀 감지 유틸
    # ══════════════════════════════════════════════

    def _red_pixel_ratio(self, region: tuple) -> float:
        """영역 내 빨간계열 픽셀 비율 반환 (0.0~1.0).
        라이니지 타겟 HP바: R 높음, G/B 낮음."""
        try:
            img  = ImageGrab.grab(bbox=region, all_screens=True).convert("RGB")
            data = list(img.getdata())
            red  = sum(1 for r, g, b in data if r > 140 and g < 110 and b < 110)
            return red / len(data) if data else 0.0
        except Exception:
            return 0.0

    def _bar_ratio(self, region: tuple, color: str = "red") -> float:
        """HP(red)/MP(blue) 바 채워진 비율 추정 (0.0~1.0).
        바 이미지를 가로로 스캔 — 색상 픽셀이 끊기는 x 위치 / 전체 폭."""
        try:
            img  = ImageGrab.grab(bbox=region, all_screens=True).convert("RGB")
            w, h = img.size
            # 중앙 수평선 픽셀들
            pixels = [img.getpixel((x, h // 2)) for x in range(w)]
            if color == "red":
                filled = [r > 120 and g < 100 and b < 100 for r, g, b in pixels]
            else:  # blue
                filled = [b > 120 and r < 120 and g < 130 for r, g, b in pixels]
            # 오른쪽에서부터 첫 번째 filled 위치
            last_filled = 0
            for x, ok in enumerate(filled):
                if ok:
                    last_filled = x
            return (last_filled + 1) / w if w > 0 else 0.0
        except Exception:
            return 1.0  # 읽기 실패 시 안전하게 가득 찬 것으로

    def _is_dark(self, region: tuple, threshold: int = 40) -> bool:
        """영역 평균 밝기가 임계값 미만이면 True (사망 화면 감지)."""
        try:
            img  = ImageGrab.grab(bbox=region, all_screens=True).convert("L")
            data = list(img.getdata())
            avg  = sum(data) / len(data) if data else 128
            return avg < threshold
        except Exception:
            return False

    # ══════════════════════════════════════════════
    #  사냥 로직
    # ══════════════════════════════════════════════

    def _press_key_hunt(self, key: str):
        """키 입력 (Arduino 우선)."""
        hwnd = self._get_hwnd()
        if hwnd and win32gui.GetForegroundWindow() != hwnd:
            force_foreground(hwnd)
            time.sleep(0.08)
        if _ar_mod._arduino and _ar_mod._arduino.is_open:
            arduino_send(f"KEY:{key}:60")
        else:
            vk = _KEY_CODES.get(key, 0)
            if vk:
                win32api.keybd_event(vk, 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    def _scan_for_monster(self) -> tuple[int, int] | None:
        """hunt_region을 격자 스캔 — 검 커서 감지 위치 반환."""
        if not self._hunt_region or self._sword_handle is None:
            return None
        x1, y1, x2, y2 = self._hunt_region
        cols, rows = 8, 6
        step_x = max(1, (x2 - x1) // cols)
        step_y = max(1, (y2 - y1) // rows)
        for row in range(rows):
            for col in range(cols):
                if not self.running:
                    return None
                mx = x1 + step_x * col + step_x // 2
                my = y1 + step_y * row + step_y // 2
                win32api.SetCursorPos((mx, my))
                time.sleep(0.05)
                if self._is_sword_cursor():
                    self.log(f"🎯 몬스터 감지 ({mx},{my})", tag="감지")
                    return mx, my
        return None

    def _attack_target(self, x: int, y: int):
        """몬스터 위치에서 아래로 드래그 → 자동공격 시작."""
        hwnd = self._get_hwnd()
        if hwnd and win32gui.GetForegroundWindow() != hwnd:
            force_foreground(hwnd)
            time.sleep(0.1)
        dist = max(1, int(self._fv(self._drag_distance, 60.0)))
        win32api.SetCursorPos((x, y))
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        smooth_move(x, y + dist)
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        self.log(f"⚔ 공격 드래그 ({x},{y})→({x},{y+dist})", tag="공격")

    def _wait_kill(self, x: int, y: int) -> bool:
        """커서 변화 or 타임아웃까지 대기 — 검 커서 사라지면 사망 확인."""
        wait_t   = self._fv(self._attack_wait,   3.0)
        check_t  = self._fv(self._death_check_t, 0.5)
        wiggle   = max(1, int(self._fv(self._death_wiggle, 10.0)))
        deadline = time.time() + wait_t
        while time.time() < deadline and self.running:
            time.sleep(check_t)
            win32api.SetCursorPos((x - wiggle, y))
            time.sleep(0.04)
            if not self._is_sword_cursor():
                self.log("✅ 몬스터 사망", tag="전투"); return True
            win32api.SetCursorPos((x + wiggle, y))
            time.sleep(0.04)
            if not self._is_sword_cursor():
                self.log("✅ 몬스터 사망", tag="전투"); return True
            win32api.SetCursorPos((x, y))
        return True  # 타임아웃 — 루팅으로 진행

    def _do_loot(self):
        """루팅 키 입력 후 대기."""
        key  = self._loot_key.get().strip() or "F4"
        wait = self._fv(self._loot_wait, 0.8)
        self.log(f"🎁 루팅 [{key}]", tag="루팅")
        self._press_key_hunt(key)
        time.sleep(wait)

    def _check_potion(self, last_hp_t: float, last_mp_t: float) -> tuple[float, float]:
        """HP/MP 바 비율 확인 후 임계값 이하 시 포션 사용."""
        cooldown = self._fv(self._potion_cooldown, 3.0)
        now      = time.time()

        hp_key = self._hp_potion_key.get().strip()
        if hp_key and self._my_hp_region and (now - last_hp_t) >= cooldown:
            hp_pct = self._bar_ratio(self._my_hp_region, "red") * 100
            thr    = self._fv(self._hp_threshold_var, 50.0)
            if hp_pct <= thr:
                self.log(f"💊 HP {hp_pct:.0f}% → HP포션 [{hp_key}]", tag="포션")
                self._press_key_hunt(hp_key)
                last_hp_t = now

        mp_key = self._mp_potion_key.get().strip()
        if mp_key and self._my_mp_region and (now - last_mp_t) >= cooldown:
            mp_pct = self._bar_ratio(self._my_mp_region, "blue") * 100
            thr    = self._fv(self._mp_threshold_var, 30.0)
            if mp_pct <= thr:
                self.log(f"💊 MP {mp_pct:.0f}% → MP포션 [{mp_key}]", tag="포션")
                self._press_key_hunt(mp_key)
                last_mp_t = now

        return last_hp_t, last_mp_t

    def _do_move(self, wp_idx: int) -> int:
        """이동 패턴 실행 후 다음 waypoint 인덱스 반환."""
        if not self._waypoints:
            return 0
        if self._move_mode.get() == "랜덤":
            wp = random.choice(self._waypoints)
        else:
            wp_idx = wp_idx % len(self._waypoints)
            wp     = self._waypoints[wp_idx]
            wp_idx += 1

        x, y = wp
        self.log(f"🚶 이동 → ({x}, {y})", tag="이동")
        self._set_state_lbl(f"🚶 이동 중...")
        smooth_move(x, y)
        if _ar_mod._arduino and _ar_mod._arduino.is_open:
            arduino_send("CLICK")
        else:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
        return wp_idx

    # ── 메인 사냥 루프 ─────────────────────────────
    def _hunt_loop(self):
        """
        흐름: 화면 격자 스캔 → 검 커서 감지 → 드래그 공격 → 사망 확인 → 루팅
        커서 감지가 몬스터 유무 판단의 핵심 (OCR은 사용 안 함)
        """
        self.log("━━━ 사냥 루프 시작 ━━━")
        start_t       = time.time()
        last_hp_t     = 0.0
        last_mp_t     = 0.0
        last_move_t   = time.time()
        wp_idx        = 0
        no_mon_streak = 0
        move_delay    = self._fv(self._move_delay, 5.0)

        while self.running:
            # ── 시간 제한 탈출 ──────────────────
            if self._escape_on_time.get():
                limit = self._fv(self._escape_time_min, 60.0) * 60
                if time.time() - start_t >= limit:
                    self.log("⏱ 시간 제한 도달 → 중지")
                    self.after(0, self._stop); return

            # ── 사망 감지 ────────────────────────
            if self._escape_on_death.get() and self._dead_region:
                if self._is_dark(self._dead_region):
                    self.log("💀 사망 감지 → 중지")
                    self.after(0, self._stop); return

            # ── 포션 체크 ────────────────────────
            last_hp_t, last_mp_t = self._check_potion(last_hp_t, last_mp_t)

            # ── 몬스터 스캔 ──────────────────────
            self._set_state_lbl("🔍 스캔 중...")
            pos = self._scan_for_monster()

            if pos:
                no_mon_streak = 0
                mx, my = pos
                self._set_state_lbl(f"⚔ 전투 ({mx},{my})")
                self._attack_target(mx, my)
                self._wait_kill(mx, my)
                self._do_loot()
            else:
                no_mon_streak += 1
                elapsed = time.time() - last_move_t
                if elapsed >= move_delay or no_mon_streak >= 3:
                    wp_idx       = self._do_move(wp_idx)
                    last_move_t  = time.time()
                    no_mon_streak = 0
                    move_delay   = self._fv(self._move_delay, 5.0)
                    time.sleep(1.5)

            time.sleep(0.1)

        self._set_state_lbl("")
        self.log("━━━ 사냥 루프 종료 ━━━")

    # ── 시작 / 중지 ────────────────────────────────
    def _start(self):
        if not self._get_hwnd():
            self.log("창을 먼저 선택하세요."); return
        if not self._hunt_region:
            self.log("⚠ 사냥 화면 영역을 먼저 지정하세요."); return
        if self._sword_handle is None:
            self.log("⚠ 검 커서를 먼저 등록하세요."); return
        self.running = True
        self._run_evt.set()
        self._start_btn.configure(state="disabled", fg_color="#374151")
        self._stop_btn.configure(state="normal", fg_color="#EF4444",
                                  hover_color="#B91C1C")
        self._status_lbl.configure(text="● 사냥 중", text_color="#22C55E")
        threading.Thread(target=self._hunt_loop, daemon=True).start()

    def _stop(self):
        self.running = False
        self._run_evt.clear()
        self._start_btn.configure(state="normal", fg_color="#22C55E",
                                   hover_color="#16A34A")
        self._stop_btn.configure(state="disabled", fg_color="#374151",
                                  hover_color="#374151")
        self._status_lbl.configure(text="● 대기 중", text_color="#64748B")
        self._set_state_lbl("")

    # ── 설정 저장 / 로드 ───────────────────────────
    def _save_config(self):
        def _r(v): return list(v) if v else None
        cfg = {
            "hwnd_label":      self._hwnd_var.get(),
            "hunt_region":     _r(self._hunt_region),
            "tooltip_region":  _r(self._tooltip_region),
            "my_hp_region":    _r(self._my_hp_region),
            "my_mp_region":    _r(self._my_mp_region),
            "dead_region":     _r(self._dead_region),
            "sword_handle":    self._sword_handle,
            "drag_distance":   self._drag_distance.get(),
            "attack_wait":     self._attack_wait.get(),
            "death_check_t":   self._death_check_t.get(),
            "death_wiggle":    self._death_wiggle.get(),
            "hp_potion_key":   self._hp_potion_key.get(),
            "hp_threshold":    self._hp_threshold_var.get(),
            "mp_potion_key":   self._mp_potion_key.get(),
            "mp_threshold":    self._mp_threshold_var.get(),
            "potion_cooldown": self._potion_cooldown.get(),
            "loot_key":        self._loot_key.get(),
            "loot_wait":       self._loot_wait.get(),
            "waypoints":       self._waypoints,
            "move_mode":       self._move_mode.get(),
            "move_delay":      self._move_delay.get(),
            "escape_on_death": self._escape_on_death.get(),
            "escape_on_time":  self._escape_on_time.get(),
            "escape_time_min": self._escape_time_min.get(),
        }
        try:
            with open(_CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"설정 저장 실패: {e}", tag="CONFIG")

    def _load_config(self):
        if not os.path.exists(_CFG_PATH):
            return
        try:
            with open(_CFG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return

        def _t(v): return tuple(v) if v else None
        if v := cfg.get("hwnd_label"):  self._hwnd_var.set(v)
        self._hunt_region    = _t(cfg.get("hunt_region"))
        self._tooltip_region = _t(cfg.get("tooltip_region"))
        self._my_hp_region   = _t(cfg.get("my_hp_region"))
        self._my_mp_region   = _t(cfg.get("my_mp_region"))
        self._dead_region    = _t(cfg.get("dead_region"))

        if v := cfg.get("sword_handle"): self._sword_handle = v
        self._drag_distance.set(cfg.get("drag_distance",  "60"))
        self._attack_wait.set(cfg.get("attack_wait",       "3.0"))
        self._death_check_t.set(cfg.get("death_check_t",  "0.5"))
        self._death_wiggle.set(cfg.get("death_wiggle",     "10"))

        self._hp_potion_key.set(cfg.get("hp_potion_key", ""))
        self._hp_threshold_var.set(cfg.get("hp_threshold", "50"))
        self._mp_potion_key.set(cfg.get("mp_potion_key", ""))
        self._mp_threshold_var.set(cfg.get("mp_threshold", "30"))
        self._potion_cooldown.set(cfg.get("potion_cooldown", "3.0"))

        self._loot_key.set(cfg.get("loot_key",  "F4"))
        self._loot_wait.set(cfg.get("loot_wait", "0.8"))

        self._waypoints = [tuple(p) for p in cfg.get("waypoints", [])]
        self._move_mode.set(cfg.get("move_mode",  "순환"))
        self._move_delay.set(cfg.get("move_delay", "5.0"))

        self._escape_on_death.set(cfg.get("escape_on_death", True))
        self._escape_on_time.set(cfg.get("escape_on_time",  False))
        self._escape_time_min.set(cfg.get("escape_time_min", "60"))

        # UI 라벨 복원
        self.after(200, self._apply_region_labels)
        self.after(200, self._refresh_wp_display)

    def _apply_region_labels(self):
        # hunt_region / tooltip_region 라벨 복원
        for attr, lbl in [("_hunt_region", self._hunt_lbl),
                           ("_tooltip_region", self._tooltip_lbl)]:
            val = getattr(self, attr, None)
            if val:
                x1, y1, x2, y2 = val
                lbl.configure(text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")
        # sword handle 라벨 복원
        if self._sword_handle is not None:
            self._sword_handle_lbl_var.set(f"✅ 등록완료  핸들: {self._sword_handle}")
            self._sword_lbl.configure(text_color="#22C55E")
        # 서브 영역 라벨 복원
        for attr, lbl in self._region_lbls.items():
            val = getattr(self, attr, None)
            if val:
                x1, y1, x2, y2 = val
                lbl.configure(text=f"({x1},{y1})→({x2},{y2})", text_color="#22C55E")

    # ── 종료 ───────────────────────────────────────
    def _on_close(self):
        self.running = False
        self._save_config()
        self.destroy()
