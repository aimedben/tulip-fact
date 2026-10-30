from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    app_mode: str = field(default_factory=lambda: os.getenv("TULIP_APP_MODE", "production").strip().lower())
    host: str = field(default_factory=lambda: os.getenv("TULIP_HOST", "127.0.0.1"))
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
    static_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "backend" / "app" / "static")

    worker_enabled: bool = field(default_factory=lambda: not _env_bool("TULIP_DISABLE_WORKER", False))
    max_upload_mb: int = field(default_factory=lambda: _env_int("TULIP_MAX_UPLOAD_MB", 25))
    allowed_extensions: frozenset[str] = frozenset({".pdf", ".jpg", ".jpeg", ".png"})
    amount_tolerance: Decimal = field(default_factory=lambda: _env_decimal("TULIP_AMOUNT_TOLERANCE", "0.05"))

    ocr_engine: str = field(default_factory=lambda: os.getenv("TULIP_OCR_ENGINE", "tesseract").strip().lower())
    tesseract_cmd: str = field(
        default_factory=lambda: os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    )
    tesseract_langs: str = field(default_factory=lambda: os.getenv("TULIP_TESSERACT_LANGS", "fra+eng"))
    tessdata_dir: Path = field(default_factory=lambda: Path(os.getenv("TESSDATA_PREFIX", str(PROJECT_ROOT / "tessdata"))))
    ocr_psm: int = field(default_factory=lambda: _env_int("TULIP_OCR_PSM", 6))
    ocr_render_dpi: int = field(default_factory=lambda: _env_int("TULIP_OCR_DPI", 300))
    preview_dpi: int = field(default_factory=lambda: _env_int("TULIP_PREVIEW_DPI", 140))

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

    def _vision_env(self, suffix: str, default: str = "") -> str:
        provider = self.vision_active_provider.upper()
        primary = os.getenv(f"TULIP_VISION_{provider}_{suffix}", "")
        if primary:
            return primary
        return os.getenv(f"TULIP_VISION_{suffix}", default)

    @property
    def vision_api_key(self) -> str:
        return self._vision_env("API_KEY")

    @property
    def vision_model(self) -> str:
        defaults = {"gemini": "gemini-3.8-flash", "openai": "gpt-4o-mini", "groq": "openai/gpt-oss-120b"}
        return self._vision_env("MODEL", defaults.get(self.vision_active_provider, ""))

    @property
    def vision_base_url(self) -> str:
        defaults = {
            "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
        }
        return self._vision_env("BASE_URL", defaults.get(self.vision_active_provider, ""))

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
