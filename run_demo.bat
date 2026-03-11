@echo off
echo ============================================
echo  Vue Test Healer - Demo Calistirici
echo ============================================
call venv\Scripts\activate.bat 2>NUL

echo.
echo [ADIM 1] Durum kontrolu...
echo ----------------------------------------
python main.py status
echo.

echo [ADIM 2] Data-Test Audit...
echo ----------------------------------------
python main.py data-test-audit
echo.

echo [ADIM 3] Vue Stabilite Raporu...
echo ----------------------------------------
python main.py vue-only
echo.

echo [ADIM 4] Capraz Analiz (Vue + Robot)...
echo ----------------------------------------
python main.py analyze --json
echo.

echo [ADIM 5] Heal Onerileri...
echo ----------------------------------------
python main.py heal --patch
echo.

echo Demo tamamlandi! reports/ klasorunu inceleyin.
pause
