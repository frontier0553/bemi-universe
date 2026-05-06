# -*- coding: utf-8 -*-
import customtkinter as ctk
import tkinter as tk
from core.win32_utils import get_dpi_scale

# ─────────────────────────────────────────
#  전체화면 영역 선택기
# ─────────────────────────────────────────
class RegionSelector(ctk.CTkToplevel):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self._sx = self._sy = 0
        self._rect_id = None

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.4)
        self.configure(fg_color="black")
        self.lift()
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="드래그해서 캡처 영역을 선택하세요  |  ESC: 취소",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white", fg_color="#1E293B", corner_radius=8
        ).place(relx=0.5, rely=0.05, anchor="center")

        self._canvas = tk.Canvas(self, bg="black", highlightthickness=0, cursor="crosshair")
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._finish(None))

    def _on_press(self, e):
        self._sx, self._sy = e.x_root, e.y_root
        if self._rect_id:
            self._canvas.delete(self._rect_id)

    def _on_drag(self, e):
        if self._rect_id:
            self._canvas.delete(self._rect_id)
        x1 = self._sx - self.winfo_rootx()
        y1 = self._sy - self.winfo_rooty()
        x2 = e.x_root - self.winfo_rootx()
        y2 = e.y_root - self.winfo_rooty()
        self._rect_id = self._canvas.create_rectangle(
            x1, y1, x2, y2, outline="#8B5CF6", width=2, fill=""
        )

    def _on_release(self, e):
        s = get_dpi_scale()
        x1 = int(min(self._sx, e.x_root) * s)
        y1 = int(min(self._sy, e.y_root) * s)
        x2 = int(max(self._sx, e.x_root) * s)
        y2 = int(max(self._sy, e.y_root) * s)
        if (x2 - x1) < 5 or (y2 - y1) < 5:
            return
        self._finish((x1, y1, x2, y2))

    def _finish(self, result):
        self.destroy()
        if self.callback:
            self.callback(result)


# ─────────────────────────────────────────
#  단일 좌표 클릭 선택기
# ─────────────────────────────────────────
class PointSelector(ctk.CTkToplevel):
    """화면 전체를 반투명 오버레이로 덮고, 클릭한 지점의 절대좌표를 callback(x, y)으로 반환."""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.45)
        self.configure(fg_color="#0F172A")
        self.lift()
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="클릭해서 손님 위치를 선택하세요  |  ESC: 취소",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white", fg_color="#1E293B", corner_radius=8,
        ).place(relx=0.5, rely=0.06, anchor="center")

        self._canvas = tk.Canvas(self, bg="#0F172A", highlightthickness=0, cursor="crosshair")
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self.bind("<Escape>", lambda e: self._finish(None))

    def _on_click(self, e):
        s = get_dpi_scale()
        self._finish((int(e.x_root * s), int(e.y_root * s)))

    def _finish(self, result):
        self.destroy()
        if self.callback:
            self.callback(result)
