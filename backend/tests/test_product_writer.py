from __future__ import annotations

from typing import Any

from app.services.tulip.product_writer import ProductWriter


class FakeProductClient:
    """Client isql simulé : PRODUITS vide, aucune REF existante."""

    class _Cfg:
        write_enabled = True

    def __init__(self, write_enabled: bool = True) -> None:
        self._cfg = FakeProductClient._Cfg()
        self._cfg.write_enabled = write_enabled
        self.writes: list[str] = []
        self.queries: list[str] = []

    @property
    def config(self):
        return self._cfg

    def query(self, sql: str, columns):
        self.queries.append(sql)
        return [{"COUNTED": "0"}]

    def execute(self, sql: str) -> str:
        self.writes.append(sql)
        return ""


def test_ref_generated_from_designation_letters():
    client = FakeProductClient()
    writer = ProductWriter(client)
    result = writer.create_product(code="12445", designation="ramit", dry_run=False)
    assert result["ref"] == "RA12445"
    sql = client.writes[0]
    assert "INSERT INTO PRODUITS" in sql
    assert "'RA12445', 'U', 0, 1, 0" in sql


def test_unit_and_vat_are_written_to_tulip():
    from decimal import Decimal

    client = FakeProductClient()
    writer = ProductWriter(client)
    result = writer.create_product(
        code="3000",
        designation="HUILE FLEUR 1L",
        stock_unit="carton",
        default_vat_rate=Decimal("19"),
        dry_run=False,
    )
    sql = client.writes[0]
    assert "'CARTON', 19, 1, 0" in sql
    assert result["stock_unit"] == "CARTON"
    assert result["default_vat_rate"] == 19.0


def test_ref_prefix_fallback_when_no_letters():
    client = FakeProductClient()
    writer = ProductWriter(client)
    result = writer.create_product(code="2000", designation="1234", dry_run=False)
    assert result["ref"] == "ART2000"


def test_ref_prefix_uses_first_two_letters_tulip_style():
    assert ProductWriter._ref_prefix("BENTOUMIA ROTI") == "BE"
    assert ProductWriter._ref_prefix("le mont d'or") == "LE"
    assert ProductWriter._ref_prefix("ramit") == "RA"
    # accentuées comptent comme lettres
    assert ProductWriter._ref_prefix("Éclair") == "ÉC"
    assert ProductWriter._ref_prefix("") == "ART"


def test_ref_updates_suffix_on_conflict():
    class ConflictingClient(FakeProductClient):
        def query(self, sql: str, columns):
            # _product_exists → 0 ; _ref_exists → 1 pour la REF de base,
            # 0 dès qu'un suffixe est ajouté.
            if "PRODUITS WHERE LOWER(REF)" in sql:
                # _ref_exists passe la REF en minuscules (CU = LOWER(REF))
                base = "'ra12445'" in sql or "'art12445'" in sql
                return [{"COUNTED": "1" if base else "0"}]
            return [{"COUNTED": "0"}]

    client = ConflictingClient()
    writer = ProductWriter(client)
    result = writer.create_product(code="12445", designation="ramit", dry_run=False)
    assert result["ref"] == "RA12445_1"
