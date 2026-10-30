import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path

# Déterminer le répertoire de l'application
if getattr(sys, 'frozen', False):
    app_dir = Path(sys.executable).parent
else:
    app_dir = Path(__file__).parent.resolve()

backend_dir = app_dir / "backend"
venv_python = app_dir / ".venv" / "Scripts" / "python.exe"

# Vérifier les prérequis
if not venv_python.exists():
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Erreur",
        "Environnement virtuel non trouvé.\n\n"
        "Exécutez d'abord install.ps1"
    )
    sys.exit(1)

# Démarrer le serveur en arrière-plan
env = os.environ.copy()
env["TULIP_APP_MODE"] = "production"

process = subprocess.Popen(
    [str(venv_python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=str(backend_dir),
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
)

# Attendre que le serveur démarre
time.sleep(3)

# Ouvrir le navigateur
webbrowser.open("http://127.0.0.1:8000")

# Le script se termine, mais le serveur continue en arrière-plan
sys.exit(0)
