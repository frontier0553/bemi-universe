@echo off
chcp 65001 > nul
title 배미유니버스 — EXE 빌드

echo.
echo ═══════════════════════════════════════════════
echo    배미유니버스  EXE 빌드 도구
echo ═══════════════════════════════════════════════
echo.
echo  [1] 슬림 빌드  (~100MB, 단일 exe)
echo      OCR 미포함 — Tesseract 별도 설치 필요
echo      빌드 시간: 약 3~5분
echo.
echo  [2] 풀 빌드    (~1.5GB, 폴더 배포)
echo      easyocr + torch 내장, 별도 설치 없음
echo      빌드 시간: 약 20~40분
echo.
set /p CHOICE="번호 선택 (1 또는 2): "

if "%CHOICE%"=="1" goto SLIM
if "%CHOICE%"=="2" goto FULL
echo [ERROR] 1 또는 2만 입력하세요.
pause & exit /b 1

:: ─────────────────────────────────────────────
:CHECK_ENV
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python을 찾을 수 없습니다. https://python.org 에서 설치하세요.
    pause & exit /b 1
)
pyinstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] PyInstaller 설치 중...
    pip install pyinstaller --quiet
)
goto :EOF

:: ─────────────────────────────────────────────
:SLIM
call :CHECK_ENV

echo.
echo [1/4] 필수 패키지 설치 중...
pip install customtkinter pillow pywin32 pyserial pyinstaller --quiet --upgrade

echo [2/4] 아이콘 생성 중...
python gen_icon.py
if %errorlevel% neq 0 (
    echo [WARN] 아이콘 생성 실패 — 기본 아이콘으로 빌드 진행
)

echo [3/4] 슬림 EXE 빌드 중 (3~5분 소요)...
pyinstaller 배미유니버스_slim.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] 빌드 실패. 위 오류 메시지를 확인하세요.
    pause & exit /b 1
)

echo [4/4] 완료!
echo ─────────────────────────────────────────────
echo   결과물: dist\배미유니버스.exe
echo ─────────────────────────────────────────────
if exist "dist\배미유니버스.exe" explorer dist
goto END

:: ─────────────────────────────────────────────
:FULL
call :CHECK_ENV

echo.
echo [1/4] 전체 패키지 설치 중 (시간 소요)...
pip install customtkinter pillow pywin32 pyserial pyinstaller easyocr --quiet --upgrade

echo [2/4] 아이콘 생성 중...
python gen_icon.py
if %errorlevel% neq 0 (
    echo [WARN] 아이콘 생성 실패 — 기본 아이콘으로 빌드 진행
)

echo [3/4] 풀 빌드 중 (20~40분 소요, 기다려주세요)...
pyinstaller 배미유니버스_full.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] 빌드 실패. 위 오류 메시지를 확인하세요.
    pause & exit /b 1
)

echo [4/4] 완료!
echo ─────────────────────────────────────────────
echo   결과물 폴더: dist\배미유니버스\
echo   실행 파일:   dist\배미유니버스\배미유니버스.exe
echo ─────────────────────────────────────────────
if exist "dist\배미유니버스\배미유니버스.exe" explorer "dist\배미유니버스"
goto END

:: ─────────────────────────────────────────────
:END
echo.
pause
