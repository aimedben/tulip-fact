@echo off
chcp 1252 >nul
title Configuration de la connexion Tulip

if not exist "%~dp0TulipFactures.exe" (
    echo.
    echo   ERREUR : TulipFactures.exe est introuvable dans ce dossier.
    echo.
    echo   Ce fichier doit rester A COTE de TulipFactures.exe.
    echo.
    pause
    exit /b 1
)

start "" "%~dp0TulipFactures.exe" --config-tulip
exit /b 0
