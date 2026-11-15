from __future__ import annotations

from typing import Any
from decimal import Decimal

from .firebird import FirebirdError, FirebirdIsql


def _q(value: Any) -> str:
    """Quote une valeur pour insertion SQL dans Firebird."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, Decimal, float)):
        return str(value)
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(39) * 2)}'"
    raise FirebirdError(f"Type non supporté pour PRODUITS: {type(value)!r}")


class ProductWriter:
    def __init__(self, client: FirebirdIsql | None = None) -> None:
        if client is None:
            from .firebird import firebird_client

            self.client = firebird_client()
        else:
            self.client = client

    def next_code(self) -> str:
        """Prochain code article libre dans PRODUITS.

        Tulip utilise des codes numériques positifs ; on prend le plus grand
        (en ignorant la sentinelle 2147483647 utilisée pour les articles
        spéciaux) et on ajoute 1, en sautant les codes déjà pris.
        """
        rows = self.client.query(
            "SELECT MAX(CODE) AS MAX_CODE FROM PRODUITS WHERE CODE > 0 AND CODE <> 2147483647",
            ("MAX_CODE",),
        )
        base = int(rows[0]["MAX_CODE"] or "0") if rows else 0
        candidate = base + 1
        while self._product_exists(str(candidate)):
            candidate += 1
        return str(candidate)

    def _product_exists(self, code: str) -> bool:
        """Vérifie si un produit avec ce code existe déjà dans PRODUITS."""
        # CODE dans PRODUITS est numérique dans Firebird
        try:
            code_numeric = int(code)
            rows = self.client.query(
                f"SELECT COUNT(*) AS COUNTED FROM PRODUITS WHERE CODE = {code_numeric}",
                ("COUNTED",),
            )
            return rows and int(rows[0]["COUNTED"] or "0") > 0
        except ValueError:
            # Code alphanumérique - chercher en castant le CODE en VARCHAR
            rows = self.client.query(
                f"SELECT COUNT(*) AS COUNTED FROM PRODUITS WHERE CAST(CODE AS VARCHAR(20)) = {_q(code)}",
                ("COUNTED",),
            )
            return rows and int(rows[0]["COUNTED"] or "0") > 0

    def _ref_exists(self, ref: str) -> bool:
        """Vérifie si un produit avec cette référence existe déjà dans PRODUITS.
        Nécessaire car le trigger PRODUITS_BI définit CU = LOWER(REF)
        et la contrainte UNIQUE (PC, CU) empêche les doublons."""
        try:
            rows = self.client.query(
                f"SELECT COUNT(*) AS COUNTED FROM PRODUITS WHERE LOWER(REF) = {_q(ref.lower())}",
                ("COUNTED",),
            )
            return rows and int(rows[0]["COUNTED"] or "0") > 0
        except Exception:
            return False

    @staticmethod
    def _ref_prefix(designation: str) -> str:
        """Deux premières lettres de la désignation (convention Tulip : BE72, LE76).

        « ramit » → « RA ». Lettres latines accentuées incluses, tout le reste
        ignoré. Retombe sur « ART » si la désignation n'a pas deux lettres.
        """
        letters = "".join(
            ch for ch in designation.upper()
            if (ch.isascii() and ch.isalpha()) or ch in "ÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ"
        )
        if len(letters) >= 2:
            return letters[:2]
        return "ART"

    def create_product(
        self,
        code: str,
        designation: str,
        ref: str | None = None,
        barcode: str | None = None,
        packaging: str | None = None,
        stock_unit: str | None = None,
        default_vat_rate: Decimal | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Crée un nouveau produit dans la table PRODUITS de Firebird.

        Args:
            code: Code article Tulip (obligatoire, doit être numérique)
            designation: Désignation du produit (obligatoire)
            ref: Référence article
            barcode: Code-barres (sera inséré dans la table CODEBARRE si fourni)
            packaging: Conditionnement
            stock_unit: Unité de stock (UM)
            default_vat_rate: Taux de TVA par défaut
            dry_run: Si True, simule l'insertion sans l'exécuter

        Returns:
            Dictionnaire avec le statut de l'opération
        """
        code = (code or "").strip()
        designation = (designation or "").strip()

        if not code:
            raise FirebirdError("Code article requis pour l'écriture PRODUITS.")
        if not designation:
            raise FirebirdError("Désignation requise pour l'écriture PRODUITS.")
        if not dry_run and not self.client.config.write_enabled:
            raise FirebirdError("Les écritures Firebird Tulip sont désactivées.")

        # Vérifier que le code est numérique (requis par Firebird)
        try:
            code_numeric = int(code)
        except ValueError:
            raise FirebirdError(f"Le code article '{code}' doit être numérique pour Firebird PRODUITS.")

        # Vérifier si le produit existe déjà
        if self._product_exists(code):
            raise FirebirdError(f"Un produit avec le code {code} existe déjà dans Tulip.")

        if dry_run:
            return {
                "dry_run": True,
                "table": "PRODUITS",
                "code": code,
                "designation": designation,
                "ref": ref,
                "barcode": barcode,
                "packaging": packaging,
                "stock_unit": stock_unit,
                "default_vat_rate": float(default_vat_rate) if default_vat_rate else None,
                "note": "Simulation : le produit serait inséré dans PRODUITS.",
            }

        # Préparer les valeurs pour l'insertion
        # PRODUCTLABEL est la colonne réelle, D/LABEL/DESIGNATION sont des colonnes calculées (Computed by)
        # REF doit être fourni car le trigger PRODUITS_BI définit CU = LOWER(REF)
        # La contrainte UNIQUE (PC, CU) nécessite que CU soit unique

        # Générer une référence unique qui évite les conflits
        # Le trigger fait CU = LOWER(REF), donc on génère un REF qui sera unique en minuscules
        if ref and ref.strip():
            ref_value = ref.strip()
        else:
            # REF = deux premières lettres de la désignation + code, comme
            # Tulip (« ramit » 12445 → « RA12445 » ; BENTOUMIA → BE72).
            ref_value = f"{self._ref_prefix(designation)}{code_numeric}"

            # Vérifier que cette référence n'existe pas déjà
            attempt = 0
            while self._ref_exists(ref_value) and attempt < 100:
                attempt += 1
                ref_value = f"{self._ref_prefix(designation)}{code_numeric}_{attempt}"

        # NATURE = 1 (marchandise) et ETAT = 0 (actif) : sans eux le produit est
        # invisible pour Tulip (filtre d'activité P.ETAT = 0 AND NATURE IN (1,2,5,10))
        # et pour nos propres listings/synchronisations.
        # UM (unité) et TVA (%) sont les colonnes que Tulip remplit lui-même :
        # on les écrit aussi pour que l'article soit complet dans le logiciel.
        unit = (stock_unit or "").strip().upper()[:10] or "U"
        vat = default_vat_rate if default_vat_rate is not None else Decimal("0")
        sql = f"""
INSERT INTO PRODUITS (CODE, PRODUCTLABEL, REF, UM, TVA, NATURE, ETAT)
VALUES ({code_numeric}, {_q(designation[:200])}, {_q(ref_value)}, {_q(unit)}, {_q(Decimal(vat))}, 1, 0);
""".strip()

        try:
            self.client.execute(sql)
        except FirebirdError as exc:
            raise FirebirdError(f"Échec insertion PRODUITS (code {code}) : {exc}") from exc

        result = {
            "success": True,
            "table": "PRODUITS",
            "code": code,
            "designation": designation,
            "ref": ref_value,
            "stock_unit": unit,
            "default_vat_rate": float(vat),
            "note": "CODE, PRODUCTLABEL, REF, UM et TVA insérés (D/LABEL/DESIGNATION sont calculés automatiquement)",
        }

        # Insérer le code-barres dans la table CODEBARRE si fourni
        if barcode and barcode.strip():
            try:
                barcode_sql = f"""
INSERT INTO CODEBARRE (PRODUIT, CODEBARRE)
VALUES ({code_numeric}, {_q(barcode.strip())});
""".strip()
                self.client.execute(barcode_sql)
                result["barcode"] = barcode.strip()
                result["barcode_inserted"] = True
            except FirebirdError as exc:
                # Ne pas échouer si l'insertion du code-barres échoue
                result["barcode_error"] = str(exc)

        return result
