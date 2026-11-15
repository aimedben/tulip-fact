from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv


def _app_base_dir() -> Path:
    """Dossier de l'application : racine du projet en dev, dossier de l'exe en mode figé (PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _app_base_dir()
# En mode figé, les ressources packagées (static, tessdata) vivent dans _MEIPASS.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", str(PROJECT_ROOT)))
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "oui", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_decimal(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.getenv(name, default).replace(",", "."))
    except Exception:
        return Decimal(default)


VISION_PROVIDER_ALIASES = {
    "chatgpt": "openai",
    "gpt": "openai",
    "nemotron": "opencode",
}


def normalize_vision_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    return VISION_PROVIDER_ALIASES.get(value, value)


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    app_mode: str = field(default_factory=lambda: os.getenv("TULIP_APP_MODE", "production").strip().lower())
    host: str = field(default_factory=lambda: os.getenv("TULIP_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("TULIP_PORT", 8000))
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    data_dir: Path = field(init=False)
    database_url: str = field(init=False)
    documents_dir: Path = field(init=False)
    pages_dir: Path = field(init=False)
    exports_dir: Path = field(init=False)
    backups_dir: Path = field(init=False)
    archives_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    static_dir: Path = field(
        default_factory=lambda: (
            BUNDLE_DIR / "backend" / "app" / "static"
            if (BUNDLE_DIR / "backend" / "app" / "static").is_dir()
            else (BUNDLE_DIR / "static" if (BUNDLE_DIR / "static").is_dir() else PROJECT_ROOT / "backend" / "app" / "static")
        )
    )

    worker_enabled: bool = field(default_factory=lambda: not _env_bool("TULIP_DISABLE_WORKER", False))
    max_upload_mb: int = field(default_factory=lambda: _env_int("TULIP_MAX_UPLOAD_MB", 25))
    allowed_extensions: frozenset[str] = frozenset({".pdf", ".jpg", ".jpeg", ".png"})
    amount_tolerance: Decimal = field(default_factory=lambda: _env_decimal("TULIP_AMOUNT_TOLERANCE", "0.05"))

    ocr_engine: str = field(default_factory=lambda: os.getenv("TULIP_OCR_ENGINE", "auto").strip().lower())
    tesseract_cmd: str = field(
        default_factory=lambda: os.getenv(
            "TESSERACT_CMD",
            str(next((p for p in [
                PROJECT_ROOT / "tesseract" / "tesseract.exe",
                PROJECT_ROOT / "Tesseract-OCR" / "tesseract.exe",
                Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            ] if p.exists()), Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")))
        )
    )
    tesseract_langs: str = field(default_factory=lambda: os.getenv("TULIP_TESSERACT_LANGS", "fra+eng"))
    tessdata_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "TESSDATA_PREFIX",
                str(next((p for p in [PROJECT_ROOT / "tessdata", BUNDLE_DIR / "tessdata"] if p.exists()), PROJECT_ROOT / "tessdata")),
            )
        )
    )
    ocr_psm: int = field(default_factory=lambda: _env_int("TULIP_OCR_PSM", 6))
    ocr_render_dpi: int = field(default_factory=lambda: _env_int("TULIP_OCR_DPI", 300))
    preview_dpi: int = field(default_factory=lambda: _env_int("TULIP_PREVIEW_DPI", 140))

    # Modèle local spécialisé OCR documents (GOT-OCR2_0, ~580M paramètres, 100% local).
    # TULIP_OCR_ENGINE=got pour l'utiliser ; en auto, utilisé en repli si les
    # moteurs rapides échouent. Chargé paresseusement (téléchargement ~1,7 Go au
    # premier lancement, ensuite depuis le cache local).
    got_ocr_enabled: bool = field(default_factory=lambda: _env_bool("TULIP_GOT_OCR_ENABLED", True))
    got_ocr_model: str = field(
        default_factory=lambda: os.getenv("TULIP_GOT_OCR_MODEL", "stepfun-ai/GOT-OCR2_0").strip()
    )
    got_ocr_timeout_seconds: int = field(default_factory=lambda: _env_int("TULIP_GOT_OCR_TIMEOUT", 300))
    got_ocr_cache_dir: str = field(default_factory=lambda: os.getenv("TULIP_GOT_CACHE_DIR", "").strip())

    llm_enabled: bool = field(default_factory=lambda: _env_bool("TULIP_LLM_ENABLED", False))
    llm_api_key: str = field(default_factory=lambda: os.getenv("TULIP_LLM_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("TULIP_LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_model: str = field(default_factory=lambda: os.getenv("TULIP_LLM_MODEL", "gpt-4o-mini"))
    llm_timeout_seconds: int = field(default_factory=lambda: _env_int("TULIP_LLM_TIMEOUT", 60))

    vision_enabled: bool = field(default_factory=lambda: _env_bool("TULIP_VISION_ENABLED", False))
    vision_active_provider: str = field(
        default_factory=lambda: os.getenv("TULIP_VISION_PROVIDER", "gemini").strip().lower()
    )
    vision_timeout_seconds: int = field(default_factory=lambda: _env_int("TULIP_VISION_TIMEOUT", 240))

    def _vision_env(self, suffix: str, default: str = "", provider: str | None = None) -> str:
        provider = (provider or self.vision_active_provider).upper()
        primary = os.getenv(f"TULIP_VISION_{provider}_{suffix}", "")
        if primary:
            return primary
        return os.getenv(f"TULIP_VISION_{suffix}", default)

    def vision_provider_config(self, provider: str) -> tuple[str, str, str]:
        """Clé, modèle et URL pour un fournisseur vision donné.

        Les noms « chatgpt » et « nemotron » sont des alias d'interface :
        OpenAI et le modèle opencode Zen (Nemotron) derrière TULIP_LLM_*.
        """
        provider = normalize_vision_provider(provider or self.vision_active_provider) or self.vision_active_provider

        if provider == "opencode":
            key = os.getenv("TULIP_VISION_OPENCODE_API_KEY") or os.getenv("TULIP_LLM_API_KEY", "")
            model = os.getenv("TULIP_VISION_OPENCODE_MODEL") or os.getenv("TULIP_LLM_MODEL", "")
            base_url = os.getenv("TULIP_VISION_OPENCODE_BASE_URL") or os.getenv("TULIP_LLM_BASE_URL", "")
            return key, model, base_url

        defaults = {
            "gemini": ("", "gemini-3.8-flash", "https://generativelanguage.googleapis.com/v1beta/openai"),
            "openai": ("", "gpt-4o-mini", "https://api.openai.com/v1"),
            "groq": ("", "openai/gpt-oss-120b", "https://api.groq.com/openai/v1"),
        }
        _, default_model, default_url = defaults.get(provider, ("", "", ""))
        return (
            self._vision_env("API_KEY", provider=provider),
            self._vision_env("MODEL", default_model, provider=provider),
            self._vision_env("BASE_URL", default_url, provider=provider),
        )

    @property
    def vision_api_key(self) -> str:
        return self.vision_provider_config(self.vision_active_provider)[0]

    @property
    def vision_model(self) -> str:
        return self.vision_provider_config(self.vision_active_provider)[1]

    @property
    def vision_base_url(self) -> str:
        return self.vision_provider_config(self.vision_active_provider)[2]

    tulip_integration_mode: str = field(
        default_factory=lambda: os.getenv("TULIP_INTEGRATION_MODE", "export_only").strip().lower()
    )
    tulip_ui_enabled: bool = field(default_factory=lambda: _env_bool("TULIP_UI_AUTOMATION_ENABLED", False))
    tulip_ui_window_title: str = field(
        default_factory=lambda: os.getenv("TULIP_UI_WINDOW_TITLE", "Tulip Gestion commerciale")
    )
    tulip_ui_exe: str = field(default_factory=lambda: os.getenv("TULIP_UI_EXE", ""))

    tulip_fb_enabled: bool = field(default_factory=lambda: _env_bool("TULIP_FB_ENABLED", False))
    tulip_fb_host: str = field(default_factory=lambda: os.getenv("TULIP_FB_HOST", "localhost").strip())
    tulip_fb_port: int = field(default_factory=lambda: _env_int("TULIP_FB_PORT", 3050))
    tulip_fb_database: str = field(default_factory=lambda: os.getenv("TULIP_FB_DATABASE", "").strip())
    tulip_fb_user: str = field(default_factory=lambda: os.getenv("TULIP_FB_USER", "SYSDBA").strip())
    tulip_fb_password: str = field(default_factory=lambda: os.getenv("TULIP_FB_PASSWORD", ""))
    tulip_fb_isql_path: str = field(
        default_factory=lambda: os.getenv("TULIP_FB_ISQL_PATH", r"E:\zjob\firebird_2_5\bin\isql.exe").strip()
    )
    tulip_fb_home: str = field(
        default_factory=lambda: os.getenv("TULIP_FB_HOME", r"E:\zjob\firebird_2_5").strip()
    )
    tulip_fb_charset: str = field(default_factory=lambda: os.getenv("TULIP_FB_CHARSET", "WIN1252").strip())
    tulip_fb_timeout: int = field(default_factory=lambda: _env_int("TULIP_FB_TIMEOUT", 60))
    tulip_fb_write_enabled: bool = field(default_factory=lambda: _env_bool("TULIP_FB_WRITE_ENABLED", False))

    def __post_init__(self) -> None:
        self.app_mode = "production"
        default_data = self.project_root / "data"
        env_data = os.getenv("TULIP_DATA_DIR")
        if env_data:
            self.data_dir = Path(env_data).expanduser().resolve()
        else:
            self.data_dir = default_data

        self.documents_dir = self.data_dir / "documents"
        self.pages_dir = self.data_dir / "pages"
        self.exports_dir = self.data_dir / "exports"
        self.backups_dir = self.data_dir / "backups"
        self.logs_dir = self.data_dir / "logs"
        self.archives_dir = self.data_dir / "archives"
        for directory in (
            self.data_dir,
            self.documents_dir,
            self.pages_dir,
            self.exports_dir,
            self.backups_dir,
            self.logs_dir,
            self.archives_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        env_db = os.getenv("DATABASE_URL")
        if env_db:
            self.database_url = env_db
        else:
            self.database_url = f"sqlite:///{(self.data_dir / 'tulip_factures.db').as_posix()}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
