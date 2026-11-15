@echo off
REM Installation one-click de Tulip Factures (a lancer sur le PC cible)
REM Copiez tout le dossier sur le PC, puis double-cliquez ce fichier.

setlocal
cd /d "%~dp0"
echo.
echo ==========================================
echo   Installation de Tulip Factures
echo ==========================================
echo.
echo Prerequis sur ce PC :
echo   - Python 3.12+ (avec "Add Python to PATH")
echo   - Tesseract OCR 5.x (fra + eng) pour l'OCR
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Portable
echo.
echo Si l'installation a reussi, lancez TulipFactures.bat
echo.
pause
endlocal
