# -*- coding: utf-8 -*-
import os
import customtkinter as ctk

from core.icon import _apply_icon, _build_icon_image

def _load_version():
    p = os.path.join(r"C:\bemiuniverse", "version.txt")
    if os.path.exists(p):
        return open(p).read().strip()
    p2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "version.txt")
    return open(p2).read().strip() if os.path.exists(p2) else "?"

# ─────────────────────────────────────────
#  모드 선택 화면 (페이지 전환)
# ─────────────────────────────────────────
class ModeSelectWindow(ctk.CTk):
    W, H = 680, 430

    def __init__(self):
        super().__init__()
        self.selected_mode = None
        self.title(f"배미유니버스  v{_load_version()}")
        self.geometry(f"{self.W}x{self.H}")
        self.after(100, lambda: _apply_icon(self))
        self.resizable(False, False)
        self.configure(fg_color="#0A0F1E")
        self._center()
        self._page = None
        self._show_main()

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - self.W) // 2
        y = (self.winfo_screenheight() - self.H) // 2
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _clear(self):
        if self._page:
            self._page.destroy()

    # ── 공통 헬퍼 ──────────────────────────
    def _back_btn(self, parent, cmd):
        ctk.CTkButton(parent, text="← 뒤로", width=70, height=26,
                      fg_color="transparent", hover_color="#1E293B",
                      text_color="#64748B", font=ctk.CTkFont(size=12),
                      command=cmd).pack(anchor="w", padx=14, pady=(10, 0))

    def _header(self, parent, icon, title, sub):
        top = ctk.CTkFrame(parent, fg_color="transparent"); top.pack(pady=(10, 0))
        ctk.CTkLabel(top, text=icon, font=ctk.CTkFont(size=32)).pack()
        ctk.CTkLabel(top, text=title, font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#FFFFFF").pack(pady=(4, 0))
        ctk.CTkLabel(top, text=sub, font=ctk.CTkFont(size=12),
                     text_color="#64748B").pack(pady=(4, 0))
        ctk.CTkFrame(parent, height=1, fg_color="#1E293B").pack(fill="x", padx=40, pady=16)

    def _card(self, parent, bg, border, icon, title, desc, btn_color, btn_hover, cmd):
        c = ctk.CTkFrame(parent, fg_color=bg, corner_radius=14,
                         border_width=1, border_color=border)
        c.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(c, text=icon,  font=ctk.CTkFont(size=28)).pack(pady=(16, 4))
        ctk.CTkLabel(c, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#FFFFFF").pack()
        ctk.CTkLabel(c, text=desc,  font=ctk.CTkFont(size=11), text_color="#64748B",
                     justify="center").pack(pady=(4, 12))
        ctk.CTkButton(c, text="선택", width=112, height=32,
                      fg_color=btn_color, hover_color=btn_hover,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=cmd).pack(pady=(0, 16))

    # ── 페이지 1: 메인 ─────────────────────
    def _show_main(self):
        self._clear()
        f = ctk.CTkFrame(self, fg_color="transparent"); f.pack(fill="both", expand=True)
        self._page = f

        top = ctk.CTkFrame(f, fg_color="transparent"); top.pack(pady=(34, 0))
        try:
            _pil = _build_icon_image().resize((64, 64))
            _ctk_img = ctk.CTkImage(light_image=_pil, dark_image=_pil, size=(64, 64))
            _icon_lbl = ctk.CTkLabel(top, image=_ctk_img, text="")
            _icon_lbl.pack()
            self._main_icon_ref = _ctk_img  # GC 방지
        except Exception:
            ctk.CTkLabel(top, text="⚡", font=ctk.CTkFont(size=36)).pack()
        ctk.CTkLabel(top, text="배미유니버스", font=ctk.CTkFont(size=26, weight="bold"),
                     text_color="#FFFFFF").pack(pady=(4, 0))
        ctk.CTkLabel(top, text=f"모드를 선택하세요  |  v{_load_version()}", font=ctk.CTkFont(size=13),
                     text_color="#64748B").pack(pady=(6, 0))
        ctk.CTkFrame(f, height=1, fg_color="#1E293B").pack(fill="x", padx=40, pady=22)

        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(padx=24)
        self._card(row, "#0F1E38", "#1E3A5F", "⚡", "요정버프",
                   "자동클릭 / MP감지\n멀티창 제어",
                   "#3B82F6", "#2563EB", lambda: self._pick("요정버프"))
        self._card(row, "#1A0F1E", "#3D1A4F", "🛒", "헤이장사",
                   "자동 상점 판매\n채팅 광고 연동",
                   "#A855F7", "#9333EA", self._show_heyjangs)
        self._card(row, "#0F1A10", "#14532D", "⚔", "자동사냥",
                   "스킬 순환 / 포션 관리\n이동패턴 · 탈출조건",
                   "#22C55E", "#16A34A", lambda: self._pick("자동사냥"))

    # ── 페이지 2: 헤이장사 서브모드 ────────
    def _show_heyjangs(self):
        self._clear()
        f = ctk.CTkFrame(self, fg_color="transparent"); f.pack(fill="both", expand=True)
        self._page = f

        self._back_btn(f, self._show_main)
        self._header(f, "🛒", "헤이장사", "판매 방식을 선택하세요")

        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(padx=36)
        self._card(row, "#101A14", "#14532D", "👤", "싱글모드",
                   "혼자 상점 운영\n1인 자동 판매",
                   "#22C55E", "#16A34A", lambda: self._pick("헤이장사_싱글"))
        self._card(row, "#0F1525", "#1E3A5F", "👥", "멀티모드",
                   "여럿이 묶어 판매\nTCP 멀티클라이언트",
                   "#3B82F6", "#2563EB", self._show_multi)

    # ── 페이지 3: 멀티 역할 선택 ───────────
    def _show_multi(self):
        self._clear()
        f = ctk.CTkFrame(self, fg_color="transparent"); f.pack(fill="both", expand=True)
        self._page = f

        self._back_btn(f, self._show_heyjangs)
        self._header(f, "👥", "멀티모드", "역할을 선택하세요")

        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(padx=36)
        self._card(row, "#1A1000", "#78350F", "🎯", "호스트",
                   "판매 지휘 / 명령 전송\n클라이언트 관리",
                   "#F59E0B", "#D97706",
                   lambda: self._pick("헤이장사_멀티_호스트"))
        self._card(row, "#0F1525", "#1E3A5F", "📡", "클라이언트",
                   "호스트 명령 수신\n자동 실행",
                   "#3B82F6", "#2563EB",
                   lambda: self._pick("헤이장사_멀티_클라이언트"))

    def _pick(self, mode: str):
        self.selected_mode = mode
        self.destroy()
