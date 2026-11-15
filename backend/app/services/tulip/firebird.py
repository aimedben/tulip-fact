from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ...config import settings

READ_ONLY_PREFIXES = ("SELECT", "WITH", "EXECUTE BLOCK")
WRITE_MARKERS = ("INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "SET ", "COMMIT")
ERROR_MARKERS = (
    "Statement failed",
    "Dynamic SQL Error",
    "SQLSTATE",
    "Use CONNECT",
    "unavailable database",
    "Your user name and password",
)


class FirebirdError(RuntimeError):
    pass


@dataclass(frozen=True)
class FirebirdConfig:
    enabled: bool
    host: str
    port: int
    database: str
    user: str
    password: str
    isql_path: str
    firebird_home: str
    charset: str = "WIN1252"
    timeout: int = 60
    write_enabled: bool = False

    @classmethod
    def from_settings(cls) -> "FirebirdConfig":
        isql_path = settings.tulip_fb_isql_path
        firebird_home = settings.tulip_fb_home
        # Client Firebird embarqué (dossier « firebird » livré avec l'application) :
        # utilisé automatiquement si le chemin configuré est absent (autre PC,
        # installation Tulip dans un autre dossier, etc.).
        bundled_home = settings.project_root / "firebird"
        bundled_isql = bundled_home / "bin" / "isql.exe"
        if bundled_isql.is_file() and not Path(isql_path or "").is_file():
            isql_path = str(bundled_isql)
            firebird_home = str(bundled_home)
        return cls(
            enabled=settings.tulip_fb_enabled,
            host=settings.tulip_fb_host,
            port=settings.tulip_fb_port,
            database=settings.tulip_fb_database,
            user=settings.tulip_fb_user,
            password=settings.tulip_fb_password,
            isql_path=isql_path,
            firebird_home=firebird_home,
            charset=settings.tulip_fb_charset,
            timeout=settings.tulip_fb_timeout,
            write_enabled=settings.tulip_fb_write_enabled,
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.database
            and self.user
            and self.password
            and Path(self.isql_path).is_file()
        )

    @property
    def connection_string(self) -> str:
        return f"{self.host}/{self.port}:{self.database}"

    def public_status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "database": self.database or None,
            "host": self.host,
            "port": self.port,
            "charset": self.charset,
            "read_only": not self.write_enabled,
            "write_enabled": self.write_enabled,
        }


def _is_read_only(sql: str) -> bool:
    statement = sql.lstrip()
    return statement.upper().startswith(READ_ONLY_PREFIXES)


class FirebirdIsql:
    def __init__(self, config: FirebirdConfig) -> None:
        self.config = config

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "ISC_USER": self.config.user,
                "ISC_PASSWORD": self.config.password,
                "FIREBIRD": self.config.firebird_home,
                "PATH": str(Path(self.config.firebird_home) / "bin")
                + os.pathsep
                + env.get("PATH", ""),
            }
        )
        return env

    def _sanitize(self, value: str) -> str:
        if self.config.password:
            value = value.replace(self.config.password, "***")
        return value

    def _run(self, sql: str, *, write: bool = False) -> str:
        if not self.config.configured:
            raise FirebirdError("Connexion Firebird Tulip non configurée.")
        if write and not self.config.write_enabled:
            raise FirebirdError("Les écritures Firebird Tulip sont désactivées.")
        if not write and not _is_read_only(sql):
            raise FirebirdError("Cette requête n'est pas en lecture seule.")

        script = "\n".join(
            [
                "SET BAIL ON;",
                "SET ECHO OFF;",
                "SET HEADING OFF;",
                "SET LIST ON;",
                sql.rstrip().rstrip(";") + ";",
                "COMMIT;" if write else "",
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
            result = subprocess.run(
                [
                    self.config.isql_path,
                    "-charset",
                    self.config.charset,
                    "-i",
                    str(sql_path),
                    self.config.connection_string,
                ],
                capture_output=True,
                text=True,
                encoding="cp1252",
                errors="replace",
                env=self._environment(),
                cwd=str(Path(self.config.firebird_home) / "bin"),
                timeout=self.config.timeout,
                # Application sans console (exe « windowed ») : sans ce drapeau,
                # chaque appel isql ouvre une fenêtre noire qui clignote.
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            raise FirebirdError("Délai dépassé lors de la communication avec Firebird.") from exc
        except OSError as exc:
            raise FirebirdError("Impossible de lancer isql.") from exc
        finally:
            if sql_path is not None:
                sql_path.unlink(missing_ok=True)

        output = self._sanitize((result.stdout or "") + (result.stderr or ""))
        if result.returncode != 0 or any(marker in output for marker in ERROR_MARKERS):
            message = output.strip() or f"isql a retourné le code {result.returncode}."
            raise FirebirdError(message)
        return output

    def query(self, sql: str, columns: Sequence[str]) -> list[dict[str, str | None]]:
        output = self._run(sql)
        return self._parse_list(output, columns)

    def execute(self, sql: str) -> str:
        return self._run(sql, write=True)

    @staticmethod
    def _parse_list(output: str, columns: Sequence[str]) -> list[dict[str, str | None]]:
        expected = {column.upper(): column for column in columns}
        rows: list[dict[str, str | None]] = []
        current: dict[str, str | None] = {}
        for raw_line in output.splitlines():
            line = raw_line.rstrip("\r")
            if not line.strip():
                if current:
                    rows.append(current)
                    current = {}
                continue
            if len(line) > 32:
                name = line[:32].strip().upper()
                value = line[32:].strip()
            else:
                match = re.match(r"^([A-Za-z][A-Za-z0-9_$#]*)\s+(.*)$", line)
                if not match:
                    continue
                name = match.group(1).upper()
                value = match.group(2).strip()
            key = expected.get(name)
            if key is None:
                continue
            if key in current:
                rows.append(current)
                current = {}
            current[key] = None if value == "<null>" else value
        if current:
            rows.append(current)
        return rows


_client: FirebirdIsql | None = None


def firebird_client() -> FirebirdIsql:
    global _client
    if _client is None:
        _client = FirebirdIsql(FirebirdConfig.from_settings())
    return _client
