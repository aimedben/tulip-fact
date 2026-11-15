@echo off
REM Launcher pour Tulip Factures
REM Double-cliquez sur ce fichier pour démarrer l'application

setlocal enabledelayedexpansion

set "APP_DIR=%~dp0"
set "BACKEND_DIR=%APP_DIR%backend"
set "VENV_PYTHON=%APP_DIR%.venv38\Scripts\python.exe"
if not exist "%VENV_PYTHON%" set "VENV_PYTHON=%APP_DIR%.venv\Scripts\python.exe"

REM Vérifier l'environnement virtuel
if not exist "%VENV_PYTHON%" (
    echo.
    echo ======================================
    echo ERREUR: Environnement virtuel non trouve
    echo ======================================
    echo.
    echo Executez d'abord le script install.ps1:
    echo   1. Ouvrez PowerShell en tant qu'administrateur
    echo   2. Naviguez vers ce dossier
    echo   3. Executez: .\install.ps1
    echo.
    pause
    exit /b 1
)

REM Vérifier le dossier backend
if not exist "%BACKEND_DIR%" (
    echo.
    echo ======================================
    echo ERREUR: Dossier backend non trouve
    echo ======================================
    echo.
    pause
    exit /b 1
)

REM Démarrer l'application
echo.
echo ======================================
echo Demarrage de Tulip Factures...
echo ======================================
echo.
REM Autoriser l'acces depuis le telephone (une seule fois, fenetre UAC)
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%autoriser-telephone.ps1"

REM Detecter l'adresse IP locale
"%VENV_PYTHON%" -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()" > "%TEMP%\tulip_lan_ip.txt" 2>nul
set "LAN_IP="
set /p LAN_IP=<"%TEMP%\tulip_lan_ip.txt"
del "%TEMP%\tulip_lan_ip.txt" >nul 2>&1
if not defined LAN_IP set "LAN_IP=IP-DU-PC"

echo L'application s'ouvrira dans votre navigateur
echo PC: http://127.0.0.1:8000
echo Telephone (meme Wi-Fi): http://%LAN_IP%:8000
echo.
echo Fermez cette fenetre pour arreter le serveur
echo.

cd /d "%BACKEND_DIR%"

REM Définir le mode production
set "TULIP_APP_MODE=production"

REM Ouvrir le navigateur une fois le serveur pret
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 5; Start-Process 'http://127.0.0.1:8000'"

REM Démarrer le serveur FastAPI (accessible depuis le réseau local)
"%VENV_PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

REM Si le serveur s'arrête, afficher un message
echo.
echo ======================================
echo Serveur arrete
echo ======================================
echo.
pause
