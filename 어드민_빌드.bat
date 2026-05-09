@echo off
pyinstaller admin.spec --clean --noconfirm
echo.
echo Done: dist\
pause
