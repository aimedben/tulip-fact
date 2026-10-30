from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Any

from .firebird import FirebirdError, FirebirdIsql, firebird_client

SFX_COMMANDE = -32765
CMP_COMMANDE = 0

BE_COLUMNS = (
    "CODE",
    "SFX",
    "NUMERO",
    "DETTE",
    "CMP",
    "FOURNISSEUR",
    "OPDATE",
    "NBC",
    "DATEBC",
    "LIVFACT",
    "DATEFACT",
    "NOTVA",
    "MHT",
    "MTVA",
    "TIMBRE",
    "TIC",
    "REMISE",
    "MP",
    "COMMERCIAL",
    "SHP",
    "PRINTED",
    "CHARGES",
)

DETAILSBR_COLUMNS = (
    "OPDATE",
    "LINE",
    "ITEM",
    "PARENT",
    "PRODUIT",
    "LOT",
    "PUHT",
    "QTE",
    "MQX",
    "ECART",
    "TVA",
    "REMISE",
    "TREMISE",
    "AUTRES",
    "TC",
    "TIC",
    "UTIC",
    "DX",
    "MPRIX",
    "SHP",
    "CHARGES",
    "MOUVEMENT",
    "TVATIC",
)


@dataclass
class LineItem:
    product_code: int
    quantity: Decimal
    unit_price_ht: Decimal
    lot_code: int | None = None
    remise: Decimal | None = None
    remise_type: int | None = None
    mqx: Decimal | None = None
    mprix: Decimal | None = None
    tva: Decimal | None = None
    tic: Decimal | None = None
    utic: Decimal | None = None
    autres: Decimal | None = None
    tvatic: int | None = None
    dx: date | None = None


@dataclass
class BeHeader:
    fournisseur: int
    opdate: date
    nbc: str | None = None
    datebc: date | None = None
    livfact: str | None = None
    datefact: date | None = None
    chauffeur: str | None = None
    matricule: str | None = None
    notva: bool = False
    mp: int = 1


class BeWriter:
    def __init__(self, client: FirebirdIsql | None = None) -> None:
        self.client = client or firebird_client()

    def _q(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'"
        if isinstance(value, date):
            return f"'{value.isoformat()}'"
        if isinstance(value, str):
            return f"'{value.replace(chr(39), chr(39) * 2)}'"
        raise FirebirdError(f"Type non supporté pour Firebird: {type(value)!r}")

    def _next_generator(self, generator: str, table: str, column: str) -> int:
        value = int(
            self.client.query(
                f"SELECT GEN_ID({generator}, 1) AS NEXT_VALUE FROM RDB$DATABASE",
                ("NEXT_VALUE",),
            )[0]["NEXT_VALUE"]
        )
        while True:
            rows = self.client.query(
                f"SELECT COUNT(*) AS USED FROM {table} WHERE {column} = {value}",
                ("USED",),
            )
            if int(rows[0]["USED"] or "0") == 0:
                return value
            value = int(
                self.client.query(
                    f"SELECT GEN_ID({generator}, 1) AS NEXT_VALUE FROM RDB$DATABASE",
                    ("NEXT_VALUE",),
                )[0]["NEXT_VALUE"]
            )

    def _next_numero(self) -> int:
        rows = self.client.query(
            f"""SELECT COALESCE(MAX(NUMERO), 0) + 1 AS NEXT_NUM
                FROM BE
                WHERE SFX = {SFX_COMMANDE} AND CMP = {CMP_COMMANDE}""",
            ("NEXT_NUM",),
        )
        if not rows or rows[0]["NEXT_NUM"] is None:
            raise FirebirdError("Série commande (SFX/-32765) introuvable dans BE.")
        return int(rows[0]["NEXT_NUM"])

    def _line_values(self, header: BeHeader, line: LineItem, line_code: int) -> tuple[list[str], list[str]]:
        values = [
            header.opdate,
            line_code,
            32767,
            None,
            line.product_code,
            line.lot_code or 0,
            line.unit_price_ht,
            line.quantity,
            line.mqx,
            None,
            line.tva,
            line.remise,
            line.remise_type,
            Decimal("0") if line.autres is None else line.autres,
            None,
            line.tic,
            line.utic,
            line.dx,
            line.mprix,
            None,
            Decimal("0"),
            Decimal("0"),
            0 if line.tvatic is None else line.tvatic,
        ]
        columns = list(DETAILSBR_COLUMNS)
        return columns, [self._q(v) for v in values]

    def _preview_line(self, line: LineItem) -> dict[str, Any]:
        return {
            "product_code": line.product_code,
            "lot_code": line.lot_code or 0,
            "puht": line.unit_price_ht,
            "qte": line.quantity,
            "remise": line.remise,
        }

    def create_be(self, header: BeHeader, lines: list[LineItem], dry_run: bool = True) -> dict[str, Any]:
        if not lines:
            raise FirebirdError("Aucune ligne à insérer")
        if not header.fournisseur:
            raise FirebirdError("Fournisseur requis")
        if not dry_run and not getattr(self.client.config, "write_enabled", False):
            raise FirebirdError("Les écritures Firebird Tulip sont désactivées.")

        be_code = self._next_generator("BE", "BE", "CODE")
        numero = self._next_numero()

        if dry_run:
            previews = [self._preview_line(line) for line in lines]
            return {
                "dry_run": True,
                "be_code": be_code,
                "sfx": SFX_COMMANDE,
                "numero": numero,
                "fournisseur": header.fournisseur,
                "opdate": header.opdate.isoformat(),
                "nbc": header.nbc,
                "lines": previews,
            }

        header_values = [
            be_code,
            SFX_COMMANDE,
            numero,
            0,
            CMP_COMMANDE,
            header.fournisseur,
            header.opdate,
            header.nbc,
            header.datebc or header.opdate,
            header.livfact,
            header.datefact,
            1 if header.notva else 0,
            Decimal("0"),
            Decimal("0"),
            None,
            Decimal("0"),
            Decimal("0"),
            header.mp,
            1,
            0,
            0,
            Decimal("0"),
        ]

        header_sql = (
            f"INSERT INTO BE ({', '.join(BE_COLUMNS)}) "
            f"VALUES ({', '.join(self._q(v) for v in header_values)});"
        )

        try:
            statements = [header_sql, f"UPDATE BE SET DETTE = 1 WHERE CODE = {be_code};"]
            for line in lines:
                line_code = self._next_generator("LINEBE", "DETAILSBR", "LINE")
                columns, values = self._line_values(header, line, line_code)
                values[3] = str(be_code)
                statements.append(
                    f"INSERT INTO DETAILSBR ({', '.join(columns)}) "
                    f"VALUES ({', '.join(values)});"
                )
            self.client.execute("\n".join(statements))
        except FirebirdError as exc:
            raise FirebirdError(f"Échec création BE {be_code}: {exc}") from exc

        return {
            "success": True,
            "be_code": be_code,
            "sfx": SFX_COMMANDE,
            "numero": numero,
            "lines": len(lines),
        }
