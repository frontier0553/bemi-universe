# -*- coding: utf-8 -*-
"""
배미유니버스 런처 — 자동 업데이트 + 실행
"""
import os, sys, json, shutil, threading, subprocess, tempfile
import urllib.request
import tkinter as tk
from tkinter import ttk

REPO        = "frontier0553/bemi-universe"
RAW_BASE    = f"https://raw.githubusercontent.com/{REPO}/main"
API_BASE    = f"https://api.github.com/repos/{REPO}"
MAIN_EXE    = "배미유니버스.exe"
VERSION_FILE = "version.txt"
BASE_DIR    = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))


def _local_version():
    p = os.path.join(BASE_DIR, VERSION_FILE)
    return open(p).read().strip() if os.path.exists(p) else "0.0.0"

def _remote_version():
    url = f"{RAW_BASE}/{VERSION_FILE}"
    with urllib.request.urlopen(url, timeout=8) as r:
        return r.read().decode().strip()

def _get_download_url():
    url = f"{API_BASE}/releases/latest"
    with urllib.request.urlopen(url, timeout=8) as r:
        data = json.loads(r.read())
    for asset in data.get("assets", []):
        if asset["name"] == MAIN_EXE:
            return asset["browser_download_url"]
    return None


class UpdateWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("배미유니버스 업데이트")
        self.geometry("360x120")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        self._lbl = tk.Label(self, text="버전 확인 중...", bg="#1e1e2e",
                             fg="white", font=("맑은 고딕", 11))
        self._lbl.pack(pady=(18, 6))

        self._bar = ttk.Progressbar(self, length=300, mode="indeterminate")
        self._bar.pack()
        self._bar.start(12)

        self._sub = tk.Label(self, text="", bg="#1e1e2e",
                             fg="#94A3B8", font=("맑은 고딕", 9))
        self._sub.pack(pady=4)

        threading.Thread(target=self._run, daemon=True).start()

    def _set(self, msg, sub=""):
        self._lbl.configure(text=msg)
        self._sub.configure(text=sub)

    def _run(self):
        try:
            local  = _local_version()
            remote = _remote_version()
        except Exception as e:
            self._set("네트워크 오류 — 오프라인으로 실행")
            self.after(1500, self._launch)
            return

        if local == remote:
            self._set(f"최신 버전 ({local})")
            self.after(800, self._launch)
            return

        # 업데이트 필요
        self._set(f"업데이트 중... {local} → {remote}")
        try:
            dl_url = _get_download_url()
            if not dl_url:
                raise RuntimeError("다운로드 URL 없음")

            tmp = tempfile.mktemp(suffix=".exe")

            def _progress(count, block, total):
                if total > 0:
                    pct = min(count * block / total * 100, 100)
                    self.after(0, lambda p=pct: (
                        self._bar.stop(),
                        self._bar.configure(mode="determinate", value=p),
                        self._sub.configure(text=f"{p:.0f}%  ({total // 1024 // 1024} MB)")
                    ))

            urllib.request.urlretrieve(dl_url, tmp, _progress)

            dest = os.path.join(BASE_DIR, MAIN_EXE)
            # 실행 중인 EXE 교체: 임시 이름으로 백업 후 교체
            old = dest + ".old"
            if os.path.exists(old):
                os.remove(old)
            if os.path.exists(dest):
                os.rename(dest, old)
            shutil.move(tmp, dest)

            # 버전 파일 갱신
            with open(os.path.join(BASE_DIR, VERSION_FILE), "w") as f:
                f.write(remote + "\n")

            self._set(f"업데이트 완료! ({remote})")
            self.after(800, self._launch)

        except Exception as e:
            self._set("업데이트 실패 — 기존 버전으로 실행", str(e))
            self.after(2000, self._launch)

    def _launch(self):
        self.destroy()
        exe = os.path.join(BASE_DIR, MAIN_EXE)
        if os.path.exists(exe):
            subprocess.Popen([exe])
        else:
            tk.messagebox.showerror("오류", f"{MAIN_EXE} 을 찾을 수 없습니다.")


if __name__ == "__main__":
    app = UpdateWindow()
    app.mainloop()
