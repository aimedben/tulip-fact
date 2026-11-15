from __future__ import annotations

import shutil
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditEntry, Base

router = APIRouter(prefix="/db", tags=["base locale"])


@router.get("/audit/entries")
def list_audit_entries(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    session = next(get_db())
    try:
        rows = (
            session.scalars(
                select(AuditEntry).order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc()).limit(limit)
            ).all()
        )
    finally:
        session.close()
    return [
        {
            "id": entry.id,
            "invoice_id": entry.invoice_id,
            "action": entry.action,
            "actor": entry.actor,
            "details": entry.details,
        }
        for entry in rows
    ]

_DELETE_ALLOWED = {
    "audit_entries",
    "export_records",
    "import_batches",
}


def _engine():
    from ..database import engine

    return engine


def _inspector():
    from sqlalchemy import inspect

    return inspect(_engine())


def _table_payload() -> list[dict[str, Any]]:
    inspector = _inspector()
    tables: list[dict[str, Any]] = []
    for name in sorted(Base.metadata.tables):  # tables métier uniquement
        if name not in inspector.get_table_names():
            continue
        models = [table for table in Base.metadata.sorted_tables if table.name == name][0]
        columns = [
            {"name": column.name, "type": str(column.type)} for column in models.columns
        ]
        tables.append({"name": name, "columns": columns})
    return tables


def _safe_table(name: str) -> Any:
    table = Base.metadata.tables.get(name)
    if table is None:
        raise HTTPException(status_code=404, detail=f"Table inconnue : {name}.")
    return table


@router.get("/tables")
def list_tables() -> list[dict[str, Any]]:
    with _engine().connect() as connection:
        result: list[dict[str, Any]] = []
        for table in _table_payload():
            count = connection.execute(text(f"SELECT COUNT(*) FROM {table['name']}")).scalar_one()
            result.append({**table, "rows": int(count)})
    return result


@router.get("/tables/{name}")
def read_table(
    name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    q: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    table = _safe_table(name)
    column_names = [column.name for column in table.columns]
    stmt = select(table)
    if q and q.strip():
        needle = f"%{q.strip().replace('%', '')}%"
        like_parts = [text(f"CAST([{column}] AS TEXT) LIKE :needle") for column in column_names]
        stmt = stmt.where(or_(*like_parts)).params(needle=needle)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    offset = (page - 1) * page_size
    stmt = stmt.limit(page_size).offset(offset)
    def _convert(value: Any) -> Any:
        return value
    rows = [
        {column: value for column, value in zip(column_names, row)}
        for row in db.execute(stmt).fetchall()
    ]
    return {"table": name, "columns": column_names, "total": int(total), "page": page, "page_size": page_size, "items": rows}


@router.get("/backups")
def list_backups() -> dict[str, Any]:
    from ..config import settings

    backups = sorted(settings.backups_dir.glob("tulip_factures-*.db*"), reverse=True)[:20]
    files = []
    for path in backups:
        st = path.stat()
        files.append({"name": path.name, "size": st.st_size, "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))})
    return {"directory": str(settings.backups_dir), "items": files}


@router.post("/backups")
def create_backup() -> dict[str, Any]:
    from ..config import settings
    from ..database import engine

    # engine.url.database renvoie le chemin tel que construit : str(engine.url)
    # percent-encode le chemin depuis SQLAlchemy 2 (« C%3A/Users/... »), ce qui
    # cassait la copie du fichier de base.
    source = engine.url.database or "tulip_factures.db"
    if not settings.backups_dir.exists():
        settings.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destination = settings.backups_dir / f"tulip_factures-{stamp}.db"
    with engine.connect() as connection:
        connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    shutil.copy2(source, destination)
    return {"created": destination.name, "size": destination.stat().st_size}


@router.delete("/tables/{name}")
def clear_table(name: str, confirm: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    if name not in _DELETE_ALLOWED:
        raise HTTPException(status_code=403, detail="Cette table ne peut pas être purgée ici.")
    table = _safe_table(name)
    if not confirm:
        raise HTTPException(status_code=400, detail="Purge non confirmée. Ajoutez confirm=true.")
    deleted = db.execute(delete(table)).rowcount
    db.commit()
    return {"table": name, "deleted": int(deleted or 0)}
