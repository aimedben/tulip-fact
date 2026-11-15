"""Moteur OCR local GOT-OCR2_0 (stepfun-ai), spécialisé documents/tickets.

GOT-OCR2_0 est un petit modèle vision-langage (~580M paramètres) entraîné
spécifiquement pour l'OCR de documents : reçus, tickets, tableaux, formules.
Contrairement à Tesseract/RapidOCR, il « comprend » la mise en page : il
restitue les lignes dans l'ordre de lecture et gère bien les tickets multi-lignes
où les produits et les montants sont séparés.

100 % local, sans quota ni clé API. Le modèle (~1,7 Go) est téléchargé une
seule fois depuis Hugging Face puis mis en cache ; ensuite tout tourne hors
ligne. Sur CPU l'inférence prend quelques secondes par page — c'est le prix
d'une lecture bien plus fidèle des tickets.

La sortie étant du texte mis en forme (pas de boîtes par mot), on reconstruit
des OcrLines avec des bboxes approximées par ligne ; le parseur de tickets
n'a besoin que de l'ordre des lignes, et le parseur de tableaux standard
reste servi par RapidOCR/Tesseract en parallèle.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image

from ...config import settings
from .base import OcrLine

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_MODEL: Any | None = None
_TOKENIZER: Any | None = None
_LOAD_ERROR: str | None = None

MAX_SIDE = 1344  # GOT-OCR2 travaille nativement en ~1024-1344 px
MIN_CACHE_FREE_BYTES = 3 * 1024**3  # marge pour le modèle (~1,5 Go) + téléchargement


def _drive_free(path: Path) -> int:
    try:
        return shutil.disk_usage(str(path)).free
    except Exception:
        return 0


def _prepare_cache() -> None:
    """Pointe le cache Hugging Face vers un emplacement avec assez de place.

    Le modèle fait ~1,5 Go : sur un poste où C: est presque plein, on bascule
    automatiquement sur le disque le plus vaste (ex. E:) sauf si l'utilisateur
    a fixé TULIP_GOT_CACHE_DIR ou si le modèle est déjà en cache par défaut.
    À faire AVANT d'importer transformers.
    """
    configured = settings.got_ocr_cache_dir.strip()
    if configured:
        target = Path(configured).expanduser()
        target.mkdir(parents=True, exist_ok=True)
    else:
        default_home = Path(
            os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
        )
        repo_dir = default_home / "hub" / _model_cache_dirname()
        if repo_dir.exists() or _drive_free(default_home) >= MIN_CACHE_FREE_BYTES:
            return
        candidates: list[Path] = []
        for letter in ("E", "D", "F", "G", "C"):
            root = Path(f"{letter}:\\") / "tulip-hf-cache"
            if root.drive and Path(root.anchor).exists():
                candidates.append(root)
        candidates.sort(key=_drive_free, reverse=True)
        if not candidates or _drive_free(candidates[0]) < MIN_CACHE_FREE_BYTES:
            return
        target = candidates[0]
        target.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Cache Hugging Face déplacé vers %s (disque par défaut trop plein).", target
        )
    resolved = str(target.resolve())
    os.environ["HF_HOME"] = resolved
    os.environ["HF_HUB_CACHE"] = str((target / "hub").resolve())
    os.environ.setdefault("TRANSFORMERS_CACHE", str((target / "hub").resolve()))


def _model_cache_dirname() -> str:
    """Nom du dossier de cache HF pour le modèle (models--org--nom)."""
    return "models--" + settings.got_ocr_model.replace("/", "--")


# Le cache doit être décidé AVANT tout import de transformers/huggingface_hub
# (leurs constantes de chemins sont figées au premier import). Ce module étant
# importé par document.py avant tout autre usage de transformers, la préparation
# au niveau du module garantit le bon emplacement de cache.
_prepare_cache()


def _load_model() -> tuple[Any, Any]:
    """Charge GOT-OCR2 une seule fois (processus entier)."""
    global _MODEL, _TOKENIZER, _LOAD_ERROR
    if _MODEL is not None:
        return _MODEL, _TOKENIZER
    with _LOCK:
        if _MODEL is not None:
            return _MODEL, _TOKENIZER
        if _LOAD_ERROR:
            raise RuntimeError(_LOAD_ERROR)
        try:
            _prepare_cache()
            import torch  # noqa: F401
            from transformers import AutoModel, AutoTokenizer

            _apply_transformers_compat()
            logger.info("Chargement du modèle GOT-OCR2 (%s)...", settings.got_ocr_model)
            tokenizer = AutoTokenizer.from_pretrained(
                settings.got_ocr_model, trust_remote_code=True
            )
            model = AutoModel.from_pretrained(
                settings.got_ocr_model,
                trust_remote_code=True,
                device_map="cpu",
                torch_dtype="auto",  # poids natifs bfloat16 (~1,4 Go RAM, pas 2,8 en float32)
                low_cpu_mem_usage=True,
            )
            model.eval()
            _MODEL, _TOKENIZER = model, tokenizer
            logger.info("Modèle GOT-OCR2 prêt.")
            return _MODEL, _TOKENIZER
        except Exception as exc:  # noqa: BLE001
            _LOAD_ERROR = f"{type(exc).__name__}: {exc}"
            logger.error("Chargement GOT-OCR2 impossible : %s", _LOAD_ERROR)
            raise


def _resize(image_path: str) -> tuple[str, int, int, Path | None]:
    """Ramène l'image à une taille que GOT-OCR2 traite bien.

    Retourne (chemin, largeur, hauteur, fichier_temporaire_à_supprimer).
    """
    try:
        with Image.open(image_path) as image:
            width, height = image.size
            if max(width, height) <= MAX_SIDE:
                return str(image_path), width, height, None
            ratio = MAX_SIDE / float(max(width, height))
            resized = image.convert("RGB").resize(
                (max(1, int(width * ratio)), max(1, int(height * ratio))),
                Image.Resampling.LANCZOS,
            )
    except Exception:
        return str(image_path), 0, 0, None
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    handle.close()
    target = Path(handle.name)
    resized.save(target, format="PNG")
    return str(target), resized.width, resized.height, target


def _apply_transformers_compat() -> None:
    """Compatibilité transformers 5.x avec le code remote GOT-OCR2 (écrit pour 4.x).

    `prepare_inputs_for_generation` du modèle lit `past_key_values.seen_tokens`
    (attribut renommé en 5.x) et `get_max_length()` (lève ValueError sur un
    cache vide en 5.x). On restaure un comportement 4.x sur ces deux points ;
    GOT-OCR2 est le seul utilisateur de transformers dans ce process.
    """
    try:
        from transformers.cache_utils import DynamicCache
    except Exception:  # noqa: BLE001
        return
    if not hasattr(DynamicCache, "seen_tokens"):
        DynamicCache.seen_tokens = property(lambda self: self.get_seq_length())
    if not hasattr(DynamicCache, "_tulip_orig_get_max_length"):
        original = DynamicCache.get_max_length

        def safe_get_max_length(cache):
            try:
                return original(cache)
            except Exception:  # noqa: BLE001
                return None

        DynamicCache.get_max_length = safe_get_max_length
        DynamicCache._tulip_orig_get_max_length = original


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _cpu_compat_patches(model: Any) -> list[Any]:
    """Patchs neutralisant le CUDA forcé par le code remote de GOT-OCR2.

    modeling_GOT.py appelle `.cuda()`, `torch.autocast("cuda", ...)` et
    `.half()` en dur pendant `chat()`. Sous un torch compilé sans CUDA ces
    appels lèvent une erreur. On remplace, le temps de l'inférence seulement :
    - Tensor.cuda -> identité (les tenseurs restent sur CPU) ;
    - Tensor.half -> conversion vers le dtype du modèle (bfloat16 natif ;
      identité s'il est en float32) pour garder des dtypes cohérents ;
    - torch.autocast("cuda") -> context manager no-op (pas de cast implicite).
    """
    import contextlib
    import torch
    from unittest import mock

    try:
        model_dtype = next(model.parameters()).dtype
    except Exception:  # noqa: BLE001
        model_dtype = torch.float32

    return [
        mock.patch.object(torch.Tensor, "cuda", lambda self, *a, **k: self),
        mock.patch.object(torch.Tensor, "half", lambda self, *a, **k: self.to(model_dtype)),
        mock.patch.object(torch, "autocast", lambda *a, **k: contextlib.nullcontext()),
    ]


class GotOcrEngine:
    name = "got-ocr2"

    def available(self) -> bool:
        if not settings.got_ocr_enabled:
            return False
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401

            return True
        except Exception:
            return False

    def _infer(self, image_path: str) -> str:
        model, tokenizer = _load_model()
        prepared, _w, _h, temp = _resize(image_path)
        try:
            with _LOCK:
                if _cuda_available():
                    result = model.chat(tokenizer, prepared, ocr_type="format")
                else:
                    patches = _cpu_compat_patches(model)
                    for patch in patches:
                        patch.start()
                    try:
                        result = model.chat(tokenizer, prepared, ocr_type="format")
                    finally:
                        for patch in patches:
                            patch.stop()
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        return str(result or "")

    def recognize(self, image_path: str, page_number: int = 1) -> tuple[str, list[OcrLine], float | None]:
        try:
            text = self._infer(image_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Inférence GOT-OCR2 échouée : %s", exc)
            raise

        try:
            with Image.open(image_path) as image:
                width, height = image.size
        except Exception:
            width = height = 0
        width = width or 1
        height = height or 1

        lines: list[OcrLine] = []
        raw_lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        raw_lines = [line for line in raw_lines if line]
        step = 1.0 / max(1, len(raw_lines))
        for index, line_text in enumerate(raw_lines):
            bbox = {
                "x0": 0.01,
                "y0": round(index * step, 5),
                "x1": 0.99,
                "y1": round((index + 1) * step, 5),
            }
            lines.append(
                OcrLine(
                    text=line_text,
                    page_number=page_number,
                    bbox=bbox,
                    confidence=0.85,
                    words=[],
                    source="got-ocr2",
                )
            )
        page_confidence = round(mean([0.85] * len(lines)), 2) if lines else None
        return "\n".join(line.text for line in lines), lines, page_confidence


engine = GotOcrEngine()
