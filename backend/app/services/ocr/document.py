from __future__ import annotations

import re
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageOps

from ...config import settings
from .base import DocumentOcr, OcrError, OcrLine, PageResult
from .preprocessing import prepare_image
from .tesseract_engine import engine as tesseract_engine

MAX_PAGES = 60
MIN_DOCUMENT_CHARS = 25


def _has_usable_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return len(compact) >= 40 and len(re.findall(r"\d", compact)) >= 4


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
    lines: list[OcrLine] = []
    for block in payload.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
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
            words = []
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
            lines.append(
                OcrLine(
                    text=text,
                    page_number=page_number,
                    bbox=normalized,
                    confidence=None,
                    words=words if len(words) > 1 else [],
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
                prepared, rotation = prepare_image(image)
                _save_preview(prepared, image_target)
                prepared_path = temp_path.with_name(temp_path.stem + "-prepared.png")
                prepared.save(prepared_path, format="PNG")
                try:
                    text_ocr, ocr_lines, confidence = tesseract_engine.recognize(str(prepared_path), page_number)
                finally:
                    prepared_path.unlink(missing_ok=True)
                pages.append(
                    PageResult(
                        page_number=page_number,
                        image_path=image_rel,
                        text=text_ocr,
                        lines=ocr_lines,
                        engine="tesseract",
                        confidence=confidence,
                        width=prepared.width,
                        height=prepared.height,
                        rotation=rotation,
                    )
                )
            finally:
                temp_path.unlink(missing_ok=True)
            progress(page_number, total_pages, "OCR Tesseract")
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
    }
    return DocumentOcr(pages=pages, engine="pdf", text=combined, meta=meta)


def _process_image(path: Path, pages_dir: Path, images_prefix: str) -> DocumentOcr:
    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as exc:
        raise OcrError(f"L'image est illisible : {exc}") from exc

    prepared, rotation = prepare_image(image)
    image_name = "page-001.png"
    image_target = pages_dir / image_name
    _save_preview(prepared, image_target)
    prepared_path = pages_dir / "page-001-ocr.png"
    prepared.save(prepared_path, format="PNG")
    try:
        text, lines, confidence = tesseract_engine.recognize(str(prepared_path), 1)
    finally:
        prepared_path.unlink(missing_ok=True)
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
        engine="tesseract",
        confidence=confidence,
        width=prepared.width,
        height=prepared.height,
        rotation=rotation,
    )
    return DocumentOcr(
        pages=[page],
        engine="tesseract",
        text=text,
        meta={
            "digital_pages": 0,
            "ocr_pages": 1,
            "average_confidence": confidence,
            "page_count": 1,
            "rotation": rotation,
        },
    )


def process_document(path: Path, pages_dir: Path, images_prefix: str, progress=None) -> DocumentOcr:
    if settings.ocr_engine not in {"tesseract", "auto"}:
        raise OcrError(
            f"Moteur OCR local « {settings.ocr_engine} » non pris en charge. "
            "Utilisez TULIP_OCR_ENGINE=tesseract."
        )
    if not tesseract_engine.available():
        raise OcrError(
            "Tesseract est introuvable. Installez Tesseract OCR et vérifiez la variable TESSERACT_CMD."
        )

    def default_progress(current: int, total: int, label: str) -> None:
        return None

    callback = progress or default_progress
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _process_pdf(path, pages_dir, images_prefix, callback)
    return _process_image(path, pages_dir, images_prefix)
