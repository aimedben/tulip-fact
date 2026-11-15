import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { InvoiceDetail, InvoiceLine, ReprocessMethod } from "../types";
import {
  formatDateFR,
  formatDateTimeFR,
  formatFileSize,
  formatMoney,
  isLocked,
  isProcessing,
  parseAmount,
} from "../lib/format";
import { CheckList, EmptyState, ProgressBar, Spinner } from "../components/Common";
import { StatusBadge } from "../components/StatusBadge";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { DocumentViewer } from "../components/review/DocumentViewer";
import { HeaderEditor } from "../components/review/HeaderEditor";
import { LinesEditor } from "../components/review/LinesEditor";
import { ExportModal, ValidationModal } from "../components/review/ReviewModals";
import { TulipBeModal } from "../components/TulipBeModal";
import { useToast } from "../components/Toast";

const AUDIT_LABELS: Record<string, string> = {
  import: "Import du document",
  extraction: "Extraction OCR",
  correction_entete: "Correction de l'en-tête",
  correction_ligne: "Correction d'une ligne",
  confirmation_fournisseur: "Confirmation fournisseur",
  confirmation_article: "Rapprochement article",
  validation: "Validation",
  export: "Export",
  relance_traitement: "Relance du traitement",
  ajout_ligne: "Ajout d'une ligne",
  suppression_ligne: "Suppression d'une ligne",
};

function auditLabel(action: string): string {
  return AUDIT_LABELS[action] ?? action.replace(/_/g, " ");
}

const REPROCESS_METHODS: { value: ReprocessMethod; label: string; hint: string }[] = [
  { value: "auto", label: "Automatique", hint: "Configuration actuelle de l'application" },
  { value: "ocr", label: "OCR local", hint: "Tesseract uniquement, sans IA" },
  { value: "gemini", label: "Gemini", hint: "Analyse d'image Gemini" },
  { value: "chatgpt", label: "ChatGPT", hint: "Analyse d'image OpenAI" },
  { value: "nemotron", label: "Nemotron (opencode)", hint: "Analyse d'image opencode Zen" },
];

function amountTone(extracted: string | null | undefined, calculated: string | null | undefined): string {
  const left = parseAmount(extracted);
  const right = parseAmount(calculated);
  if (left === null || right === null) return "";
  return Math.abs(left - right) > 0.01 ? "mismatch" : "match";
}

export function InvoiceReview() {
  const { id } = useParams();
  const invoiceId = Number(id);
  const navigate = useNavigate();
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedLineId, setSelectedLineId] = useState<number | null>(null);
  const [validateOpen, setValidateOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [reprocessMethod, setReprocessMethod] = useState<ReprocessMethod>("auto");
  const [tulipBeOpen, setTulipBeOpen] = useState(false);
  const [checksOpen, setChecksOpen] = useState(false);
  const { show } = useToast();
  const reprocessLabel = REPROCESS_METHODS.find((option) => option.value === reprocessMethod)?.label ?? "Automatique";

  useEffect(() => {
    let cancelled = false;
    if (!Number.isFinite(invoiceId)) {
      setLoadError("Identifiant de facture invalide.");
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .invoice(invoiceId)
      .then((result) => {
        if (cancelled) return;
        setDetail(result);
        setLoadError(null);
        if (result.lines.length > 0) setSelectedLineId(result.lines[0].id);
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Facture introuvable.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [invoiceId]);

  useEffect(() => {
    if (!detail || !isProcessing(detail.status)) return;
    const timer = window.setInterval(() => {
      api
        .invoice(invoiceId)
        .then((result) => setDetail(result))
        .catch(() => undefined);
    }, 1600);
    return () => window.clearInterval(timer);
  }, [detail?.status, invoiceId]);

  const update = (updated: InvoiceDetail) => {
    setDetail(updated);
    if (selectedLineId !== null && !updated.lines.some((line) => line.id === selectedLineId)) {
      setSelectedLineId(updated.lines[0]?.id ?? null);
    }
  };

  const deleteInvoice = async () => {
    setDeleting(true);
    try {
      await api.deleteInvoice(invoiceId);
      show("Facture supprimée.", "success");
      navigate("/history");
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : "Suppression impossible.";
      show(message, "error");
      setDeleting(false);
    }
  };

  const reprocess = async () => {
    setReprocessing(true);
    try {
      await api.reprocess(invoiceId, reprocessMethod);
      const refreshed = await api.invoice(invoiceId);
      setDetail(refreshed);
      show(`Traitement relancé avec ${reprocessLabel}.`, "success");
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : "Relance impossible.";
      show(message, "error");
    } finally {
      setReprocessing(false);
    }
  };

  const scanWithMethod = async (method: ReprocessMethod) => {
    setReprocessing(true);
    const methodLabel = REPROCESS_METHODS.find((m) => m.value === method)?.label ?? method;
    try {
      await api.reprocess(invoiceId, method);
      const refreshed = await api.invoice(invoiceId);
      setDetail(refreshed);
      show(`Scan lancé avec ${methodLabel}.`, "success");
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : "Scan impossible.";
      show(message, "error");
    } finally {
      setReprocessing(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-page">
        <Spinner label="Chargement de la facture…" />
      </div>
    );
  }

  if (loadError || !detail) {
    return (
      <EmptyState
        icon="invoice"
        title="Facture indisponible"
        description={loadError ?? "Cette facture n'existe pas ou a été supprimée."}
        action={
          <Link to="/history" className="button">
            <Icon name="arrowLeft" size={16} /> Retour à l'historique
          </Link>
        }
      />
    );
  }

  const processing = isProcessing(detail.status);
  const locked = isLocked(detail.status);
  const readOnly = locked || processing;
  const selectedLine: InvoiceLine | null = detail.lines.find((line) => line.id === selectedLineId) ?? null;
  const hardCount = detail.readiness.hard.length;
  const accountingCount = detail.readiness.accounting_errors.length;
  const allChecks = [...detail.checks, ...detail.warnings];
  const blockers = allChecks.filter((check) => check.severity === "error").length;
  const warnCount = allChecks.filter((check) => check.severity === "warning").length;

  const readinessLabel = locked
    ? "Facture verrouillée"
    : processing
      ? "Traitement en cours"
      : hardCount > 0
        ? `${hardCount} information${hardCount > 1 ? "s" : ""} obligatoire${hardCount > 1 ? "s" : ""} manquante${hardCount > 1 ? "s" : ""}`
        : accountingCount > 0
          ? `${accountingCount} écart${accountingCount > 1 ? "s" : ""} comptable${accountingCount > 1 ? "s" : ""} à confirmer`
          : "Prête à valider";

  const totalRows = [
    { label: "Total HT", extracted: detail.totals_extracted.total_ht, calculated: detail.totals_calculated.total_ht },
    { label: "TVA", extracted: detail.totals_extracted.vat_total, calculated: detail.totals_calculated.vat_total },
    { label: "Timbre", extracted: detail.totals_extracted.timbre, calculated: detail.totals_calculated.timbre },
    { label: "Autres taxes", extracted: detail.totals_extracted.other_taxes, calculated: detail.totals_calculated.other_taxes },
    { label: "Total TTC", extracted: detail.totals_extracted.total_ttc, calculated: detail.totals_calculated.total_ttc },
  ];

  return (
    <>
      <div className="review-heading">
        <Link to="/history" className="back-link">
          <Icon name="arrowLeft" size={16} /> Historique
        </Link>
        <div className="review-title-row">
          <div>
            <div className="review-title">
              <h1>{detail.invoice_number ? `Facture ${detail.invoice_number}` : `Facture #${detail.id}`}</h1>
              <StatusBadge status={detail.status} />
              {detail.is_duplicate && <span className="status-badge tone-danger">Doublon potentiel</span>}
            </div>
            <p className="page-subtitle">
              {detail.supplier?.name ?? detail.supplier_name_raw ?? "Fournisseur non identifié"} ·{" "}
              {formatDateFR(detail.invoice_date)} · <span className="mono">{detail.original_filename}</span> ·{" "}
              {formatFileSize(detail.file_size)}
            </p>
          </div>
          <div className="review-heading-actions">
            {locked && (
              <button type="button" className="button" onClick={() => setTulipBeOpen(true)} disabled={processing}>
                <Icon name="database" size={16} /> Créer BE Tulip
              </button>
            )}
            {!locked && (
              <button
                type="button"
                className="button button-primary"
                onClick={() => setValidateOpen(true)}
                disabled={processing}
              >
                <Icon name="check" size={16} /> Valider
              </button>
            )}
            {!locked && detail.status !== "EXTRACTION" && detail.status !== "IMPORTEE" && (
              <div className="reprocess-control">
                <select
                  aria-label="Méthode de scan"
                  title="Choisir la méthode de scan"
                  value={reprocessMethod}
                  onChange={(event) => setReprocessMethod(event.target.value as ReprocessMethod)}
                  disabled={reprocessing}
                >
                  {REPROCESS_METHODS.map((option) => (
                    <option key={option.value} value={option.value} title={option.hint}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="button"
                  onClick={reprocess}
                  disabled={reprocessing}
                  title={`Relancer avec ${reprocessLabel}`}
                >
                  {reprocessing ? <span className="spinner small" /> : <Icon name="refresh" size={16} />} Relancer l'OCR
                </button>
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => scanWithMethod("gemini")}
                  disabled={reprocessing}
                  title="Scanner avec Gemini (utilise la clé API de la configuration)"
                >
                  {reprocessing ? <span className="spinner small" /> : <Icon name="spark" size={16} />} Scanner avec Gemini
                </button>
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => scanWithMethod("chatgpt")}
                  disabled={reprocessing}
                  title="Scanner avec ChatGPT (utilise la clé API de la configuration)"
                >
                  {reprocessing ? <span className="spinner small" /> : <Icon name="spark" size={16} />} Scanner avec ChatGPT
                </button>
              </div>
            )}
            <button type="button" className="button button-ghost-danger" onClick={() => setDeleteOpen(true)} disabled={processing}>
              <Icon name="trash" size={16} /> Supprimer
            </button>
          </div>
        </div>
      </div>

      {processing && (
        <div className="banner banner-info processing-banner">
          <Spinner />
          <div className="processing-text">
            <strong>{detail.stage}</strong>
            <span className="muted small">
              {detail.progress} % · traitement OCR et extraction en cours. Cette page se met à jour automatiquement.
            </span>
            <ProgressBar value={detail.progress} />
          </div>
        </div>
      )}

      {detail.status === "ECHEC" && (
        <div className="banner banner-danger">
          <Icon name="alert" size={18} />
          <div>
            <strong>Le traitement a échoué</strong>
            <p>{detail.error_message ?? "Consultez le message d'erreur et relancez le traitement."}</p>
            <button type="button" className="button button-sm" onClick={reprocess} disabled={reprocessing}>
              <Icon name="refresh" size={15} /> Relancer le traitement ({reprocessLabel})
            </button>
          </div>
        </div>
      )}

      {detail.is_duplicate && (
        <div className="banner banner-warning">
          <Icon name="alert" size={18} />
          <div>
            <strong>Doublon potentiel détecté</strong>
            <p>
              {detail.duplicate_reason ??
                "Un document identique ou portant le même numéro fournisseur existe déjà dans l'application."}
              {detail.duplicate_of_id && (
                <>
                  {" "}
                  <Link to={`/invoices/${detail.duplicate_of_id}`}>Consulter la facture existante #{detail.duplicate_of_id}</Link>.
                </>
              )}
            </p>
          </div>
        </div>
      )}

      {locked && (
        <div className="banner banner-success">
          <Icon name="shield" size={18} />
          <div>
            <strong>
              {detail.status === "EXPORTEE" ? "Facture exportée" : "Facture validée"} — document verrouillé
            </strong>
            <p>
              Validée par <strong>{detail.validation_user ?? "—"}</strong> le {formatDateTimeFR(detail.validated_at)}. Toute
              correction ultérieure doit passer par un avoir ou une procédure explicite.
            </p>
          </div>
        </div>
      )}

      <div className="review-top-split">
        <DocumentViewer detail={detail} selectedLine={selectedLine} onSelectLine={(line) => setSelectedLineId(line.id)} />
        <section className="panel review-header-panel">
          <header className="panel-header">
            <div>
              <h2>En-tête de facture</h2>
              <p className="muted small">Champs enregistrés dans Tulip</p>
            </div>
            <span className="muted tiny">Les corrections sont historisées</span>
          </header>
          <div className="panel-body">
            <HeaderEditor detail={detail} readOnly={readOnly} onUpdated={update} />
          </div>
        </section>
      </div>

      <LinesEditor
        detail={detail}
        readOnly={readOnly}
        selectedLineId={selectedLineId}
        onSelectLine={(line) => setSelectedLineId(line.id)}
        onUpdated={update}
      />

      <div className="review-bottom">

        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>Totaux</h2>
              <p className="muted small">Extrait du document et recalculé</p>
            </div>
          </header>
          <div className="panel-body">
            <table className="totals-table">
              <thead>
                <tr>
                  <th>Poste</th>
                  <th className="align-right">Extrait</th>
                  <th className="align-right">Calculé</th>
                </tr>
              </thead>
              <tbody>
                {totalRows.map((row) => (
                  <tr key={row.label} className={amountTone(row.extracted, row.calculated)}>
                    <td>{row.label}</td>
                    <td className="align-right mono">{formatMoney(row.extracted, detail.currency)}</td>
                    <td className="align-right mono">{formatMoney(row.calculated, detail.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted tiny">
              Tolérance de contrôle appliquée aux écarts d'arrondi. Un écart n'est jamais corrigé silencieusement.
            </p>
          </div>
        </section>

        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>Audit & exports</h2>
              <p className="muted small">Traçabilité des opérations</p>
            </div>
          </header>
          <div className="panel-body">
            {detail.audits.length === 0 ? (
              <p className="muted small">Aucune opération enregistrée.</p>
            ) : (
              <ol className="audit-list">
                {detail.audits.slice(0, 7).map((entry) => (
                  <li key={entry.id}>
                    <span className="audit-dot" />
                    <div>
                      <strong>{auditLabel(entry.action)}</strong>
                      <div className="muted tiny">
                        {entry.actor} · {formatDateTimeFR(entry.created_at)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {detail.exports.length > 0 && (
              <div className="export-history">
                <span className="label">Exports</span>
                {detail.exports.slice(0, 4).map((record) => (
                  <a key={record.id} href={record.download_url} className="export-chip">
                    <span className="format-chip">{record.format.toUpperCase()}</span>
                    <Icon name="download" size={14} />
                  </a>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="action-bar">
        <div className="action-bar-status">
          <StatusBadge status={detail.status} />
          <div>
            <strong>{readinessLabel}</strong>
            <span className="muted tiny">
              {locked
                ? "Export disponible ; toute correction nécessite une procédure explicite."
                : "Le recalcul est effectué côté serveur avant validation."}
            </span>
          </div>
        </div>
        <div className="action-bar-buttons">
          <a href="#controles" className="button">
            Voir les contrôles
          </a>
          <button
            type="button"
            className="button"
            disabled={detail.status !== "VALIDEE" && detail.status !== "EXPORTEE"}
            title={
              detail.status !== "VALIDEE" && detail.status !== "EXPORTEE"
                ? "La facture doit être validée avant l'export."
                : undefined
            }
            onClick={() => setExportOpen(true)}
          >
            <Icon name="download" size={16} /> Exporter
          </button>
          <button
            type="button"
            className="button button-primary"
            disabled={locked || processing}
            onClick={() => setValidateOpen(true)}
          >
            <Icon name="check" size={16} /> Valider
          </button>
        </div>
      </div>

      <ValidationModal
        detail={detail}
        open={validateOpen}
        onClose={() => setValidateOpen(false)}
        onValidated={(updated) => update(updated)}
      />

      <TulipBeModal
        invoiceId={invoiceId}
        invoiceNumber={detail.invoice_number ?? `#${detail.id}`}
        open={tulipBeOpen}
        onClose={() => setTulipBeOpen(false)}
        onCreated={() => {
          api
            .invoice(invoiceId)
            .then((updated) => setDetail(updated))
            .catch(() => undefined);
        }}
      />

      <ExportModal
        detail={detail}
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExported={() => {
          api
            .invoice(invoiceId)
            .then((updated) => setDetail(updated))
            .catch(() => undefined);
        }}
      />

      <Modal
        open={deleteOpen}
        title="Supprimer la facture ?"
        subtitle={`${detail.original_filename} — action définitive`}
        onClose={() => setDeleteOpen(false)}
        footer={
          <>
            <button type="button" className="button" onClick={() => setDeleteOpen(false)}>
              Annuler
            </button>
            <button type="button" className="button button-danger" onClick={deleteInvoice} disabled={deleting}>
              {deleting ? <span className="spinner small light" /> : <Icon name="trash" size={16} />} Supprimer
            </button>
          </>
        }
      >
        <p className="muted">
          Le document, ses pages et ses données extraites seront supprimés définitivement, y compris si la facture est
          déjà validée ou exportée. Une trace d'audit (facture_supprimee) est conservée.
        </p>
      </Modal>
    </>
  );
}
