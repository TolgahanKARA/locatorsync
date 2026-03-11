@echo off
REM Vue Test Healer - Hizli calistirici
REM Kullanim: run.bat [komut] [secenekler]
REM Ornek:   run.bat status
REM          run.bat analyze --json
REM          run.bat heal --patch --apply

if not exist "venv\Scripts\activate.bat" (
    echo [HATA] Sanal ortam bulunamadi. Once setup.bat calistirin!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python main.py %*
