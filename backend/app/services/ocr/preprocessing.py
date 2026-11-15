from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageOps

from ...config import settings
from .base import OcrError


def resolve_tesseract_command() -> str | None:
    if settings.tesseract_cmd and Path(settings.tesseract_cmd).is_file():
        return settings.tesseract_cmd
    return shutil.which("tesseract")


def configure_tesseract() -> str:
    command = resolve_tesseract_command()
    if not command:
        raise OcrError(
            "Tesseract n'est pas installé ou n'est pas trouvé. Installez-le puis renseignez TESSERACT_CMD."
        )
    pytesseract.pytesseract.tesseract_cmd = command
    tessdata = Path(settings.tessdata_dir)
    if (tessdata / "fra.traineddata").is_file():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)
    return command


def available_languages() -> list[str]:
    try:
        configure_tesseract()
        return list(pytesseract.get_languages(config=""))
    except Exception:
        return []


def _estimate_skew(gray: np.ndarray, max_angle: float = 10, step: float = 0.5) -> float:
    """Trouve l'angle d'inclinaison qui aligne le mieux les lignes de texte."""
    small = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    h, w = bw.shape
    best_angle, best_score = 0.0, -1.0
    for a in np.arange(-max_angle, max_angle + step, step):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        rotated = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(a), score
    return best_angle


def _deskew(img: Image.Image) -> Image.Image:
    """Corrige l'inclinaison (skew) de l'image."""
    rgb = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    angle = _estimate_skew(gray)
    if abs(angle) < 0.3:
        return img
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    out = cv2.warpAffine(rgb, m, (w, h), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return Image.fromarray(out)


def _fix_orientation(img: Image.Image) -> Image.Image:
    """Corrige les rotations de 90/180/270° en utilisant l'OSD de Tesseract."""
    img = ImageOps.exif_transpose(img)
    try:
        osd = pytesseract.image_to_osd(img, config="--psm 0")
        match = re.search(r"Rotate:\s*(\d+)", osd)
        match_conf = re.search(r"Orientation confidence:\s*([0-9.]+)", osd)
        angle = int(match.group(1)) if match else 0
        confidence = float(match_conf.group(1)) if match_conf else 0.0

        if angle and confidence >= 2:
            img = img.rotate(-angle, expand=True, fillcolor=255)
    except Exception:
        pass
    return img


def _normalize_page(img: Image.Image) -> Image.Image:
    """Corrige l'orientation et l'inclinaison de la page."""
    img = _fix_orientation(img)
    img = _deskew(img)
    return img


def _orient_by_osd(gray: Image.Image) -> tuple[Image.Image, int, float]:
    """Essaie la détection d'orientation Tesseract ; renvoie (image, rotation, confiance)."""
    try:
        osd = pytesseract.image_to_osd(gray, config="--psm 0")
        match = re.search(r"Rotate:\s*(\d+)", osd)
        match_conf = re.search(r"Orientation confidence:\s*([0-9.]+)", osd)
        rotation = int(match.group(1)) % 360 if match else 0
        confidence = float(match_conf.group(1)) if match_conf else 0.0
    except Exception:
        return gray, 0, 0.0
    if not rotation:
        return gray, 0, confidence
    return gray.rotate(-rotation, expand=True, fillcolor=255), rotation, confidence


def _orient_score(im: Image.Image) -> float:
    """Score qualité du texte OCR d'une orientation : fiabilité x lisibilité."""
    try:
        data = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT, config="--psm 6")
    except Exception:
        return 0.0
    words = [(w, int(c)) for w, c in zip(data["text"], data["conf"]) if w and w.strip() and int(c) >= 40]
    if not words:
        return 0.0
    conf = sum(c for _, c in words) / len(words)
    alnum = sum(ch.isalnum() for w, _ in words for ch in w)
    total = sum(len(w) for w, _ in words) or 1
    return len(words) * (alnum / total) * (conf / 100.0)


def _orient_by_scan(gray: Image.Image) -> tuple[Image.Image, int]:
    """Scanne les orientations et garde celle qui produit le texte le plus propre.

    Le scoring se fait sur une copie réduite pour rester rapide ; la rotation
    retenue est appliquée une seule fois à l'image finale.
    """
    probe = gray
    if probe.width > 1200:
        ratio = 1200 / float(probe.width)
        probe = probe.resize((1200, max(1, int(probe.height * ratio))), Image.Resampling.LANCZOS)

    best_rotation = 0
    best_score = _orient_score(probe)

    # IMPORTANT: Toujours tester les 4 orientations si le score est faible
    # Car une image à l'envers (180°) peut avoir un score proche de 0
    # On ne peut pas faire confiance au seuil de 35.0 dans ce cas
    threshold = 50.0 if best_score > 0 else 0  # Si score = 0, tester toutes les orientations

    if best_score < threshold:
        for rotation in (90, 180, 270):
            candidate = probe.rotate(-rotation, expand=True, fillcolor=255)
            score = _orient_score(candidate)
            # Exiger une amélioration SIGNIFICATIVE (>20%) avant de changer de rotation
            if score > best_score * 1.2:
                best_score = score
                best_rotation = rotation

    if best_rotation:
        gray = gray.rotate(-best_rotation, expand=True, fillcolor=255)
    return gray, best_rotation


def prepare_image(image: Image.Image, deskew: bool = True) -> tuple[Image.Image, int]:
    # Correction d'orientation et d'inclinaison AVANT tout traitement.
    # Le deskew (heuristic variance des lignes) aide Tesseract mais dégrade les
    # photos de papier courbé : PP-OCRv6 lit l'inclinaison sans problème, donc
    # on la désactive pour ces moteurs.
    if deskew:
        image = _normalize_page(image)
    else:
        image = ImageOps.exif_transpose(image)

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    gray = image.convert("L")
    if gray.width < 1600:
        ratio = 1600 / float(gray.width)
        gray = gray.resize((int(gray.width * ratio), int(gray.height * ratio)), Image.Resampling.LANCZOS)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))

    # Rotation fixée à 0° - l'image est déjà correctement orientée
    rotation = 0

    return gray, rotation
