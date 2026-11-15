import io
import os
import socket
import subprocess
import sys

# Exécutable sans console (PyInstaller --windowed) : sys.stdout / sys.stderr
# valent None et le formateur de logs d'Uvicorn plante sur sys.stdout.isatty().
# On redirige vers un buffer vide — les erreurs restent visibles via launcher-error.log.
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import webbrowser


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class TulipLauncher:
    CONFIG_FILE = "portable-config.ini"

    def __init__(self, config_only: bool = False):
        self.config_only = config_only
        self.base_dir = _base_dir()
        # Charger .env AVANT toute détection : la configuration enregistrée
        # par la fenêtre « Connexion Tulip » doit primer sur l'auto-détection.
        try:
            from tulip_setup import load_env

            load_env(self.base_dir)
        except Exception:
            pass
        self.frozen = getattr(sys, "frozen", False)
        self.backend_dir = self.base_dir / "backend"
        self.venv_python = self.base_dir / ".venv" / "Scripts" / "python.exe"
        self.process = None
        self.server_thread = None
        self.running = False
        self.root = None
        # Mémorise la base associée : une seule sélection, rappelée à chaque lancement.
        cfg = self.base_dir / self.CONFIG_FILE
        if cfg.is_file() and not os.environ.get("TULIP_DATA_DIR"):
            try:
                saved = cfg.read_text(encoding="utf-8").strip().splitlines()
                for line in saved:
                    if line.lower().startswith("data_dir="):
                        value = line.split("=", 1)[1].strip()
                        if value and Path(value).is_dir():
                            os.environ["TULIP_DATA_DIR"] = value
                        break
            except Exception:
                pass

        # Aucun dossier configuré : chercher la base existante aux emplacements
        # usuels. L'application ne crée jamais de base — elle doit être reliée
        # à l'existante.
        if "TULIP_DATA_DIR" not in os.environ and self.frozen:
            db = self._search_existing_db()
            if db is not None:
                os.environ["TULIP_DATA_DIR"] = str(db.parent)
                self.save_data_dir(str(db.parent))

        # Relier l'application à la MÊME base que le logiciel Tulip (SUPERETTE.TFE)
        # afin que les modifications faites ici soient visibles dans Tulip/GCP.
        self.tulip_db, self.tulip_source = self.setup_tulip_link()

    def save_data_dir(self, path: str):
        try:
            (self.base_dir / self.CONFIG_FILE).write_text(f"data_dir={path}\n", encoding="utf-8")
        except Exception:
            pass

    # ---------- utilitaires ----------

    def lan_ip(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            sock.close()

    def data_dir(self) -> str:
        return os.environ.get("TULIP_DATA_DIR") or str(self.base_dir / "data")

    def db_path(self) -> Path:
        return Path(self.data_dir()) / "tulip_factures.db"

    def _locate_tulip_kit(self):
        """Trouve la base du logiciel Tulip (SUPERETTE.TFE) : registre du kit, puis scan des disques."""
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\TH\TFZ") as k:
                pth, _ = winreg.QueryValueEx(k, "Pth")
            cand = Path(str(pth).strip().strip('"'))
            if (cand / "SUPERETTE.TFE").is_file():
                return cand
        except Exception:
            pass
        import string
        for letter in string.ascii_uppercase:
            if not os.path.exists(f"{letter}:\\" ):
                continue
            for sub in (r"zjob\tulip", r"tulip", r"TULIP_KIT\tulip"):
                cand = Path(f"{letter}:\\") / sub
                if (cand / "SUPERETTE.TFE").is_file():
                    return cand
        return None

    def setup_tulip_link(self):
        """Relie l'application à la MÊME base que le logiciel Tulip (SUPERETTE.TFE).

        Les modifications faites ici apparaissent directement dans Tulip/GCP.
        Ne fait rien si les réglages Firebird sont déjà définis (.env ou variable).
        """
        if os.environ.get("TULIP_FB_DATABASE"):
            return Path(os.environ["TULIP_FB_DATABASE"]), "configuration enregistrée (.env)"
        tulip_dir = self._locate_tulip_kit()
        if tulip_dir is None:
            return None, ""
        db = tulip_dir / "SUPERETTE.TFE"
        isql = tulip_dir.parent / "firebird_2_5" / "bin" / "isql.exe"
        os.environ["TULIP_FB_ENABLED"] = "true"
        # L'écriture reste désactivée par défaut : l'auto-détection ne doit
        # jamais l'autoriser à la place de l'utilisateur.
        os.environ.setdefault("TULIP_FB_WRITE_ENABLED", "false")
        os.environ["TULIP_FB_DATABASE"] = str(db)
        os.environ.setdefault("TULIP_FB_USER", "SYSDBA")
        os.environ.setdefault("TULIP_FB_PASSWORD", "masterkey")
        if isql.is_file():
            os.environ["TULIP_FB_ISQL_PATH"] = str(isql)
            os.environ["TULIP_FB_HOME"] = str(isql.parent.parent)
        return db, "détection automatique du kit Tulip"

    def _search_existing_db(self):
        """Cherche une base existante aux emplacements usuels — ne crée jamais de base."""
        home = Path.home()
        onedrive = os.environ.get("OneDrive")
        roots = [
            self.base_dir,
            self.base_dir / "data",
            home / "Documents",
            home / "Desktop",
        ]
        if onedrive:
            roots += [Path(onedrive) / "Documents", Path(onedrive) / "Desktop"]
        for root in roots:
            db = root / "tulip_factures.db"
            if db.is_file():
                return db
        return None

    def check_requirements(self):
        if self.frozen:
            return True, ""
        issues = []
        if not self.venv_python.exists():
            issues.append("Environnement virtuel Python non trouvé.\nExécutez INSTALLER.bat d'abord.")
        if not self.backend_dir.exists():
            issues.append("Dossier backend introuvable.")
        if issues:
            return False, "\n\n".join(issues)
        return True, ""

    def server_already_running(self, port=8000):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        finally:
            sock.close()

    # ---------- sélection base / données ----------

    def choose_data_dir(self):
        """Choisir le dossier de données OU directement le fichier .db."""
        current = self.data_dir()
        chosen = filedialog.askdirectory(
            title="Choisir le dossier qui contient tulip_factures.db — Annuler pour le dossier par défaut",
            initialdir=current if os.path.isdir(current) else str(self.base_dir),
        )
        if chosen:
            db = Path(chosen) / "tulip_factures.db"
            if not db.is_file():
                # Autoriser de pointer directement sur le fichier .db d'un autre dossier
                picked = filedialog.askopenfilename(
                    title="Aucun tulip_factures.db ici — sélectionnez tulip_factures.db (ou Annulez)",
                    initialdir=str(Path(chosen)),
                    filetypes=[("Base Tulip Factures", "tulip_factures.db"), ("Tous fichiers", "*.*")],
                )
                if picked:
                    chosen_dir = str(Path(picked).resolve().parent)
                    os.environ["TULIP_DATA_DIR"] = chosen_dir
                    self.save_data_dir(chosen_dir)
                    return self.data_dir()
            os.environ["TULIP_DATA_DIR"] = chosen
            self.save_data_dir(chosen)
        return self.data_dir()

    # ---------- démarrage serveur ----------

    def _log_startup_error(self, message: str) -> str:
        log_dir = Path(self.data_dir())
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "launcher-error.log"
            log_file.write_text(message, encoding="utf-8")
            return str(log_file)
        except Exception:
            return message

    def _open_browser(self, url: str) -> None:
        """Ouvre l'interface : Firefox portable embarqué si présent, sinon navigateur par défaut.

        PC cible hors connexion et sans installation : IE11 ne sait pas afficher
        l'interface React. Le dossier ``navigateur`` contient donc un Firefox ESR
        complet, utilisé avec son propre profil pour ne pas toucher au Firefox
        éventuellement installé sur la machine.
        """
        firefox = self.base_dir / "navigateur" / "firefox.exe"
        if firefox.is_file():
            profile = self.base_dir / "navigateur" / "profil"
            try:
                profile.mkdir(parents=True, exist_ok=True)
                user_js = profile / "user.js"
                if not user_js.is_file():
                    user_js.write_text(
                        "\n".join(
                            [
                                'user_pref("app.update.enabled", false);',
                                'user_pref("app.update.auto", false);',
                                'user_pref("app.update.service.enabled", false);',
                                'user_pref("toolkit.telemetry.enabled", false);',
                                'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
                                'user_pref("datareporting.healthreport.uploadEnabled", false);',
                                'user_pref("network.captive-portal-service.enabled", false);',
                                'user_pref("network.connectivity-service.enabled", false);',
                                'user_pref("browser.shell.checkDefaultBrowser", false);',
                                'user_pref("browser.aboutwelcome.enabled", false);',
                                'user_pref("browser.startup.page", 0);',
                                'user_pref("browser.sessionstore.resume_from_crash", false);',
                                'user_pref("browser.tabs.warnOnClose", false);',
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.Popen(
                    [str(firefox), "-no-remote", "-profile", str(profile), url],
                    cwd=str(firefox.parent),
                    creationflags=flags,
                )
                return
            except Exception:
                pass
        webbrowser.open(url)

    def start_server(self):
        if self.server_already_running():
            self._open_browser("http://127.0.0.1:8000")
            return True

        os.environ.setdefault("TULIP_APP_MODE", "production")

        # Relier l'app à la base du logiciel Tulip (détection + variables Firebird)
        try:
            self.setup_tulip_link()
        except Exception:
            pass
        # Le serveur Firebird du kit doit tourner pour que la connexion marche,
        # même si le logiciel Tulip/GCP n'a pas encore été lancé aujourd'hui.
        try:
            self._ensure_firebird_running()
        except Exception:
            pass

        if self.frozen:
            self._start_inprocess()
        else:
            self._start_subprocess()
        self.running = True

        # Attendre que le port réponde (max ~15 s)
        came_up = False
        for _ in range(60):
            time.sleep(0.25)
            if self.server_already_running():
                came_up = True
                break
        if came_up:
            self._open_browser("http://127.0.0.1:8000")
        return came_up

    def _ensure_firebird_running(self):
        """Démarre le serveur Firebird du kit s'il ne tourne pas déjà (port 3050)."""
        home = os.environ.get("TULIP_FB_HOME")
        if not home:
            return
        fbserver = Path(home) / "bin" / "fbserver.exe"
        if not fbserver.is_file():
            return
        if self.server_already_running(3050):
            return
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen([str(fbserver), "-a"], cwd=str(fbserver.parent), creationflags=flags)
        # Firebird met quelques secondes à ouvrir le port
        for _ in range(20):
            time.sleep(0.5)
            if self.server_already_running(3050):
                break

    def _start_inprocess(self):
        # En mode figé, le backend est packagé : lance uvicorn dans ce process.
        for path in (str(self.base_dir), str(self.base_dir / "backend")):
            if path not in sys.path:
                sys.path.insert(0, path)
        # Neutralise pymupdf.layout (module optionnel lourd, ~49 Mo, jamais utilisé ;
        # son absence est gérée proprement par PyMuPDF via try/except ImportError).
        sys.modules.setdefault("pymupdf.layout", None)

        def run():
            try:
                import uvicorn
                # host 0.0.0.0 pour l'accès LAN ; l'UI locale reste 127.0.0.1
                uvicorn.run("app.main:app", host="0.0.0.0", port=8000, log_level="info")
            except Exception:
                err = traceback.format_exc()
                where = self._log_startup_error(err)
                self._notify_startup_error(f"Le serveur n'a pas démarré.\nDétail enregistré dans :\n{where}\n\n{err[-800:]}")

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

    def _start_subprocess(self):
        import subprocess
        env = os.environ.copy()
        cmd = [str(self.venv_python), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
        self.process = subprocess.Popen(
            cmd,
            cwd=str(self.backend_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    def _notify_startup_error(self, message: str):
        def show():
            try:
                messagebox.showerror("Tulip Factures", message)
            except Exception:
                pass
        self._after(show)

    def _after(self, fn):
        root = self.root
        if root is not None:
            try:
                root.after(0, fn)
            except Exception:
                pass

    # ---------- interface ----------

    def create_gui(self):
        root = tk.Tk()
        self.root = root
        root.title("Tulip Factures")
        root.geometry("480x440")
        root.resizable(False, False)
        root.eval("tk::PlaceWindow . center")

        frame = tk.Frame(root, padx=20, pady=16)
        frame.pack(expand=True, fill="both")

        tk.Label(frame, text="Tulip Factures", font=("Arial", 18, "bold"), fg="#2563eb").pack(pady=(0, 4))
        tk.Label(frame, text="Gestion des factures fournisseurs", font=("Arial", 10), fg="#666").pack(pady=(0, 6))
        tk.Label(frame, text=f"Téléphone (même Wi-Fi) : http://{self.lan_ip()}:8000", font=("Arial", 9), fg="#2563eb").pack(pady=(0, 6))

        self.data_label = tk.Label(
            frame,
            text=self._data_status_text(),
            font=("Arial", 8),
            fg="#555",
            wraplength=430,
            justify="left",
        )
        self.data_label.pack(pady=(0, 6))

        self.status_label = tk.Label(frame, text="", font=("Arial", 10, "bold"), fg="#0a7f2c")
        self.status_label.pack(pady=(2, 6))

        ok, error = self.check_requirements()
        if not ok:
            tk.Label(frame, text=error, fg="red", wraplength=400, justify="left").pack(pady=8)
            tk.Button(
                frame, text="Ouvrir le guide d'installation",
                command=lambda: os.startfile(str(self.base_dir / "INSTALLATION_PORTABLE.md")),
                bg="#ef4444", fg="white", font=("Arial", 10), padx=20, pady=8,
            ).pack(pady=8)
        else:
            tk.Button(
                frame, text="Choisir le dossier / la base de données",
                command=self._pick_data,
                bg="#e5e7eb", fg="#111827", font=("Arial", 9), padx=14, pady=6, cursor="hand2",
            ).pack(pady=(0, 4))
            self.tulip_btn = tk.Button(
                frame, text="Connexion Tulip…",
                command=self.open_tulip_setup,
                bg="#e5e7eb", fg="#111827", font=("Arial", 9), padx=14, pady=6, cursor="hand2",
            )
            self.tulip_btn.pack(pady=(0, 6))
            self.start_btn = tk.Button(
                frame, text="Démarrer l'application",
                command=lambda: self.on_start(),
                bg="#2563eb", fg="white", font=("Arial", 12, "bold"),
                padx=28, pady=12, cursor="hand2",
            )
            self.start_btn.pack(pady=4)
            self.stop_btn = tk.Button(
                frame, text="Arrêter le serveur",
                command=lambda: self.on_close(),
                bg="#e5e7eb", fg="#374151", padx=16, pady=5,
            )

        tk.Button(frame, text="Quitter", command=lambda: self.on_close(), bg="#e5e7eb", fg="#374151", padx=18, pady=5).pack(pady=(6, 0))
        tk.Label(root, text="Le navigateur s'ouvre sur http://127.0.0.1:8000 — laissez cette fenêtre ouverte pendant l'utilisation.",
                 font=("Arial", 8), fg="#999", wraplength=440, justify="center").pack(side="bottom", pady=8)

        # Si déjà lancé ailleurs, montrer directement l'état
        if self.server_already_running():
            self._mark_running(" déjà démarrée (autre instance)")

        # Fenêtre de configuration Tulip : bouton dédié, ouverture automatique
        # au premier lancement si rien n'est configuré ni détecté.
        # Une seule fenêtre doit être visible à l'écran : le lanceur se cache
        # tant que la configuration est ouverte (voir open_tulip_setup).
        configured = bool(os.environ.get("TULIP_FB_DATABASE")) or getattr(self, "tulip_db", None) is not None
        needs_setup = ok and not configured
        if self.config_only:
            root.withdraw()
            root.after(300, lambda: self.open_tulip_setup(exit_after=True))
        elif needs_setup:
            root.withdraw()
            root.after(300, lambda: self.open_tulip_setup(first_run=True))

        # Mode exécutable : ouverture directe - le serveur démarre automatiquement
        # et le navigateur ouvre l'application ; la fenêtre reste ouverte en
        # superviseur (la fermer = arrêter).
        if ok and self.frozen and not self.config_only and not needs_setup:
            root.after(400, self.on_start)

        root.protocol("WM_DELETE_WINDOW", lambda: self.on_close())
        root.mainloop()

    def _data_status_text(self):
        db = self.db_path()
        lines = []
        if db.is_file():
            lines.append(f"Base : {db}  (reliée ✓)")
        else:
            lines.append(
                f"Données : {self.data_dir()}\n"
                "Aucune tulip_factures.db reliée — l'application ne crée jamais de base.\n"
                "Cliquez « Choisir le dossier / la base de données » pour la localiser."
            )
        if getattr(self, "tulip_db", None):
            lines.append(f"Base Tulip (GCP) : {self.tulip_db}  ✓\nLes modifications sont partagées avec le logiciel Tulip.")
        else:
            lines.append("⚠ Kit Tulip (SUPERETTE.TFE) introuvable — lancez au moins une fois DEMARRER_TULIP.bat, ou utilisez les réglages de l'application.")
        return "\n\n".join(lines)

    def _pick_data(self):
        previous = self.data_dir()
        path = self.choose_data_dir()
        self.data_label.config(text=self._data_status_text())
        if path == previous and self.server_already_running():
            return
        if self.running:
            messagebox.showinfo(
                "Base modifiée",
                f"Le dossier de données pointe désormais sur :\n{self.data_dir()}\n\n"
                "Cliquez « Arrêter le serveur » puis « Démarrer » pour utiliser cette base.",
            )

    # ---------- configuration Tulip ----------

    def open_tulip_setup(self, exit_after: bool = False, first_run: bool = False):
        """Ouvre la configuration de la connexion Tulip, seule à l'écran."""
        try:
            import tulip_setup
        except Exception as exc:  # noqa: BLE001
            self._show_launcher()
            messagebox.showerror(
                "Connexion Tulip",
                f"Impossible d'ouvrir la configuration :\n{exc}",
            )
            return None

        # Une seule fenêtre à l'écran : on cache le lanceur le temps de la
        # configuration, il réapparaît à la fermeture (sauf en mode --config-tulip).
        if not exit_after:
            self._hide_launcher()

        def closed(saved: bool) -> None:
            # Mode --config-tulip : la configuration est la seule fenêtre,
            # on quitte enregistré ou non (sinon il resterait un processus
            # invisible sans aucune fenêtre).
            if exit_after:
                self.on_close()
                return
            self._show_launcher()
            # Premier lancement : la connexion étant enregistrée, on démarre
            # directement (sinon le marchand doit cliquer une deuxième fois).
            if first_run and saved and self.root is not None:
                self.root.after(200, self.on_start)

        dialog = tulip_setup.TulipSetupDialog(
            self.root,
            folder=self.base_dir,
            on_saved=self._on_tulip_saved,
            on_closed=closed,
        )
        self.setup_dialog = dialog
        return dialog

    def _hide_launcher(self) -> None:
        """Cache la fenêtre du lanceur (une seule fenêtre visible à la fois)."""
        if self.root is None:
            return
        try:
            self.root.withdraw()
            self.root.update_idletasks()
        except Exception:
            pass

    def _show_launcher(self) -> None:
        """Réaffiche la fenêtre du lanceur, au premier plan."""
        if self.root is None:
            return
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass

    def _on_tulip_saved(self, values: dict) -> None:
        database = values.get("TULIP_FB_DATABASE") or ""
        self.tulip_db = Path(database) if database else None
        self.tulip_source = "configuration enregistrée (.env)"
        try:
            self.data_label.config(text=self._data_status_text())
        except Exception:
            pass

    def _mark_running(self, suffix=""):
        if self.root is None:
            return
        try:
            self.status_label.config(text=f"Application en cours{suffix} — https://127.0.0.1:8000 disponible")
            if hasattr(self, "start_btn"):
                self.start_btn.config(state="disabled", text="Application en cours…")
            if hasattr(self, "stop_btn"):
                self.stop_btn.pack(pady=2)
        except Exception:
            pass

    def on_start(self):
        if self.running:
            return
        # Règle : ne JAMAIS créer de base. Si aucune tulip_factures.db n'est
        # reliée, exiger la sélection de l'existante avant de démarrer.
        if not self.db_path().is_file():
            go = messagebox.askyesno(
                "Base de données requise",
                "Aucune base n'est reliée à l'application.\n\n"
                "L'application ne crée JAMAIS de nouvelle base : il faut la "
                "relier à l'existante (tulip_factures.db) pour conserver "
                "vos factures.\n\nVoulez-vous la localiser maintenant ?",
            )
            if go:
                self.choose_data_dir()
                self.data_label.config(text=self._data_status_text())
            if not self.db_path().is_file():
                messagebox.showwarning(
                    "Démarrage annulé",
                    "Aucune base tulip_factures.db n'a été sélectionnée.\n\n"
                    "Le serveur n'a pas été démarré. Placez la base existante "
                    "à côté du programme ou dans son dossier « data » puis relancez.",
                )
                return
        try:
            came_up = self.start_server()
        except Exception as e:
            where = self._log_startup_error(traceback.format_exc())
            messagebox.showerror("Erreur", f"Impossible de démarrer :\n\n{e}\n\nDétail : {where}")
            return
        if not came_up:
            import time as _t
            # Redonner une chance (imports lourds onnxruntime peuvent tarder)
            for _ in range(20):
                _t.sleep(0.25)
                if self.server_already_running():
                    came_up = True
                    break
        if not came_up:
            self.running = False
            import time as _t
            where = Path(self.data_dir()) / "launcher-error.log"
            try:
                self.status_label.config(text="Échec du démarrage du serveur", fg="#b91c1c")
            except Exception:
                pass
            self._notify_startup_error(
                f"Le serveur n'écoute pas sur le port 8000 après démarrage.\n\n"
                f"Motif exact (si enregistré) : {where}\n"
                f"Ouvrez ce fichier et communiquez son contenu pour diagnostic."
            )
            return
        self._mark_running()
        self.root.deiconify()

    def on_close(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        try:
            if self.root is not None:
                self.root.quit()
                self.root.destroy()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    TulipLauncher(config_only="--config-tulip" in sys.argv[1:]).create_gui()
