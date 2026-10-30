from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_SPACES = re.compile(r"[\s\u00a0\u202f]+")
_LEGAL_SUFFIXES = {
    "sarl",
    "sarlau",
    "eurl",
    "snc",
    "spa",
    "scs",
    "sce",
    "ets",
    "etablissement",
    "etablissements",
    "ste",
    "societe",
}


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    replacements = {
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u202f": " ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def normalize_key(value: str) -> str:
    value = strip_accents(clean_text(value)).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return _SPACES.sub(" ", value).strip()


def name_key(value: str) -> str:
    tokens = normalize_key(value).split()
    filtered = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    return " ".join(filtered) if filtered else " ".join(tokens)


def normalize_reference(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = strip_accents(clean_text(value)).upper()
    cleaned = re.sub(r"[^A-Z0-9/_.-]+", "", cleaned)
    cleaned = cleaned.strip("._-/")
    return cleaned or None


def normalize_invoice_number(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = strip_accents(clean_text(value)).upper()
    cleaned = re.sub(r"[\s._/-]+", "", cleaned)
    return cleaned or None


_NUMBER_TOKEN = re.compile(
    r"(?<![\w])([+-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,4})?|[+-]?\d+(?:[.,]\d{1,4})?)(?![\w])"
)
_CURRENCY = re.compile(r"(?i)\b(dzd|da|dinar(?:s)?|dinars?|dinar\s+algerien|دج)\b")


def parse_decimal(raw: str | Decimal | int | float | None) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    text = clean_text(str(raw)).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = _CURRENCY.sub(" ", text)
    text = text.replace("%", " ").strip()
    text = re.sub(r"[^0-9,.\-+]", " ", text)
    text = re.sub(r"\s+", "", text)
    if not re.search(r"\d", text):
        return None
    if text.endswith("-") and not text.startswith("-"):
        negative = True
        text = text[:-1]
    sign = ""
    if text.startswith(("-", "+")):
        sign, text = text[0], text[1:]
    text = text.replace(" ", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts) > 2:
            text = "".join(parts[:-1]) + "." + parts[-1]
        else:
            text = text.replace(",", ".")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 2:
            text = "".join(parts[:-1]) + "." + parts[-1]
        elif len(parts[-1]) == 3 and 1 <= len(parts[0]) <= 3 and len(parts) == 2:
            text = "".join(parts)
    if text.count(".") > 1:
        head, _, tail = text.rpartition(".")
        text = head.replace(".", "") + "." + tail
    if sign == "-" or negative:
        text = "-" + text.lstrip("-")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


_DATE_PATTERNS = (
    re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?!\d)"),
)


def parse_date(raw: str | date | datetime | None) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = clean_text(str(raw))
    for index, pattern in enumerate(_DATE_PATTERNS):
        for match in pattern.finditer(text):
            try:
                if index == 0:
                    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
                else:
                    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
                if year < 100:
                    year += 2000
                if not (2000 <= year <= 2100):
                    continue
                return date(year, month, day)
            except ValueError:
                continue
    return None


def format_money_fr(value: Decimal | float | int | None, currency: str = "DZD") -> str:
    if value is None:
        return ""
    number = Decimal(str(value))
    formatted = f"{number:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{formatted} {currency}"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, sort_keys=True)
