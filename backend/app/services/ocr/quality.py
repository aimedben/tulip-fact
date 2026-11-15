"""Contrôle de qualité du texte OCR.

Tesseract, sur une photo floue ou mal orientée, produit parfois des lignes de bruit
du type « 2 Mama Ce i boat (c) *. d »Y SR NL Se mA ... ». Ces lignes polluent
l'extraction et l'interface : on les note puis on les écarte, et si la page entière
est illisible on bascule automatiquement sur l'autre moteur OCR.
"""

from __future__ import annotations

import re
from statistics import mean

from .base import OcrLine

JUNK_CHARS = re.compile(r"[^0-9A-Za-zÀ-ÿ .,;:/%°#\-+()&'*€$=_]")
TOKEN_CLEAN = re.compile(r"^[^\wÀ-ÿ]+|[^\wÀ-ÿ]+$")

# Lignes à ne jamais écarter, quels que soient leurs symboles : montants
# («150,00», «1 060,00»), colisages («1X8», «2X40», «1 × 10 = 10» â le
# multiplicateur × et le = sont comptés comme bruit par JUNK_CHARS alors que
# ce sont des données métier « quantité × contenu = total, prix ».
AMOUNT_RE = re.compile(r"\b\d{1,3}(?:[ \u00a0\u202f]\d{3})*[.,]\d{2}\b")
QUANTITY_RE = re.compile(r"\d+\s*[xX×]\s*\d")

# Un « vrai mot » de 5 lettres consécutives (BURGER, FOURRE, EXTRA...) avec
# à peine de ponctuation suspecte : désignation produit probable, pas du
# bruit. Le bruit OCR type « Mama Ce i boat » ne forme que des mots de 4
# lettres au plus, les désignations réelles contiennent presque toujours un
# segment plus long.
WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]{5,}")


def _junk_ratio(text: str) -> float:
    return len(JUNK_CHARS.findall(text)) / max(1, len(text))


def line_quality(text: str) -> float:
    """Note entre 0 (bruit pur) et 1 (texte propre)."""
    stripped = text.strip()
    if not stripped:
        return 0.0
    tokens = [token for token in stripped.split() if token]
    if not tokens:
        return 0.0
    junk = _junk_ratio(stripped)
    short = sum(1 for token in tokens if len(TOKEN_CLEAN.sub("", token)) <= 2) / len(tokens)
    alnum = len(re.findall(r"[0-9A-Za-zÀ-ÿ]", stripped)) / len(stripped)
    letters = re.findall(r"[A-Za-zÀ-ÿ]", stripped)
    vowels = re.findall(r"[aeiouyàâäéèêëîïôöùûüÿAEIOUYÀÂÄÉÈÊËÎÏÔÖÙÛÜŸ]", stripped)
    vowel_ratio = (len(vowels) / len(letters)) if letters else 1.0
    score = 1.0 - (0.7 * junk + 0.35 * short + 0.25 * max(0.0, 0.6 - alnum))
    if letters and vowel_ratio < 0.12 and len(letters) > 8:
        score -= 0.35
    return max(0.0, min(1.0, score))


def is_garbage(text: str, threshold: float = 0.4) -> bool:
    """Heuristiques de bruit : symboles anormaux, mots d'une ou deux lettres partout."""
    stripped = text.strip()
    if not stripped:
        return True
    # Les montants et colisages sont des données métier, jamais du bruit.
    if AMOUNT_RE.search(stripped) or QUANTITY_RE.search(stripped):
        return False
    # Une ligne portant un vrai mot (PAIN, FOURRE, BURGER...) quasi sans
    # symboles anormaux est une désignation probable : la garder, le parseur
    # tranchera. Les lignes de bruit réel affichent du junk (« æ * », « � »).
    if WORD_RE.search(stripped) and _junk_ratio(stripped) <= 0.02:
        return False
    tokens = [token for token in stripped.split() if token]
    if not tokens:
        return True
    cleaned = [TOKEN_CLEAN.sub("", token) for token in tokens]
    has_digit = bool(re.search(r"\d", stripped))
    if not has_digit and all(len(token) <= 2 for token in cleaned):
        return True
    junk = _junk_ratio(stripped)
    if junk > 0.08 and len(tokens) >= 3:
        return True
    short = sum(1 for token in cleaned if len(token) <= 2) / len(tokens)
    average = sum(len(token) for token in cleaned) / len(tokens)
    if short > 0.45 and average < 3.5 and len(tokens) >= 4:
        return True
    if average < 2.0 and len(tokens) >= 3:
        return True
    return line_quality(stripped) < threshold


def filter_garbage(lines: list[OcrLine], threshold: float = 0.4) -> tuple[list[OcrLine], int]:
    kept = [line for line in lines if not is_garbage(line.text, threshold)]
    return kept, len(lines) - len(kept)


def page_quality(lines: list[OcrLine]) -> float:
    if not lines:
        return 0.0
    return round(mean(line_quality(line.text) for line in lines), 3)


def garbage_ratio(lines: list[OcrLine], threshold: float = 0.4) -> float:
    if not lines:
        return 1.0
    return sum(1 for line in lines if is_garbage(line.text, threshold)) / len(lines)
