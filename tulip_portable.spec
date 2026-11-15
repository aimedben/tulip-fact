# -*- mode: python ; coding: utf-8 -*-
# Build PyInstaller (onedir) — serveur + UI embarqués, sans Python à installer sur le PC cible.
# Construire depuis la racine du projet avec le .venv actif :
#   .\.venv\Scripts\python.exe -m PyInstaller tulip_portable.spec --noconfirm
# Limitations : pas de torch/GOT-OCR2 ; Tesseract reste un programme externe (installer ou placer à côté) ;
# RapidOCR télécharge ses modèles ONNX dans le profil utilisateur au premier lancement (délai + Internet une fois).

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
root = Path(SPECPATH)

datas = []
# UI compilée + tessdata embarqués
datas += [(str(root / 'backend' / 'app' / 'static'), 'backend/app/static')]
datas += [(str(root / 'tessdata'), 'tessdata')]
datas += [(str(root / '.env.example'), '.')]
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
