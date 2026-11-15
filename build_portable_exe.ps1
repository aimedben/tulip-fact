# Construit un exécutable portable (onedir) : pas de Python à installer sur le PC cible.
# Limitations importantes (à lire) :
# - Exclut torch/transformers/GOT-OCR2 (trop lourds à embarquer). OCR = RapidOCR/Tesseract.
# - Tesseract OCR est un programme EXTERNE : installez-le sur le PC cible, ou placez un dossier
#   "tesseract\" (contenant tesseract.exe) à côté de TulipFactures.exe. tessdata (fra/eng/osd) est embarqué.
# - RapidOCR/onnxruntime peut télécharger ses modèles ONNX dans le profil utilisateur au 1er lancement
#   (délai + Internet la première fois). Les DLL natives onnxruntime sont embarquées.
# - "Associer la base" : au lancement, bouton "Choisir le dossier de données / base" -> pointez vers le
#   dossier qui contient tulip_factures.db (et documents/), ou laissez le dossier data par défaut.

param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Environnement .venv introuvable. Exécutez install.ps1 d'abord." }

# Vérifier le frontend compilé
if (-not (Test-Path (Join-Path $root "backend\app\static\index.html"))) {
    throw "Frontend compilé absent (backend\app\static\index.html). Faites: cd frontend; npm run build"
}

# PyInstaller
& $venvPy -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) { & $venvPy -m pip install -r (Join-Path $root "requirements-build-exe.txt") }

$args = @("-m", "PyInstaller", (Join-Path $root "tulip_portable.spec"), "--noconfirm")
if ($Clean) { $args += "--clean" }

Write-Host "Construction de l'exécutable (plusieurs minutes)..." -ForegroundColor Yellow
& $venvPy @args
if ($LASTEXITCODE -ne 0) { throw "Échec PyInstaller (voir messages ci-dessus)." }

$dist = Join-Path $root "dist\TulipFactures"
if (-not (Test-Path (Join-Path $dist "TulipFactures.exe"))) { throw "Exécutable non produit." }

# Note d'usage à côté de l'exe
$note = @"
TULIP FACTURES — VERSION EXÉCUTABLE (portable)
==============================================
Double-cliquez TulipFactures.exe : le serveur démarre automatiquement
et le navigateur ouvre l'application (http://127.0.0.1:8000).
La petite fenêtre "Tulip Factures" doit rester ouverte pendant l'utilisation
(elle fait tourner le serveur ; "Arrêter le serveur" pour couper).

ASSOCIER VOTRE BASE / DONNÉES
- Si vous n'avez jamais associé de base, la base par défaut est utilisée
  (dossier "data" à côté de l'exe). Utilisez le bouton
  "Choisir le dossier / la base de données" pour pointer sur votre
  tulip_factures.db (il est possible de sélectionner directement le fichier .db).
- La base choisie est mémorisée (portable-config.ini) : aux lancements suivants,
  l'application s'ouvre directement dessus.

PRÉREQUIS RESTANTS (externes)
- Tesseract OCR (recommandé) : installez-le, ou placez un dossier "tesseract\" (avec tesseract.exe)
  à côté de TulipFactures.exe. Les fichiers de langue (tessdata) sont embarqués.
- Premier lancement OCR (RapidOCR) : peut télécharger des modèles ONNX (Internet requis une fois).

EN CAS DE PROBLÈME
- Si la page ne s'ouvre pas : regardez data\launcher-error.log à côté de l'exe
  (c'est le journal d'erreur de démarrage du serveur).
- Copiez TOUT le dossier (exe + _internal) — idéalement via le fichier ZIP unique.
"@
$note | Out-File -FilePath (Join-Path $dist "LISEZ-MOI-EXE.txt") -Encoding UTF8

$sizeMB = [math]::Round(((Get-ChildItem -Path $dist -Recurse -File | Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
Write-Host "OK -> $dist ($sizeMB Mo). Copiez TOUT ce dossier sur le PC cible." -ForegroundColor Green
