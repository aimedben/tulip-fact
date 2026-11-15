# Préparation d'un package portable (copie sur un autre PC Windows)
# - N'inclut PAS : .venv, data (base/documents), .env (secrets), logs, caches, .git
# - Inclut     : code, frontend compilé (backend/app/static), tessdata, installateur
# Sur le PC cible : Python 3.12+ puis lancer INSTALLER.bat (recrée le .venv).

param(
    [string]$OutputPath = "$PSScriptRoot\TulipFactures-Portable",
    [switch]$IncludeGit = $false
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Préparation package portable" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$SourcePath = $PSScriptRoot

# Vérifier que le frontend compilé est présent (FastAPI le sert depuis backend/app/static)
$staticIndex = Join-Path $SourcePath "backend\app\static\index.html"
if (-not (Test-Path $staticIndex)) {
    Write-Host "ERREUR : frontend compilé absent (backend\app\static\index.html)." -ForegroundColor Red
    Write-Host "Compilez d'abord : cd frontend ; npm run build" -ForegroundColor Yellow
    exit 1
}
Write-Host "OK : frontend compilé détecté (backend\app\static)." -ForegroundColor Green

# Dossier de sortie
Write-Host "Dossier cible : $OutputPath" -ForegroundColor Yellow
if (Test-Path $OutputPath) {
    Write-Host "Suppression de l'ancien package..." -ForegroundColor Yellow
    Remove-Item -Path $OutputPath -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null

# Copie racine (fichiers utiles) — jamais le .env réel ni les logs
$rootFiles = @(
    ".env.example",
    ".env.mistral.example",
    ".gitignore",
    "README.md",
    "INSTALLATION_PORTABLE.md",
    "MIGRATION_MISTRAL_OCR.md",
    "install.ps1",
    "INSTALLER.bat",
    "TulipFactures.bat",
    "launcher.py",
    "start-silent.py",
    "invisible.vbs",
    "creer-executable.ps1",
    "autoriser-telephone.ps1",
    "add_article.py",
    "add_product_to_firebird.py",
    "insert_lines.py"
)

Write-Host ""
Write-Host "Copie des fichiers racine..." -ForegroundColor Yellow
foreach ($f in $rootFiles) {
    $src = Join-Path $SourcePath $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $OutputPath -Force
        Write-Host "  + $f" -ForegroundColor Gray
    }
}

# Copie des dossiers (backend contient le frontend compilé dans app/static)
$folders = @("backend", "frontend", "docs", "examples", "scripts", "tessdata")
Write-Host ""
Write-Host "Copie des dossiers..." -ForegroundColor Yellow
foreach ($d in $folders) {
    $src = Join-Path $SourcePath $d
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $OutputPath $d) -Recurse -Force
        Write-Host "  + $d/" -ForegroundColor Gray
    }
}

# Nettoyage des artefacts locaux / lourds / sensibles
Write-Host ""
Write-Host "Nettoyage (venv, caches, données, logs, secrets)..." -ForegroundColor Yellow

$removeDirNames = @("__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv", "venv", "data", ".claude", "dist")
if (-not $IncludeGit) { $removeDirNames += ".git" }

foreach ($name in $removeDirNames) {
    Get-ChildItem -Path $OutputPath -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq $name } | ForEach-Object {
            Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "  - dir  $($_.Name)" -ForegroundColor DarkGray
        }
}

$removeFilePatterns = @("*.pyc", "*.pyo", "*.log", "*.err.log", "*.out.log", ".env", "facture_raw.txt",
    "uvicorn.err.log", "uvicorn.out.log", "backend.log", "dev.log", "dev-server.log", "server.log", "server.err.log",
    "tulip_factures.db", "tulip_factures.db-*")
foreach ($pat in $removeFilePatterns) {
    Get-ChildItem -Path $OutputPath -Recurse -File -Force -Include $pat -ErrorAction SilentlyContinue | ForEach-Object {
        # ne jamais supprimer les .env.example
        if ($_.Name -notmatch '\.env\..*example') {
            Remove-Item -Path $_.FullName -Force -ErrorAction SilentlyContinue
            Write-Host "  - file $($_.Name)" -ForegroundColor DarkGray
        }
    }
}

# Squelette data vide (créé aussi par install.ps1, mais utile si on lance sans install complet)
$dataDirs = @("data", "data\documents", "data\pages", "data\exports", "data\backups", "data\logs")
foreach ($rel in $dataDirs) {
    New-Item -ItemType Directory -Path (Join-Path $OutputPath $rel) -Force | Out-Null
}

# LISEZ-MOI
$dateStr = Get-Date -Format "yyyy-MM-dd HH:mm"
$readme = @"
TULIP FACTURES — PACKAGE PORTABLE
=================================
Préparé le : $dateStr

Ce dossier est prêt à être copié sur un autre PC Windows.
Il ne contient PAS vos données (base/documents) ni vos clés API.

INSTALLATION SUR LE PC CIBLE (obligatoire, une seule fois)
----------------------------------------------------------
1. Copiez tout ce dossier sur le PC (ex. C:\TulipFactures ou une clé USB).
   Évitez un chemin avec des espaces exotiques ; un chemin simple est préférable.
2. Installez les prérequis :
   - Python 3.12 ou supérieur : https://www.python.org/downloads/
     -> cochez "Add Python to PATH" pendant l'installation.
   - (Recommandé pour l'OCR) Tesseract OCR 5.x + langues fra, eng :
     https://github.com/UB-Mannheim/tesseract/wiki
3. Double-cliquez sur INSTALLER.bat  (ou clic droit PowerShell admin : .\install.ps1 -Portable)
   -> cela crée l'environnement .venv et installe les dépendances.
   -> nécessite une connexion Internet pour télécharger les paquets Python.
4. Lancez l'application : double-cliquez sur TulipFactures.bat
   -> PC : http://127.0.0.1:8000
   -> Téléphone (même Wi-Fi) : l'adresse affichée au démarrage.

IMPORTANT
---------
- Le dossier .venv NE PEUT PAS être copié d'un PC à l'autre : lancez toujours INSTALLER.bat
  sur chaque nouveau PC (recréation de l'environnement).
- Vos factures/données ne sont pas incluses. Pour migrer vos données, copiez le dossier
  data\ (surtout data\tulip_factures.db et data\documents\) depuis l'ancien PC vers le
  nouveau, APRÈS installation, application arrêtée.
- Configurez vos clés/chemins locaux dans .env (copié depuis .env.example à l'installation).
  Ne partagez jamais votre fichier .env (il peut contenir des clés API).
- Tesseract est requis pour l'OCR local ; sans lui, l'extraction OCR échouera.
  Les moteurs RapidOCR/Paddle/GOT/OCR IA ont leurs propres prérequis (voir README).

DÉPANNAGE RAPIDE
----------------
- "Python non détecté" : réinstallez Python en cochant "Add Python to PATH", puis relancez
  INSTALLER.bat (fermez/rouvrez la fenêtre).
- "Environnement virtuel non trouvé" au lancement : exécutez INSTALLER.bat.
- Port 8000 occupé : changez le port dans .env (TULIP_PORT=8001) et relancez.
- OCR indisponible : vérifiez TESSERACT_CMD dans .env et l'installation de Tesseract.

Documentation complète : README.md, INSTALLATION_PORTABLE.md, docs/
"@
$readme | Out-File -FilePath (Join-Path $OutputPath "LISEZ-MOI.txt") -Encoding UTF8

# Manifeste
$sizeMB = [math]::Round(((Get-ChildItem -Path $OutputPath -Recurse -File | Measure-Object -Property Length -Sum).Sum) / 1MB, 2)
$manifest = [ordered]@{
    app        = "Tulip Factures"
    prepared   = (Get-Date -Format "o")
    size_mb    = $sizeMB
    has_static = $true
    notes      = "Sans .venv, sans data, sans .env. Lancer INSTALLER.bat sur le PC cible."
}
$manifest | ConvertTo-Json | Out-File -FilePath (Join-Path $OutputPath "manifest.json") -Encoding UTF8

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Package prêt" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Emplacement : $OutputPath" -ForegroundColor Green
Write-Host "Taille      : $sizeMB Mo" -ForegroundColor Green
Write-Host ""
Write-Host "Prochaine étape : copiez ce dossier sur le PC cible, puis lancez INSTALLER.bat." -ForegroundColor Yellow
Write-Host ""