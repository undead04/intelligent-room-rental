@echo off
chcp 65001 >nul
title Homigo Crawler Runner
cd /d "%~dp0"

IF EXIST ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
) ELSE (
    set "PY_BIN=python"
)

REM Nếu người dùng có truyền tham số dòng lệnh thì chạy trực tiếp
if not "%~1"=="" (
    echo [INFO] Chạy với tham số: %*
    %PY_BIN% crawler\main.py %*
    goto end
)

:menu
cls
echo ================================================================
echo      HOMIGO - SMART HOUSING DECISION SUPPORT SYSTEM
echo             TRÌNH KHỞI CHẠY CRAWLER & ETL PIPELINE
echo ================================================================
echo.
echo   Chọn chế độ chạy (chỉ cần gõ số 1, 2, 3... rồi nhấn Enter):
echo.
echo   [1] Cào cơ bản (5 trang TP.HCM -> Lưu Staging DB & Xuất CSV, Parquet)
echo   [2] Cào + Bóc tách tiện ích LLM Gemini (--llm)
echo   [3] Full Pipeline A-Z (Cào + LLM + ML Price Score + E5 Embed + Nạp DB) (--full)
echo   [4] Cào nhanh tin mới nhất (2 trang TP.HCM - Update mode)
echo   [5] Kiểm tra tin cũ còn hạn hay đã hết hạn (Verify 50 tin)
echo   [6] DEBUG: CHỈ CÀO DỮ LIỆU THÔ (Không chạy Pipeline ETL) (--no-clean)
echo   [7] DEBUG: CHỈ CHẠY ETL PIPELINE (Xử lý dữ liệu đã cào trong Staging DB)
echo   [0] Thoát
echo.
echo ================================================================
set "choice=1"
set /p choice="Nhập lựa chọn của bạn [Mặc định 1 - nhấn Enter]: "

if "%choice%"=="1" (
    echo.
    echo [INFO] Đang khởi chạy: Cào cơ bản 5 trang TP.HCM...
    %PY_BIN% crawler\main.py --pages 5
    goto end
)
if "%choice%"=="2" (
    echo.
    echo [INFO] Đang khởi chạy: Cào 5 trang TP.HCM + Bóc tách LLM Gemini...
    %PY_BIN% crawler\main.py --pages 5 --llm
    goto end
)
if "%choice%"=="3" (
    echo.
    echo [INFO] Đang khởi chạy: Full Pipeline từ A-Z (Cào + LLM + Price Score + Embed + DB)...
    %PY_BIN% crawler\main.py --pages 5 --full
    goto end
)
if "%choice%"=="4" (
    echo.
    echo [INFO] Đang khởi chạy: Quét 2 trang tin mới nhất...
    %PY_BIN% crawler\main.py --mode update --pages 2
    goto end
)
if "%choice%"=="5" (
    echo.
    echo [INFO] Đang kiểm tra trạng thái tin cũ trong kho...
    %PY_BIN% crawler\main.py --mode verify --limit 50
    goto end
)
if "%choice%"=="6" (
    echo.
    echo [INFO] Đang chỉ cào dữ liệu thô (không chạy ETL)...
    %PY_BIN% crawler\main.py --pages 5 --no-clean
    goto end
)
if "%choice%"=="7" (
    echo.
    echo [INFO] Đang chạy riêng lẻ ETL Pipeline trên dữ liệu Staging DB...
    %PY_BIN% -m crawler.etl.pipeline --full
    goto end
)
if "%choice%"=="0" exit /b 0

echo Lựa chọn không hợp lệ, vui lòng chọn lại!
pause
goto menu

:end
echo.
echo ================================================================
echo   Tiến trình đã hoàn tất!
echo ================================================================
pause
