# -*- mode: python ; coding: utf-8 -*-
# Build PyInstaller (onedir) — serveur + UI embarqués, sans Python à installer sur le PC cible.
# Construire depuis la racine du projet avec le .venv actif :
#   .\.venv\Scripts\python.exe -m PyInstaller tulip_portable.spec --noconfirm
# Limitations : pas de torch/GOT-OCR2 ; l'OCR hors ligne est RapidOCR (modèles ONNX embarqués).
# Le client Firebird 2.5 et l'UCRT « downlevel » sont embarqués pour Windows 7.

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
root = Path(SPECPATH)

datas = []
# UI compilée + tessdata embarqués
datas += [(str(root / 'backend' / 'app' / 'static'), 'backend/app/static')]
datas += [(str(root / 'tessdata'), 'tessdata')]
datas += [(str(root / '.env.example'), '.')]
# Documentation et scripts livrés à côté de l'exe (aucune installation requise).
for _doc in ('INSTALLATION_PORTABLE.md', '2-LISEZ-MOI-SUPERETTE.txt',
             '3-DIAGNOSTIC-WIN7.bat', '.env.portable'):
    if (root / _doc).is_file():
        datas += [(str(root / _doc), '.')]
# Client Firebird embarqué (isql + fbclient + assembly VC80 privée) : permet de
# joindre la base Tulip sans installer Firebird sur le PC cible.
if (root / 'vendor' / 'firebird').is_dir():
    datas += [(str(root / 'vendor' / 'firebird'), 'firebird')]
# UCRT « downlevel » (ucrtbase.dll + shims api-ms-win-*) : Windows 7 SP1 sans
# KB2999226 ne fournit pas le runtime C universel exigé par Python 3.8.
if (root / 'vendor' / 'ucrt32').is_dir():
    for _ucrt in sorted((root / 'vendor' / 'ucrt32').glob('*.dll')):
        datas += [(str(_ucrt), '.')]
# migrations (optionnelles ; init_db retombe sur create_all si absentes)
if (root / 'backend' / 'migrations').is_dir():
    datas += [(str(root / 'backend' / 'migrations'), 'backend/migrations')]
if (root / 'backend' / 'alembic.ini').is_file():
    datas += [(str(root / 'backend' / 'alembic.ini'), 'backend')]

# Paquets natifs / données de modèles rapides
for pkg in ('rapidocr', 'rapidocr_onnxruntime', 'onnxruntime'):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

hiddenimports = []
for mod in (
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols',
    'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on',
    'sqlalchemy.dialects.sqlite', 'multipart', 'python_multipart',
    'PIL', 'fitz', 'rapidocr', 'rapidocr_onnxruntime', 'openpyxl',
    'tulip_setup',
    'app', 'app.main', 'app.config', 'app.database',
):
    hiddenimports.append(mod)
for pkg in ('app.api', 'app.models', 'app.services'):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

a = Analysis(
    [str(root / 'launcher.py')],
    pathex=[str(root), str(root / 'backend')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'accelerate', 'sentencepiece', 'einops', 'timm', 'tiktoken', 'verovio', 'huggingface_hub', 'pymupdf.layout'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
# Économie de taille : la DLL vidéo ffmpeg d'OpenCV n'est jamais utilisée
# (aucun VideoCapture/VideoWriter dans l'application).
a.binaries = [b for b in a.binaries if 'opencv_videoio_ffmpeg' not in b[0]]
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TulipFactures',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=[str(root / 'assets' / 'tulip-factures.ico')],
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TulipFactures',
)

# --- Compatibilité Windows 7 ---
# La DLL MSVCP140 collectée automatiquement vient du runtime installé sur la
# machine de build ; à partir des versions 14.4x/14.5x elle importe
# GetSystemTimePreciseAsFileTime, absent de Windows 7 => l'application ne
# démarre pas. On force la version 14.30 (signée Microsoft, compatible
# Windows 7 SP1, tous les symboles utilisés par fitz/onnxruntime/pyclipper
# sont présents).
_win7_crt = root / 'vendor' / 'win7' / 'msvcp140.dll'
if _win7_crt.is_file():
    import shutil
    shutil.copy2(str(_win7_crt), str(Path(DISTPATH) / 'TulipFactures' / 'MSVCP140.dll'))
