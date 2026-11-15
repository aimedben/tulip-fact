import os
import socket
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

firewall_script = app_dir / "autoriser-telephone.ps1"
if firewall_script.exists():
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(firewall_script)],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    )

def server_already_running():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        return sock.connect_ex(("127.0.0.1", 8000)) == 0
    finally:
        sock.close()

def lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()

def write_phone_qr():
    try:
        import segno
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        if not desktop.exists():
            desktop = Path.home()
        qr_path = desktop / "Tulip-acces-telephone.png"
        segno.make(f"http://{lan_ip()}:8000").save(str(qr_path), scale=8, border=2)
    except Exception:
        pass

# Démarrer le serveur en arrière-plan
if not server_already_running():
    env = os.environ.copy()
    env["TULIP_APP_MODE"] = "production"

    subprocess.Popen(
        [str(venv_python), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(backend_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    )

    # Attendre que le serveur démarre
    time.sleep(3)

# Générer le QR code d'accès téléphone
write_phone_qr()

# Ouvrir le navigateur
webbrowser.open("http://127.0.0.1:8000")

# Le script se termine, mais le serveur continue en arrière-plan
sys.exit(0)
