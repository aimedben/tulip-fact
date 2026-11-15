# Script pour creer un executable launcher Windows
# Usage: .\creer-executable.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Creation de l'executable Tulip Factures" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$SourcePath = $PSScriptRoot

# 1. Creer le script launcher Python
Write-Host "Creation du script launcher..." -ForegroundColor Yellow

$launcherScript = @'
import os
import socket
import sys
import subprocess
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import webbrowser
import time

class TulipLauncher:
    def __init__(self):
        self.app_dir = Path(__file__).parent.resolve()
        self.backend_dir = self.app_dir / "backend"
        self.venv_python = self.app_dir / ".venv" / "Scripts" / "python.exe"
        self.process = None

    def lan_ip(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            sock.close()

    def check_requirements(self):
        issues = []
        if not self.venv_python.exists():
            issues.append("Environnement virtuel Python non trouve.\nExecutez install.ps1 d'abord.")
        if not self.backend_dir.exists():
            issues.append("Dossier backend introuvable.")
        if issues:
            return False, "\n\n".join(issues)
        return True, ""

    def ensure_firewall(self):
        script = self.app_dir / "autoriser-telephone.ps1"
        if not script.exists():
            return
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except OSError:
            pass

    def server_already_running(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            return sock.connect_ex(("127.0.0.1", 8000)) == 0
        finally:
            sock.close()

    def start_server(self, demo=False):
        self.ensure_firewall()
        if self.server_already_running():
            webbrowser.open("http://127.0.0.1:8000")
            return

        env = os.environ.copy()
        env["TULIP_APP_MODE"] = "demo" if demo else "production"

        if demo:
            subprocess.run([str(self.venv_python), "-m", "app.demo"], cwd=str(self.backend_dir), env=env)

        cmd = [str(self.venv_python), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

        self.process = subprocess.Popen(cmd, cwd=str(self.backend_dir), env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        time.sleep(3)
        webbrowser.open("http://127.0.0.1:8000")

    def create_gui(self):
        root = tk.Tk()
        root.title("Tulip Factures")
        root.geometry("420x300")
        root.resizable(False, False)
        root.eval('tk::PlaceWindow . center')

        frame = tk.Frame(root, padx=20, pady=20)
        frame.pack(expand=True, fill='both')

        title = tk.Label(frame, text="Tulip Factures", font=("Arial", 18, "bold"), fg="#2563eb")
        title.pack(pady=(0, 10))

        subtitle = tk.Label(frame, text="Gestion des factures fournisseurs", font=("Arial", 10), fg="#666")
        subtitle.pack(pady=(0, 10))

        phone = tk.Label(frame, text=f"Telephone : http://{self.lan_ip()}:8000", font=("Arial", 9), fg="#2563eb")
        phone.pack(pady=(0, 10))

        ok, error = self.check_requirements()

        if not ok:
            error_label = tk.Label(frame, text=error, fg="red", wraplength=350, justify="left")
            error_label.pack(pady=10)
            install_btn = tk.Button(frame, text="Ouvrir le guide d'installation",
                                   command=lambda: os.startfile(str(self.app_dir / "INSTALLATION_PORTABLE.md")),
                                   bg="#ef4444", fg="white", font=("Arial", 10), padx=20, pady=10)
            install_btn.pack(pady=10)
        else:
            start_btn = tk.Button(frame, text="Demarrer l'application",
                                 command=lambda: self.on_start(root, False),
                                 bg="#2563eb", fg="white", font=("Arial", 12, "bold"),
                                 padx=30, pady=15, cursor="hand2")
            start_btn.pack(pady=10)

            demo_btn = tk.Button(frame, text="Mode DEMO (donnees isolees)",
                                command=lambda: self.on_start(root, True),
                                bg="#f59e0b", fg="white", font=("Arial", 10),
                                padx=20, pady=10, cursor="hand2")
            demo_btn.pack(pady=5)

        quit_btn = tk.Button(frame, text="Quitter", command=root.quit,
                            bg="#e5e7eb", fg="#374151", font=("Arial", 9),
                            padx=20, pady=8, cursor="hand2")
        quit_btn.pack(pady=(10, 0))

        info = tk.Label(root, text="L'application s'ouvrira dans votre navigateur",
                       font=("Arial", 8), fg="#999")
        info.pack(side='bottom', pady=10)

        root.protocol("WM_DELETE_WINDOW", lambda: self.on_close(root))
        root.mainloop()

    def on_start(self, root, demo):
        root.withdraw()
        try:
            self.start_server(demo)
            mode = "DEMO" if demo else "production"
            messagebox.showinfo("Application demarree",
                              f"Tulip Factures demarree en mode {mode}.\n\n"
                              f"PC : http://127.0.0.1:8000\n"
                              f"Telephone : http://{self.lan_ip()}:8000\n\n"
                              f"Fermez cette fenetre pour arreter.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de demarrer:\n\n{e}")
        finally:
            self.on_close(root)

    def on_close(self, root):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                self.process.kill()
        root.quit()
        root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    launcher = TulipLauncher()
    launcher.create_gui()
'@

$launcherPath = Join-Path $SourcePath "launcher.py"
$launcherScript | Out-File -FilePath $launcherPath -Encoding UTF8
Write-Host "OK Script launcher.py cree" -ForegroundColor Green

# 2. Verifier/Installer PyInstaller
Write-Host ""
Write-Host "Verification de PyInstaller..." -ForegroundColor Yellow

$venvPython = Join-Path $SourcePath ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERREUR: Environnement virtuel non trouve." -ForegroundColor Red
    Write-Host "Executez d'abord: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

$pyinstallerCheck = & $venvPython -c "import PyInstaller" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installation de PyInstaller..." -ForegroundColor Yellow
    & $venvPython -m pip install pyinstaller --quiet
    Write-Host "OK PyInstaller installe" -ForegroundColor Green
} else {
    Write-Host "OK PyInstaller detecte" -ForegroundColor Green
}

# 3. Compiler l'executable
Write-Host ""
Write-Host "Compilation de l'executable (peut prendre 2-3 minutes)..." -ForegroundColor Yellow

& $venvPython -m PyInstaller --name TulipFactures --onefile --windowed --clean launcher.py

$exePath = Join-Path $SourcePath "dist\TulipFactures.exe"

if (Test-Path $exePath) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Executable cree avec succes !" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Emplacement: $exePath" -ForegroundColor Green

    $size = (Get-Item $exePath).Length / 1MB
    Write-Host "Taille: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan

    # Copier dans le dossier portable
    $portablePath = "C:\Users\Thinkpad\Desktop\TulipFactures-Portable"
    if (Test-Path $portablePath) {
        Copy-Item $exePath -Destination (Join-Path $portablePath "TulipFactures.exe") -Force
        Write-Host ""
        Write-Host "OK Copie dans le package portable" -ForegroundColor Green
    }

    # Creer raccourci Bureau
    Write-Host ""
    Write-Host "Creation du raccourci Bureau..." -ForegroundColor Yellow
    $WScriptShell = New-Object -ComObject WScript.Shell
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $shortcut = $WScriptShell.CreateShortcut("$desktopPath\Tulip Factures.lnk")
    $shortcut.TargetPath = $exePath
    $shortcut.WorkingDirectory = $SourcePath
    $shortcut.Description = "Tulip Factures - Gestion des factures fournisseurs"
    $shortcut.Save()
    Write-Host "OK Raccourci cree" -ForegroundColor Green

    Write-Host ""
    Write-Host "Pour lancer l'application:" -ForegroundColor Yellow
    Write-Host "  - Double-cliquez sur TulipFactures.exe" -ForegroundColor White
    Write-Host "  - OU utilisez le raccourci du Bureau" -ForegroundColor White
    Write-Host ""

} else {
    Write-Host ""
    Write-Host "ERREUR: Echec de la compilation" -ForegroundColor Red
    Write-Host "Verifiez les erreurs ci-dessus" -ForegroundColor Yellow
}
