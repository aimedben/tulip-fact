import os
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

    def check_requirements(self):
        issues = []
        if not self.venv_python.exists():
            issues.append("Environnement virtuel Python non trouve.\nExecutez install.ps1 d'abord.")
        if not self.backend_dir.exists():
            issues.append("Dossier backend introuvable.")
        if issues:
            return False, "\n\n".join(issues)
        return True, ""

    def start_server(self):
        env = os.environ.copy()
        env["TULIP_APP_MODE"] = "production"

        cmd = [str(self.venv_python), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

        self.process = subprocess.Popen(cmd, cwd=str(self.backend_dir), env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        time.sleep(3)
        webbrowser.open("http://127.0.0.1:8000")

    def create_gui(self):
        root = tk.Tk()
        root.title("Tulip Factures")
        root.geometry("400x250")
        root.resizable(False, False)
        root.eval('tk::PlaceWindow . center')

        frame = tk.Frame(root, padx=20, pady=20)
        frame.pack(expand=True, fill='both')

        title = tk.Label(frame, text="Tulip Factures", font=("Arial", 18, "bold"), fg="#2563eb")
        title.pack(pady=(0, 10))

        subtitle = tk.Label(frame, text="Gestion des factures fournisseurs", font=("Arial", 10), fg="#666")
        subtitle.pack(pady=(0, 20))

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
                                 command=lambda: self.on_start(root),
                                 bg="#2563eb", fg="white", font=("Arial", 12, "bold"),
                                 padx=30, pady=15, cursor="hand2")
            start_btn.pack(pady=10)

        quit_btn = tk.Button(frame, text="Quitter", command=root.quit,
                            bg="#e5e7eb", fg="#374151", font=("Arial", 9),
                            padx=20, pady=8, cursor="hand2")
        quit_btn.pack(pady=(10, 0))

        info = tk.Label(root, text="L'application s'ouvrira dans votre navigateur",
                       font=("Arial", 8), fg="#999")
        info.pack(side='bottom', pady=10)

        root.protocol("WM_DELETE_WINDOW", lambda: self.on_close(root))
        root.mainloop()

    def on_start(self, root):
        root.withdraw()
        try:
            self.start_server()
            messagebox.showinfo("Application demarree",
                              f"Tulip Factures demarree.\n\n"
                              f"URL: http://127.0.0.1:8000\n\n"
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
