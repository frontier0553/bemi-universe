# -*- coding: utf-8 -*-
"""
배미유니버스 어드민 — 화이트리스트 관리
"""
import os, sys, subprocess
import customtkinter as ctk

BASE      = os.path.dirname(os.path.abspath(__file__))
WL_FILE   = os.path.join(BASE, "whitelist.txt")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _read_whitelist():
    users = []
    if not os.path.exists(WL_FILE):
        return users
    for line in open(WL_FILE, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) == 2:
            users.append({"name": parts[0].strip(), "mac": parts[1].strip().upper()})
    return users

def _write_whitelist(users):
    with open(WL_FILE, "w", encoding="utf-8") as f:
        f.write("# 배미유니버스 허용 목록\n")
        f.write("# 형식: 이름|MAC주소\n")
        for u in users:
            f.write(f"{u['name']}|{u['mac']}\n")

def _git_push():
    subprocess.run("git add whitelist.txt", shell=True, cwd=BASE)
    subprocess.run('git commit -m "whitelist update"', shell=True, cwd=BASE)
    subprocess.run("git push", shell=True, cwd=BASE)


class AdminApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("배미유니버스 어드민")
        self.geometry("540x480")
        self.resizable(False, False)

        self._users = _read_whitelist()

        # 타이틀
        ctk.CTkLabel(self, text="허용 목록 관리", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(16, 4))

        # 목록
        list_frame = ctk.CTkFrame(self)
        list_frame.pack(fill="both", expand=True, padx=16, pady=8)

        self._listbox = ctk.CTkScrollableFrame(list_frame, height=240)
        self._listbox.pack(fill="both", expand=True, padx=8, pady=8)

        # 추가 입력
        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(add_frame, text="이름:", width=40).pack(side="left", padx=(8, 2), pady=8)
        self._name_entry = ctk.CTkEntry(add_frame, width=140, placeholder_text="예) 미소페")
        self._name_entry.pack(side="left", padx=2, pady=8)

        ctk.CTkLabel(add_frame, text="MAC:", width=40).pack(side="left", padx=(8, 2))
        self._mac_entry = ctk.CTkEntry(add_frame, width=160, placeholder_text="AA:BB:CC:DD:EE:FF")
        self._mac_entry.pack(side="left", padx=2, pady=8)

        ctk.CTkButton(add_frame, text="추가", width=60, command=self._add).pack(side="left", padx=8)

        # 저장 버튼
        ctk.CTkButton(self, text="저장 & GitHub 반영", height=36,
                      fg_color="#16A34A", hover_color="#15803D",
                      command=self._save).pack(pady=(0, 16))

        self._refresh()

    def _refresh(self):
        for w in self._listbox.winfo_children():
            w.destroy()
        for i, u in enumerate(self._users):
            row = ctk.CTkFrame(self._listbox, fg_color="#1e293b")
            row.pack(fill="x", pady=2, padx=2)
            ctk.CTkLabel(row, text=u["name"], width=140, anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(row, text=u["mac"], width=180, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#94A3B8").pack(side="left")
            idx = i
            ctk.CTkButton(row, text="삭제", width=52, height=26,
                          fg_color="#DC2626", hover_color="#B91C1C",
                          command=lambda i=idx: self._remove(i)).pack(side="right", padx=8)

    def _add(self):
        name = self._name_entry.get().strip()
        mac  = self._mac_entry.get().strip().upper()
        if not name or not mac:
            return
        self._users.append({"name": name, "mac": mac})
        self._name_entry.delete(0, "end")
        self._mac_entry.delete(0, "end")
        self._refresh()

    def _remove(self, idx):
        self._users.pop(idx)
        self._refresh()

    def _save(self):
        _write_whitelist(self._users)
        _git_push()
        ctk.CTkLabel(self, text="✅ 저장 및 반영 완료!", text_color="#22C55E").pack()
        self.after(2000, lambda: [w.destroy() for w in self.winfo_children() if isinstance(w, ctk.CTkLabel) and "완료" in str(w.cget("text"))])


if __name__ == "__main__":
    app = AdminApp()
    app.mainloop()
