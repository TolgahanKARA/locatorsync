@echo off
echo ============================================
echo  LocatorSync - Kurulum
echo ============================================
echo.

REM Python'u bul: python, py, python3 sirasiyla dene
set PYTHON_CMD=

python --version >NUL 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :python_found
)

py --version >NUL 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto :python_found
)

python3 --version >NUL 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python3
    goto :python_found
)

echo [HATA] Python bulunamadi!
echo.
echo Python 3.11+ yuklemeniz gerekiyor:
echo   https://www.python.org/downloads/
echo.
echo Kurulumdan sonra "Python'u PATH'e ekle" secenegini isaretleyin,
echo ardindan bu dosyayi tekrar calistirin.
pause
exit /b 1

:python_found
echo [OK] Python bulundu: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

REM Venv varsa atla, yoksa olustur
if exist "venv\Scripts\activate.bat" (
    echo [OK] Sanal ortam zaten mevcut.
) else (
    echo [1/3] Sanal ortam olusturuluyor...
    %PYTHON_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [HATA] Sanal ortam olusturulamadi!
        pause
        exit /b 1
    )
    echo [OK] Sanal ortam olusturuldu.
)

echo [2/3] Bagimliliklar yukleniyor...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [HATA] Bagimliliklar yuklenemedi!
    pause
    exit /b 1
)

echo [3/3] Kurulum dogrulaniyor...
python -c "import yaml, colorama, click, rich, bs4, robot, fastapi, uvicorn, requests; print('[OK] Tum bagimliliklar hazir!')"
if %errorlevel% neq 0 (
    echo [UYARI] Bazi bagimliliklar eksik olabilir.
)

echo.
echo ============================================
echo  Kurulum tamamlandi!
echo ============================================
echo.
echo Kullanim:
echo   run_web.bat                 -- Web arayuzunu baslat (http://localhost:8000)
echo   run.bat status              -- Yapilandirma kontrolu
echo   run.bat data-test-audit     -- data-test eksiklikleri
echo   run.bat vue-only            -- Vue stabilite raporu
echo   run.bat analyze --json      -- Capraz analiz (Vue + Robot)
echo   run.bat heal --patch        -- Heal onerileri + patch
echo.
pause
