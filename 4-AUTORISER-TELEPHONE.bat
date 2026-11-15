@echo off
chcp 1252 >nul
title Autoriser l'acces telephone (port 8000)
setlocal

set "OUT=%~dp0acces-telephone.txt"

echo =================================================
echo   AUTORISER L'ACCES DEPUIS LE TELEPHONE
echo =================================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo   Ce fichier doit etre lance en ADMINISTRATEUR.
    echo.
    echo   Une fenetre de securite (UAC) va s'ouvrir : cliquez OUI.
    echo.
    timeout /t 2 >nul
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    if errorlevel 1 (
        echo   Elevation refusee ou impossible.
        echo.
        echo   Faites un CLIC DROIT sur ce fichier puis
        echo   "Executer en tant qu'administrateur".
        echo.
        pause
    )
    exit /b
)

> "%OUT%" echo ===== ACCES TELEPHONE (port 8000) =====
>>"%OUT%" echo Date: %DATE% %TIME%
>>"%OUT%" echo.

>>"%OUT%" echo [1] SUPPRESSION ANCIENNE REGLE
netsh advfirewall firewall delete rule name="Tulip Factures (LAN)" >>"%OUT%" 2>&1

>>"%OUT%" echo.
>>"%OUT%" echo [2] AJOUT DE LA REGLE
netsh advfirewall firewall add rule name="Tulip Factures (LAN)" dir=in action=allow protocol=TCP localport=8000 profile=any remoteip=localsubnet >>"%OUT%" 2>&1

>>"%OUT%" echo.
>>"%OUT%" echo [3] VERIFICATION
netsh advfirewall firewall show rule name="Tulip Factures (LAN)" >>"%OUT%" 2>&1

>>"%OUT%" echo.
>>"%OUT%" echo [4] ECOUTE DU PORT 8000
netstat -ano | findstr ":8000" >>"%OUT%" 2>&1

>>"%OUT%" echo.
>>"%OUT%" echo [5] ADRESSES IP DE CE PC
ipconfig | findstr /i "IPv4" >>"%OUT%" 2>&1

>>"%OUT%" echo.
>>"%OUT%" echo [6] ADRESSE A TAPER SUR LE TELEPHONE (meme Wi-Fi) :
>>"%OUT%" echo     http://IP-DU-PC:8000
>>"%OUT%" echo     (remplacer IP-DU-PC par une adresse du point [5])
>>"%OUT%" echo.
>>"%OUT%" echo FIN

echo   Termine.
echo   Le rapport va s'ouvrir : acces-telephone.txt
echo.
timeout /t 2 >nul
notepad "%OUT%"
