from __future__ import annotations

import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from .firebird import FirebirdError, FirebirdIsql, firebird_client

SUPPLIER_FILTER = "C.FRCLT = -1 AND C.ETAT = 0"
# Natures actives a exposer dans le catalogue. La nature 4 existe chez
# SUPERETTE (148 articles actifs, 137 avec code-barres, 101 deja vendus) :
# l'exclure faisait disparaitre de vrais articles visibles dans Tulip.
PRODUCT_FILTER = "P.ETAT = 0 AND P.NATURE IN (1, 2, 4, 5, 10)"
TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,30}$")


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _decimal(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None


def _number(value: str | None) -> float | None:
    parsed = _decimal(value)
    return float(parsed) if parsed is not None else None


def _compact(value: str | None) -> str | None:
    parsed = _decimal(value)
    if parsed is None:
        return _text(value)
    normalized = parsed.normalize()
    return format(normalized, "f")


def _like(value: str) -> str:
    escaped = (
        value.strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace("'", "''")
    )
    return f"'%{escaped}%'"


def _page(page: int, page_size: int) -> tuple[int, int, int]:
    page = max(1, int(page))
    page_size = min(500, max(1, int(page_size)))
    return page, page_size, (page - 1) * page_size


class TulipCatalog:
    def __init__(self, client: FirebirdIsql | None = None) -> None:
        self.client = client or firebird_client()

    def status(self) -> dict[str, Any]:
        config = self.client.config
        status = config.public_status()
        status.update(
            {
                "connected": False,
                "engine_version": None,
                "latency_ms": None,
                "error": None,
            }
        )
        if not config.configured:
            status["error"] = "Tulip Firebird n'est pas configuré."
            return status
        started = time.perf_counter()
        try:
            rows = self.client.query(
                "SELECT rdb$get_context('SYSTEM','ENGINE_VERSION') AS ENGINE_VERSION FROM rdb$database",
                ("ENGINE_VERSION",),
            )
            status["connected"] = True
            status["engine_version"] = _text(rows[0].get("ENGINE_VERSION")) if rows else None
        except FirebirdError as exc:
            status["error"] = str(exc)
        status["latency_ms"] = round((time.perf_counter() - started) * 1000)
        return status

    def suppliers(self, q: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        page, page_size, offset = _page(page, page_size)
        condition = SUPPLIER_FILTER
        if q and q.strip():
            pattern = _like(q)
            condition += (
                " AND ("
                "UPPER(CAST(C.RSOUNOM AS VARCHAR(255))) LIKE " + pattern + " ESCAPE '\\' OR "
                "UPPER(CAST(C.PRINCIPAL AS VARCHAR(30))) LIKE " + pattern + " ESCAPE '\\' OR "
                "CAST(C.CODE AS VARCHAR(20)) LIKE " + pattern + " ESCAPE '\\'"
                ")"
            )
        total_rows = self.client.query(
            f"SELECT COUNT(*) AS TOTAL FROM CLIENTS C WHERE {condition}",
            ("TOTAL",),
        )
        rows = self.client.query(
            f"""
SELECT FIRST {page_size} SKIP {offset}
  CAST(C.CODE AS VARCHAR(20)) AS CODE,
  CAST(C.PRINCIPAL AS VARCHAR(30)) AS PRINCIPAL,
  CAST(C.RSOUNOM AS VARCHAR(255)) AS NAME,
  CAST(C.ADRESSE AS VARCHAR(255)) AS ADDRESS1,
  CAST(C.ZIPCODE AS VARCHAR(20)) AS ZIPCODE,
  CAST(C.CITY AS VARCHAR(100)) AS CITY,
  CAST(C.TEL AS VARCHAR(50)) AS PHONE,
  CAST(C.EMAIL AS VARCHAR(100)) AS EMAIL,
  CAST(C.NRC AS VARCHAR(50)) AS NRC,
  CAST(C.MF AS VARCHAR(50)) AS MF,
  CAST(C.NIS AS VARCHAR(50)) AS NIS
FROM CLIENTS C
WHERE {condition}
ORDER BY C.RSOUNOM, C.CODE
""".strip(),
            ("CODE", "PRINCIPAL", "NAME", "ADDRESS1", "ZIPCODE", "CITY", "PHONE", "EMAIL", "NRC", "MF", "NIS"),
        )
        total = _number(total_rows[0].get("TOTAL")) if total_rows else 0
        return {
            "source": "tulip",
            "items": [self._supplier_payload(row) for row in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    def products(self, q: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        page, page_size, offset = _page(page, page_size)
        condition = PRODUCT_FILTER
        if q and q.strip():
            pattern = _like(q)
            condition += (
                " AND ("
                "UPPER(CAST(P.REF AS VARCHAR(64))) LIKE " + pattern + " ESCAPE '\\' OR "
                "UPPER(CAST(P.D AS VARCHAR(255))) LIKE " + pattern + " ESCAPE '\\' OR "
                "UPPER(CAST(P.REF_O AS VARCHAR(64))) LIKE " + pattern + " ESCAPE '\\' OR "
                "CAST(P.CODE AS VARCHAR(20)) LIKE " + pattern + " ESCAPE '\\' OR "
                "EXISTS (SELECT 1 FROM CODEBARRE C WHERE C.PRODUIT = P.CODE "
                "AND UPPER(CAST(C.CODEBARRE AS VARCHAR(64))) LIKE " + pattern + " ESCAPE '\\')"
                ")"
            )
        total_rows = self.client.query(
            f"SELECT COUNT(*) AS TOTAL FROM PRODUITS P WHERE {condition}",
            ("TOTAL",),
        )
        rows = self.client.query(
            f"""
SELECT FIRST {page_size} SKIP {offset}
  CAST(P.CODE AS VARCHAR(20)) AS CODE,
  CAST(P.REF AS VARCHAR(64)) AS REF,
  CAST(P.D AS VARCHAR(255)) AS DESIGNATION,
  CAST(P.REF_O AS VARCHAR(64)) AS REF_O,
  CAST(P.LOT AS VARCHAR(20)) AS LOT,
  CAST(P.TVA AS VARCHAR(30)) AS TVA,
  CAST(P.RECEP AS VARCHAR(30)) AS RECEP,
  CAST(P.MPRIXRECEP AS VARCHAR(30)) AS MPRIXRECEP,
  CAST(P.STOCK AS VARCHAR(30)) AS STOCK,
  CAST(P.CMUP AS VARCHAR(30)) AS CMUP,
  CAST(P.UM AS VARCHAR(20)) AS UM,
  CAST((SELECT FIRST 1 C.CODEBARRE FROM CODEBARRE C WHERE C.PRODUIT = P.CODE ORDER BY C.CODEBARRE) AS VARCHAR(255)) AS BARCODE
FROM PRODUITS P
WHERE {condition}
ORDER BY P.D, P.CODE
""".strip(),
            (
                "CODE",
                "REF",
                "DESIGNATION",
                "REF_O",
                "LOT",
                "TVA",
                "RECEP",
                "MPRIXRECEP",
                "STOCK",
                "CMUP",
                "UM",
                "BARCODE",
            ),
        )
        total = _number(total_rows[0].get("TOTAL")) if total_rows else 0
        return {
            "source": "tulip",
            "items": [self._product_payload(row) for row in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    def product_by_code(self, code: str) -> dict[str, Any] | None:
        code = code.strip()
        if not code:
            return None
        rows = self.client.query(
            f"""
SELECT FIRST 1
  CAST(P.CODE AS VARCHAR(20)) AS CODE,
  CAST(P.REF AS VARCHAR(64)) AS REF,
  CAST(P.D AS VARCHAR(255)) AS DESIGNATION,
  CAST(P.REF_O AS VARCHAR(64)) AS REF_O,
  CAST(P.LOT AS VARCHAR(20)) AS LOT,
  CAST(P.TVA AS VARCHAR(30)) AS TVA,
  CAST(P.RECEP AS VARCHAR(30)) AS RECEP,
  CAST(P.MPRIXRECEP AS VARCHAR(30)) AS MPRIXRECEP,
  CAST(P.STOCK AS VARCHAR(30)) AS STOCK,
  CAST(P.CMUP AS VARCHAR(30)) AS CMUP,
  CAST(P.UM AS VARCHAR(20)) AS UM,
  CAST((SELECT FIRST 1 C.CODEBARRE FROM CODEBARRE C WHERE C.PRODUIT = P.CODE ORDER BY C.CODEBARRE) AS VARCHAR(255)) AS BARCODE
FROM PRODUITS P
WHERE {PRODUCT_FILTER} AND (CAST(P.CODE AS VARCHAR(20)) = '{code.replace("'", "''")}' OR P.REF = '{code.replace("'", "''")}')
""".strip(),
            (
                "CODE",
                "REF",
                "DESIGNATION",
                "REF_O",
                "LOT",
                "TVA",
                "RECEP",
                "MPRIXRECEP",
                "STOCK",
                "CMUP",
                "UM",
                "BARCODE",
            ),
        )
        return self._product_payload(rows[0]) if rows else None

    def summary(self) -> dict[str, Any]:
        def count(sql: str) -> int:
            rows = self.client.query(sql, ("TOTAL",))
            return int(_number(rows[0].get("TOTAL")) or 0)

        return {
            "suppliers": count(f"SELECT COUNT(*) AS TOTAL FROM CLIENTS C WHERE {SUPPLIER_FILTER}"),
            "products": count(f"SELECT COUNT(*) AS TOTAL FROM PRODUITS P WHERE {PRODUCT_FILTER}"),
            "be_total": count("SELECT COUNT(*) AS TOTAL FROM BE"),
            "be_dette": count("SELECT COUNT(*) AS TOTAL FROM BE WHERE DETTE = 1"),
        }

    def be_documents(self, q: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        page, page_size, offset = _page(page, page_size)
        condition = "B.CMP = 0"
        if q and q.strip():
            pattern = _like(q)
            condition += (
                " AND ("
                "CAST(B.NUMERO AS VARCHAR(20)) LIKE " + pattern + " ESCAPE '\\' OR "
                "UPPER(CAST(B.NBC AS VARCHAR(64))) LIKE " + pattern + " ESCAPE '\\' OR "
                "UPPER(CAST(B.LIVFACT AS VARCHAR(64))) LIKE " + pattern + " ESCAPE '\\' OR "
                "UPPER(CAST(C.RSOUNOM AS VARCHAR(255))) LIKE " + pattern + " ESCAPE '\\' OR "
                "CAST(B.FOURNISSEUR AS VARCHAR(20)) LIKE " + pattern + " ESCAPE '\\'"
                ")"
            )
        total_rows = self.client.query(
            f"SELECT COUNT(*) AS TOTAL FROM BE B LEFT JOIN CLIENTS C ON C.CODE = B.FOURNISSEUR WHERE {condition}",
            ("TOTAL",),
        )
        rows = self.client.query(
            f"""
SELECT FIRST {page_size} SKIP {offset}
  CAST(B.CODE AS VARCHAR(20)) AS CODE,
  CAST(B.NUMERO AS VARCHAR(20)) AS NUMERO,
  CAST(B.NBC AS VARCHAR(64)) AS NBC,
  CAST(B.LIVFACT AS VARCHAR(64)) AS LIVFACT,
  CAST(B.FOURNISSEUR AS VARCHAR(20)) AS SUPPLIER_CODE,
  CAST(C.RSOUNOM AS VARCHAR(255)) AS SUPPLIER_NAME,
  CAST(B.OPDATE AS VARCHAR(32)) AS OPDATE,
  CAST(B.DATEBC AS VARCHAR(32)) AS DATEBC,
  CAST(B.DETTE AS VARCHAR(4)) AS DETTE,
  CAST(B.STOCK AS VARCHAR(4)) AS STOCK,
  CAST(B.MHT AS VARCHAR(30)) AS MHT,
  CAST(B.MTVA AS VARCHAR(30)) AS MTVA,
  CAST(B.TTC AS VARCHAR(30)) AS TTC
FROM BE B
LEFT JOIN CLIENTS C ON C.CODE = B.FOURNISSEUR
WHERE {condition}
ORDER BY B.OPDATE DESC, B.NUMERO DESC, B.CODE DESC
""".strip(),
            (
                "CODE",
                "NUMERO",
                "NBC",
                "LIVFACT",
                "SUPPLIER_CODE",
                "SUPPLIER_NAME",
                "OPDATE",
                "DATEBC",
                "DETTE",
                "STOCK",
                "MHT",
                "MTVA",
                "TTC",
            ),
        )
        total = _number(total_rows[0].get("TOTAL")) if total_rows else 0
        return {
            "source": "tulip",
            "items": [self._be_payload(row) for row in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    def be_document(self, code: str | int) -> dict[str, Any] | None:
        code = str(code).strip()
        if not code:
            return None
        safe = code.replace("'", "''")
        header_rows = self.client.query(
            f"""
SELECT FIRST 1
  CAST(B.CODE AS VARCHAR(20)) AS CODE,
  CAST(B.NUMERO AS VARCHAR(20)) AS NUMERO,
  CAST(B.NBC AS VARCHAR(64)) AS NBC,
  CAST(B.LIVFACT AS VARCHAR(64)) AS LIVFACT,
  CAST(B.FOURNISSEUR AS VARCHAR(20)) AS SUPPLIER_CODE,
  CAST(C.RSOUNOM AS VARCHAR(255)) AS SUPPLIER_NAME,
  CAST(B.OPDATE AS VARCHAR(32)) AS OPDATE,
  CAST(B.DATEBC AS VARCHAR(32)) AS DATEBC,
  CAST(B.DETTE AS VARCHAR(4)) AS DETTE,
  CAST(B.STOCK AS VARCHAR(4)) AS STOCK,
  CAST(B.MHT AS VARCHAR(30)) AS MHT,
  CAST(B.MTVA AS VARCHAR(30)) AS MTVA,
  CAST(B.TTC AS VARCHAR(30)) AS TTC
FROM BE B
LEFT JOIN CLIENTS C ON C.CODE = B.FOURNISSEUR
WHERE B.CODE = '{safe}'
""".strip(),
            (
                "CODE",
                "NUMERO",
                "NBC",
                "LIVFACT",
                "SUPPLIER_CODE",
                "SUPPLIER_NAME",
                "OPDATE",
                "DATEBC",
                "DETTE",
                "STOCK",
                "MHT",
                "MTVA",
                "TTC",
            ),
        )
        if not header_rows:
            return None
        payload = self._be_payload(header_rows[0])
        line_rows = self.client.query(
            f"""
SELECT
  CAST(D.LINE AS VARCHAR(20)) AS LINE,
  CAST(D.PRODUIT AS VARCHAR(20)) AS PRODUCT_CODE,
  CAST(D.TVA AS VARCHAR(30)) AS TVA,
  CAST(D.QTE AS VARCHAR(30)) AS QTE,
  CAST(D.QX AS VARCHAR(30)) AS QX,
  CAST(D.PUHT AS VARCHAR(30)) AS PUHT,
  CAST(D.PRIXHT AS VARCHAR(30)) AS PRIXHT,
  CAST(D.HT AS VARCHAR(30)) AS HT
FROM DETAILSBR D
WHERE D.PARENT = '{safe}'
ORDER BY D.ITEM
""".strip(),
            ("LINE", "PRODUCT_CODE", "TVA", "QTE", "QX", "PUHT", "PRIXHT", "HT"),
        )
        lines: list[dict[str, Any]] = []
        for row in line_rows:
            product_code = _text(row.get("PRODUCT_CODE"))
            designation = None
            if product_code:
                product_rows = self.client.query(
                    f"SELECT FIRST 1 CAST(P.D AS VARCHAR(255)) AS DESIGNATION FROM PRODUITS P WHERE P.CODE = {product_code}",
                    ("DESIGNATION",),
                )
                designation = _text(product_rows[0].get("DESIGNATION")) if product_rows else None
            lines.append(
                {
                    "line": _text(row.get("LINE")),
                    "product_code": product_code,
                    "designation": designation,
                    "vat_rate": _number(row.get("TVA")),
                    "quantity": _number(row.get("QTE")),
                    "quantity_units": _number(row.get("QX")),
                    "unit_price": _number(row.get("PUHT")),
                    "unit_price_net": _number(row.get("PRIXHT")),
                    "total_ht": _number(row.get("HT")),
                }
            )
        payload["lines"] = lines
        return payload

    @staticmethod
    def _be_payload(row: dict[str, str | None]) -> dict[str, Any]:
        code = _text(row.get("CODE"))
        supplier_name = _text(row.get("SUPPLIER_NAME"))
        supplier_code = _text(row.get("SUPPLIER_CODE"))
        return {
            "id": int(code) if code else None,
            "numero": _number(row.get("NUMERO")),
            "nbc": _text(row.get("NBC")),
            "livfact": _text(row.get("LIVFACT")),
            "supplier_code": supplier_code,
            "supplier_id": int(supplier_code) if supplier_code else None,
            "supplier_name": supplier_name,
            "opdate": _text(row.get("OPDATE")),
            "datebc": _text(row.get("DATEBC")),
            "dette": (row.get("DETTE") or "0").strip() == "1",
            "stock": (row.get("STOCK") or "0").strip() == "1",
            "mht": _number(row.get("MHT")),
            "mtva": _number(row.get("MTVA")),
            "ttc": _number(row.get("TTC")),
        }

    @staticmethod
    def _supplier_payload(row: dict[str, str | None]) -> dict[str, Any]:
        address = " ".join(
            part for part in (_text(row.get("ADDRESS1")), _text(row.get("ZIPCODE")), _text(row.get("CITY"))) if part
        ) or None
        code = _text(row.get("CODE"))
        principal = _text(row.get("PRINCIPAL")) or code
        return {
            "id": int(code) if code else None,
            "tulip_id": int(code) if code else None,
            "tulip_code": code,
            "code": principal,
            "account_code": principal,
            "name": _text(row.get("NAME")) or principal or "",
            "name_variants": [],
            "tax_id": _text(row.get("NRC")),
            "tax_ids": {key.lower(): _text(row.get(key)) for key in ("NRC", "MF", "NIS")},
            "phone": _text(row.get("PHONE")),
            "email": _text(row.get("EMAIL")),
            "address": address,
            "city": _text(row.get("CITY")),
            "notes": None,
            "active": True,
            "source": "tulip",
        }

    @staticmethod
    def _product_payload(row: dict[str, str | None]) -> dict[str, Any]:
        code = _text(row.get("CODE"))
        ref = _text(row.get("REF"))
        return {
            "id": int(code) if code else None,
            "tulip_id": int(code) if code else None,
            "tulip_code": ref or code,
            "ref": ref,
            "reference": ref,
            "supplier_ref": _text(row.get("REF_O")),
            "barcode": _text(row.get("BARCODE")),
            "designation": _text(row.get("DESIGNATION")) or ref or code or "",
            "brand": None,
            "packaging": _compact(row.get("RECEP")),
            "stock_unit": _text(row.get("UM")),
            "default_vat_rate": _number(row.get("TVA")),
            "active": True,
            "source": "tulip",
            "lot_number": _text(row.get("LOT")),
            "stock": _number(row.get("STOCK")),
            "cmup": _number(row.get("CMUP")),
            "purchase_factor": _number(row.get("RECEP")),
            "purchase_price_factor": _number(row.get("MPRIXRECEP")),
        }

    @staticmethod
    def _check_table_name(name: str) -> None:
        if not TABLE_NAME_PATTERN.match(name or ""):
            raise FirebirdError("Nom de table invalide.")

    def tables(self, with_rows: bool = True) -> list[dict[str, Any]]:
        rows = self.client.query(
            """
SELECT CAST(R.RDB$RELATION_NAME AS VARCHAR(92)) AS NAME
FROM RDB$RELATIONS R
WHERE R.RDB$SYSTEM_FLAG = 0 AND R.RDB$VIEW_BLR IS NULL
ORDER BY R.RDB$RELATION_NAME
""".strip(),
            ("NAME",),
        )
        names = [row["NAME"].strip().upper() for row in rows if row["NAME"] and row["NAME"].strip()]
        names = sorted(set(names))
        if not with_rows:
            return [{"name": name, "rows": None} for name in names]
        items: list[dict[str, Any]] = []
        for name in names:
            total = self.client.query(
                f"SELECT COUNT(*) AS ROWCOUNT FROM {name}",
                ("ROWCOUNT",),
            )
            items.append({"name": name, "rows": int(total[0]["ROWCOUNT"] or "0") if total else None})
        return items

    def table_columns(self, name: str) -> list[str]:
        self._check_table_name(name)
        rows = self.client.query(
            f"""
SELECT FIRST 400
  CAST(RF.RDB$FIELD_NAME AS VARCHAR(92)) AS NAME
FROM RDB$RELATION_FIELDS RF
WHERE RF.RDB$RELATION_NAME = '{name}'
ORDER BY RF.RDB$FIELD_POSITION
""".strip(),
            ("NAME",),
        )
        return [row["NAME"].strip().upper() for row in rows if row["NAME"] and row["NAME"].strip()]

    def table_rows(self, name: str, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self._check_table_name(name)
        columns = self.table_columns(name)
        if not columns:
            raise FirebirdError(f"Colonnes introuvables pour {name}.")
        offset = (page - 1) * page_size
        column_sql = ", ".join(
            f"CAST({column} AS VARCHAR(255)) AS {column}" for column in columns
        )
        rows = self.client.query(
            f"SELECT FIRST {page_size} SKIP {offset} {column_sql} FROM {name}",
            tuple(columns),
        )
        total = self.client.query(f"SELECT COUNT(*) AS ROWCOUNT FROM {name}", ("ROWCOUNT",))
        return {
            "table": name,
            "columns": columns,
            "total": int(total[0]["ROWCOUNT"] or "0") if total else None,
            "page": page,
            "page_size": page_size,
            "items": rows,
        }
