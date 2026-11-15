import { useEffect, useState, useRef } from "react";
import { api, ApiError } from "../../lib/api";
import { parseAmount } from "../../lib/format";
import { fieldClass, numberFieldState, textFieldState } from "../../lib/validation";
import type { InvoiceDetail, Supplier, SupplierCandidate } from "../../types";
import { useToast } from "../Toast";
import { Icon } from "../Icon";
import { ConfidenceDot } from "../Common";
import { SupplierInputWithSuggestions } from "../SupplierInputWithSuggestions";

interface Draft {
  invoice_number: string;
  invoice_date: string;
  document_type: string;
  bl_facture: string;
  bc_number: string;
  bc_date: string;
  bl_number: string;
  bl_date: string;
  currency: string;
  supplier_name_raw: string;
  notes: string;
  total_ht: string;
  discount_total: string;
  vat_total: string;
  other_taxes: string;
  timbre: string;
  total_ttc: string;
}

const TOTAL_KEYS = ["total_ht", "discount_total", "vat_total", "other_taxes", "timbre", "total_ttc"] as const;
type TotalKey = (typeof TOTAL_KEYS)[number];

function amountToInput(value: string | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(".", ",");
}

function draftFrom(detail: InvoiceDetail): Draft {
  const totals = detail.totals_extracted ?? {};
  return {
    invoice_number: detail.invoice_number ?? "",
    invoice_date: detail.invoice_date ?? "",
    document_type: detail.document_type ?? "FACTURE",
    bl_facture: detail.bl_facture === true ? "true" : detail.bl_facture === false ? "false" : "",
    bc_number: detail.bc_number ?? "",
    bc_date: detail.bc_date ?? "",
    bl_number: detail.bl_number ?? "",
    bl_date: detail.bl_date ?? "",
    currency: detail.currency ?? "DZD",
    supplier_name_raw: detail.supplier_name_raw ?? "",
    notes: detail.notes ?? "",
    total_ht: amountToInput(totals.total_ht),
    discount_total: amountToInput(totals.discount_total),
    vat_total: amountToInput(totals.vat_total),
    other_taxes: amountToInput(totals.other_taxes),
    timbre: amountToInput(totals.timbre),
    total_ttc: amountToInput(totals.total_ttc),
  };
}

function sameAmount(left: string, right: string | null | undefined): boolean {
  return (parseAmount(left) ?? null) === (parseAmount(right) ?? null);
}

export function HeaderEditor({
  detail,
  readOnly,
  onUpdated,
}: {
  detail: InvoiceDetail;
  readOnly: boolean;
  onUpdated: (detail: InvoiceDetail) => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(detail));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { show } = useToast();

  useEffect(() => {
    setDraft(draftFrom(detail));
    setError(null);
  }, [detail.id, detail.processed_at, detail.supplier?.id]);

  const original = draftFrom(detail);
  const dirty =
    draft.invoice_number !== original.invoice_number ||
    draft.invoice_date !== original.invoice_date ||
    draft.document_type !== original.document_type ||
    draft.bl_facture !== original.bl_facture ||
    draft.bc_number !== original.bc_number ||
    draft.bc_date !== original.bc_date ||
    draft.bl_number !== original.bl_number ||
    draft.bl_date !== original.bl_date ||
    draft.currency !== original.currency ||
    draft.supplier_name_raw !== original.supplier_name_raw ||
    draft.notes !== original.notes ||
    TOTAL_KEYS.some((key) => !sameAmount(draft[key], original[key]));

  const set = (key: keyof Draft, value: string) => setDraft((current) => ({ ...current, [key]: value }));

  const confidence = (field: string): number | null => {
    if ((TOTAL_KEYS as readonly string[]).includes(field)) {
      const value = detail.totals_extracted.confidence?.[field];
      return typeof value === "number" ? value : null;
    }
    const entry = detail.header_raw?.[field];
    return entry && typeof entry.value === "number" ? entry.value : null;
  };

  const save = async () => {
    setError(null);
    if (!draft.invoice_number.trim()) {
      setError("Le numéro de facture est obligatoire avant validation.");
    }
    const payload: Record<string, unknown> = {};
    const textFields: [keyof Draft, string | null][] = [
      ["invoice_number", detail.invoice_number],
      ["bc_number", detail.bc_number],
      ["bl_number", detail.bl_number],
      ["currency", detail.currency],
      ["supplier_name_raw", detail.supplier_name_raw],
      ["notes", detail.notes],
    ];
    for (const [key, current] of textFields) {
      const value = draft[key].trim();
      if (value !== (current ?? "")) payload[key] = value === "" ? null : key === "currency" ? value.toUpperCase() : value;
    }
    const dateFields: [keyof Draft, string | null][] = [
      ["invoice_date", detail.invoice_date],
      ["bc_date", detail.bc_date],
      ["bl_date", detail.bl_date],
    ];
    for (const [key, current] of dateFields) {
      const value = draft[key];
      if (value !== (current ?? "")) payload[key] = value || null;
    }
    if (draft.document_type !== (detail.document_type ?? "FACTURE")) payload.document_type = draft.document_type;
    const originalBl = detail.bl_facture === true ? "true" : detail.bl_facture === false ? "false" : "";
    if (draft.bl_facture !== originalBl) payload.bl_facture = draft.bl_facture === "" ? null : draft.bl_facture === "true";

    const totals: Record<string, number | null> = {};
    for (const key of TOTAL_KEYS) {
      if (!sameAmount(draft[key], original[key])) {
        const parsed = parseAmount(draft[key]);
        if (draft[key].trim() !== "" && parsed === null) {
          setError(`Montant invalide pour « ${key.replace(/_/g, " ")} ». Utilisez un nombre, par exemple 1 234,50.`);
          return;
        }
        totals[key] = parsed;
      }
    }
    if (Object.keys(totals).length > 0) payload.totals = totals;

    if (Object.keys(payload).length === 0) {
      setDraft(original);
      show("Aucune modification à enregistrer.", "info");
      return;
    }

    setSaving(true);
    try {
      const updated = await api.updateHeader(detail.id, payload);
      setDraft(draftFrom(updated));
      onUpdated(updated);
      show("En-tête enregistré. Les totaux et contrôles ont été recalculés.", "success");
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Enregistrement impossible.";
      setError(message);
      show(message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="form-stack">
      {(detail.readiness?.hard?.length || detail.checks?.some((c) => c.severity === "error")) ? (
        <div className="banner banner-danger">
          <Icon name="alert" size={16} />
          <div>
            <strong>Informations obligatoires manquantes</strong>
            <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
              {detail.readiness?.hard?.map((item, idx) => (
                <li key={idx} className="small">{item.message}</li>
              ))}
              {detail.checks?.filter((c) => c.severity === "error" && !detail.readiness?.hard?.some((h) => h.message === c.message)).map((item, idx) => (
                <li key={`c-${idx}`} className="small">{item.message}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      <div className="form-section">
        <div className="section-title">
          <span>Identification</span>
          <span className="muted small">Champs du bon d'entrée</span>
        </div>
        <div className="form-grid">
          <label className={`field ${fieldClass(textFieldState(draft.invoice_number, readOnly, true))}`}>
            <span>
              N° facture (obligatoire) <ConfidenceDot value={confidence("invoice_number")} />
            </span>
            <input
              value={draft.invoice_number}
              onChange={(event) => set("invoice_number", event.target.value)}
              disabled={readOnly}
              placeholder="Ex. FA-2026-001"
            />
          </label>
          <label className="field">
            <span>
              Date facture <ConfidenceDot value={confidence("invoice_date")} />
            </span>
            <input type="date" value={draft.invoice_date} onChange={(event) => set("invoice_date", event.target.value)} disabled={readOnly} />
          </label>
          <label className="field">
            <span>Type de document</span>
            <select value={draft.document_type} onChange={(event) => set("document_type", event.target.value)} disabled={readOnly}>
              <option value="FACTURE">Facture</option>
              <option value="BL">Bon de livraison</option>
              <option value="AVOIR">Avoir</option>
              <option value="AUTRE">Autre</option>
            </select>
          </label>
          <label className="field">
            <span>Devise</span>
            <input
              value={draft.currency}
              onChange={(event) => set("currency", event.target.value.toUpperCase())}
              maxLength={8}
              disabled={readOnly}
              placeholder="DZD"
            />
          </label>
        </div>
      </div>

      <div className="form-section">
        <div className="section-title">
          <span>Rattachement BC / BL</span>
          <span className="muted small">Selon les informations présentes sur le document</span>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>BL-Facture ?</span>
            <select value={draft.bl_facture} onChange={(event) => set("bl_facture", event.target.value)} disabled={readOnly}>
              <option value="">Non renseigné</option>
              <option value="true">Oui — la facture tient lieu de BL</option>
              <option value="false">Non — BL distinct</option>
            </select>
          </label>
          <label className="field">
            <span>N° BC</span>
            <input value={draft.bc_number} onChange={(event) => set("bc_number", event.target.value)} disabled={readOnly} />
          </label>
          <label className="field">
            <span>Date BC</span>
            <input type="date" value={draft.bc_date} onChange={(event) => set("bc_date", event.target.value)} disabled={readOnly} />
          </label>
          <label className="field">
            <span>N° BL</span>
            <input value={draft.bl_number} onChange={(event) => set("bl_number", event.target.value)} disabled={readOnly} />
          </label>
          <label className="field">
            <span>Date BL</span>
            <input type="date" value={draft.bl_date} onChange={(event) => set("bl_date", event.target.value)} disabled={readOnly} />
          </label>
          <label className="field">
            <span>
              Fournisseur (tapez pour rechercher ou créer) <ConfidenceDot value={confidence("supplier_name_raw")} />
              {detail.supplier ? (
                <span className="status-badge tone-success" style={{ marginLeft: "0.5rem" }}>
                  <Icon name="check-circle" size={13} /> Confirmé
                </span>
              ) : (
                <span className="status-badge tone-danger" style={{ marginLeft: "0.5rem" }}>
                  <Icon name="alert-triangle" size={13} /> Requis pour validation
                </span>
              )}
            </span>
            <SupplierInputWithSuggestions
              value={draft.supplier_name_raw}
              onChange={(value) => set("supplier_name_raw", value)}
              onSupplierConfirmed={(_supplierId, _supplierName, updated) => {
                // La confirmation relance le rapprochement côté serveur et
                // renvoie la facture recalculée : on remplace l'état courant.
                if (updated) onUpdated(updated);
              }}
              disabled={readOnly}
              invoiceId={detail.id}
            />
            {detail.supplier ? (
              <span className="muted small">
                Code Tulip : <span className="mono">{detail.supplier_code}</span>
                {detail.supplier.tax_id ? ` • NIF : ${detail.supplier.tax_id}` : ""}
                {detail.supplier_name_raw &&
                 detail.supplier_name_raw !== detail.supplier.name &&
                 ` • Sur le document : ${detail.supplier_name_raw}`}
              </span>
            ) : null}
          </label>
        </div>
      </div>

      <div className="form-section">
        <div className="section-title">
          <span>Montants extraits</span>
          <span className="muted small">Corrigez uniquement en cas d'écart constaté sur le document</span>
        </div>
        <div className="form-grid three">
          {(
            [
              ["total_ht", "Total HT"],
              ["discount_total", "Remise totale"],
              ["vat_total", "TVA totale"],
              ["other_taxes", "Autres taxes"],
              ["timbre", "Timbre"],
              ["total_ttc", "Total TTC"],
            ] as [TotalKey, string][]
          ).map(([key, label]) => (
            <label className={`field ${fieldClass(numberFieldState(draft[key], readOnly))}`} key={key}>
              <span>
                {label} <ConfidenceDot value={confidence(key)} />
              </span>
              <input
                className="mono"
                inputMode="decimal"
                value={draft[key]}
                onChange={(event) => set(key, event.target.value)}
                disabled={readOnly}
                placeholder="0,00"
              />
            </label>
          ))}
        </div>
        <div className="field-legend">
          <span className="legend-item"><span className="legend-swatch danger" /> valeur obligatoire manquante ou montant invalide</span>
          <span className="legend-item"><span className="legend-swatch success" /> valeur valide</span>
        </div>
        {detail.totals_extracted.vat_breakdown && Object.keys(detail.totals_extracted.vat_breakdown).length > 0 && (
          <div className="vat-breakdown">
            <span className="muted small">Détail TVA :</span>
            {Object.entries(detail.totals_extracted.vat_breakdown).map(([rate, amount]) => (
              <span key={rate} className="chip mono">
                {rate} % → {amount}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="form-section">
        <label className="field">
          <span>Notes internes</span>
          <textarea
            rows={2}
            value={draft.notes}
            onChange={(event) => set("notes", event.target.value)}
            disabled={readOnly}
            placeholder="Commentaire de vérification, information de livraison…"
          />
        </label>
      </div>

      {error && <p className="inline-error">{error}</p>}

      {!readOnly && (
        <div className="form-actions">
          <span className={`dirty-hint${dirty ? " visible" : ""}`}>
            <span className="dirty-dot" /> Modifications non enregistrées
          </span>
          <button type="button" className="button" onClick={() => setDraft(draftFrom(detail))} disabled={!dirty || saving}>
            Annuler
          </button>
          <button type="button" className="button button-primary" onClick={save} disabled={!dirty || saving}>
            {saving ? <span className="spinner small light" /> : <Icon name="save" size={16} />}
            Enregistrer
          </button>
        </div>
      )}
    </div>
  );
}
