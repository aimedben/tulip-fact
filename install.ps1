# Script d'installation automatique de Tulip Factures
# Usage : .\install.ps1 [-Portable] [-InstallPath "C:\chemin\installation"]

param(
    [switch]$Portable = $false,
    [string]$InstallPath = ""
)

$ErrorActionPreference = "Stop"

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Installation Tulip Factures" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Déterminer le chemin d'installation
if ($InstallPath -eq "") {
    if ($Portable) {
        $InstallPath = $PSScriptRoot
        Write-Host "Mode portable : installation dans $InstallPath" -ForegroundColor Yellow
    } else {
        $InstallPath = "C:\TulipFactures"
        Write-Host "Mode standard : installation dans $InstallPath" -ForegroundColor Green
    }
} else {
    Write-Host "Installation dans : $InstallPath" -ForegroundColor Green
}

# Créer le répertoire d'installation si nécessaire
if (-not $Portable -and $PSScriptRoot -ne $InstallPath) {
    if (-not (Test-Path $InstallPath)) {
        Write-Host "Création du répertoire d'installation..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    }

    Write-Host "Copie des fichiers..." -ForegroundColor Yellow
    Copy-Item -Path "$PSScriptRoot\*" -Destination $InstallPath -Recurse -Force -Exclude @(".git", ".venv", "node_modules", "data", "__pycache__", "*.pyc")
    Set-Location $InstallPath
}

# Vérifier Python
Write-Host ""
Write-Host "Vérification de Python..." -ForegroundColor Yellow
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "✓ Python détecté : $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python 3.12+ requis mais non détecté." -ForegroundColor Red
    Write-Host "Téléchargez Python depuis https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Vérifier Tesseract
Write-Host ""
Write-Host "Vérification de Tesseract OCR..." -ForegroundColor Yellow
$tesseractPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
if (Test-Path $tesseractPath) {
    Write-Host "✓ Tesseract détecté : $tesseractPath" -ForegroundColor Green
} else {
    Write-Host "✗ Tesseract OCR non détecté à l'emplacement par défaut" -ForegroundColor Yellow
    Write-Host "  Téléchargez Tesseract depuis https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
    Write-Host "  Installez avec les langues française et anglaise" -ForegroundColor Yellow
}

# Créer l'environnement virtuel
Write-Host ""
Write-Host "Création de l'environnement virtuel Python..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "L'environnement virtuel existe déjà" -ForegroundColor Yellow
} else {
    & python -m venv .venv
    Write-Host "✓ Environnement virtuel créé" -ForegroundColor Green
}

# Activer l'environnement virtuel
Write-Host ""
Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Installer les dépendances Python
Write-Host ""
Write-Host "Installation des dépendances Python..." -ForegroundColor Yellow
& python -m pip install --upgrade pip --quiet
& pip install -r backend\requirements.txt --quiet
Write-Host "✓ Dépendances Python installées" -ForegroundColor Green

# Créer le fichier .env s'il n'existe pas
Write-Host ""
Write-Host "Configuration de l'environnement..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "✓ Fichier .env créé (à personnaliser)" -ForegroundColor Green
} else {
    Write-Host "Fichier .env existant conservé" -ForegroundColor Yellow
}

# Créer les raccourcis
Write-Host ""
Write-Host "Création des raccourcis..." -ForegroundColor Yellow

# Script de démarrage
$startScript = @"
`$env:TULIP_APP_MODE = "production"
Set-Location "$InstallPath\backend"
& "$InstallPath\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"@
$startScript | Out-File -FilePath "$InstallPath\demarrer.ps1" -Encoding UTF8

# Script de démarrage DEMO
$demoScript = @"
`$env:TULIP_APP_MODE = "demo"
Set-Location "$InstallPath\backend"
& "$InstallPath\.venv\Scripts\python.exe" -m app.demo
& "$InstallPath\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"@
$demoScript | Out-File -FilePath "$InstallPath\demarrer-demo.ps1" -Encoding UTF8

# Raccourci Bureau (production)
$WScriptShell = New-Object -ComObject WScript.Shell
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcut = $WScriptShell.CreateShortcut("$desktopPath\Tulip Factures.lnk")
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoExit -ExecutionPolicy Bypass -File `"$InstallPath\demarrer.ps1`""
$shortcut.WorkingDirectory = "$InstallPath\backend"
$shortcut.IconLocation = "shell32.dll,165"
$shortcut.Save()

Write-Host "✓ Raccourci créé sur le Bureau" -ForegroundColor Green

# Créer la structure de données
Write-Host ""
Write-Host "Création de la structure de données..." -ForegroundColor Yellow
$dataDirs = @("data", "data\documents", "data\pages", "data\exports", "data\backups", "data\logs", "data\archives")
foreach ($dir in $dataDirs) {
    $fullPath = Join-Path $InstallPath $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
}
Write-Host "✓ Structure de données créée" -ForegroundColor Green

# Instructions finales
Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Installation terminée !" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour démarrer l'application :" -ForegroundColor Yellow
Write-Host "  1. Double-cliquez sur le raccourci 'Tulip Factures' sur le Bureau" -ForegroundColor White
Write-Host "  OU" -ForegroundColor Yellow
Write-Host "  2. Exécutez : .\demarrer.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Mode DEMO (données isolées) :" -ForegroundColor Yellow
Write-Host "  Exécutez : .\demarrer-demo.ps1" -ForegroundColor White
Write-Host ""
Write-Host "L'application sera accessible sur : http://127.0.0.1:8000" -ForegroundColor Green
Write-Host ""
Write-Host "Documentation : README.md" -ForegroundColor Yellow
Write-Host "Configuration : .env (à personnaliser selon votre environnement)" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $tesseractPath)) {
    Write-Host "ATTENTION : Tesseract OCR n'est pas installé !" -ForegroundColor Red
    Write-Host "L'OCR ne fonctionnera pas sans Tesseract." -ForegroundColor Red
    Write-Host ""
}

Write-Host "Appuyez sur Entrée pour continuer..."
Read-Host
