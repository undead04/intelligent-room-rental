@echo off
chcp 65001 >nul
echo ========================================================
echo   Homigo - Smart Housing Decision Support System
echo   Khởi chạy FastAPI Backend Server (Port 8000)
echo ========================================================

cd /d "%~dp0"

IF EXIST ".venv\Scripts\python.exe" (
    echo [INFO] Sử dụng môi trường ảo: .venv
    .venv\Scripts\python.exe backend\run.py
) ELSE IF EXIST "backend\.venv\Scripts\python.exe" (
    echo [INFO] Sử dụng môi trường ảo: backend\.venv
    backend\.venv\Scripts\python.exe backend\run.py
) ELSE (
    echo [INFO] Sử dụng Python hệ thống
    python backend\run.py
)

pause
