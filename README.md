# 배미유니버스

라이니지 자동 판매 보조 프로그램

---

## 기능

### 헤이장사 (자동 판매)
- 손님 감지 (흰 픽셀 스캔)
- 교환창 자동 열기 (Arduino HID)
- 금액 OCR 인식 (easyocr)
- 상대방 OK 감지 (회색 픽셀 변화)
- 자동 OK 클릭 → 마법 시전 → 감사 채팅
- MP 관리: 3초 폴링, 방 수 계산, 광고 채팅 자동 전송
- 평상시 광고 (최대 4개 문구, {n}=방수 치환)
- 60초 타임아웃 자동 초기화

### 자동 사냥 (Auto Hunt)
- Win32 커서 핸들 기반 몬스터 감지
- 격자 스캔 → 공격 → 처치 확인 → 루팅
- 사냥 영역 / 드래그 거리 / 루팅 키 설정

### 요정 버프
- 버프 자동 반복

### Arduino Leonardo HID
- Serial 명령 수신 → 마우스/키보드 동작
- 명령: `CLICK`, `DBLCLICK`, `KEY:<key>:<ms>`

---

## 구조

```
files/
  core/
    arduino.py       Arduino 시리얼 통신
    constants.py     공통 상수
    icon.py          LoL 삼위일체 스타일 아이콘
    ocr_engine.py    easyocr / tesseract OCR 엔진
    win32_utils.py   Win32 유틸리티
  ui/
    mode_select.py   모드 선택 메인 화면
    hey_jangsa.py    헤이장사 자동 판매
    auto_hunt.py     자동 사냥
    yojong_buff.py   요정 버프
    region_selector.py 영역 선택 도구
  ino/
    bemi_universe.ino  Arduino 스케치
    Arduino_설치.txt   Arduino IDE 설치 가이드
  launcher.py        자동 업데이트 런처
  deploy.py          GitHub 배포 스크립트
  배포.bat           배포 실행 배치
  version.txt        현재 버전
```

---

## 설치 (다른 컴퓨터)

1. `launcher.exe` 다운로드 후 실행
2. 자동으로 `C:\bemiuniverse\` 에 설치

```
https://github.com/frontier0553/bemi-universe/releases/latest/download/launcher.exe
```

---

## Arduino 설정

1. [Arduino IDE 설치](https://www.arduino.cc/en/software)
2. `ino/bemi_universe.ino` 더블클릭
3. Tools → Board → Arduino Leonardo
4. Tools → Port → COM 포트 선택
5. 업로드 (배미유니버스 프로그램 종료 후 진행)

---

## 배포 방법

```
배포.bat 실행 → 변화 크기 선택 (1/2/3)
```

| 선택 | 변화 | 예시 |
|------|------|------|
| 1 | 큰 변화 (+1.0.0) | 신기능 추가 |
| 2 | 작은 변화 (+0.1.0) | 기능 개선 |
| 3 | 아주 작은 (+0.0.1) | 버그 수정 |

자동으로 빌드 → GitHub 릴리즈 생성 → EXE + 런처 업로드

---

## OCR 엔진

- **easyocr** (기본): 딥러닝 기반, 정확도 높음, 풀빌드에 내장
- **tesseract** (슬림빌드): 별도 설치 필요, 용량 작음

---

## 설정 파일

| 파일 | 내용 |
|------|------|
| `config.json` | 공통 설정 |
| `config_hj.json` | 헤이장사 설정 |
| `config_hunt.json` | 자동 사냥 설정 |
