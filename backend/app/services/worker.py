from __future__ import annotations

import logging
import queue
import threading
import time

from sqlalchemy import select

from .. import database
from ..config import settings
from ..models import Invoice
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

_jobs: "queue.Queue[tuple[int, str]]" = queue.Queue()
_started = False
_lock = threading.Lock()


def _loop() -> None:
    while True:
        invoice_id, method = _jobs.get()
        try:
            run_pipeline(invoice_id, method=method)
        except Exception as exc:  # pragma: no cover - filet de sécurité du worker
            logger.error("Erreur worker facture %s : %s", invoice_id, type(exc).__name__)
        finally:
            _jobs.task_done()


def start_worker() -> None:
    global _started
    if not settings.worker_enabled:
        return
    with _lock:
        if _started:
            return
        thread = threading.Thread(target=_loop, name="facture-worker", daemon=True)
        thread.start()
        _started = True


def enqueue(invoice_id: int, method: str = "auto") -> None:
    if not settings.worker_enabled:
        return
    start_worker()
    _jobs.put((invoice_id, method))


def requeue_unfinished() -> list[int]:
    ids: list[int] = []
    with database.SessionLocal() as db:
        invoices = db.scalars(
            select(Invoice).where(Invoice.status.in_(("IMPORTEE", "EXTRACTION")))
        ).all()
        for invoice in invoices:
            invoice.status = "IMPORTEE"
            invoice.stage = "en attente de reprise"
            invoice.progress = 2
            ids.append(invoice.id)
        db.commit()
    for invoice_id in ids:
        enqueue(invoice_id)
    return ids


def wait_idle(timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _jobs.unfinished_tasks == 0:
            return True
        time.sleep(0.05)
    return _jobs.unfinished_tasks == 0
