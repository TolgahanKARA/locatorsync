@echo off
echo LocatorSync - Web Arayuzu baslatiliyor...
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [HATA] Sanal ortam bulunamadi. Once setup.bat calistirin.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo Sunucu baslatiliyor: http://localhost:8000
echo Durdurmak icin: Ctrl+C
echo.

python -m uvicorn web.server:app --host 0.0.0.0 --port 8000 --reload
