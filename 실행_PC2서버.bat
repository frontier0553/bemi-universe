@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo 배미유니버스 원격 서버 (PC2) 시작 중...
python remote_server.py
pause
