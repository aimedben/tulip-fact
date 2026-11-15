"""Configuration de la connexion Tulip (Firebird) — fenêtre native Tkinter.

Port Python du ``SetupForm`` de la version C# : détection automatique du kit
Tulip (isql.exe + base .TFE), test de connexion réel via isql, activation,
synchronisation des référentiels, écriture désactivée par défaut.

Aucune base n'est créée : la fenêtre relie l'application à l'installation
Tulip existante et enregistre les clés ``TULIP_FB_*`` dans le fichier ``.env``
placé à côté de l'exécutable (en préservant les autres réglages).
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox

CHARSET = "WIN1252"
DEFAULT_TIMEOUT = 60
SERVER_URL = "http://127.0.0.1:8000"

ERROR_MARKERS = (
    "Statement failed",
    "Dynamic SQL Error",
    "SQLSTATE",
    "Use CONNECT",
    "unavailable database",
    "Your user name and password",
    "Unable to complete network request",
)

TEST_SQL = "SELECT rdb$get_context('SYSTEM','ENGINE_VERSION') FROM RDB$DATABASE;"

ENV_ORDER = (
    "TULIP_FB_ENABLED",
    "TULIP_FB_WRITE_ENABLED",
    "TULIP_FB_HOST",
    "TULIP_FB_PORT",
    "TULIP_FB_DATABASE",
    "TULIP_FB_USER",
    "TULIP_FB_PASSWORD",
    "TULIP_FB_ISQL_PATH",
    "TULIP_FB_HOME",
    "TULIP_FB_CHARSET",
    "TULIP_FB_TIMEOUT",
)


# --------------------------------------------------------------------------
# Utilitaires fichiers / environnement
# --------------------------------------------------------------------------

def base_dir() -> Path:
    """Dossier de l'exécutable (ou du script en mode source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def env_path(folder: Path | None = None) -> Path:
    return Path(folder or base_dir()) / ".env"


def load_env(folder: Path | None = None) -> None:
    """Charge ``.env`` dans os.environ sans écraser les variables existantes.

    Implémentation minimale volontairement sans dépendance : le lanceur doit
    pouvoir lire la configuration avant d'importer le backend.
    """
    path = env_path(folder)
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name.lower().startswith("export "):
            name = name[7:].strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def read_env(folder: Path | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    path = env_path(folder)
    if not path.is_file():
        return values
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def persist_env(values: dict[str, str], folder: Path | None = None) -> Path:
    """Écrit les clés TULIP_FB_* dans .env en conservant toutes les autres."""
    path = env_path(folder)
    lines: list[str] = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
    kept = [
        line
        for line in lines
        if not line.split("=", 1)[0].strip().startswith("TULIP_FB_")
    ]
    for key in ENV_ORDER:
        if key in values:
            kept.append(f"{key}={values[key]}")
    for key, value in values.items():
        if key not in ENV_ORDER:
            kept.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return path


def apply_env(values: dict[str, str]) -> None:
    for key, value in values.items():
        os.environ[key] = value


# --------------------------------------------------------------------------
# Détection de l'installation Tulip / Firebird
# --------------------------------------------------------------------------

def _tfe_in(folder: Path) -> Path | None:
    preferred = folder / "SUPERETTE.TFE"
    if preferred.is_file():
        return preferred
    try:
        for pattern in ("*.TFE", "*.tfe", "*.FDB", "*.fdb"):
            for candidate in sorted(folder.glob(pattern)):
                if candidate.is_file():
                    return candidate
    except OSError:
        pass
    return None


def locate_database() -> Path | None:
    """Registre du kit Tulip, puis scan des emplacements usuels des disques."""
    for hive in ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"):
        try:
            import winreg

            with winreg.OpenKey(getattr(winreg, hive), r"Software\TH\TFZ") as key:
                value, _ = winreg.QueryValueEx(key, "Pth")
            candidate = Path(str(value).strip().strip('"'))
            found = _tfe_in(candidate)
            if found is not None:
                return found
        except Exception:
            pass
    import string

    extra_roots: list[Path] = []
    for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData", "PUBLIC"):
        value = os.environ.get(name)
        if value:
            extra_roots.append(Path(value))
    home = Path.home()
    for sub in ("Desktop", "Documents", "Bureau"):
        extra_roots.append(home / sub)
    extra_roots += [
        Path(r"C:\Program Files\Tulip"),
        Path(r"C:\Program Files (x86)\Tulip"),
        Path(r"C:\Program Files\Tulip Gestion commerciale"),
        Path(r"C:\Program Files (x86)\Tulip Gestion commerciale"),
    ]
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if not root.exists():
            continue
        for sub in (
            r"zjob\tulip",
            "tulip",
            "Tulip",
            "TULIP",
            r"TULIP_KIT\tulip",
            r"zjob\TULIP_KIT\tulip",
            "TULIP_KIT",
            r"zjob\TULIP",
            r"zjob\Tulip",
            "GCP",
        ):
            extra_roots.append(root / sub)
    for candidate in extra_roots:
        found = _tfe_in(candidate)
        if found is not None:
            return found
        # Un seul niveau de sous-dossier (ex. C:\TULIP_KIT\<version>\SUPERETTE.TFE)
        try:
            for child in sorted(candidate.iterdir()):
                if child.is_dir():
                    found = _tfe_in(child)
                    if found is not None:
                        return found
        except OSError:
            continue
    return None


def _local_drives() -> list[Path]:
    """Disques locaux, en commençant par ceux qui ne portent pas Windows."""
    import string

    system = (os.environ.get("SystemDrive") or "C:").rstrip("\\").upper()[:2]
    drives: list[Path] = []
    for letter in string.ascii_uppercase[2:]:
        root = Path(f"{letter}:\\")
        try:
            if root.exists():
                drives.append(root)
        except OSError:
            continue
    drives.sort(key=lambda p: str(p).upper().startswith(system))
    return drives


_SKIP_DIRS = {
    "windows", "$recycle.bin", "system volume information", "recovery",
    "appdata", "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv",
    "winsxs", "temp", "tmp", "cache", "caches", "driverstore", "installer",
}


def _tfe_rank(path: Path) -> tuple[int, float, str]:
    name = path.name.lower()
    parent = path.parent.name.lower()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    if name == "superette.tfe":
        rank = 0
    elif "superette" in name:
        rank = 1
    elif "tulip" in name or "tulip" in parent or "gcp" in parent:
        rank = 2
    else:
        rank = 3
    # À nom égal, la base modifiée le plus récemment est la plus probable.
    return (rank, -mtime, str(path).lower())


def locate_database_deep(budget: float = 15.0) -> Path | None:
    """Recherche bornée de *.TFE / *.FDB sur les disques locaux.

    Parcours en largeur, profondeur 3, avec un budget de temps : ne bloque
    jamais l'interface et ignore les dossiers système inutiles.
    """
    started = time.monotonic()
    found: list[Path] = []
    queue: list[tuple[Path, int]] = [(root, 0) for root in _local_drives()]
    while queue and len(found) < 8:
        if time.monotonic() - started > budget:
            break
        folder, depth = queue.pop(0)
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if time.monotonic() - started > budget:
                        break
                    try:
                        if entry.is_file(follow_symlinks=False):
                            if entry.name.lower().endswith((".tfe", ".fdb")):
                                found.append(Path(entry.path))
                        elif entry.is_dir(follow_symlinks=False) and depth < 3:
                            name = entry.name.lower()
                            if name in _SKIP_DIRS or name.startswith("."):
                                continue
                            queue.append((Path(entry.path), depth + 1))
                    except OSError:
                        continue
        except OSError:
            continue
    if not found:
        return None
    found.sort(key=_tfe_rank)
    return found[0]



def locate_isql(database: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    # Client Firebird livré avec l'application (dossier portable).
    candidates.append(base_dir() / "firebird" / "bin" / "isql.exe")
    if database is not None:
        for parent in (database.parent, database.parent.parent, database.parent.parent.parent):
            candidates.append(parent / "firebird_2_5" / "bin" / "isql.exe")
            for version in ("firebird_5_0", "Firebird_5_0", "firebird_4_0",
                            "Firebird_4_0", "firebird_3_0", "Firebird_3_0",
                            "firebird", "Firebird"):
                candidates.append(parent / version / "bin" / "isql.exe")
    bases = [
        Path(r"C:\Program Files\Firebird"),
        Path(r"C:\Program Files (x86)\Firebird"),
        Path(r"C:\Firebird"),
        Path(r"C:\Program Files\Tulip"),
        Path(r"C:\Program Files (x86)\Tulip"),
    ]
    versions = ("Firebird_5_0", "Firebird_4_0", "Firebird_3_0", "Firebird_2_5",
                "firebird_5_0", "firebird_4_0", "firebird_3_0", "firebird_2_5", "")
    for base in bases:
        for version in versions:
            candidates.append(base / version / "bin" / "isql.exe" if version else base / "bin" / "isql.exe")
    import string

    for letter in string.ascii_uppercase:
        if not Path(f"{letter}:\\").exists():
            continue
        root = Path(f"{letter}:\\")
        candidates.append(root / "firebird_2_5" / "bin" / "isql.exe")
        candidates.append(root / "zjob" / "firebird_2_5" / "bin" / "isql.exe")
        candidates.append(root / "Firebird" / "Firebird_2_5" / "bin" / "isql.exe")
        candidates.append(root / "Firebird" / "bin" / "isql.exe")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def home_for(isql: Path | None) -> str:
    if isql is None:
        return ""
    return str(isql.parent.parent)


def _local_ip() -> str:
    for target in ("8.8.8.8", "1.1.1.1"):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect((target, 80))
                return sock.getsockname()[0]
            finally:
                sock.close()
        except OSError:
            continue
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return ""


def scan_firebird_hosts(port: int = 3050, timeout: float = 0.25) -> list[str]:
    """Hôtes du réseau local qui écoutent sur le port Firebird (scan du /24)."""
    ip = _local_ip()
    if not ip or ip.startswith("127.") or ip.count(".") != 3:
        return []
    prefix = ip.rsplit(".", 1)[0]
    hosts: list[str] = []

    def probe(candidate: str) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            if sock.connect_ex((candidate, port)) == 0:
                hosts.append(candidate)
        except OSError:
            pass
        finally:
            sock.close()

    from concurrent.futures import ThreadPoolExecutor

    candidates = [f"{prefix}.{index}" for index in range(1, 255)]
    with ThreadPoolExecutor(max_workers=64) as pool:
        list(pool.map(probe, candidates))
    hosts.sort(key=lambda host: int(host.rsplit(".", 1)[1]))
    return hosts


def guess_server_database(
    host: str, port: str, isql: str, home: str, user: str, password: str,
    timeout: int = 4,
) -> str:
    """Essaie les alias et chemins usuels du kit Tulip côté serveur.

    L'utilisateur n'a rien à connaître : on teste les noms de base Firebird
    (alias `SUPERETTE`) puis les emplacements classiques du kit Tulip.
    """
    aliases = ["SUPERETTE", "superette", "TULIP", "Tulip", "tulip"]
    paths = [
        r"C:\zjob\tulip\SUPERETTE.TFE",
        r"D:\zjob\tulip\SUPERETTE.TFE",
        r"E:\zjob\tulip\SUPERETTE.TFE",
        r"C:\TULIP_KIT\tulip\SUPERETTE.TFE",
        r"D:\TULIP_KIT\tulip\SUPERETTE.TFE",
        r"C:\tulip\SUPERETTE.TFE",
        r"D:\tulip\SUPERETTE.TFE",
        r"E:\tulip\SUPERETTE.TFE",
        r"C:\TULIP\SUPERETTE.TFE",
        r"D:\TULIP\SUPERETTE.TFE",
        r"C:\Program Files\Tulip\SUPERETTE.TFE",
        r"C:\Program Files (x86)\Tulip\SUPERETTE.TFE",
        r"C:\Program Files\Tulip Gestion commerciale\SUPERETTE.TFE",
    ]
    for database in aliases + paths:
        try:
            run_isql(
                isql=isql, home=home, user=user, password=password,
                connection=connection_string(host, port, database),
                sql="SELECT 1 FROM RDB$DATABASE;", timeout=timeout,
            )
            return database
        except Exception:  # noqa: BLE001 - on essaie le suivant
            continue
    return ""


def detect_all(
    *, isql: str = "", home: str = "", user: str = "SYSDBA",
    password: str = "", host: str = "", port: str = "3050",
) -> dict[str, str]:
    """Détection complète : base, client isql, serveur — sans rien demander à l'utilisateur."""
    notes: list[str] = []
    found = locate_install()
    isql_path = isql.strip() if isql.strip() and Path(isql.strip()).is_file() else ""
    if not isql_path:
        isql_path = found["isql"] or str(base_dir() / "firebird" / "bin" / "isql.exe")
        if not Path(isql_path).is_file():
            isql_path = ""
    firebird_home = home.strip() or found["home"] or home_for(Path(isql_path) if isql_path else None)
    database = found["database"]
    if not database:
        deep = locate_database_deep()
        if deep is not None:
            database = str(deep)
            notes.append("base trouvée par recherche disque")
    used_host = host.strip() or "localhost"
    used_port = port.strip() or "3050"
    if not database and isql_path:
        try:
            if port_open(int(used_port), used_host):
                guess = guess_server_database(
                    used_host, used_port, isql_path, firebird_home, user or "SYSDBA", password
                )
                if guess:
                    database = guess
                    notes.append("base trouvée sur le serveur " + used_host)
        except Exception:  # noqa: BLE001
            pass
    if not database and isql_path:
        try:
            hosts = [h for h in scan_firebird_hosts(int(used_port)) if h != used_host]
        except Exception:  # noqa: BLE001
            hosts = []
        for candidate in hosts[:4]:
            guess = guess_server_database(
                candidate, used_port, isql_path, firebird_home, user or "SYSDBA", password
            )
            if guess:
                used_host = candidate
                database = guess
                notes.append("serveur trouvé : " + candidate)
                break
    return {
        "database": database or "",
        "isql": isql_path,
        "home": firebird_home,
        "host": used_host,
        "port": used_port,
        "note": " ; ".join(notes),
    }


def locate_install() -> dict[str, str]:
    """Retourne les chemins détectés : database, isql, home."""
    database = locate_database()
    isql = locate_isql(database)
    return {
        "database": str(database) if database else "",
        "isql": str(isql) if isql else "",
        "home": home_for(isql),
    }


# --------------------------------------------------------------------------
# Firebird : serveur local + test réel en lecture seule
# --------------------------------------------------------------------------

def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.6) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def is_local_host(host: str) -> bool:
    return host.strip().lower() in ("", "localhost", "127.0.0.1", "::1")


def ensure_firebird_running(home: str, port: int = 3050) -> None:
    """Démarre fbserver.exe du kit si le serveur local n'écoute pas encore."""
    if not home:
        return
    if port_open(port):
        return
    server = Path(home) / "bin" / "fbserver.exe"
    if not server.is_file():
        return
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        subprocess.Popen(
            [str(server), "-a"],
            cwd=str(server.parent),
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return
    for _ in range(20):
        time.sleep(0.4)
        if port_open(port):
            return


def _isql_environment(isql: str, home: str, user: str, password: str) -> dict[str, str]:
    env = os.environ.copy()
    env["ISC_USER"] = user
    env["ISC_PASSWORD"] = password
    if home:
        env["FIREBIRD"] = home
        bin_dir = str(Path(home) / "bin")
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    return env


def connection_string(host: str, port: str, database: str) -> str:
    host = host.strip() or "localhost"
    return f"{host}/{port.strip() or '3050'}:{database}"


def run_isql(
    *,
    isql: str,
    home: str,
    user: str,
    password: str,
    connection: str,
    sql: str,
    charset: str = CHARSET,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    script = "\n".join(
        [
            "SET BAIL ON;",
            "SET ECHO OFF;",
            "SET HEADING OFF;",
            "SET LIST ON;",
            sql.rstrip().rstrip(";") + ";",
            "QUIT;",
            "",
        ]
    )
    sql_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sql", delete=False, encoding="cp1252", errors="replace"
        ) as handle:
            handle.write(script)
            sql_path = Path(handle.name)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [isql, "-charset", charset, "-i", str(sql_path), connection],
            capture_output=True,
            text=True,
            encoding="cp1252",
            errors="replace",
            env=_isql_environment(isql, home, user, password),
            cwd=str(Path(home) / "bin") if home and Path(home, "bin").is_dir() else None,
            timeout=timeout,
            creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Délai dépassé : Firebird ne répond pas.")
    except OSError as exc:
        raise RuntimeError(f"Impossible de lancer isql : {exc}")
    finally:
        if sql_path is not None:
            try:
                sql_path.unlink()
            except OSError:
                pass

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if password:
        output = output.replace(password, "***")
    if result.returncode != 0 or any(marker in output for marker in ERROR_MARKERS):
        raise RuntimeError(output or f"isql a retourné le code {result.returncode}.")
    return output


def _friendly_error(raw: str) -> str:
    """Traduit les erreurs isql les plus fréquentes en message compréhensible."""
    text = raw or ""
    lowered = text.lower()
    if "sqlstate = 28000" in lowered or "user name and password" in lowered:
        return "Utilisateur ou mot de passe refusé par Firebird (SQLSTATE 28000)."
    if "unable to complete network request" in lowered or "connection refused" in lowered:
        return "Serveur Firebird injoignable — vérifiez l'hôte et le port 3050."
    if "unavailable database" in lowered or "i/o error" in lowered or "no such file" in lowered:
        return "Base inaccessible — vérifiez le chemin du fichier .TFE et que Firebird est démarré."
    if "is not a valid database" in lowered or "wrong or obsolete version" in lowered:
        return "Ce fichier n'est pas une base Firebird valide."
    if "attempt to reclose a closed cursor" in lowered:
        return text[:160]
    return text[:160] or "Échec de la connexion."


def test_connection(
    database: str,
    host: str,
    port: str,
    user: str,
    password: str,
    isql: str,
    home: str,
    timeout: int = 30,
) -> tuple[bool, str, str, int]:
    """Teste la connexion en lecture seule.

    Retourne (ok, message, version_du_moteur, latence_ms).
    """
    started = time.time()
    if not database.strip():
        return False, "Sélectionnez le fichier de base Tulip (.TFE).", "", 0
    if not isql.strip() or not Path(isql).is_file():
        return False, "isql.exe introuvable — indiquez son emplacement.", "", 0
    if is_local_host(host):
        ensure_firebird_running(home, int(port or 3050))
        if Path(database).is_file() is False:
            # Chemin réseau (\\serveur\...) : on laisse isql décider.
            if not database.startswith("\\\\"):
                return False, f"Base introuvable : {database}", "", 0
    try:
        output = run_isql(
            isql=isql,
            home=home,
            user=user or "SYSDBA",
            password=password,
            connection=connection_string(host, port, database),
            sql=TEST_SQL,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - message tel quel pour l'utilisateur
        raw = " ".join(str(exc).split())
        return False, _friendly_error(raw), "", 0
    latency = int((time.time() - started) * 1000)
    match = re.search(r"(?:ENGINE_VERSION|RDB\$GET_CONTEXT)\s+(\S+)", output, re.IGNORECASE)
    version = match.group(1) if match else "Firebird"
    return True, "OK", version, latency


# --------------------------------------------------------------------------
# Synchronisation des référentiels (serveur en cours, sinon direct)
# --------------------------------------------------------------------------

def _server_up() -> bool:
    return port_open(8000)


def _http_json(url: str, payload: dict | None = None, method: str | None = None, timeout: int = 60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method or ("POST" if data is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    return json.loads(body) if body else {}


def notify_backend(values: dict[str, str]) -> bool:
    """Applique la configuration au serveur déjà lancé (si présent)."""
    if not _server_up():
        return False
    payload = {
        "enabled": values.get("TULIP_FB_ENABLED", "false").lower() == "true",
        "database": values.get("TULIP_FB_DATABASE", ""),
        "host": values.get("TULIP_FB_HOST", "localhost"),
        "port": int(values.get("TULIP_FB_PORT", "3050") or 3050),
        "user": values.get("TULIP_FB_USER", "SYSDBA"),
        "password": values.get("TULIP_FB_PASSWORD", ""),
        "isql_path": values.get("TULIP_FB_ISQL_PATH", ""),
        "fb_home": values.get("TULIP_FB_HOME", ""),
        "charset": values.get("TULIP_FB_CHARSET", CHARSET),
        "write_enabled": values.get("TULIP_FB_WRITE_ENABLED", "false").lower() == "true",
    }
    try:
        _http_json(f"{SERVER_URL}/api/settings/firebird", payload, method="PUT", timeout=15)
        return True
    except Exception:
        return False


def _direct_sync(values: dict[str, str], folder: Path) -> tuple[dict, dict]:
    """Synchronise sans passer par le serveur HTTP (import du backend en local)."""
    root = Path(folder)
    for path in (str(root), str(root / "backend")):
        if path not in sys.path:
            sys.path.insert(0, path)

    from app.database import SessionLocal
    from app.services.tulip.catalog import TulipCatalog
    from app.services.tulip.firebird import FirebirdConfig, FirebirdIsql
    from app.services.tulip.sync import sync_products, sync_suppliers

    config = FirebirdConfig(
        enabled=True,
        host=values.get("TULIP_FB_HOST", "localhost"),
        port=int(values.get("TULIP_FB_PORT", "3050") or 3050),
        database=values.get("TULIP_FB_DATABASE", ""),
        user=values.get("TULIP_FB_USER", "SYSDBA"),
        password=values.get("TULIP_FB_PASSWORD", ""),
        isql_path=values.get("TULIP_FB_ISQL_PATH", ""),
        firebird_home=values.get("TULIP_FB_HOME", ""),
        charset=values.get("TULIP_FB_CHARSET", CHARSET),
        timeout=int(values.get("TULIP_FB_TIMEOUT", "60") or 60),
        write_enabled=False,
    )
    catalog = TulipCatalog(FirebirdIsql(config))
    session = SessionLocal()
    try:
        suppliers = sync_suppliers(session, catalog, 500)
        products = sync_products(session, catalog, 500)
    finally:
        session.close()
    return suppliers, products


def sync_catalogs(values: dict[str, str], folder: Path, timeout: int = 1800) -> tuple[dict, dict, str]:
    """Synchronise fournisseurs + articles.

    Retourne (resultat_fournisseurs, resultat_articles, origine).
    """
    if _server_up():
        try:
            notify_backend(values)
            suppliers = _http_json(
                f"{SERVER_URL}/api/tulip/live/suppliers/sync", {}, method="POST", timeout=timeout
            )
            products = _http_json(
                f"{SERVER_URL}/api/tulip/live/products/sync", {}, method="POST", timeout=timeout
            )
            return suppliers, products, "serveur"
        except Exception:
            # Le serveur a peut-être refusé la config : bascule en direct.
            pass
    suppliers, products = _direct_sync(values, folder)
    return suppliers, products, "direct"


# --------------------------------------------------------------------------
# Fenêtre de configuration
# --------------------------------------------------------------------------

class TulipSetupDialog(tk.Toplevel):
    """Équivalent Python du SetupForm C# (mêmes champs, mêmes règles)."""

    def __init__(self, master: tk.Misc, folder: Path | None = None,
                 on_saved=None, on_closed=None):
        super().__init__(master)
        self.folder = Path(folder or base_dir())
        self.on_saved = on_saved
        self.on_closed = on_closed
        self._test_ok = False
        self._sync_done = False
        self._busy = False
        self._closed = False

        self.title("Tulip Factures — Configuration de la connexion Tulip")
        self.resizable(False, False)
        self.configure(padx=16, pady=14)

        self._build_ui()
        self._auto_detect()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        try:
            # Une fenêtre «transient» d'un parent retiré (mode autonome) reste
            # invisible sous Windows : ne le rattacher que s'il est affiché.
            if master is not None and master.winfo_viewable():
                self.transient(master)
        except tk.TclError:
            pass
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.after(30, self._center)
        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self._cancel())
        # Config déjà en place : vérifier tout de suite pour rendre
        # l'activation et la synchronisation immédiatement utilisables.
        if self._isql_var.get() and self._database_var.get():
            self.after(250, lambda: self._test(silent=True))

    # ---------- construction ----------

    def _build_ui(self) -> None:
        self._isql_var = tk.StringVar()
        self._home_var = tk.StringVar()
        self._host_var = tk.StringVar()
        self._port_var = tk.StringVar()
        self._database_var = tk.StringVar()
        self._user_var = tk.StringVar()
        self._password_var = tk.StringVar()

        body = tk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        def label(text: str, row: int, column: int = 0) -> tk.Label:
            widget = tk.Label(body, text=text, anchor="w")
            widget.grid(row=row, column=column, sticky="w", padx=(0, 8), pady=6)
            return widget

        def entry(var: tk.StringVar, row: int, width: int = 46, column: int = 1,
                  show: str | None = None) -> tk.Entry:
            widget = tk.Entry(body, textvariable=var, width=width, show=show or "")
            widget.grid(row=row, column=column, sticky="we", pady=6)
            widget.bind("<KeyRelease>", self._invalidate_test)
            return widget

        label("Installation Firebird (isql.exe) :", 0)
        isql_row = tk.Frame(body)
        isql_row.grid(row=0, column=1, sticky="we", pady=6)
        isql_row.columnconfigure(0, weight=1)
        self._isql_entry = tk.Entry(isql_row, textvariable=self._isql_var, width=38)
        self._isql_entry.grid(row=0, column=0, sticky="we")
        self._isql_entry.bind("<KeyRelease>", self._invalidate_test)
        tk.Button(isql_row, text="Parcourir…", command=self._browse_isql,
                  padx=6).grid(row=0, column=1, padx=(6, 0))

        label("Dossier Firebird :", 1)
        tk.Entry(body, textvariable=self._home_var, width=46,
                 state="readonly").grid(row=1, column=1, sticky="we", pady=6)

        host_row = tk.Frame(body)
        host_row.grid(row=2, column=1, sticky="we", pady=6)
        host_row.columnconfigure(0, weight=0)
        self._host_entry = tk.Entry(host_row, textvariable=self._host_var, width=22)
        self._host_entry.grid(row=0, column=0, sticky="w")
        self._host_entry.bind("<KeyRelease>", self._invalidate_test)
        tk.Label(host_row, text="Port :").grid(row=0, column=1, padx=(16, 6))
        self._port_entry = tk.Entry(host_row, textvariable=self._port_var, width=8)
        self._port_entry.grid(row=0, column=2, sticky="w")
        self._port_entry.bind("<KeyRelease>", self._invalidate_test)
        label("Serveur (hôte) :", 2)

        db_row = tk.Frame(body)
        db_row.grid(row=3, column=1, sticky="we", pady=6)
        db_row.columnconfigure(0, weight=1)
        self._database_entry = tk.Entry(db_row, textvariable=self._database_var, width=38)
        self._database_entry.grid(row=0, column=0, sticky="we")
        self._database_entry.bind("<KeyRelease>", self._invalidate_test)
        tk.Button(db_row, text="Parcourir…", command=self._browse_database,
                  padx=6).grid(row=0, column=1, padx=(6, 0))
        label("Fichier de base (.TFE) :", 3)

        user_row = tk.Frame(body)
        user_row.grid(row=4, column=1, sticky="we", pady=6)
        self._user_entry = tk.Entry(user_row, textvariable=self._user_var, width=22)
        self._user_entry.grid(row=0, column=0, sticky="w")
        self._user_entry.bind("<KeyRelease>", self._invalidate_test)
        tk.Label(user_row, text="Mot de passe :").grid(row=0, column=1, padx=(16, 6))
        self._password_entry = tk.Entry(user_row, textvariable=self._password_var,
                                        width=18, show="*")
        self._password_entry.grid(row=0, column=2, sticky="w")
        self._password_entry.bind("<KeyRelease>", self._invalidate_test)
        label("Utilisateur :", 4)

        test_row = tk.Frame(body)
        test_row.grid(row=5, column=1, sticky="we", pady=(10, 4))
        self._test_btn = tk.Button(test_row, text="Tester la connexion",
                                   command=self._test, padx=12)
        self._test_btn.pack(side="left")
        self._detect_btn = tk.Button(test_row, text="Détecter automatiquement",
                                     command=self._detect, padx=10)
        self._detect_btn.pack(side="left", padx=(8, 0))
        self._test_label = tk.Label(test_row, text="", anchor="w", width=30)
        self._test_label.pack(side="left", padx=(10, 0))

        self._enable_var = tk.BooleanVar(value=False)
        self._enable_check = tk.Checkbutton(
            body, text="Activer la connexion Tulip", variable=self._enable_var,
            anchor="w", state="disabled",
        )
        self._enable_check.grid(row=6, column=1, sticky="w", pady=(4, 4))

        sync_row = tk.Frame(body)
        sync_row.grid(row=7, column=1, sticky="we", pady=4)
        self._sync_btn = tk.Button(sync_row, text="Synchroniser les référentiels",
                                   command=self._sync, padx=12, state="disabled")
        self._sync_btn.pack(side="left")
        self._sync_label = tk.Label(sync_row, text="", anchor="w", width=28)
        self._sync_label.pack(side="left", padx=(12, 0))

        self._write_var = tk.BooleanVar(value=False)
        self._write_check = tk.Checkbutton(
            body,
            text="Autoriser l'écriture dans Tulip (bons d'entrée, fournisseurs, articles)",
            variable=self._write_var, anchor="w", command=self._on_write_toggle,
        )
        self._write_check.grid(row=8, column=0, columnspan=2, sticky="w", pady=(6, 2))

        tk.Label(
            body,
            text="L'écriture modifie directement la base Tulip. Sauvegardez-la avant "
                 "de cocher cette case.",
            fg="#8b0000", anchor="w", justify="left", wraplength=560,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 6))

        tk.Label(
            body,
            text="Vous ne connaissez pas les chemins ? Cliquez sur « Détecter "
                 "automatiquement » : la base, le client Firebird et le serveur "
                 "sont recherchés sur ce PC et sur le réseau local.",
            fg="#374151", anchor="w", justify="left", wraplength=560,
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(0, 10))

        actions = tk.Frame(self)
        actions.pack(fill="x", pady=(10, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(3, weight=1)
        self._save_btn = tk.Button(actions, text="Enregistrer", command=self._save,
                                   bg="#2563eb", fg="white", padx=22, pady=6)
        self._save_btn.grid(row=0, column=1, padx=(0, 8))
        self._cancel_btn = tk.Button(actions, text="Annuler", command=self._cancel,
                                     padx=16, pady=4)
        self._cancel_btn.grid(row=0, column=2)

    # ---------- remplissage / détection ----------

    def _auto_detect(self) -> None:
        found = locate_install()
        env = os.environ
        isql = env.get("TULIP_FB_ISQL_PATH") or found["isql"]
        home = env.get("TULIP_FB_HOME") or found["home"] or home_for(Path(isql) if isql else None)
        database = env.get("TULIP_FB_DATABASE") or found["database"]
        self._isql_var.set(isql)
        self._home_var.set(home)
        self._database_var.set(database)
        self._host_var.set(env.get("TULIP_FB_HOST") or "localhost")
        self._port_var.set(env.get("TULIP_FB_PORT") or "3050")
        self._user_var.set(env.get("TULIP_FB_USER") or "SYSDBA")
        self._password_var.set(env.get("TULIP_FB_PASSWORD") or "masterkey")
        write = env.get("TULIP_FB_WRITE_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
        self._write_var.set(write)
        enabled = env.get("TULIP_FB_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
        if enabled and database:
            self._enable_var.set(True)

    def _browse_isql(self) -> None:
        initial = str(Path(self._isql_var.get()).parent) if self._isql_var.get() else None
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Sélectionner isql.exe",
            initialdir=initial,
            filetypes=[("isql.exe", "isql.exe"), ("Exécutable", "*.exe"), ("Tous fichiers", "*.*")],
        )
        if chosen:
            self._isql_var.set(chosen)
            self._home_var.set(home_for(Path(chosen)))
            self._invalidate_test()

    def _browse_database(self) -> None:
        initial = str(Path(self._database_var.get()).parent) if self._database_var.get() else None
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Sélectionner la base Tulip",
            initialdir=initial,
            filetypes=[
                ("Base Tulip", "*.TFE *.tfe *.FDB *.fdb"),
                ("Tous fichiers", "*.*"),
            ],
        )
        if chosen:
            self._database_var.set(chosen)
            if not self._home_var.get():
                isql = locate_isql(Path(chosen))
                if isql is not None:
                    self._isql_var.set(str(isql))
                    self._home_var.set(home_for(isql))
            self._invalidate_test()

    # ---------- état ----------

    def _invalidate_test(self, _event=None) -> None:
        if self._busy:
            return
        if not self._test_ok:
            return
        self._test_ok = False
        self._enable_var.set(False)
        self._enable_check.config(state="disabled")
        self._sync_btn.config(state="disabled")
        self._test_label.config(text="", fg="#111827")
        self._sync_label.config(text="", fg="#111827")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._test_btn.config(state=state)
        self._detect_btn.config(state=state)
        self._save_btn.config(state=state)
        if not busy and self._test_ok:
            self._sync_btn.config(state="normal")
        else:
            self._sync_btn.config(state="disabled")

    def _values(self) -> dict[str, str]:
        return {
            "TULIP_FB_ENABLED": "true" if (self._enable_var.get() and self._test_ok) else "false",
            "TULIP_FB_WRITE_ENABLED": "true" if self._write_var.get() else "false",
            "TULIP_FB_HOST": self._host_var.get().strip() or "localhost",
            "TULIP_FB_PORT": self._port_var.get().strip() or "3050",
            "TULIP_FB_DATABASE": self._database_var.get().strip(),
            "TULIP_FB_USER": self._user_var.get().strip() or "SYSDBA",
            "TULIP_FB_PASSWORD": self._password_var.get(),
            "TULIP_FB_ISQL_PATH": self._isql_var.get().strip(),
            "TULIP_FB_HOME": self._home_var.get().strip(),
            "TULIP_FB_CHARSET": CHARSET,
            "TULIP_FB_TIMEOUT": str(DEFAULT_TIMEOUT),
        }

    # ---------- test ----------

    def _detect(self) -> None:
        """Recherche automatique : base, client Firebird et serveur."""
        if self._busy:
            return
        self._test_ok = False
        self._enable_check.config(state="disabled")
        self._sync_btn.config(state="disabled")
        self._test_label.config(text="Recherche en cours…", fg="#374151")
        self._set_busy(True)
        # Les variables Tk ne doivent être lues que depuis le thread principal.
        values = {
            "isql": self._isql_var.get(),
            "home": self._home_var.get(),
            "user": self._user_var.get(),
            "password": self._password_var.get(),
            "host": self._host_var.get(),
            "port": self._port_var.get(),
        }
        holder: dict = {}

        def work() -> None:
            try:
                holder["result"] = detect_all(**values)
            except Exception as exc:  # noqa: BLE001
                holder["result"] = exc

        threading.Thread(target=work, daemon=True).start()
        self._poll(holder, self._detect_done)

    def _detect_done(self, result) -> None:
        self._set_busy(False)
        if isinstance(result, Exception):
            self._test_label.config(text="Recherche impossible", fg="#8b0000")
            return
        if result.get("isql"):
            self._isql_var.set(result["isql"])
        if result.get("home"):
            self._home_var.set(result["home"])
        if result.get("host"):
            self._host_var.set(result["host"])
        if result.get("port"):
            self._port_var.set(result["port"])
        if result.get("database"):
            self._database_var.set(result["database"])
            self._test_label.config(text="Base détectée — vérification…", fg="#374151")
            self._invalidate_test()
            self.after(120, self._test)
        else:
            self._test_label.config(text="Base non trouvée — Parcourir…", fg="#8b0000")

    def _test(self, silent: bool = False) -> None:
        if self._busy:
            return
        values = self._values()
        self._test_ok = False
        self._enable_check.config(state="disabled")
        self._sync_btn.config(state="disabled")
        if not silent:
            self._test_label.config(text="Test en cours…", fg="#374151")
        self._set_busy(True)
        holder: dict = {}

        def work() -> None:
            holder["result"] = test_connection(
                database=values["TULIP_FB_DATABASE"],
                host=values["TULIP_FB_HOST"],
                port=values["TULIP_FB_PORT"],
                user=values["TULIP_FB_USER"],
                password=values["TULIP_FB_PASSWORD"],
                isql=values["TULIP_FB_ISQL_PATH"],
                home=values["TULIP_FB_HOME"],
                timeout=20 if silent else 40,
            )

        threading.Thread(target=work, daemon=True).start()
        self._poll(holder, lambda result: self._test_done(result, silent))

    def _test_done(self, result, silent: bool) -> None:
        self._set_busy(False)
        ok, message, version, latency = result
        if ok:
            self._test_ok = True
            self._test_label.config(
                text=f"OK — {version} ({latency} ms)", fg="#0a7f2c"
            )
            self._enable_check.config(state="normal")
            if not self._enable_var.get():
                self._enable_var.set(True)
            self._sync_btn.config(state="normal")
        else:
            self._test_ok = False
            self._enable_var.set(False)
            text = message if len(message) <= 90 else message[:90] + "…"
            self._test_label.config(text=f"Échec : {text}", fg="#8b0000")
            self._enable_check.config(state="disabled")
            if not silent:
                messagebox.showwarning(
                    "Connexion Tulip",
                    "La connexion a échoué :\n\n" + message,
                    parent=self,
                )

    def _poll(self, holder: dict, callback) -> None:
        if self._closed:
            return
        if "result" in holder:
            callback(holder["result"])
        else:
            self.after(120, lambda: self._poll(holder, callback))

    # ---------- synchronisation ----------

    def _sync(self) -> None:
        if self._busy:
            return
        if not self._test_ok:
            messagebox.showinfo(
                "Synchronisation", "Testez d'abord la connexion.", parent=self
            )
            return
        if not messagebox.askyesno(
            "Synchronisation des référentiels",
            "Importer les fournisseurs et les articles Tulip dans le catalogue local ?\n\n"
            "L'opération peut durer plusieurs minutes.",
            parent=self,
        ):
            return
        values = self._values()
        values["TULIP_FB_ENABLED"] = "true"
        self._set_busy(True)
        self._sync_btn.config(state="disabled")
        self._sync_label.config(text="Synchronisation…", fg="#374151")
        holder: dict = {}

        def work() -> None:
            try:
                holder["result"] = sync_catalogs(values, self.folder)
            except Exception as exc:  # noqa: BLE001
                holder["result"] = exc

        threading.Thread(target=work, daemon=True).start()
        self._poll(holder, self._sync_done)

    def _sync_done(self, result) -> None:
        self._set_busy(False)
        if isinstance(result, Exception):
            self._sync_label.config(text="Échec", fg="#8b0000")
            messagebox.showerror(
                "Erreur de synchronisation",
                str(result)[:1200],
                parent=self,
            )
            return
        suppliers, products, origin = result
        self._sync_done = True
        self._sync_label.config(
            text=f"{suppliers.get('created', 0)} fou. / {products.get('created', 0)} art.",
            fg="#0a7f2c",
        )
        messagebox.showinfo(
            "Synchronisation terminée",
            "Fournisseurs : {c} créés, {u} mis à jour.\n"
            "Articles : {pc} créés, {pu} mis à jour.\n\nOrigine : {origin}".format(
                c=suppliers.get("created", 0),
                u=suppliers.get("updated", 0),
                pc=products.get("created", 0),
                pu=products.get("updated", 0),
                origin="serveur" if origin == "serveur" else "import direct",
            ),
            parent=self,
        )

    # ---------- écriture ----------

    def _on_write_toggle(self) -> None:
        if not self._write_var.get():
            return
        answer = messagebox.askyesno(
            "Avertissement — écriture Tulip",
            "L'écriture dans Tulip va modifier directement la base du magasin\n"
            "(bons d'entrée, fournisseurs, articles).\n\n"
            "Confirmez uniquement si la base a été sauvegardée. Continuer ?",
            icon="warning",
            default="no",
            parent=self,
        )
        if not answer:
            self._write_var.set(False)

    # ---------- enregistrement ----------

    def _save(self) -> None:
        if self._busy:
            return
        values = self._values()
        if self._enable_var.get() and not self._test_ok:
            messagebox.showwarning(
                "Configuration",
                "Testez la connexion avant d'activer.",
                parent=self,
            )
            return
        if not values["TULIP_FB_DATABASE"]:
            messagebox.showwarning(
                "Configuration",
                "Sélectionnez le fichier de base Tulip (.TFE).",
                parent=self,
            )
            return
        if self._enable_var.get() and not Path(values["TULIP_FB_ISQL_PATH"]).is_file():
            messagebox.showwarning(
                "Configuration",
                "isql.exe est introuvable : indiquez l'installation Firebird.",
                parent=self,
            )
            return
        try:
            path = persist_env(values, self.folder)
        except OSError as exc:
            messagebox.showerror("Configuration", f"Écriture impossible :\n{exc}", parent=self)
            return
        apply_env(values)
        applied = notify_backend(values)
        if self.on_saved is not None:
            try:
                self.on_saved(values)
            except Exception:
                pass
        detail = (
            "\n\nRéglages enregistrés dans :\n" + str(path)
            + ("\n\nServeur actuel mis à jour immédiatement." if applied else
               "\n\nRedémarrez l'application pour appliquer ces réglages.")
        )
        if values["TULIP_FB_ENABLED"] == "true":
            messagebox.showinfo(
                "Configuration Tulip",
                "Connexion Tulip activée en lecture seule."
                + (" L'écriture est autorisée." if values["TULIP_FB_WRITE_ENABLED"] == "true"
                   else " L'écriture reste désactivée.")
                + detail,
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Configuration Tulip",
                "Réglages enregistrés (connexion Tulip désactivée)." + detail,
                parent=self,
            )
        self._close(saved=True)

    def _cancel(self) -> None:
        self._close(saved=False)

    def _close(self, saved: bool) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass
        if self.on_closed is not None:
            try:
                self.on_closed(saved)
            except Exception:
                pass

    def _center(self) -> None:
        try:
            self.update_idletasks()
            width = self.winfo_width()
            height = self.winfo_height()
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 3)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass


# --------------------------------------------------------------------------
# Lancement autonome (test depuis les sources)
# --------------------------------------------------------------------------

def main() -> int:
    root = tk.Tk()
    root.withdraw()

    def stop(_saved: bool) -> None:
        try:
            root.destroy()
        except tk.TclError:
            pass

    TulipSetupDialog(root, folder=base_dir(), on_closed=stop)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
