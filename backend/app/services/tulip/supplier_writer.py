from __future__ import annotations

from typing import Any

from .catalog import SUPPLIER_FILTER
from .firebird import FirebirdError, FirebirdIsql

CLIENTS_COLUMNS = (
    "CODE",
    "FRCLT",
    "PRINCIPAL",
    "RSOUNOM",
    "ADRESSE",
    "CITY",
    "TEL",
    "EMAIL",
    "NRC",
    "MF",
    "NIS",
    "ETAT",
)


def _q(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(39) * 2)}'"
    raise FirebirdError(f"Type non supporté pour CLIENTS: {type(value)!r}")


class SupplierWriter:
    def __init__(self, client: FirebirdIsql | None = None) -> None:
        if client is None:
            from .firebird import firebird_client

            self.client = firebird_client()
        else:
            self.client = client

    def _next_code(self) -> int:
        rows = self.client.query(
            "SELECT COALESCE(MAX(CODE), -2147483648) AS NEXT_CODE FROM CLIENTS WHERE CODE < 0",
            ("NEXT_CODE",),
        )
        base = int(rows[0]["NEXT_CODE"] or "-2147483648")
        return base + 1

    def create_supplier(
        self,
        name: str,
        principal: str,
        address: str | None = None,
        city: str | None = None,
        tel: str | None = None,
        email: str | None = None,
        nrc: str | None = None,
        mf: str | None = None,
        nis: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        name = (name or "").strip()
        principal = (principal or "").strip()
        if not name:
            raise FirebirdError("Nom du fournisseur requis pour l'écriture CLIENTS.")
        if not principal:
            raise FirebirdError("Code principal Tulip requis (PRINCIPAL).")
        if not dry_run and not self.client.config.write_enabled:
            raise FirebirdError("Les écritures Firebird Tulip sont désactivées.")

        principal_quoted = _q(principal)
        existing = self.client.query(
            f"SELECT COUNT(*) AS COUNTED FROM CLIENTS WHERE PRINCIPAL = {principal_quoted}",
            ("COUNTED",),
        )
        if existing and int(existing[0]["COUNTED"] or "0") > 0:
            raise FirebirdError(
                f"Un client/fournisseur Tulip utilise déjà le code principal {principal}."
            )

        if dry_run:
            preview = {
                "dry_run": True,
                "table": "CLIENTS",
                "frclt": -1,
                "rsounom": name,
                "principal": principal,
                "adresse": address,
                "city": city,
                "tel": tel,
                "email": email,
                "nrc": nrc,
                "mf": mf,
                "nis": nis,
                "note": "Séquence CODE réserve MAX(CODE négatif)+1 via trigger vides.",
            }
            return preview

        while True:
            code = self._next_code()
            used = self.client.query(
                f"SELECT COUNT(*) AS COUNTED FROM CLIENTS WHERE CODE = {code}",
                ("COUNTED",),
            )
            if not (used and int(used[0]["COUNTED"] or "0") > 0):
                break

        values = [
            code,
            -1,
            principal,
            name,
            address,
            city,
            tel,
            email,
            nrc,
            mf,
            nis,
            0,
        ]
        sql = (
            f"INSERT INTO CLIENTS ({', '.join(CLIENTS_COLUMNS)}) "
            f"VALUES ({', '.join(_q(v) for v in values)});"
        )
        try:
            self.client.execute(sql)
        except FirebirdError as exc:
            raise FirebirdError(f"Échec insertion CLIENTS (code {code}) : {exc}") from exc
        return {"success": True, "table": "CLIENTS", "code": code, "principal": principal, "rsounom": name}
