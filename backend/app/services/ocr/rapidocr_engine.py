from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image

from .base import OcrLine

for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_THREAD_LIMIT"):
    os.environ.setdefault(_key, "1")


import numpy as np


_INFER_LOCK = threading.Lock()


class RapidOcrEngine:
    """Moteur OCR local RapidOCR.

    API v3 (rapidocr >= 3.x, modèles PaddleOCR PP-OCRv6 embarqués) par
    défaut, avec repli sur l'ancien paquet rapidocr_onnxruntime
    (PP-OCRv3/v4) si seulement celui-ci est installé.

    RapidOCR renvoie une boîte par segment de texte. On regroupe les segments
    dont le centre vertical est proche pour reconstruire les lignes du ticket,
    puis on conserve chaque segment comme « mot » positionné : les colonnes
    désignation / quantité / prix / total restent exploitables par le parseur.
    """

    name = "rapidocr"
    _MAX_SIDE = 1800

    def __init__(self) -> None:
        self._engine: Any | None = None
        self._api: str = "v3"

    def available(self) -> bool:
        try:
            import rapidocr  # noqa: F401  # API v3

            return True
        except Exception:
            pass
        try:
            import rapidocr_onnxruntime  # noqa: F401  # repli ancien paquet

            return True
        except Exception:
            return False

    def _load(self) -> Any:
        if self._engine is None:
            try:
                from rapidocr import RapidOCR

                self._engine = RapidOCR()
                self._api = "v3"
            except Exception:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR()
                self._api = "legacy"
        return self._engine

    def _reset(self) -> None:
        self._engine = None

    @staticmethod
    def _box(words: list[dict[str, Any]]) -> dict[str, float]:
        return {
            "x0": min(float(word["x0"]) for word in words),
            "y0": min(float(word["y0"]) for word in words),
            "x1": max(float(word["x1"]) for word in words),
            "y1": max(float(word["y1"]) for word in words),
        }

    def _group(
        self, boxes: list[dict[str, Any]], min_threshold: float = 0.004
    ) -> list[list[dict[str, Any]]]:
        if not boxes:
            return []
        heights = sorted(float(box["y1"]) - float(box["y0"]) for box in boxes)
        median_height = heights[len(heights) // 2] if heights else 0.0
        threshold = max(min_threshold, 0.55 * median_height)
        ordered = sorted(boxes, key=lambda box: ((float(box["y0"]) + float(box["y1"])) / 2, float(box["x0"])))
        groups: list[list[dict[str, Any]]] = []
        for box in ordered:
            center = (float(box["y0"]) + float(box["y1"])) / 2
            placed = False
            for group in groups:
                group_center = mean((float(item["y0"]) + float(item["y1"])) / 2 for item in group)
                if abs(center - group_center) <= threshold:
                    group.append(box)
                    placed = True
                    break
            if not placed:
                groups.append([box])
        return groups

    def _resize(self, image_path: str, max_side: int) -> tuple[str, int, int, Path | None]:
        """Réduit les photos trop grandes : ONNX manque de mémoire au-delà de ~2000 px."""
        try:
            with Image.open(image_path) as image:
                width, height = image.size
                if max(width, height) <= max_side:
                    return str(image_path), width, height, None
                ratio = max_side / float(max(width, height))
                resized = image.convert("RGB").resize(
                    (max(1, int(width * ratio)), max(1, int(height * ratio))),
                    Image.Resampling.LANCZOS,
                )
                target_width, target_height = resized.size
        except Exception:
            return str(image_path), 0, 0, None
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        handle.close()
        target = Path(handle.name)
        resized.save(target, format="PNG")
        return str(target), target_width, target_height, target

    def _segments(self, result: Any) -> list[tuple[Any, str, float]]:
        """Normalise la sortie des deux APIs en segments (boîte, texte, score)."""
        if self._api == "v3":
            txts = getattr(result, "txts", None)
            if not txts:
                return []
            boxes = getattr(result, "boxes", None)
            scores = getattr(result, "scores", None)
            if boxes is not None:
                arr = np.asarray(boxes)
                if arr.ndim == 3 and arr.shape[1:] == (4, 2):
                    boxes_iter = list(arr)
                else:
                    boxes_iter = [None] * len(txts)
            else:
                boxes_iter = [None] * len(txts)
            if scores is None:
                scores_iter: list[Any] = [None] * len(txts)
            else:
                scores_iter = list(scores)
            segments: list[tuple[Any, str, float]] = []
            for index, text in enumerate(txts):
                raw_text = str(text or "").strip()
                if not raw_text:
                    continue
                box = boxes_iter[index] if index < len(boxes_iter) else None
                score = scores_iter[index] if index < len(scores_iter) else None
                try:
                    score_value = float(score)
                except (TypeError, ValueError):
                    score_value = 0.0
                segments.append((box, raw_text, score_value))
            return segments
        # API legacy (rapidocr_onnxruntime) : liste de (box, text, score)
        raw = result[0] if isinstance(result, tuple) else result
        segments = []
        for entry in raw or []:
            box, text, score = entry[0], entry[1], entry[2]
            raw_text = str(text or "").strip()
            if not raw_text:
                continue
            try:
                score_value = float(score)
            except (TypeError, ValueError):
                score_value = 0.0
            segments.append((box, raw_text, score_value))
        return segments

    def _infer(self, image_path: str) -> tuple[list[tuple[Any, str, float]], str, int, int]:
        """Inférence ONNX, avec repli progressif si la mémoire manque.

        Un échec ONNX ("bad allocation") est fréquent sur les grosses photos :
        on recharge le modèle, puis on réduit l'image. La réduction ne doit pas
        être trop forte, sinon les lignes du tableau fusionnent et l'OCR devient
        inutilisable : on s'arrête à 1200 px de large minimum.
        """
        last_error: Exception | None = None
        for max_side in (self._MAX_SIDE, self._MAX_SIDE, max(1200, self._MAX_SIDE * 2 // 3)):
            path, width, height, temp = self._resize(image_path, max_side)
            try:
                with _INFER_LOCK:
                    result = self._load()(path)
                segments = self._segments(result)
                if segments:
                    return segments, path, width, height
            except Exception as exc:
                last_error = exc
                self._reset()
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)
        if last_error is not None:
            raise last_error
        return [], str(image_path), 0, 0

    def recognize(self, image_path: str, page_number: int = 1) -> tuple[str, list[OcrLine], float | None]:
        segments, _path, width, height = self._infer(image_path)
        if not segments:
            return "", [], None
        width = width or 1
        height = height or 1

        boxes: list[dict[str, Any]] = []
        for box, raw_text, score_value in segments:
            xs: list[float]
            ys: list[float]
            if box is not None:
                try:
                    points = np.asarray(box)
                    xs = [float(point[0]) for point in points]
                    ys = [float(point[1]) for point in points]
                except Exception:
                    xs = ys = []
                    continue
            else:
                xs = ys = [0.0]
            if not xs or not ys:
                continue
            boxes.append(
                {
                    "text": raw_text,
                    "x0": round(min(xs) / width, 5),
                    "y0": round(min(ys) / height, 5),
                    "x1": round(max(xs) / width, 5),
                    "y1": round(max(ys) / height, 5),
                    "confidence": score_value,
                }
            )

        lines: list[OcrLine] = []
        confidences: list[float] = []
        # Plus agressif pour les tickets (groupement plus serré)
        for group in self._group(boxes, min_threshold=4.0 / height):
            group = sorted(group, key=lambda box: float(box["x0"]))
            text = " ".join(str(box["text"]) for box in group)
            if not text.strip():
                continue
            bbox = self._box(group)
            scores = [float(box["confidence"]) for box in group if box["confidence"] is not None]
            line_confidence = round(mean(scores), 2) if scores else None
            if line_confidence is not None:
                confidences.append(line_confidence)
            lines.append(
                OcrLine(
                    text=text,
                    page_number=page_number,
                    bbox=bbox,
                    confidence=line_confidence,
                    words=[
                        {
                            "text": box["text"],
                            "x0": box["x0"],
                            "y0": box["y0"],
                            "x1": box["x1"],
                            "y1": box["y1"],
                        }
                        for box in group
                    ],
                    source="rapidocr",
                )
            )

        text = "\n".join(line.text for line in lines)
        page_confidence = round(mean(confidences), 2) if confidences else None
        return text, lines, page_confidence


engine = RapidOcrEngine()
