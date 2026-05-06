# -*- coding: utf-8 -*-
"""
빌드 전 실행 — PIL로 bemi_icon.ico 생성
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.icon import _build_icon_image
from PIL import Image

img    = _build_icon_image()
sizes  = [256, 128, 64, 48, 32, 16]
frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]
out    = os.path.join(os.path.dirname(__file__), "bemi_icon.ico")
frames[0].save(out, format="ICO", append_images=frames[1:],
               sizes=[(s, s) for s in sizes])
print(f"[OK] 아이콘 생성: {out}")
