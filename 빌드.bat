@echo off
chcp 65001 > nul
title 배미유니버스 빌드

echo.
echo  배미유니버스 전체 빌드 시작...
echo  (20~40분 소요)
echo.

cd /d "%~dp0"

python gen_icon.py
if %errorlevel% neq 0 (
    echo [경고] 아이콘 생성 실패 — 계속 진행
)

pyinstaller 배미유니버스_full.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo.
    echo [실패] 빌드 오류 발생
    pause
    exit /b 1
)

echo.
echo  완료! dist\배미유니버스\ 폴더를 zip으로 묶어서 전달하세요.
echo.
explorer dist\배미유니버스
pause
