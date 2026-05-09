# -*- coding: utf-8 -*-
"""
배미유니버스 어드민 — 화이트리스트 관리 + 클라이언트 현황
"""
import os, subprocess, json, ssl, threading
import urllib.request
import customtkinter as ctk
from tkinter import messagebox

BASE     = os.path.dirname(os.path.abspath(__file__))
WL_FILE  = os.path.join(BASE, "whitelist.txt")
REPO     = "frontier0553/bemi-universe"
API_BASE = f"https://api.github.com/repos/{REPO}"

_ssl = ssl.create_default_context()
_ssl.check_hostname = False
_ssl.verify_mode = ssl.CERT_NONE

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── 화이트리스트 파일 I/O ──────────────────────────────
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


# ── 클라이언트 목록 (GitHub API) ───────────────────────
def _read_token():
    p = os.path.join(BASE, "github_token.txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return ""

def _fetch_clients():
    token = _read_token()
    if not token:
        return None   # 토큰 없음 구분
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        req = urllib.request.Request(f"{API_BASE}/contents/clients", headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=_ssl) as r:
            files = json.loads(r.read())
    except Exception:
        return []
    clients = []
    for f in files:
        if not f["name"].endswith(".json"):
            continue
        try:
            req2 = urllib.request.Request(f["download_url"])
            with urllib.request.urlopen(req2, timeout=8, context=_ssl) as r2:
                clients.append(json.loads(r2.read()))
        except Exception:
            pass
    clients.sort(key=lambda x: x.get("last_seen", ""), reverse=True)
    return clients


# ── 메인 앱 ───────────────────────────────────────────
class AdminApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("배미유니버스 어드민")
        self.geometry("660x580")
        self.resizable(False, False)

        self._users = _read_whitelist()

        ctk.CTkLabel(self, text="배미유니버스 어드민",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 6))

        self._tabs = ctk.CTkTabview(self, width=640, height=490)
        self._tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._tabs.add("허용 목록")
        self._tabs.add("클라이언트 현황")

        self._build_whitelist_tab()
        self._build_clients_tab()

    # ── 허용 목록 탭 ──────────────────────────────────
    def _build_whitelist_tab(self):
        tab = self._tabs.tab("허용 목록")

        self._listbox = ctk.CTkScrollableFrame(tab, height=280)
        self._listbox.pack(fill="both", expand=True, padx=8, pady=8)

        add_frame = ctk.CTkFrame(tab)
        add_frame.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(add_frame, text="이름:", width=40).pack(side="left", padx=(8, 2), pady=8)
        self._name_entry = ctk.CTkEntry(add_frame, width=140, placeholder_text="예) 미소페")
        self._name_entry.pack(side="left", padx=2, pady=8)

        ctk.CTkLabel(add_frame, text="MAC:", width=40).pack(side="left", padx=(8, 2))
        self._mac_entry = ctk.CTkEntry(add_frame, width=170, placeholder_text="AA:BB:CC:DD:EE:FF")
        self._mac_entry.pack(side="left", padx=2, pady=8)

        ctk.CTkButton(add_frame, text="추가", width=60, command=self._add).pack(side="left", padx=8)

        ctk.CTkButton(tab, text="저장 & GitHub 반영", height=36,
                      fg_color="#16A34A", hover_color="#15803D",
                      command=self._save).pack(pady=(0, 8))

        self._refresh_whitelist()

    def _refresh_whitelist(self):
        for w in self._listbox.winfo_children():
            w.destroy()
        for i, u in enumerate(self._users):
            row = ctk.CTkFrame(self._listbox, fg_color="#1e293b")
            row.pack(fill="x", pady=2, padx=2)
            ctk.CTkLabel(row, text=u["name"], width=140, anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(row, text=u["mac"], width=200, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#94A3B8").pack(side="left")
            ctk.CTkButton(row, text="삭제", width=52, height=26,
                          fg_color="#DC2626", hover_color="#B91C1C",
                          command=lambda i=i: self._remove(i)).pack(side="right", padx=8)

    def _add(self, name=None, mac=None):
        name = (name or self._name_entry.get()).strip()
        mac  = (mac  or self._mac_entry.get()).strip().upper()
        if not name or not mac:
            return
        if any(u["mac"] == mac for u in self._users):
            messagebox.showinfo("알림", f"{mac}\n이미 허용 목록에 있습니다.")
            return
        self._users.append({"name": name, "mac": mac})
        self._name_entry.delete(0, "end")
        self._mac_entry.delete(0, "end")
        self._refresh_whitelist()

    def _remove(self, idx):
        self._users.pop(idx)
        self._refresh_whitelist()

    def _save(self):
        _write_whitelist(self._users)
        _git_push()
        messagebox.showinfo("완료", "저장 및 GitHub 반영 완료!")

    # ── 클라이언트 현황 탭 ────────────────────────────
    def _build_clients_tab(self):
        tab = self._tabs.tab("클라이언트 현황")

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))
        self._client_status = ctk.CTkLabel(top, text="", text_color="#94A3B8",
                                           font=ctk.CTkFont(size=11))
        self._client_status.pack(side="left")
        ctk.CTkButton(top, text="새로고침", width=80, height=28,
                      command=self._refresh_clients).pack(side="right")

        # 헤더
        hdr = ctk.CTkFrame(tab, fg_color="#1e3a5f", corner_radius=4)
        hdr.pack(fill="x", padx=8, pady=(0, 2))
        for txt, w in [("사용자명", 100), ("컴퓨터명", 120),
                       ("MAC 주소", 145), ("IP 주소", 110), ("마지막 접속", 130)]:
            ctk.CTkLabel(hdr, text=txt, width=w, anchor="center",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#93C5FD").pack(side="left", padx=2, pady=6)
        ctk.CTkLabel(hdr, text="관리", width=80, anchor="center",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#93C5FD").pack(side="left", padx=2)

        self._client_scroll = ctk.CTkScrollableFrame(tab, fg_color="#0B1020")
        self._client_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._refresh_clients()

    def _refresh_clients(self):
        self._client_status.configure(text="불러오는 중...")
        for w in self._client_scroll.winfo_children():
            w.destroy()
        threading.Thread(target=self._do_fetch, daemon=True).start()

    def _do_fetch(self):
        clients = _fetch_clients()
        self.after(0, lambda: self._render_clients(clients))

    def _render_clients(self, clients):
        for w in self._client_scroll.winfo_children():
            w.destroy()

        if clients is None:
            ctk.CTkLabel(self._client_scroll,
                         text="github_token.txt 없음 — 토큰을 추가하세요",
                         text_color="#EF4444").pack(pady=20)
            self._client_status.configure(text="토큰 없음")
            return

        if not clients:
            ctk.CTkLabel(self._client_scroll, text="접속 기록 없음",
                         text_color="#64748B").pack(pady=20)
            self._client_status.configure(text="클라이언트 없음")
            return

        for c in clients:
            name     = c.get("username", "")
            computer = c.get("computer", "")
            mac      = c.get("mac", "")
            ip       = c.get("ip", "")
            seen     = c.get("last_seen", "")[:16].replace("T", " ")
            approved = any(u["mac"].upper() == mac.upper() for u in self._users)

            row = ctk.CTkFrame(self._client_scroll,
                               fg_color="#0f2a1a" if approved else "#1e293b",
                               corner_radius=4)
            row.pack(fill="x", pady=2, padx=2)

            for txt, w in [(name, 100), (computer, 120), (mac, 145), (ip, 110), (seen, 130)]:
                ctk.CTkLabel(row, text=txt, width=w, anchor="center",
                             font=ctk.CTkFont(family="Consolas", size=11),
                             text_color="#E2E8F0").pack(side="left", padx=2, pady=6)

            if approved:
                ctk.CTkLabel(row, text="허용됨", width=80, anchor="center",
                             text_color="#22C55E",
                             font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            else:
                _n, _m = name, mac
                ctk.CTkButton(row, text="허용 추가", width=80, height=24,
                              fg_color="#7C3AED", hover_color="#6D28D9",
                              command=lambda n=_n, m=_m: self._approve(n, m)
                              ).pack(side="left", padx=4)

        self._client_status.configure(text=f"총 {len(clients)}명")

    def _approve(self, name, mac):
        self._add(name=name, mac=mac)
        # 현황 탭 새로고침해서 버튼을 "허용됨"으로 바꿈
        self._refresh_clients()
        messagebox.showinfo("추가됨", f"{name} 추가 완료\n저장 버튼을 눌러 GitHub에 반영하세요.")


if __name__ == "__main__":
    app = AdminApp()
    app.mainloop()
