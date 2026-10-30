from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Invoice, InvoiceLine, Product
from ..normalization import normalize_key, to_jsonable
from ..schemas import (
    BulkDeleteRequest,
    InvoiceHeaderUpdate,
    LineCreate,
    LineUpdate,
    NewProductFromLine,
    ProductConfirm,
    SupplierConfirm,
    ValidateRequest,
)
from ..services.accounting import verify_invoice
from ..services.audit import record_audit
from ..services.duplicates import detect_duplicates, duplicate_warning
from ..services.matching.products import confirm_product as confirm_line_product
from ..services.matching.products import match_lines, suggest_products
from ..services.matching.suppliers import confirm_supplier
from ..services.storage import (
    StorageError,
    delete_invoice_files,
    pages_dir_for,
    resolve_relative,
    sanitize_filename,
    sha256_file,
    sniff_extension,
    store_document,
)
from ..services.extraction.llm import extractor as llm_extractor  # noqa: F401 (cond. d'écriture)
from ..services.extraction.assistant import analyze_invoice, apply_proposal
from ..services.validation import ValidationError, readiness, recompute_invoice, validate_invoice
from ..services.worker import enqueue
from ..services.tulip.catalog import TulipCatalog
from ..services.tulip.firebird import FirebirdError, firebird_client
from ..services.tulip.invoice_be import build_be_from_invoice
from ..services.tulip.writer import BeWriter
from .serializers import invoice_detail, invoice_summary, line_payload, product_payload

router = APIRouter(tags=["factures"])

LOCKED_STATUSES = {"VALIDEE", "EXPORTEE"}


def _get_invoice(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable.")
    return invoice


def _ensure_editable(invoice: Invoice) -> None:
    if invoice.status in LOCKED_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Cette facture est validée ou exportée. Créez une nouvelle version ou contactez un administrateur.",
        )
    if invoice.status in {"IMPORTEE", "EXTRACTION"}:
        raise HTTPException(status_code=409, detail="Le traitement de cette facture est encore en cours.")


def _duplicate_refresh(db: Session, invoice: Invoice) -> None:
    _, _, _, reasons = detect_duplicates(db, invoice)
    warnings = [
        warning
        for warning in (invoice.warnings or [])
        if warning.get("code") not in {"DOUBLON_POSSIBLE", "FOURNISSEUR_A_CONFIRMER"}
    ]
    if reasons:
        warnings.extend(duplicate_warning(reasons))
        invoice.document_meta = {**(invoice.document_meta or {}), "duplicate_reasons": reasons}
    else:
        invoice.document_meta = {
            key: value for key, value in (invoice.document_meta or {}).items() if key != "duplicate_reasons"
        }
    invoice.warnings = warnings


def _recompute_and_refresh(db: Session, invoice: Invoice) -> None:
    recompute_invoice(invoice)
    _duplicate_refresh(db, invoice)
    state = readiness(invoice)
    has_errors = any(check.get("severity") == "error" for check in (invoice.checks or []))
    all_matched = bool(invoice.lines) and all(
        line.match_status in {"RAPPROCHE", "CONFIRME"} for line in invoice.lines
    )
    if (
        not invoice.is_duplicate
        and invoice.supplier_id is not None
        and invoice.invoice_number
        and invoice.invoice_date is not None
        and all_matched
        and not has_errors
    ):
        invoice.status = "PRETE_A_VALIDER"
    else:
        invoice.status = "A_VERIFIER"
    db.flush()


@router.post("/invoices/import", status_code=201)
async def import_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    original_name = sanitize_filename(file.filename)
    suffix = Path(original_name).suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=f"Format non pris en charge ({suffix or 'inconnu'}). Formats acceptés : PDF, JPG, JPEG, PNG.",
        )

    temp_dir = settings.data_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"upload-{uuid.uuid4().hex}.part"
    total = 0
    try:
        with temp_path.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux (limite : {settings.max_upload_mb} Mo).",
                    )
                handle.write(chunk)
    finally:
        await file.close()

    if total == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Le fichier est vide.")

    sniffed = sniff_extension(temp_path)
    if sniffed is None:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Le contenu du fichier ne correspond pas à un PDF, JPEG ou PNG valide.",
        )
    if sniffed == ".jpg" and suffix == ".jpeg":
        suffix = ".jpg"

    invoice_uuid = str(uuid.uuid4())
    relative_path = store_document(temp_path, invoice_uuid, sniffed)
    digest = sha256_file(temp_path)
    temp_path.unlink(missing_ok=True)

    mime = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}[sniffed.lstrip(".")]
    invoice = Invoice(
        uuid=invoice_uuid,
        original_filename=original_name,
        stored_path=relative_path,
        sha256=digest,
        file_size=total,
        mime_type=mime,
        status="IMPORTEE",
        stage="en attente de traitement",
        progress=2,
        currency="DZD",
        header_raw={},
        totals_extracted={},
        totals_calculated={},
        checks=[],
        warnings=[],
        document_meta={},
        supplier_match={},
    )
    db.add(invoice)
    db.flush()
    record_audit(
        db,
        invoice.id,
        "import",
        details={"filename": original_name, "size": total, "sha256": digest, "mime": mime},
    )
    db.commit()
    db.refresh(invoice)
    enqueue(invoice.id)
    return invoice_summary(invoice)


@router.get("/invoices")
def list_invoices(
    db: Session = Depends(get_db),
    status: str | None = None,
    supplier_id: int | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    duplicates: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(Invoice)
    count_stmt = select(func.count(Invoice.id))
    conditions = []
    if status:
        statuses = [item.strip().upper() for item in status.split(",") if item.strip()]
        conditions.append(Invoice.status.in_(statuses))
    if supplier_id is not None:
        conditions.append(Invoice.supplier_id == supplier_id)
    if q:
        needle = f"%{q.strip()}%"
        conditions.append(
            or_(
                Invoice.invoice_number.ilike(needle),
                Invoice.supplier_name_raw.ilike(needle),
                Invoice.original_filename.ilike(needle),
            )
        )
    if date_from:
        conditions.append(Invoice.invoice_date >= date_from)
    if date_to:
        conditions.append(Invoice.invoice_date <= date_to)
    if duplicates:
        conditions.append(Invoice.is_duplicate.is_(True))
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    invoices = db.scalars(
        stmt.order_by(Invoice.imported_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [invoice_summary(invoice) for invoice in invoices],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    return invoice_detail(invoice, readiness(invoice))


@router.get("/invoices/{invoice_id}/pages/{page_number}/image")
def get_page_image(invoice_id: int, page_number: int, db: Session = Depends(get_db)):
    invoice = _get_invoice(db, invoice_id)
    page = next((item for item in invoice.pages if item.page_number == page_number), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page introuvable.")
    try:
        path = resolve_relative(page.image_path)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image de page introuvable sur le disque.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.patch("/invoices/{invoice_id}")
def update_header(invoice_id: int, payload: InvoiceHeaderUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    changed: dict[str, Any] = {}
    header_raw = dict(invoice.header_raw or {})

    for field_name in payload.model_fields_set:
        if field_name == "totals":
            continue
        old_value = getattr(invoice, field_name)
        new_value = getattr(payload, field_name)
        if old_value != new_value:
            changed[field_name] = {"old": to_jsonable(old_value), "new": to_jsonable(new_value)}
            setattr(invoice, field_name, new_value)
            header_raw[field_name] = {"value": 1.0, "source": "correction utilisateur"}

    if payload.totals is not None:
        totals = dict(invoice.totals_extracted or {})
        confidence = dict(totals.get("confidence") or {})
        raw_values = dict(totals.get("raw") or {})
        for field_name in payload.totals.model_fields_set:
            if field_name == "vat_breakdown":
                breakdown = payload.totals.vat_breakdown
                if breakdown is None:
                    totals.pop("vat_breakdown", None)
                else:
                    totals["vat_breakdown"] = {str(key): str(value) for key, value in breakdown.items()}
                continue
            value = getattr(payload.totals, field_name)
            if value is None:
                totals.pop(field_name, None)
            else:
                totals[field_name] = str(value)
                confidence[field_name] = 1.0
                raw_values[field_name] = str(value)
            changed[f"totals.{field_name}"] = {"new": to_jsonable(value)}
        totals["confidence"] = confidence
        totals["raw"] = raw_values
        invoice.totals_extracted = totals

    invoice.header_raw = header_raw
    if changed:
        invoice.status = "A_VERIFIER" if invoice.status not in {"IMPORTEE", "EXTRACTION"} else invoice.status
        _recompute_and_refresh(db, invoice)
        record_audit(db, invoice.id, "correction_entete", details={"changes": changed})
    db.commit()
    db.refresh(invoice)
    return invoice_detail(invoice, readiness(invoice))


@router.post("/invoices/{invoice_id}/supplier")
def set_supplier(invoice_id: int, payload: SupplierConfirm, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    try:
        confirm_supplier(db, invoice, payload.supplier_id, payload.supplier_name_raw)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    match_lines(db, invoice)
    _recompute_and_refresh(db, invoice)
    record_audit(
        db,
        invoice.id,
        "confirmation_fournisseur",
        details={"supplier_id": payload.supplier_id, "code": invoice.supplier_code_snapshot},
    )
    db.commit()
    db.refresh(invoice)
    return invoice_detail(invoice, readiness(invoice))


@router.patch("/invoices/{invoice_id}/lines/{line_id}")
def update_line(
    invoice_id: int,
    line_id: int,
    payload: LineUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    line = next((item for item in invoice.lines if item.id == line_id), None)
    if line is None:
        raise HTTPException(status_code=404, detail="Ligne introuvable.")

    changed: dict[str, Any] = {}
    rematch_needed = False
    for field_name in payload.model_fields_set:
        old_value = getattr(line, field_name)
        new_value = getattr(payload, field_name)
        if old_value != new_value:
            changed[field_name] = {"old": to_jsonable(old_value), "new": to_jsonable(new_value)}
            setattr(line, field_name, new_value)
            if field_name in {"raw_designation", "raw_reference"}:
                rematch_needed = True

    if changed:
        corrections = list((line.original_values or {}).get("corrections") or [])
        corrections.append({"at": datetime.now(timezone.utc).isoformat(), "changes": changed})
        line.original_values = {**(line.original_values or {}), "corrections": corrections}
        line.user_modified = True
        if rematch_needed:
            line.tulip_product_id = None
            line.catalog_designation = None
            candidates = suggest_products(
                db,
                raw_reference=line.raw_reference,
                raw_designation=line.raw_designation,
                supplier_id=invoice.supplier_id,
            )
            line.match_candidates = candidates
            line.match_status = "SUGGERE" if candidates else "NON_RAPPROCHE"
            line.match_score = Decimal(str(candidates[0]["score"])) if candidates else None
        invoice.status = "A_VERIFIER"
        _recompute_and_refresh(db, invoice)
        record_audit(db, invoice.id, "correction_ligne", entity_type="line", entity_id=line.id, details={"changes": changed})
    db.commit()
    db.refresh(invoice)
    return invoice_detail(invoice, readiness(invoice))


@router.post("/invoices/{invoice_id}/lines", status_code=201)
def add_line(invoice_id: int, payload: LineCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    next_position = max((line.position for line in invoice.lines), default=0) + 1
    line = InvoiceLine(
        invoice_id=invoice.id,
        position=next_position,
        raw_reference=payload.raw_reference,
        raw_designation=payload.raw_designation,
        lot_number=payload.lot_number,
        packages=payload.packages,
        quantity=payload.quantity,
        unit=payload.unit,
        packaging=payload.packaging,
        unit_price_ht=payload.unit_price_ht,
        vat_rate=payload.vat_rate,
        line_total_ht_extracted=payload.line_total_ht_extracted,
        discount_value=payload.discount_value,
        discount_type=payload.discount_type,
        confidence={"global": 1.0, "source": "saisie manuelle"},
        original_values={"source": "saisie manuelle"},
        user_modified=True,
        match_candidates=[],
        match_status="NON_RAPPROCHE",
    )
    invoice.lines.append(line)
    db.flush()
    candidates = suggest_products(
        db,
        raw_reference=line.raw_reference,
        raw_designation=line.raw_designation,
        supplier_id=invoice.supplier_id,
    )
    line.match_candidates = candidates
    if candidates:
        line.match_status = "SUGGERE"
        line.match_score = Decimal(str(candidates[0]["score"]))
    invoice.status = "A_VERIFIER"
    _recompute_and_refresh(db, invoice)
    record_audit(db, invoice.id, "ajout_ligne", entity_type="line", entity_id=line.id, details={"designation": line.raw_designation})
    db.commit()
    db.refresh(invoice)
    return invoice_detail(invoice, readiness(invoice))


@router.delete("/invoices/{invoice_id}/lines/{line_id}")
def delete_line(invoice_id: int, line_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    line = next((item for item in invoice.lines if item.id == line_id), None)
    if line is None:
        raise HTTPException(status_code=404, detail="Ligne introuvable.")
    designation = line.raw_designation
    invoice.lines.remove(line)
    db.flush()
    for index, remaining in enumerate(invoice.lines, start=1):
        remaining.position = index
    invoice.status = "A_VERIFIER"
    _recompute_and_refresh(db, invoice)
    record_audit(db, invoice.id, "suppression_ligne", entity_type="line", entity_id=line_id, details={"designation": designation})
    db.commit()
    db.refresh(invoice)
    return invoice_detail(invoice, readiness(invoice))


@router.post("/invoices/{invoice_id}/lines/{line_id}/match")
def match_line(
    invoice_id: int,
    line_id: int,
    payload: ProductConfirm,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    line = next((item for item in invoice.lines if item.id == line_id), None)
    if line is None:
        raise HTTPException(status_code=404, detail="Ligne introuvable.")
    try:
        confirm_line_product(db, invoice, line, payload.product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    invoice.status = "A_VERIFIER"
    _recompute_and_refresh(db, invoice)
    record_audit(
        db,
        invoice.id,
        "confirmation_article",
        entity_type="line",
        entity_id=line.id,
        details={"product_id": payload.product_id, "designation": line.raw_designation},
    )
    db.commit()
    db.refresh(invoice)
    return invoice_detail(invoice, readiness(invoice))


@router.post("/invoices/{invoice_id}/lines/{line_id}/new-product", status_code=201)
def create_line_product(
    invoice_id: int,
    line_id: int,
    payload: NewProductFromLine,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    line = next((item for item in invoice.lines if item.id == line_id), None)
    if line is None:
        raise HTTPException(status_code=404, detail="Ligne introuvable.")

    designation = (payload.designation or line.raw_designation or "").strip()
    if not designation:
        raise HTTPException(status_code=400, detail="La désignation de l'article est obligatoire.")

    code = (payload.tulip_code or "").strip()
    if code and db.scalar(select(Product).where(Product.tulip_code == code)):
        raise HTTPException(status_code=409, detail="Un article avec ce code Tulip existe déjà.")
    if not code:
        numeric_codes = db.scalars(
            select(Product.tulip_code).where(Product.tulip_code.op("GLOB")("[0-9]*"))
        ).all()
        next_number = max((int(item) for item in numeric_codes if item.isdigit()), default=1000) + 1
        code = str(next_number)
        while db.scalar(select(Product).where(Product.tulip_code == code)):
            next_number += 1
            code = str(next_number)

    product = Product(
        tulip_code=code,
        supplier_ref=payload.supplier_ref or line.raw_reference,
        designation=designation,
        normalized_designation=normalize_key(designation),
        packaging=payload.packaging or (str(line.packages) if line.packages is not None else None),
        stock_unit=payload.stock_unit,
        default_vat_rate=payload.default_vat_rate if payload.default_vat_rate is not None else line.vat_rate,
    )
    db.add(product)
    db.flush()

    confirm_line_product(db, invoice, line, product.id)
    invoice.status = "A_VERIFIER"
    _recompute_and_refresh(db, invoice)
    record_audit(
        db,
        invoice.id,
        "creation_article",
        entity_type="line",
        entity_id=line.id,
        details={"product_id": product.id, "tulip_code": code, "designation": designation},
    )
    db.commit()
    db.refresh(invoice)
    return invoice_detail(invoice, readiness(invoice))


@router.get("/products/suggest")
def suggest_product(
    db: Session = Depends(get_db),
    q: str = Query(min_length=1, max_length=120),
    supplier_id: int | None = None,
    limit: int = Query(default=8, ge=1, le=30),
) -> dict[str, Any]:
    normalized = quote_like(q)
    candidates = suggest_products(db, raw_reference=normalized, raw_designation=q, supplier_id=supplier_id, limit=limit)
    if not candidates:
        direct = db.scalars(
            select(Product)
            .where(
                or_(
                    Product.tulip_code.ilike(f"%{q.strip()}%"),
                    Product.designation.ilike(f"%{q.strip()}%"),
                    Product.barcode.ilike(f"%{q.strip()}%"),
                )
            )
            .limit(limit)
        ).all()
        candidates = [
            {
                "product_id": product.id,
                "tulip_code": product.tulip_code,
                "designation": product.designation,
                "score": 0.5,
                "method": "recherche libre",
            }
            for product in direct
        ]
    return {"items": candidates}


def quote_like(value: str) -> str:
    return value.strip()


@router.post("/invoices/{invoice_id}/validate")
def validate(invoice_id: int, payload: ValidateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    if invoice.status in {"IMPORTEE", "EXTRACTION"}:
        raise HTTPException(status_code=409, detail="Le traitement de la facture n'est pas terminé.")
    try:
        result = validate_invoice(
            db,
            invoice,
            payload.actor,
            acknowledge_duplicate=payload.acknowledge_duplicate,
            acknowledge_totals=payload.acknowledge_totals,
            acknowledge_warnings=payload.acknowledge_warnings,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "issues": getattr(exc, "issues", [])},
        ) from exc
    db.commit()
    db.refresh(invoice)
    return {"message": "Facture validée.", "invoice": invoice_detail(invoice, readiness(invoice)), **result}


@router.post("/invoices/{invoice_id}/tulip/be")
def create_tulip_be(
    invoice_id: int,
    dry_run: bool = Query(default=True),
    actor: str = Query(default="utilisateur"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    if invoice.status not in {"VALIDEE", "EXPORTEE"}:
        raise HTTPException(status_code=409, detail="La facture doit être validée avant la création du bon d'entrée.")

    client = firebird_client()
    if not client.config.configured:
        raise HTTPException(status_code=400, detail="L'accès Tulip Firebird n'est pas configuré.")

    built = build_be_from_invoice(db, invoice, TulipCatalog(client))
    if not built["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Le BE Tulip ne peut pas être préparé.",
                "issues": built["issues"],
                "skipped_lines": built["skipped_lines"],
            },
        )

    try:
        result = BeWriter(client).create_be(built["header"], built["lines"], dry_run=dry_run)
    except FirebirdError as exc:
        raise HTTPException(status_code=502, detail=f"Écriture Firebird impossible : {exc}") from exc

    result["issues"] = built["issues"]
    result["skipped_lines"] = built["skipped_lines"]

    if not dry_run:
        numero = result.get("numero")
        be_code = result.get("be_code")
        record_audit(
            db,
            invoice.id,
            "tulip_be_cree",
            actor=actor,
            details={"be_code": be_code, "numero": numero, "lines": result.get("lines")},
        )
        db.add(
            ExportRecord(
                invoice_id=invoice.id,
                format="tulip_be",
                file_path=f"BE/{be_code}",
                sha256="",
                mode="tulip_be",
                status="GENERE",
                note=(
                    f"BEDS Tulip n°{numero} (CODE {be_code}) créé depuis la facture "
                    f"{invoice.invoice_number or invoice.id} — {result.get('lines')} ligne(s)."
                ),
            )
        )
        db.commit()

    return result


@router.post("/invoices/{invoice_id}/ai/analyze")
def ai_analyze(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    analysis = analyze_invoice(db, invoice)
    proposal = analysis["proposal"]
    total = len(proposal["header"]) + len(proposal["totals"]) + len(proposal["lines"])
    return {**analysis, "applicable": total > 0 or invoice.supplier_id is None, "total_fields": total}


@router.post("/invoices/{invoice_id}/ai/apply")
def ai_apply(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    _ensure_editable(invoice)
    analysis = analyze_invoice(db, invoice)
    changes = apply_proposal(db, invoice, analysis)
    db.commit()
    db.refresh(invoice)
    return {"changes": changes, "invoice": invoice_detail(invoice, readiness(invoice))}


@router.post("/invoices/{invoice_id}/reprocess")
def reprocess(invoice_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    if invoice.status in LOCKED_STATUSES:
        raise HTTPException(status_code=409, detail="Une facture validée ou exportée ne peut pas être retraitée.")
    invoice.status = "IMPORTEE"
    invoice.stage = "en attente de retraitement"
    invoice.progress = 2
    invoice.error_message = None
    record_audit(db, invoice.id, "relance_traitement")
    db.commit()
    enqueue(invoice.id)
    return invoice_summary(invoice)


def _purge_invoice(db: Session, invoice: Invoice, keep_image: bool = False) -> dict[str, Any]:
    """Supprime la facture (y compris validée/exportée) en conservant une trace d'audit sans FK."""
    from ..models import ExportRecord, InvoiceLine, InvoicePage

    document_relative = invoice.stored_path
    invoice_uuid = invoice.uuid
    status_avant = invoice.status
    trace = {
        "uuid": invoice_uuid,
        "fournisseur_id": invoice.supplier_id,
        "numero": invoice.invoice_number,
        "montant_ttc": (invoice.totals_extracted or {}).get("total_ttc") or None,
        "status_avant": status_avant,
        "lignes": int(
            db.scalar(select(func.count(InvoiceLine.id)).where(InvoiceLine.invoice_id == invoice.id)) or 0
        ),
        "pages": int(
            db.scalar(select(func.count(InvoicePage.id)).where(InvoicePage.invoice_id == invoice.id)) or 0
        ),
        "exports": int(
            db.scalar(select(func.count(ExportRecord.id)).where(ExportRecord.invoice_id == invoice.id)) or 0
        ),
    }
    db.delete(invoice)
    record_audit(
        db,
        None,
        "facture_supprimee",
        actor="utilisateur",
        entity_type="invoice",
        entity_id=None,
        details=trace,
    )
    db.commit()
    trace["photo_conservee"] = None
    if keep_image:
        try:
            trace["photo_conservee"] = _archive_document(document_relative, invoice_uuid, trace["numero"])
        except Exception as archive_error:  # noqa: BLE001
            trace["photo_erreur"] = str(archive_error)
    else:
        try:
            document_path = resolve_relative(document_relative)
            document_path.unlink(missing_ok=True)
        except StorageError:
            pass
    delete_invoice_files(invoice_uuid)
    return trace


def _archive_document(document_relative: str | None, uuid: str, invoice_number: str | None) -> str | None:
    """Déplace le fichier original (photo/scann) vers data/archives/ avant purge."""
    if not document_relative:
        return None
    try:
        source = resolve_relative(document_relative)
    except StorageError:
        return None
    if not source.is_file():
        return None
    targets_dir = settings.archives_dir
    targets_dir.mkdir(parents=True, exist_ok=True)
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "_", str(invoice_number or "facture"))[:60].strip("_")
    destination = targets_dir / f"{uuid}_{safe_number}{source.suffix or '.bin'}"
    counter = 1
    while destination.exists():
        destination = targets_dir / f"{uuid}_{safe_number}_{counter}{source.suffix or '.bin'}"
        counter += 1
    shutil.move(str(source), destination)
    return destination.relative_to(settings.data_dir).as_posix()


@router.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, confirm: bool = False, keep_image: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    invoice = _get_invoice(db, invoice_id)
    if not confirm:
        raise HTTPException(status_code=400, detail="Suppression non confirmée. Ajoutez confirm=true.")
    trace = _purge_invoice(db, invoice, keep_image=keep_image)
    return {"message": "Facture supprimée.", "invoice_id": invoice_id, "trace": trace}


@router.post("/invoices/delete-bulk")
def delete_invoices_bulk(payload: BulkDeleteRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Aucune facture sélectionnée.")
    deleted: list[int] = []
    refused: list[dict[str, Any]] = []
    for invoice_id in payload.ids[:200]:
        invoice = db.get(Invoice, invoice_id)
        if invoice is None:
            refused.append({"invoice_id": invoice_id, "reason": "introuvable"})
            continue
        trace = _purge_invoice(db, invoice, keep_image=payload.keep_image)
        deleted.append(invoice_id)
    return {"message": f"{len(deleted)} facture(s) supprimée(s).", "deleted": deleted, "refused": refused}


