@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════╗
echo  ║   BIST Sinyal Tarayıcısı - Kurulum  ║
echo  ╚══════════════════════════════════════╝
echo.

echo  [1/2] Gerekli paketler kuruluyor...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  HATA: Paket kurulumu basarisiz!
    pause
    exit /b 1
)

echo  [2/2] Uygulama baslatiliyor...
echo.
python uygulama.py

if errorlevel 1 (
    echo.
    echo  HATA olustu. Detaylar icin yukaridaki mesajlara bakin.
    pause
)
