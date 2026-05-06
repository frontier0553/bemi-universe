# -*- coding: utf-8 -*-
import os
import math
import tempfile

# ─────────────────────────────────────────
#  앱 아이콘 생성 — LoL 삼위일체 스타일
# ─────────────────────────────────────────
_cached_icon_path: "str | None" = None
_cached_icon_img:  "object | None" = None  # PIL Image (캐시)


def _build_icon_image():
    """LoL 삼위일체(Trinity Force) 스타일 PIL Image(256×256 RGBA) 생성"""
    from PIL import Image, ImageDraw, ImageFilter

    S  = 256
    cx = cy = S // 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # ── 배경 ──────────────────────────────
    d.rounded_rectangle([0, 0, S-1, S-1], radius=44,
                        fill=(6, 4, 16, 255))
    # 외곽 골드 테두리 (2레이어 글로우)
    d.rounded_rectangle([2, 2, S-3, S-3], radius=42,
                        outline=(180, 120, 10, 90), width=3)
    d.rounded_rectangle([5, 5, S-6, S-6], radius=40,
                        outline=(210, 160, 30, 255), width=5)

    # ── 색상 팔레트 ───────────────────────
    G_DARK   = (120,  80,   5, 255)
    G_MID    = (200, 145,  20, 255)
    G_BRIGHT = (245, 205,  60, 255)
    G_HI     = (255, 240, 140, 255)
    WHITE_G  = (255, 250, 200, 255)

    # ── 삼위일체 세 삼각형 ────────────────
    # 트라이포스 배치: 위, 왼쪽아래, 오른쪽아래
    # 각 삼각형의 중심
    TRI_OFFSET = 38   # 중심에서의 거리
    TRI_R      = 46   # 각 삼각형 외접원 반지름

    tri_centers = []
    for i in range(3):
        a = math.radians(-90 + 120 * i)
        tri_centers.append((cx + TRI_OFFSET * math.cos(a),
                            cy + TRI_OFFSET * math.sin(a)))

    def triangle(d_obj, tcx, tcy, r, angle_offset, fill_color):
        pts = []
        for j in range(3):
            a = math.radians(angle_offset + 120 * j)
            pts.append((tcx + r * math.cos(a), tcy + r * math.sin(a)))
        return pts

    for idx, (tcx, tcy) in enumerate(tri_centers):
        ao = -90  # 위쪽 꼭짓점이 기준

        # 그림자
        shadow = triangle(d, tcx + 2, tcy + 3, TRI_R, ao, G_DARK)
        d.polygon(shadow, fill=(0, 0, 0, 100))

        # 바깥 테두리 레이어
        outer = triangle(d, tcx, tcy, TRI_R, ao, G_DARK)
        d.polygon(outer, fill=G_DARK)

        # 메인 면
        mid = triangle(d, tcx, tcy, TRI_R * 0.85, ao, G_MID)
        d.polygon(mid, fill=G_MID)

        # 중간 밝은 면
        inner = triangle(d, tcx, tcy, TRI_R * 0.60, ao, G_BRIGHT)
        d.polygon(inner, fill=G_BRIGHT)

        # 상단 하이라이트 (꼭짓점 쪽)
        hi = triangle(d, tcx, tcy, TRI_R * 0.28, ao, G_HI)
        d.polygon(hi, fill=G_HI)

    # ── 삼각형 테두리 선 (입체감) ─────────
    for tcx, tcy in tri_centers:
        ao = -90
        outer = triangle(d, tcx, tcy, TRI_R, ao, G_DARK)
        d.polygon(outer, outline=(255, 235, 120, 180), width=2)

    # ── 중앙 글로우 (코어) ────────────────
    glow_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for r, alpha in [(34, 30), (24, 60), (16, 110), (10, 180), (5, 240)]:
        gd.ellipse([cx - r, cy - r, cx + r, cy + r],
                   fill=(255, 220, 80, alpha))
    glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=4))
    img = Image.alpha_composite(img, glow_blurred)
    d   = ImageDraw.Draw(img)

    # 코어 원 (선명)
    d.ellipse([cx - 9,  cy - 9,  cx + 9,  cy + 9],  fill=(255, 235, 100, 255))
    d.ellipse([cx - 5,  cy - 5,  cx + 5,  cy + 5],  fill=WHITE_G)

    # ── 빛 방사선 3개 (삼각형 꼭짓점 방향) ─
    RAY_R = TRI_OFFSET + TRI_R + 10
    for i in range(3):
        a   = math.radians(-90 + 120 * i)
        x1  = cx + 10 * math.cos(a)
        y1  = cy + 10 * math.sin(a)
        x2  = cx + RAY_R * math.cos(a)
        y2  = cy + RAY_R * math.sin(a)
        d.line([(x1, y1), (x2, y2)], fill=(255, 240, 130, 60), width=3)

    return img


def _make_app_icon_path() -> "str | None":
    global _cached_icon_path, _cached_icon_img
    if _cached_icon_path and os.path.exists(_cached_icon_path):
        return _cached_icon_path
    try:
        from PIL import Image
        img = _build_icon_image()
        _cached_icon_img = img
        ico    = os.path.join(tempfile.gettempdir(), "bemi_universe.ico")
        sizes  = [256, 128, 64, 48, 32, 16]
        frames = [img.resize((sz, sz), Image.LANCZOS) for sz in sizes]
        frames[0].save(ico, format="ICO", append_images=frames[1:])
        _cached_icon_path = ico
        return ico
    except Exception:
        return None


def _apply_icon(window) -> None:
    """타이틀바 + 작업표시줄 아이콘 동시 설정"""
    try:
        ico = _make_app_icon_path()
        if ico:
            window.iconbitmap(ico)
        from PIL import Image, ImageTk
        img   = _cached_icon_img or _build_icon_image()
        photo = ImageTk.PhotoImage(img.resize((64, 64), Image.LANCZOS))
        window.wm_iconphoto(True, photo)
        window._bemi_icon_ref = photo  # GC 방지
    except Exception:
        pass
