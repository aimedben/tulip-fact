@echo off
title Diagnostic TulipFactures - compatibilite Windows
echo ==========================================================
echo   DIAGNOSTIC du dossier TulipFactures sur ce PC
echo   (aucune modification n'est faite)
echo ==========================================================
echo.

echo [1] Version de Windows :
powershell -NoProfile -Command "[System.Environment]::OSVersion.Version.ToString() + ' - ' + [System.Environment]::OSVersion.VersionString"
echo.

echo [2] Architecture :
powershell -NoProfile -Command "$env:PROCESSOR_ARCHITECTURE; if ([System.IntPtr]::Size -eq 8) { 'Windows 64 bits - application 32 bits OK' } else { 'Windows 32 bits' }"
echo.

echo [3] Emplacement du dossier (doit finir par \TulipFactures...) :
echo    %~dp0
echo.

echo [4] Fichiers de base :
if exist "%~dp0TulipFactures.exe" (echo     TulipFactures.exe        OK) else (echo     TulipFactures.exe        MANQUANT - copie incomplete)
if exist "%~dp0python38.dll"      (echo     python38.dll             OK) else (echo     python38.dll             MANQUANT - copie incomplete)
if exist "%~dp0MSVCP140.dll"      (echo     MSVCP140.dll             OK) else (echo     MSVCP140.dll             MANQUANT - copie incomplete)
if exist "%~dp0VCRUNTIME140.dll"  (echo     VCRUNTIME140.dll         OK) else (echo     VCRUNTIME140.dll         MANQUANT - copie incomplete)
echo.

echo [5] Runtime C universel (Windows 7 ne l'a pas toujours) :
if exist "%~dp0ucrtbase.dll" (echo     ucrtbase.dll             OK) else (echo     ucrtbase.dll             MANQUANT - copie incomplete)
set /a N=0
for %%F in ("%~dp0api-ms-win-crt-*.dll") do set /a N+=1
echo     api-ms-win-crt-*.dll     %N% fichier(s)  ^(doit etre au moins 14^)
echo.

echo [6] Client Firebird embarque :
if exist "%~dp0firebird\bin\isql.exe"          (echo     firebird\bin\isql.exe    OK) else (echo     firebird\bin\isql.exe    MANQUANT - copie incomplete)
if exist "%~dp0firebird\bin\fbclient.dll"      (echo     firebird\bin\fbclient    OK) else (echo     firebird\bin\fbclient    MANQUANT)
if exist "%~dp0firebird\bin\msvcr80.dll"       (echo     firebird\bin\msvcr80     OK) else (echo     firebird\bin\msvcr80     MANQUANT)
if exist "%~dp0firebird\firebird.msg"          (echo     firebird\firebird.msg    OK) else (echo     firebird\firebird.msg    MANQUANT)
echo.

echo [7] Navigateur portable :
if exist "%~dp0navigateur\firefox.exe" (echo     navigateur\firefox.exe   OK) else (echo     navigateur\firefox.exe   MANQUANT - l'app utilisera le navigateur par defaut)
echo.

echo [8] Donnees locales :
if exist "%~dp0data\tulip_factures.db" (echo     data\tulip_factures.db   OK) else (echo     data\tulip_factures.db   MANQUANT - copiez le dossier data complet)
echo.

echo [9] Kit Tulip (registre) :
powershell -NoProfile -Command "$p=(Get-ItemProperty 'HKCU:\Software\TH\TFZ' -ErrorAction SilentlyContinue).Pth; if ($p) { $q=$p.TrimEnd('\') + '\SUPERETTE.TFE'; if (Test-Path $q) { 'base trouvee : ' + $q } else { 'cle presente mais base introuvable : ' + $q } } else { 'cle absente (l''app fera une recherche sur les disques)' }"
echo.

echo [10] Ports Firebird 3050 / application 8000 :
netstat -an | findstr ":3050 " | findstr LISTENING
if errorlevel 1 (echo     port 3050 : aucun serveur Firebird en ecoute) else (echo     port 3050 : OK)
netstat -an | findstr ":8000 " | findstr LISTENING
if errorlevel 1 (echo     port 8000 : libre ^(l'app n'est pas encore lancee^)) else (echo     port 8000 : deja utilise - l'app est peut-etre ouverte)
echo.

echo [11] Espace libre sur ce disque :
powershell -NoProfile -Command "$d=Get-PSDrive ($env:SystemDrive[0]); 'libre : ' + [math]::Round($d.Free/1MB) + ' Mo'"
echo.

echo ==========================================================
echo   Si [4] [5] [6] indiquent MANQUANT, recopiez TOUT le
echo   dossier (la copie a ete interrompue).
echo   Sinon, lancez 1-REGLER-CONNEXION-TULIP.bat.
echo ==========================================================
pause
