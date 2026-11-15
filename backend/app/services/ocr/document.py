from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageOps

from ...config import settings
from .base import DocumentOcr, OcrError, OcrLine, PageResult
from .got_engine import engine as got_engine
from .preprocessing import prepare_image
from .quality import filter_garbage, garbage_ratio, page_quality
from .rapidocr_engine import engine as rapidocr_engine
from .tesseract_engine import engine as tesseract_engine
from .mistral_engine import engine as mistral_engine

MAX_PAGES = 60
MIN_DOCUMENT_CHARS = 25


def _select_engine():
    configured = (settings.ocr_engine or "auto").strip().lower()

    if configured == "mistral" or configured == "mistral-ocr":
        if not mistral_engine.available():
            raise OcrError(
                "Mistral OCR indisponible (MISTRAL_API_KEY manquante ou quota en cooldown)."
            )
        return mistral_engine

    if configured == "rapidocr":
        if not rapidocr_engine.available():
            raise OcrError(
                "RapidOCR n'est pas installé. Installez rapidocr ou utilisez TULIP_OCR_ENGINE=tesseract."
            )
        return rapidocr_engine
    if configured == "got" or configured == "got-ocr2":
        if not got_engine.available():
            raise OcrError(
                "GOT-OCR2 indisponible : installez torch et transformers (pip install torch transformers)."
            )
        return got_engine
    if configured == "tesseract":
        if not tesseract_engine.available():
            raise OcrError(
                "Tesseract est introuvable. Installez Tesseract OCR et vérifiez la variable TESSERACT_CMD."
            )
        return tesseract_engine
    if configured not in ("auto",):
        raise OcrError(
            f"Moteur OCR local « {configured} » non pris en charge. "
            "Utilisez TULIP_OCR_ENGINE=auto, got, mistral, rapidocr ou tesseract."
        )

    # Mode auto : privilégier local gratuit (rapide, sans token) - RapidOCR d'abord
    if rapidocr_engine.available():
        return rapidocr_engine
    if got_engine.available():
        return got_engine
    if mistral_engine.available():
        return mistral_engine
    return tesseract_engine


def _has_usable_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return len(compact) >= 40 and len(re.findall(r"\d", compact)) >= 4


@dataclass
class _OcrRun:
    text: str = ""
    lines: list[OcrLine] = field(default_factory=list)
    confidence: float | None = None
    engine: str = ""
    garbage: float = 1.0
    quality: float = 0.0
    error: str | None = None

    @property
    def score(self) -> tuple:
        return (self.error is not None, round(self.garbage, 2), -self.quality)


def _run_once(engine, image_path: Path, page_number: int) -> _OcrRun:
    try:
        text, lines, confidence = engine.recognize(str(image_path), page_number)
    except Exception as exc:
        return _OcrRun(engine=getattr(engine, "name", "ocr"), error=str(exc) or type(exc).__name__)
    return _OcrRun(
        text=text,
        lines=lines,
        confidence=confidence,
        engine=engine.name,
        garbage=garbage_ratio(lines),
        quality=page_quality(lines),
    )


def _other_engine(primary):
    """Premier moteur de repli différent du moteur principal."""
    for alternate in _fallback_engines(primary):
        return alternate
    return None


def _fallback_engines(primary):
    """Énumère les moteurs de repli, dans l'ordre de pertinence.

    Mistral (cloud) est passé avant Tesseract, mais au-dessus d'un garde :
    si l'image n'existe pas (tests offline, fichier factice), inutile de le
    solliciter — il planterait sur la lecture du fichier.
    """
    for candidate in (rapidocr_engine, mistral_engine, tesseract_engine, got_engine):
        if candidate is primary:
            continue
        try:
            if candidate.available():
                yield candidate
        except Exception:
            continue


def _read_page(image_path: Path, page_number: int, primary) -> tuple[_OcrRun, list[dict]]:
    warnings: list[dict] = []
    best = _run_once(primary, image_path, page_number)
    if best.error is not None or best.garbage > 0.3:
        image_exists = Path(image_path).is_file()
        for alternate in _fallback_engines(primary):
            # Moteur cloud : ne pas gaspiller un appel réseau sur un fichier absent.
            if alternate is mistral_engine and not image_exists:
                continue
            retry = _run_once(alternate, image_path, page_number)
            if retry.error is not None:
                continue
            if retry.score < best.score:
                warnings.append(
                    {
                        "code": "OCR_MOTEUR_REPLI",
                        "severity": "info",
                        "message": (
                            f"Page relue avec {retry.engine} : lecture {best.engine} peu fiable."
                        ),
                    }
                )
                best = retry
                break
    if best.error is not None:
        raise OcrError(f"OCR impossible avec {best.engine} : {best.error}")
    kept, dropped = filter_garbage(best.lines)
    if dropped:
        warnings.append(
            {
                "code": "OCR_BRUIT_ECARTE",
                "severity": "info",
                "message": f"{dropped} ligne(s) illisible(s) ignorée(s) ({best.engine}).",
            }
        )
        best.lines = kept
        best.text = "\n".join(line.text for line in kept)
        best.garbage = garbage_ratio(kept)
        best.quality = page_quality(kept)
    return best, warnings


def _save_preview(image: Image.Image, target: Path, max_width: int = 1700) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if image.width > max_width:
        ratio = max_width / float(image.width)
        image = image.resize((max_width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.save(target, format="PNG", optimize=True)


def _pdf_text_lines(page: fitz.Page, page_number: int) -> list[OcrLine]:
    payload = page.get_text("dict")
    width = page.rect.width or 1.0
    height = page.rect.height or 1.0
    words_by_line: dict[tuple[int, int], list[dict[str, object]]] = {}
    try:
        raw_words = page.get_text("words")
    except Exception:
        raw_words = []
    for x0, y0, x1, y1, word, block_no, line_no, _word_no in raw_words:
        token = re.sub(r"\s+", " ", word).strip()
        if not token:
            continue
        words_by_line.setdefault((int(block_no), int(line_no)), []).append(
            {
                "text": token,
                "x0": round(float(x0) / width, 5),
                "y0": round(float(y0) / height, 5),
                "x1": round(float(x1) / width, 5),
                "y1": round(float(y1) / height, 5),
            }
        )

    lines: list[OcrLine] = []
    for block_index, block in enumerate(payload.get("blocks", [])):
        if block.get("type") != 0:
            continue
        block_no = block.get("number")
        if not isinstance(block_no, int):
            block_no = block_index
        for line_index, line in enumerate(block.get("lines", [])):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            bbox = line.get("bbox")
            normalized = None
            if bbox and len(bbox) == 4:
                normalized = {
                    "x0": round(float(bbox[0]) / width, 5),
                    "y0": round(float(bbox[1]) / height, 5),
                    "x1": round(float(bbox[2]) / width, 5),
                    "y1": round(float(bbox[3]) / height, 5),
                }
            words = words_by_line.get((block_no, line_index), [])
            if not words:
                for span in line.get("spans", []):
                    span_text = re.sub(r"\s+", " ", span.get("text", "")).strip()
                    span_bbox = span.get("bbox")
                    if not span_text or not span_bbox or len(span_bbox) != 4:
                        continue
                    words.append(
                        {
                            "text": span_text,
                            "x0": round(float(span_bbox[0]) / width, 5),
                            "y0": round(float(span_bbox[1]) / height, 5),
                            "x1": round(float(span_bbox[2]) / width, 5),
                            "y1": round(float(span_bbox[3]) / height, 5),
                        }
                    )
            words.sort(key=lambda item: item["x0"])
            lines.append(
                OcrLine(
                    text=text,
                    page_number=page_number,
                    bbox=normalized,
                    confidence=None,
                    words=words if len(words) > 1 else [],
                    source="pdf-text",
                )
            )
    lines.sort(key=lambda item: ((item.bbox or {}).get("y0", 0), (item.bbox or {}).get("x0", 0)))
    return lines


def _normalize_rotated_bbox(bbox: dict[str, float] | None, rotation: int) -> dict[str, float] | None:
    if not bbox or not rotation:
        return bbox
    x0, y0, x1, y1 = bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"]
    rot = rotation % 360
    if rot == 90:
        return {"x0": round(1 - y1, 5), "y0": round(x0, 5), "x1": round(1 - y0, 5), "y1": round(x1, 5)}
    if rot == 180:
        return {"x0": round(1 - x1, 5), "y0": round(1 - y1, 5), "x1": round(1 - x0, 5), "y1": round(1 - y0, 5)}
    if rot == 270:
        return {"x0": round(y0, 5), "y0": round(1 - x1, 5), "x1": round(y1, 5), "y1": round(1 - x0, 5)}
    return bbox


def _process_pdf(
    path: Path,
    pages_dir: Path,
    images_prefix: str,
    progress,
    ocr_engine,
) -> DocumentOcr:
    try:
        document = fitz.open(str(path))
    except Exception as exc:
        raise OcrError(f"Le fichier PDF est illisible ou endommagé : {exc}") from exc
    if document.page_count == 0:
        raise OcrError("Le PDF ne contient aucune page.")
    if document.page_count > MAX_PAGES:
        raise OcrError(f"Le PDF contient {document.page_count} pages ; la limite est de {MAX_PAGES} pages.")

    pages: list[PageResult] = []
    warnings: list[dict] = []
    page_qualities: list[float] = []
    digital_pages = 0
    total_pages = document.page_count
    try:
        for index in range(total_pages):
            page = document.load_page(index)
            page_number = index + 1
            text = page.get_text("text")
            lines = _pdf_text_lines(page, page_number)
            image_name = f"page-{page_number:03d}.png"
            image_target = pages_dir / image_name
            image_rel = f"{images_prefix}/{image_name}"

            if _has_usable_text(text):
                digital_pages += 1
                page_qualities.append(1.0)
                pixmap = page.get_pixmap(dpi=settings.preview_dpi, colorspace=fitz.csRGB, alpha=False)
                pixmap.save(str(image_target))
                pages.append(
                    PageResult(
                        page_number=page_number,
                        image_path=image_rel,
                        text=text,
                        lines=lines,
                        engine="pdf-texte",
                        confidence=None,
                        width=pixmap.width,
                        height=pixmap.height,
                        rotation=0,
                    )
                )
                progress(page_number, total_pages, "texte PDF natif")
                continue

            pixmap = page.get_pixmap(dpi=settings.ocr_render_dpi, colorspace=fitz.csRGB, alpha=False)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                temp_path = Path(handle.name)
            try:
                pixmap.save(str(temp_path))
                image = Image.open(temp_path)
                prepared, rotation = prepare_image(image, deskew=ocr_engine is not rapidocr_engine)
                _save_preview(prepared, image_target)
                prepared_path = temp_path.with_name(temp_path.stem + "-prepared.png")
                prepared.save(prepared_path, format="PNG")
                try:
                    run, page_warnings = _read_page(prepared_path, page_number, ocr_engine)
                finally:
                    prepared_path.unlink(missing_ok=True)
                warnings.extend(page_warnings)
                page_qualities.append(run.quality)
                pages.append(
                    PageResult(
                        page_number=page_number,
                        image_path=image_rel,
                        text=run.text,
                        lines=run.lines,
                        engine=run.engine,
                        confidence=run.confidence,
                        width=prepared.width,
                        height=prepared.height,
                        rotation=rotation,
                        meta={"garbage_ratio": run.garbage, "quality": run.quality},
                    )
                )
            finally:
                temp_path.unlink(missing_ok=True)
            progress(page_number, total_pages, f"OCR {run.engine}")
    finally:
        document.close()

    combined = "\n".join(page.text for page in pages)
    if len(re.sub(r"\s+", "", combined)) < MIN_DOCUMENT_CHARS:
        raise OcrError(
            "Le document est illisible : presque aucun texte n'a pu être extrait. "
            "Réessayez avec une meilleure photo ou vérifiez la résolution du scan."
        )
    confidences = [page.confidence for page in pages if page.confidence is not None]
    meta = {
        "digital_pages": digital_pages,
        "ocr_pages": total_pages - digital_pages,
        "average_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "page_count": total_pages,
        "ocr_engine": pages[0].engine if pages else ocr_engine.name,
        "ocr_quality": round(sum(page_qualities) / len(page_qualities), 3) if page_qualities else None,
        "ocr_warnings": warnings,
    }
    return DocumentOcr(pages=pages, engine="pdf", text=combined, meta=meta)


def _process_image(path: Path, pages_dir: Path, images_prefix: str, ocr_engine) -> DocumentOcr:
    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as exc:
        raise OcrError(f"L'image est illisible : {exc}") from exc

    prepared, rotation = prepare_image(image, deskew=ocr_engine is not rapidocr_engine)
    image_name = "page-001.png"
    image_target = pages_dir / image_name
    _save_preview(prepared, image_target)
    prepared_path = pages_dir / "page-001-ocr.png"
    prepared.save(prepared_path, format="PNG")
    try:
        run, warnings = _read_page(prepared_path, 1, ocr_engine)
    finally:
        prepared_path.unlink(missing_ok=True)
    text, lines, confidence = run.text, run.lines, run.confidence
    if len(re.sub(r"\s+", "", text)) < MIN_DOCUMENT_CHARS:
        raise OcrError(
            "Le document est illisible : presque aucun texte n'a pu être extrait. "
            "Réessayez avec une photo plus nette, droite et suffisamment éclairée."
        )
    page = PageResult(
        page_number=1,
        image_path=f"{images_prefix}/{image_name}",
        text=text,
        lines=lines,
        engine=run.engine,
        confidence=confidence,
        width=prepared.width,
        height=prepared.height,
        rotation=rotation,
        meta={"garbage_ratio": run.garbage, "quality": run.quality},
    )
    return DocumentOcr(
        pages=[page],
        engine=run.engine,
        text=text,
        meta={
            "digital_pages": 0,
            "ocr_pages": 1,
            "average_confidence": confidence,
            "page_count": 1,
            "rotation": rotation,
            "ocr_engine": run.engine,
            "ocr_quality": run.quality,
            "ocr_warnings": warnings,
        },
    )


def process_document(path: Path, pages_dir: Path, images_prefix: str, progress=None) -> DocumentOcr:
    ocr_engine = _select_engine()

    def default_progress(current: int, total: int, label: str) -> None:
        return None

    callback = progress or default_progress
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _process_pdf(path, pages_dir, images_prefix, callback, ocr_engine)
    return _process_image(path, pages_dir, images_prefix, ocr_engine)
