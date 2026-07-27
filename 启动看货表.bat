@echo off
chcp 65001 >nul
cd /d "%~dp0"
python product_viewer.py
if errorlevel 1 (
    echo.
    echo 程序异常退出，请检查是否已安装 Python 3
    pause
)
