# -*- coding: utf-8 -*-
import re, os, sys

# ─────────────────────────────────────────
#  OCR 엔진 초기화
# ─────────────────────────────────────────
OCR_ENGINE = None
_ocr_reader = None

def _get_model_dir():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'easyocr_models')
    return os.path.join(os.path.expanduser('~'), '.EasyOCR', 'model')

_init_error = ""

def _init_ocr():
    global OCR_ENGINE, _ocr_reader, _init_error
    try:
        import easyocr
        model_dir = _get_model_dir()
        _ocr_reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False,
                                     model_storage_directory=model_dir)
        OCR_ENGINE = "easyocr"
        return
    except Exception as e:
        _init_error = f"easyocr 실패: {e}"
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        OCR_ENGINE = "tesseract"
        return
    except Exception as e:
        _init_error += f" / tesseract 실패: {e}"
    OCR_ENGINE = None

def ocr_read(pil_img, numbers_only=True):
    def _fix_slash(text):
        """라이니지 픽셀폰트에서 '/'를 '7' 또는 '0'으로 오인식할 때 자동 교정
        예) 1137113->113/113,  65765->65/65,  49088->49/88"""
        def try_slash(m):
            s = m.group(0)
            for i in range(1, len(s) - 1):
                if s[i] in ('7', '0'):
                    left, right = s[:i], s[i+1:]
                    # 양쪽 모두 2~3자리여야 N/M 분수로 인정
                    if (2 <= len(left) <= 3 and 2 <= len(right) <= 3
                            and abs(len(left) - len(right)) <= 1):
                        try:
                            if int(left) <= int(right):
                                return f"{left}/{right}"
                        except Exception:
                            pass
            return s
        return re.sub(r'\d{4,}', try_slash, text)

    if OCR_ENGINE == "easyocr":
        import numpy as np
        img_np = np.array(pil_img.convert("RGB"))
        if numbers_only:
            # 숫자만 허용 → 알파벳/특수문자 오인식 차단
            results = _ocr_reader.readtext(
                img_np, detail=0, paragraph=False,
                allowlist='0123456789')
        else:
            results = _ocr_reader.readtext(img_np, detail=0, paragraph=False)
        raw = " ".join(str(r) for r in results).strip()
        fixed = _fix_slash(raw)
        matches = re.findall(r'\d+/\d+|\d+', fixed)
        return " ".join(matches) if matches else raw
    elif OCR_ENGINE == "tesseract":
        import pytesseract
        if numbers_only:
            cfg = '--psm 7 -c tessedit_char_whitelist=0123456789/.'
        else:
            cfg = '--psm 3'
        raw = pytesseract.image_to_string(pil_img, config=cfg).strip()
        fixed = _fix_slash(raw)
        matches = re.findall(r'\d+/\d+|\d+', fixed)
        return " ".join(matches) if matches else raw
    return "(OCR 엔진 없음)"
