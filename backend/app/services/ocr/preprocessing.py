from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

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


def prepare_image(image: Image.Image) -> tuple[Image.Image, int]:
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    gray = image.convert("L")
    if gray.width < 1600:
        ratio = 1600 / float(gray.width)
        gray = gray.resize((int(gray.width * ratio), int(gray.height * ratio)), Image.Resampling.LANCZOS)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))

    rotation = 0
    try:
        osd = pytesseract.image_to_osd(gray, config="--psm 0")
        match = re.search(r"Rotate:\s*(\d+)", osd)
        if match:
            rotation = int(match.group(1)) % 360
    except Exception:
        rotation = 0
    if rotation:
        gray = gray.rotate(-rotation, expand=True, fillcolor=255)
    return gray, rotation
