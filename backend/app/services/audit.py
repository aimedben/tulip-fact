from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEntry
from ..normalization import to_jsonable


def record_audit(
    db: Session,
    invoice_id: int | None,
    action: str,
    *,
    actor: str = "system",
    entity_type: str = "invoice",
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        invoice_id=invoice_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        details=to_jsonable(details or {}),
    )
    db.add(entry)
    return entry
