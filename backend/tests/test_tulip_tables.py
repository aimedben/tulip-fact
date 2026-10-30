from __future__ import annotations

import pytest

from app.services.tulip.catalog import TulipCatalog
from app.services.tulip.firebird import FirebirdError


class TableFakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, sql, columns):
        self.queries.append(sql)
        upper = sql.upper()
        if "RDB$RELATIONS" in upper:
            return [{"NAME": "BE              "}, {"NAME": "CLIENTS         "}]
        if "RDB$RELATION_FIELDS" in upper:
            return [{"NAME": "CODE       "}, {"NAME": "NUMERO     "}, {"NAME": "NBC        "}]
        if "COUNT(*) AS ROWCOUNT" in upper:
            return [{"ROWCOUNT": "10"}]
        if " FROM BE" in upper:
            return [{"CODE": "2407", "NUMERO": "2407", "NBC": "TEST"}]
        return []

    def execute(self, sql):
        return "OK"


def test_tables_and_rows_readonly():
    client = TableFakeClient()
    catalog = TulipCatalog(client)
    tables = catalog.tables()
    assert [t["name"] for t in tables] == ["BE", "CLIENTS"]
    assert tables[0]["rows"] == 10

    rows = catalog.table_rows("BE", page=2, page_size=10)
    assert rows["table"] == "BE"
    assert rows["columns"][0] == "CODE"
    assert rows["items"][0]["NUMERO"] == "2407"
    assert any("SKIP 10" in q for q in client.queries)


def test_table_name_validation():
    catalog = TulipCatalog(TableFakeClient())
    with pytest.raises(FirebirdError):
        catalog.table_rows("BE; DROP TABLE BE")
