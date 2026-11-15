from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ocr import document as document_module
from app.services.ocr.base import OcrLine
from app.services.ocr.quality import (
    filter_garbage,
    garbage_ratio,
    is_garbage,
    line_quality,
    page_quality,
)

NOISE = (
    "2 Mama Ce i boat © *. d »Y SR NL Se mA MES NS LORS SN VON. "
    "N 6 . RE os : ae is ee Oe ae oe ee: rrr sr rr cl ee"
)

CLEAN_LINES = [
    "Delicia 480 gr 4X1 265.00 1060.00",
    "Pate fromage 2 kg 6.091X1 340,00 2 070,94",
    "TOTAL TTC 11320,40",
    "Reste a payer 0,00",
    "EURL MS FOOD DISTRIBUTION",
    "1 060,00",
    "ES 4.043X1 340,00 1 374,62 :",
]


def _line(text: str) -> OcrLine:
    return OcrLine(text=text, page_number=1)


def test_noise_line_is_detected() -> None:
    assert is_garbage(NOISE)
    assert line_quality(NOISE) < line_quality("Delicia 480 gr 4X1 265.00 1060.00")


@pytest.mark.parametrize("text", CLEAN_LINES)
def test_real_lines_are_kept(text: str) -> None:
    assert not is_garbage(text)


def test_filter_removes_only_noise() -> None:
    kept, dropped = filter_garbage([_line(NOISE), *(_line(text) for text in CLEAN_LINES)])
    assert dropped == 1
    assert len(kept) == len(CLEAN_LINES)
    assert all(line.text != NOISE for line in kept)


def test_garbage_ratio_on_clean_page() -> None:
    lines = [_line(text) for text in CLEAN_LINES]
    assert garbage_ratio(lines) == 0.0
    assert page_quality(lines) > 0.8


class _FakeEngine:
    def __init__(self, name: str, texts: list[str]) -> None:
        self.name = name
        self._texts = texts
        self.calls = 0

    def available(self) -> bool:
        return True

    def recognize(self, image_path: str, page_number: int = 1):
        self.calls += 1
        lines = [OcrLine(text=text, page_number=page_number) for text in self._texts]
        return "\n".join(self._texts), lines, 70.0


def test_read_page_switches_engine_when_primary_is_noise(monkeypatch) -> None:
    noise = _FakeEngine("tesseract", [NOISE])
    clean = _FakeEngine("rapidocr", ["Delicia 480 gr 4X1 265.00 1060.00", "TOTAL TTC 11320,40"])
    monkeypatch.setattr(document_module, "rapidocr_engine", clean)
    monkeypatch.setattr(document_module, "tesseract_engine", noise)

    run, warnings = document_module._read_page(Path("dummy.png"), 1, noise)

    assert run.engine == "rapidocr"
    assert run.text.startswith("Delicia")
    assert [warning["code"] for warning in warnings] == ["OCR_MOTEUR_REPLI"]
    assert noise.calls == 1 and clean.calls == 1


def test_read_page_keeps_primary_when_clean(monkeypatch) -> None:
    primary = _FakeEngine("rapidocr", ["Delicia 480 gr 4X1 265.00 1060.00"])
    alternate = _FakeEngine("tesseract", [NOISE])
    monkeypatch.setattr(document_module, "rapidocr_engine", primary)
    monkeypatch.setattr(document_module, "tesseract_engine", alternate)

    run, warnings = document_module._read_page(Path("dummy.png"), 1, primary)

    assert run.engine == "rapidocr"
    assert warnings == []
    assert alternate.calls == 0
