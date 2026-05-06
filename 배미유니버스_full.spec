# -*- mode: python ; coding: utf-8 -*-
# ────────────────────────────────────────────────────────────
#  배미유니버스 — 풀 빌드
#  easyocr + torch 포함 → 결과물 ~1.5GB
#  OCR 완전 내장, 별도 설치 불필요
# ────────────────────────────────────────────────────────────
import sys, os
from PyInstaller.utils.hooks import collect_all, collect_data_files

# ── pywin32 DLL 수동 수집 ──────────────────────────────────
import site
_win32_dll_dir = os.path.join(site.getsitepackages()[0], 'pywin32_system32')
_win32_dlls = []
if os.path.isdir(_win32_dll_dir):
    for _f in os.listdir(_win32_dll_dir):
        if _f.lower().endswith('.dll'):
            _win32_dlls.append((os.path.join(_win32_dll_dir, _f), '.'))

# ── 패키지 수집 ────────────────────────────────────────────
import pathlib, os
datas, binaries, hiddenimports = [], [], []

# EasyOCR 모델 파일 번들
_model_src = pathlib.Path.home() / '.EasyOCR' / 'model'
if _model_src.exists():
    for _pth in _model_src.glob('*.pth'):
        datas.append((str(_pth), 'easyocr_models'))

for _pkg in ('customtkinter', 'easyocr', 'torch'):
    _r = collect_all(_pkg)
    datas += _r[0]; binaries += _r[1]; hiddenimports += _r[2]

binaries += _win32_dlls
hiddenimports += [
    'win32api', 'win32con', 'win32gui', 'win32process',
    'win32security', 'win32ts', 'pywintypes', 'win32timezone',
    'serial', 'serial.tools', 'serial.tools.list_ports',
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFilter',
    'PIL.ImageTk', 'PIL.ImageGrab',
    'numpy', 'cv2',
    'pytesseract',
]

a = Analysis(
    ['window_clicker_app.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torchaudio', 'torchvision',
        'torch.cuda', 'torch.distributed',
        'IPython', 'jupyter', 'matplotlib',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='bemi-universe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python3*.dll', 'torch*.dll'],
    console=False,
    uac_admin=True,
    icon='bemi_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['torch*.dll'],
    name='bemi-universe',
)
