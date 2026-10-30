from __future__ import annotations

import pytest

from app.services.tulip.firebird import FirebirdError
from app.services.tulip.supplier_writer import SupplierWriter, CLIENTS_COLUMNS


class _Cfg:
    def __init__(self, write_enabled: bool) -> None:
        self.enabled = True
        self.database = "D:/Temp/test.tfe"
        self.user = "sysdba"
        self.password = "x"
        self.isql_path = "C:/isql.exe"
        self.write_enabled = write_enabled


class FakeClients:
    def __init__(self, write_enabled: bool = False) -> None:
        self.config = _Cfg(write_enabled)
        self.queries: list[str] = []
        self.executions: list[str] = []
        self.principal_used = "MOLFIX"

    def query(self, sql, columns):
        self.queries.append(sql)
        if "MAX(CODE)" in sql:
            return [{"NEXT_CODE": "-2147483342"}]
        if "PRINCIPAL =" in sql and "COUNTED" in sql:
            used = "1" if f"'{self.principal_used}'" in sql else "0"
            return [{"COUNTED": used}]
        if "CODE =" in sql:
            return [{"COUNTED": "0"}]
        return []

    def execute(self, sql):
        self.executions.append(sql)
        return "OK"


def test_create_supplier_preview_and_columns():
    client = FakeClients()
    writer = SupplierWriter(client)
    preview = writer.create_supplier(
        name="Aimed Bensaci",
        principal="AIME",
        address="Seddouk",
        tel="078878787",
        nrc="44444",
        dry_run=True,
    )
    assert preview["dry_run"] is True
    assert preview["principal"] == "AIME"
    assert preview["rsounom"] == "Aimed Bensaci"
    assert client.executions == []


def test_create_supplier_writes_on_copy():
    client = FakeClients(write_enabled=True)
    writer = SupplierWriter(client)
    result = writer.create_supplier(name="FOURNISSEUR TEST", principal="FTEST", dry_run=False)
    assert result["success"] is True
    assert result["code"] == -2147483341
    sql = client.executions[0]
    assert "INSERT INTO CLIENTS" in sql
    assert all(column in sql for column in CLIENTS_COLUMNS)
    assert "-1" in sql  # FRCLT
    assert "'FOURNISSEUR TEST'" in sql


def test_create_supplier_blocked_when_write_disabled():
    client = FakeClients(write_enabled=False)
    writer = SupplierWriter(client)
    with pytest.raises(FirebirdError) as excinfo:
        writer.create_supplier(name="X", principal="XPRINC", dry_run=False)
    assert "écritures" in str(excinfo.value)
    assert client.executions == []


def test_duplicate_principal_refused():
    client = FakeClients()
    writer = SupplierWriter(client)
    with pytest.raises(FirebirdError) as excinfo:
        writer.create_supplier(name="MOLFIX", principal="MOLFIX", dry_run=True)
    assert "déjà" in str(excinfo.value)
