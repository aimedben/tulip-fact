from __future__ import annotations

from statistics import mean

import pytesseract
from PIL import Image
from pytesseract import Output

from ...config import settings
from .base import OcrLine
from .preprocessing import configure_tesseract


class TesseractEngine:
    name = "tesseract"

    def available(self) -> bool:
        try:
            configure_tesseract()
            return True
        except Exception:
            return False

    def recognize(self, image_path: str, page_number: int = 1) -> tuple[str, list[OcrLine], float | None]:
        configure_tesseract()
        image = Image.open(image_path)
        width, height = image.size
        config = f"--oem 1 --psm {settings.ocr_psm}"
        data = pytesseract.image_to_data(
            image,
            lang=settings.tesseract_langs,
            config=config,
            output_type=Output.DICT,
        )
        grouped: dict[tuple[int, int, int], list[dict]] = {}
        count = len(data.get("text", []))
        for index in range(count):
            word = (data["text"][index] or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][index])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < 0:
                conf = None
            key = (int(data["block_num"][index]), int(data["par_num"][index]), int(data["line_num"][index]))
            grouped.setdefault(key, []).append(
                {
                    "text": word,
                    "left": int(data["left"][index]),
                    "top": int(data["top"][index]),
                    "width": int(data["width"][index]),
                    "height": int(data["height"][index]),
                    "conf": conf,
                }
            )

        lines: list[OcrLine] = []
        confidences: list[float] = []
        for key in sorted(grouped.keys()):
            words = grouped[key]
            words.sort(key=lambda item: item["left"])
            text = " ".join(item["text"] for item in words)
            if not text.strip():
                continue
            x0 = min(item["left"] for item in words)
            y0 = min(item["top"] for item in words)
            x1 = max(item["left"] + item["width"] for item in words)
            y1 = max(item["top"] + item["height"] for item in words)
            confs = [item["conf"] for item in words if item["conf"] is not None]
            line_conf = round(mean(confs), 2) if confs else None
            if line_conf is not None:
                confidences.append(line_conf)
            lines.append(
                OcrLine(
                    text=text,
                    page_number=page_number,
                    bbox={
                        "x0": round(x0 / width, 5),
                        "y0": round(y0 / height, 5),
                        "x1": round(x1 / width, 5),
                        "y1": round(y1 / height, 5),
                    },
                    confidence=line_conf,
                    words=[
                        {
                            "text": item["text"],
                            "x0": round(item["left"] / width, 5),
                            "x1": round((item["left"] + item["width"]) / width, 5),
                            "y0": round(item["top"] / height, 5),
                            "y1": round((item["top"] + item["height"]) / height, 5),
                        }
                        for item in words
                    ],
                )
            )
        text = "\n".join(line.text for line in lines)
        page_confidence = round(mean(confidences), 2) if confidences else None
        return text, lines, page_confidence


engine = TesseractEngine()
