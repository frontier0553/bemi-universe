# -*- coding: utf-8 -*-
"""
배미유니버스 런처 — 자동 업데이트 + 실행
"""
import os, json, shutil, threading, subprocess, tempfile, zipfile, ssl
import urllib.request
import tkinter as tk
from tkinter import ttk

_ssl = ssl.create_default_context()
_ssl.check_hostname = False
_ssl.verify_mode = ssl.CERT_NONE

REPO             = "frontier0553/bemi-universe"
RAW_BASE         = f"https://raw.githubusercontent.com/{REPO}/main"
API_BASE         = f"https://api.github.com/repos/{REPO}"
ZIP_NAME         = "bemi-universe.zip"
MAIN_EXE         = "bemi-universe.exe"
VERSION_FILE     = "version.txt"
BASE_DIR         = r"C:\bemiuniverse"
WHITELIST_ENABLED = False   # False 로 바꾸면 화이트리스트 검사 비활성화
os.makedirs(BASE_DIR, exist_ok=True)


def _get_mac():
    import uuid
    mac = uuid.getnode()
    return ":".join(f"{(mac >> (8*i)) & 0xff:02X}" for i in reversed(range(6)))

def _check_whitelist():
    try:
        url = f"{RAW_BASE}/whitelist.txt"
        with urllib.request.urlopen(url, timeout=8, context=_ssl) as r:
            content = r.read().decode("utf-8")
        mac = _get_mac()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or "|" not in line:
                continue
            if line.split("|")[1].strip().upper() == mac:
                return True, mac
        return False, mac
    except Exception:
        return True, ""  # 네트워크 오류 시 통과


def _local_version():
    p = os.path.join(BASE_DIR, VERSION_FILE)
    return open(p).read().strip() if os.path.exists(p) else "0.0.0"

def _remote_version():
    url = f"{RAW_BASE}/{VERSION_FILE}"
    with urllib.request.urlopen(url, timeout=8, context=_ssl) as r:
        return r.read().decode().strip()

def _get_download_url():
    url = f"{API_BASE}/releases/latest"
    with urllib.request.urlopen(url, timeout=8, context=_ssl) as r:
        data = json.loads(r.read())
    for asset in data.get("assets", []):
        if asset["name"] == ZIP_NAME:
            return asset["browser_download_url"]
    return None


class UpdateWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        local = _local_version()
        self.title(f"배미유니버스 업데이트  v{local}")
        self.geometry("360x155")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        # MAC 주소 상시 표시
        mac_frame = tk.Frame(self, bg="#1e1e2e")
        mac_frame.pack(pady=(12, 0))
        tk.Label(mac_frame, text="내 MAC:", bg="#1e1e2e", fg="#94A3B8",
                 font=("맑은 고딕", 9)).pack(side="left", padx=(0, 4))
        self._mac_var = tk.StringVar(value=_get_mac())
        mac_entry = tk.Entry(mac_frame, textvariable=self._mac_var, width=18,
                             bg="#1e1e2e", fg="#FACC15", relief="flat",
                             font=("Consolas", 10), state="readonly",
                             readonlybackground="#1e1e2e")
        mac_entry.pack(side="left")
        tk.Button(mac_frame, text="복사", bg="#2d2d42", fg="white", relief="flat",
                  font=("맑은 고딕", 8), cursor="hand2", padx=6,
                  command=lambda: (self.clipboard_clear(),
                                   self.clipboard_append(self._mac_var.get()))
                  ).pack(side="left", padx=(4, 0))

        self._lbl = tk.Label(self, text="버전 확인 중...", bg="#1e1e2e",
                             fg="white", font=("맑은 고딕", 11))
        self._lbl.pack(pady=(8, 4))

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
        if WHITELIST_ENABLED:
            allowed, mac = _check_whitelist()
        else:
            allowed, mac = True, ""
        if not allowed:
            self._set("접근 권한 없음", f"아래 MAC 주소를 관리자에게 전달하세요")
            self.after(0, lambda: self._sub.configure(
                text=mac, font=("Consolas", 11), fg="#FACC15"))
            self._bar.stop()
            self._bar.configure(mode="determinate", value=0)
            return

        exe = os.path.join(BASE_DIR, MAIN_EXE)
        first_install = not os.path.exists(exe)

        try:
            local  = _local_version()
            remote = _remote_version()
        except Exception as e:
            if first_install:
                self._set("네트워크 오류 — 인터넷 연결 필요")
                return
            self._set("네트워크 오류 — 오프라인으로 실행")
            self.after(1500, self._launch)
            return

        if not first_install and local == remote:
            self.after(0, lambda v=local: self.title(f"배미유니버스 업데이트  v{v}"))
            self._set(f"최신 버전 ({local})")
            self.after(800, self._launch)
            return

        if first_install:
            self._set(f"최초 설치 중... v{remote}")
        else:
            self._set(f"업데이트 중... {local} → {remote}")

        try:
            dl_url = _get_download_url()
            if not dl_url:
                raise RuntimeError("다운로드 URL 없음")

            tmp = tempfile.mktemp(suffix=".zip")

            def _progress(count, block, total):
                if total > 0:
                    pct = min(count * block / total * 100, 100)
                    self.after(0, lambda p=pct, t=total: (
                        self._bar.stop(),
                        self._bar.configure(mode="determinate", value=p),
                        self._sub.configure(text=f"{p:.0f}%  ({t // 1024 // 1024} MB)")
                    ))

            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl))
            with opener.open(dl_url, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        _progress(downloaded, 1, total)

            self._set("압축 해제 중...")
            self.after(0, lambda: self._bar.configure(mode="indeterminate"))
            self.after(0, lambda: self._bar.start(12))

            # 설정 파일 백업 (업데이트 후 복원)
            CONFIG_FILES = ["config.json", "config_hj.json", "config_hunt.json"]
            config_backup = {}
            for cf in CONFIG_FILES:
                for search_dir in [BASE_DIR, os.path.join(BASE_DIR, "_internal")]:
                    cp = os.path.join(search_dir, cf)
                    if os.path.exists(cp):
                        try:
                            with open(cp, "rb") as f:
                                config_backup[cp] = f.read()
                        except Exception:
                            pass

            # 기존 파일 정리 후 압축 해제
            for f in os.listdir(BASE_DIR):
                p = os.path.join(BASE_DIR, f)
                if f != VERSION_FILE:
                    try:
                        if os.path.isdir(p): shutil.rmtree(p)
                        else: os.remove(p)
                    except Exception:
                        pass

            with zipfile.ZipFile(tmp, "r") as zf:
                zf.extractall(BASE_DIR)
            os.remove(tmp)

            # 설정 파일 복원
            for cp, data in config_backup.items():
                try:
                    os.makedirs(os.path.dirname(cp), exist_ok=True)
                    with open(cp, "wb") as f:
                        f.write(data)
                except Exception:
                    pass

            with open(os.path.join(BASE_DIR, VERSION_FILE), "w") as f:
                f.write(remote + "\n")

            self.after(0, lambda v=remote: self.title(f"배미유니버스 업데이트  v{v}"))
            self._set(f"설치 완료! ({remote})")
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
