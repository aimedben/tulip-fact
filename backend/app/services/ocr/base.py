from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class OcrError(RuntimeError):
    """Erreur OCR explicite, destinée à être affichée à l'utilisateur."""


@dataclass
class OcrLine:
    text: str
    page_number: int
    bbox: dict[str, float] | None = None
    confidence: float | None = None
    words: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PageResult:
    page_number: int
    image_path: str
    text: str
    lines: list[OcrLine] = field(default_factory=list)
    engine: str = "tesseract"
    confidence: float | None = None
    width: int = 0
    height: int = 0
    rotation: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentOcr:
    pages: list[PageResult]
    engine: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def all_lines(self) -> list[OcrLine]:
        result: list[OcrLine] = []
        for page in self.pages:
            result.extend(page.lines)
        return result


class OcrEngine(Protocol):
    name: str

    def available(self) -> bool: ...

    def recognize(self, image_path: str) -> tuple[str, list[OcrLine], float | None]: ...
