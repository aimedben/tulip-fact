# Script de préparation du package portable pour clé USB
# Ce script prépare une version prête à copier sur clé USB

param(
    [string]$OutputPath = "C:\TulipFactures-Portable"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Préparation Package Portable" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$SourcePath = $PSScriptRoot

# Créer le dossier de sortie
Write-Host "Création du dossier de package : $OutputPath" -ForegroundColor Yellow
if (Test-Path $OutputPath) {
    Write-Host "Le dossier existe déjà. Suppression..." -ForegroundColor Yellow
    Remove-Item -Path $OutputPath -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null

# Liste des fichiers/dossiers à copier
$itemsToCopy = @(
    "backend",
    "frontend",
    "docs",
    "examples",
    "scripts",
    "tessdata",
    ".env.example",
    ".gitignore",
    "README.md",
    "INSTALLATION_PORTABLE.md",
    "install.ps1"
)

Write-Host ""
Write-Host "Copie des fichiers..." -ForegroundColor Yellow

foreach ($item in $itemsToCopy) {
    $sourcePath = Join-Path $SourcePath $item
    if (Test-Path $sourcePath) {
        Write-Host "  Copie : $item" -ForegroundColor Gray
        Copy-Item -Path $sourcePath -Destination $OutputPath -Recurse -Force
    }
}

# Nettoyer les fichiers inutiles
Write-Host ""
Write-Host "Nettoyage des fichiers inutiles..." -ForegroundColor Yellow

$cleanupPatterns = @(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "data",
    ".git"
)

foreach ($pattern in $cleanupPatterns) {
    $items = Get-ChildItem -Path $OutputPath -Recurse -Include $pattern -Force -ErrorAction SilentlyContinue
    foreach ($item in $items) {
        Write-Host "  Suppression : $($item.FullName)" -ForegroundColor DarkGray
        Remove-Item -Path $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Créer le fichier README pour la clé USB
$usbReadme = @"
# Tulip Factures - Installation Portable

Ce dossier contient l'application Tulip Factures prête à être installée sur n'importe quel PC Windows.

## Installation Rapide

1. Copiez ce dossier sur le PC cible
2. Ouvrez PowerShell en tant qu'administrateur
3. Naviguez vers ce dossier
4. Exécutez : ``.\install.ps1``

## Prérequis

- Windows 10/11
- Python 3.12 ou supérieur (https://www.python.org/downloads/)
- Tesseract OCR 5.x (https://github.com/UB-Mannheim/tesseract/wiki)
  - Installer avec les langues française et anglaise

## Documentation

- **INSTALLATION_PORTABLE.md** : Guide complet d'installation
- **README.md** : Documentation de l'application
- **docs/** : Documentation technique

## Support

Pour toute question, consultez la documentation ou contactez l'administrateur système.

---
Version préparée le : $(Get-Date -Format "yyyy-MM-dd HH:mm")
"@

$usbReadme | Out-File -FilePath "$OutputPath\LISEZ-MOI.txt" -Encoding UTF8

# Créer un fichier de vérification
$manifest = @{
    version = "1.0.0"
    created = Get-Date -Format "o"
    contents = $itemsToCopy
    readme = "LISEZ-MOI.txt"
    install_script = "install.ps1"
}

$manifest | ConvertTo-Json | Out-File -FilePath "$OutputPath\manifest.json" -Encoding UTF8

# Calculer la taille totale
$totalSize = (Get-ChildItem -Path $OutputPath -Recurse -File | Measure-Object -Property Length -Sum).Sum
$sizeMB = [math]::Round($totalSize / 1MB, 2)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Package prêt !" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Emplacement : $OutputPath" -ForegroundColor Green
Write-Host "Taille totale : $sizeMB MB" -ForegroundColor Green
Write-Host ""
Write-Host "Instructions :" -ForegroundColor Yellow
Write-Host "1. Copiez le dossier complet sur une clé USB (minimum 2 GB)" -ForegroundColor White
Write-Host "2. Sur le PC cible, exécutez install.ps1" -ForegroundColor White
Write-Host "3. Consultez INSTALLATION_PORTABLE.md pour les détails" -ForegroundColor White
Write-Host ""
Write-Host "Fichiers inclus :" -ForegroundColor Yellow
Get-ChildItem -Path $OutputPath -Directory | ForEach-Object {
    Write-Host "  - $($_.Name)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "Le package est prêt à être copié sur clé USB !" -ForegroundColor Green
Write-Host ""
