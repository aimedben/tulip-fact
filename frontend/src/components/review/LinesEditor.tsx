import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import { formatMoney, matchLabel, parseAmount } from "../../lib/format";
import { fieldClass, numberFieldState, textFieldState } from "../../lib/validation";
import type { InvoiceDetail, InvoiceLine, ProductCandidate } from "../../types";
import { BarcodeScanInput } from "../BarcodeScanInput";
import { Icon } from "../Icon";
import { Modal } from "../Modal";
import { ConfidenceDot } from "../Common";
import { useToast } from "../Toast";
import { SupplierDropdown } from "../SupplierDropdown";
import { ProductAutocomplete } from "../ProductAutocomplete";

function decimalInput(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(".", ",");
}

interface LineDraft {
  raw_reference: string;
  raw_designation: string;
  lot_number: string;
  packages: string;
  quantity: string;
  unit_price_ht: string;
  vat_rate: string;
  line_total_ht_extracted: string;
  discount_value: string;
  prix_vente: string;
}

const TEXT_FIELDS = ["raw_reference", "raw_designation", "lot_number"] as const;
const NUMBER_FIELDS = ["packages", "quantity", "unit_price_ht", "vat_rate", "line_total_ht_extracted", "discount_value", "prix_vente"] as const;

function draftFrom(line: InvoiceLine): LineDraft {
  return {
    raw_reference: line.raw_reference ?? "",
    raw_designation: line.raw_designation ?? "",
    lot_number: line.lot_number ?? "",
    packages: decimalInput(line.packages),
    quantity: decimalInput(line.quantity),
    unit_price_ht: decimalInput(line.unit_price_ht),
    vat_rate: decimalInput(line.vat_rate),
    line_total_ht_extracted: decimalInput(line.line_total_ht_extracted),
    discount_value: decimalInput(line.discount_value),
    prix_vente: decimalInput(line.prix_vente),
  };
}

function sameNumber(left: string, right: number | null | undefined): boolean {
  return (parseAmount(left) ?? null) === (right ?? null);
}

function numberOrNull(value: string): number | null {
  return parseAmount(value);
}

function LineRow({
  line,
  currency,
  readOnly,
  selected,
  saving,
  supplierId,
  suggestions,
  suggestionsLoading,
  onSelect,
  onSave,
  onDelete,
  onMatch,
  onPickProduct,
  onNewProduct,
}: {
  line: InvoiceLine;
  currency: string;
  readOnly: boolean;
  selected: boolean;
  saving: boolean;
  supplierId: number | null;
  suggestions: ProductCandidate[];
  suggestionsLoading: boolean;
  onSelect: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<boolean>;
  onDelete: () => void;
  onMatch: () => void;
  onPickProduct: (productId: number) => void;
  onNewProduct: () => void;
}) {
  const [draft, setDraft] = useState<LineDraft>(() => draftFrom(line));
  const [error, setError] = useState<string | null>(null);
  const { show } = useToast();

  useEffect(() => {
    setDraft(draftFrom(line));
    setError(null);
  }, [line.id, line.raw_designation, line.raw_reference, line.quantity, line.unit_price_ht, line.line_total_ht_extracted, line.vat_rate, line.packages, line.discount_value, line.lot_number]);

  const orig = draftFrom(line);
  const dirty =
    TEXT_FIELDS.some((key) => draft[key] !== orig[key]) ||
    NUMBER_FIELDS.some((key) => !sameNumber(draft[key], key === "packages" ? line.packages : line[key]));

  const set = (key: keyof LineDraft, value: string) => setDraft((current) => ({ ...current, [key]: value }));

  // Validation visuelle : bordure rouge sur obligatoire manquant / valeur
  // invalide, bordure verte sur valeur valide.
  const designationState = textFieldState(draft.raw_designation, readOnly, true);
  const cellState = (key: keyof LineDraft) => fieldClass(numberFieldState(draft[key], readOnly));

  const submit = async () => {
    setError(null);
    if (!draft.raw_designation.trim()) {
      setError("La désignation est obligatoire.");
      return;
    }
    for (const key of NUMBER_FIELDS) {
      if (draft[key].trim() !== "" && parseAmount(draft[key]) === null) {
        setError("Valeur numérique invalide.");
        return;
      }
    }
    const payload: Record<string, unknown> = {};
    for (const key of TEXT_FIELDS) {
      const value = draft[key].trim();
      const current = (line[key] ?? "") as string;
      if (value !== current) payload[key] = value === "" ? null : value;
    }
    for (const key of NUMBER_FIELDS) {
      if (!sameNumber(draft[key], line[key])) payload[key] = numberOrNull(draft[key]);
    }
    if (Object.keys(payload).length === 0) return;
    const ok = await onSave(payload);
    if (!ok) setError("La modification n'a pas pu être enregistrée.");
  };

  const calculatedTone =
    line.line_total_ht_extracted !== null &&
    line.line_total_ht_calculated !== null &&
    Math.abs(line.line_total_ht_extracted - line.line_total_ht_calculated) > 0.01
      ? "mismatch"
      : "";

  return (
    <tr className={`${selected ? "row-selected" : ""}${dirty ? " row-dirty" : ""}`}>
      <td className="line-pos">
        <button type="button" className={`position-button${selected ? " active" : ""}`} onClick={onSelect} title="Afficher sur le document">
          {line.position}
        </button>
        <ConfidenceDot value={Number(line.confidence?.global ?? 0)} source="extraction de la ligne" />
      </td>
      <td>
        <input
          className="cell-input mono"
          value={draft.raw_reference}
          onChange={(event) => set("raw_reference", event.target.value)}
          disabled={readOnly}
          aria-label={`Référence ligne ${line.position}`}
        />
      </td>
      <td className="designation-cell">
        {readOnly ? (
          <input
            className="cell-input"
            value={draft.raw_designation}
            onChange={(event) => set("raw_designation", event.target.value)}
            disabled
            aria-label={`Désignation ligne ${line.position}`}
          />
        ) : (
          <ProductAutocomplete
            value={draft.raw_designation}
            onChange={(value) => set("raw_designation", value)}
            onPick={(candidate) => set("raw_designation", candidate.designation)}
            onAssociate={(candidate) => {
              set("raw_designation", candidate.designation);
              onPickProduct(candidate.product_id);
            }}
            supplierId={supplierId}
            reference={draft.raw_reference}
            className={`cell-input ${fieldClass(designationState)}`}
            ariaLabel={`Désignation ligne ${line.position}`}
          />
        )}
        {error ? (
          <span className="cell-error">{error}</span>
        ) : (
          designationState === "error" && <span className="cell-error">Désignation obligatoire</span>
        )}
      </td>
      <td>
        <input
          className="cell-input mono"
          value={draft.lot_number}
          onChange={(event) => set("lot_number", event.target.value)}
          disabled={readOnly}
          aria-label={`Lot ligne ${line.position}`}
        />
      </td>
      <td>
        <input
          className="cell-input mono narrow"
          inputMode="decimal"
          value={draft.packages}
          onChange={(event) => set("packages", event.target.value)}
          disabled={readOnly}
          aria-label={`Colis ligne ${line.position}`}
        />
      </td>
      <td>
        <input
          className="cell-input mono narrow"
          inputMode="decimal"
          value={draft.quantity}
          onChange={(event) => set("quantity", event.target.value)}
          disabled={readOnly}
          aria-label={`Quantité ligne ${line.position}`}
        />
      </td>
      <td>
        <input
          className="cell-input mono"
          inputMode="decimal"
          value={draft.unit_price_ht}
          onChange={(event) => set("unit_price_ht", event.target.value)}
          disabled={readOnly}
          aria-label={`Prix unitaire ligne ${line.position}`}
        />
      </td>
      <td>
        <input
          className="cell-input mono narrow"
          inputMode="decimal"
          value={draft.prix_vente}
          onChange={(event) => set("prix_vente", event.target.value)}
          disabled={readOnly}
          placeholder="0"
          aria-label={`Prix de vente ligne ${line.position}`}
        />
      </td>
      <td>
        <input
          className="cell-input mono narrow"
          inputMode="decimal"
          value={draft.discount_value}
          onChange={(event) => set("discount_value", event.target.value)}
          disabled={readOnly}
          placeholder="0"
          aria-label={`Remise ligne ${line.position}`}
        />
      </td>
      <td>
        <input
          className="cell-input mono narrow"
          inputMode="decimal"
          value={draft.vat_rate}
          onChange={(event) => set("vat_rate", event.target.value)}
          disabled={readOnly}
          aria-label={`TVA ligne ${line.position}`}
        />
      </td>
      <td>
        <input
          className={`cell-input mono${calculatedTone ? " input-warning" : ""}`}
          inputMode="decimal"
          value={draft.line_total_ht_extracted}
          onChange={(event) => set("line_total_ht_extracted", event.target.value)}
          disabled={readOnly}
          aria-label={`Total HT ligne ${line.position}`}
        />
        {calculatedTone && (
          <div className="cell-hint warning-text">
            calculé {formatMoney(line.line_total_ht_calculated, currency)}
          </div>
        )}
      </td>
      <td className="match-cell">
        {line.tulip_product ? (
          <>
            <span className="product-code mono">{line.tulip_product.tulip_code}</span>
            <span className="product-name" title={line.tulip_product.designation}>
              {line.tulip_product.designation}
            </span>
            <span className={`match-badge tone-${line.match_status === "CONFIRME" ? "success" : "accent"}`}>
              {matchLabel(line.match_status)}
            </span>
            {!readOnly && (
              <button type="button" className="mini-link" onClick={onMatch}>
                Changer
              </button>
            )}
          </>
        ) : (
          <>
            <span className={`match-badge tone-${line.match_status === "SUGGERE" ? "warning" : "danger"}`}>
              {matchLabel(line.match_status)}
            </span>
            {line.match_score !== null && (
              <span className="muted tiny">meilleur score {Math.round(line.match_score * 100)} %</span>
            )}
            {!readOnly && (
              <>
                <select
                  className="product-select"
                  value=""
                  onChange={(event) => {
                    const value = event.target.value;
                    if (value === "__new__") onNewProduct();
                    else if (value) onPickProduct(Number(value));
                  }}
                  disabled={suggestionsLoading}
                >
                  <option value="">
                    {suggestionsLoading
                      ? "Recherche d'articles…"
                      : suggestions.length > 0
                        ? "— choisir l'article Tulip —"
                        : "— aucun article proposé —"}
                  </option>
                  {suggestions.map((candidate) => (
                    <option key={candidate.product_id} value={candidate.product_id}>
                      {candidate.tulip_code} · {candidate.designation}
                      {candidate.reference ? ` · réf. art. ${candidate.reference}` : ""}
                      {candidate.barcode ? ` · ${candidate.barcode}` : ""}
                      {candidate.score ? ` (${Math.round(candidate.score * 100)} %)` : ""}
                    </option>
                  ))}
                  <option value="__new__">➕ Nouveau produit (absent du référentiel)</option>
                </select>
                <button type="button" className="mini-link strong" onClick={onMatch}>
                  Recherche avancée
                </button>
              </>
            )}
          </>
        )}
      </td>
      <td className="row-actions">
        {!readOnly && (
          <>
            <button
              type="button"
              className={`icon-button${dirty ? " active" : ""}`}
              disabled={!dirty || saving}
              onClick={submit}
              title="Enregistrer la ligne"
            >
              {saving ? <span className="spinner small" /> : <Icon name="save" size={15} />}
            </button>
            <button type="button" className="icon-button danger-hover" onClick={onDelete} title="Supprimer la ligne">
              <Icon name="trash" size={15} />
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

interface AddDraft {
  raw_reference: string;
  raw_designation: string;
  lot_number: string;
  packages: string;
  quantity: string;
  unit_price_ht: string;
  vat_rate: string;
  line_total_ht_extracted: string;
}

const emptyAdd: AddDraft = {
  raw_reference: "",
  raw_designation: "",
  lot_number: "",
  packages: "",
  quantity: "",
  unit_price_ht: "",
  vat_rate: "",
  line_total_ht_extracted: "",
};

export function LinesEditor({
  detail,
  readOnly,
  selectedLineId,
  onSelectLine,
  onUpdated,
}: {
  detail: InvoiceDetail;
  readOnly: boolean;
  selectedLineId: number | null;
  onSelectLine: (line: InvoiceLine) => void;
  onUpdated: (detail: InvoiceDetail) => void;
}) {
  const [savingId, setSavingId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InvoiceLine | null>(null);
  const [productTarget, setProductTarget] = useState<InvoiceLine | null>(null);
  const [newProductTarget, setNewProductTarget] = useState<InvoiceLine | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<Record<number, ProductCandidate[]>>({});
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    let cancelled = false;
    const pending = detail.lines.filter((line) => !line.tulip_product);
    if (pending.length === 0) {
      setSuggestions({});
      return;
    }
    setSuggestionsLoading(true);
    void (async () => {
      const entries: Record<number, ProductCandidate[]> = {};
      await Promise.all(
        pending.map(async (line) => {
          if ((line.match_candidates ?? []).length > 0) {
            entries[line.id] = line.match_candidates;
            return;
          }
          try {
            const result = await api.suggestProducts(line.raw_designation, detail.supplier_id, line.raw_reference);
            entries[line.id] = result.items.slice(0, 8);
          } catch {
            entries[line.id] = [];
          }
        }),
      );
      if (!cancelled) {
        setSuggestions(entries);
        setSuggestionsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [detail.id, detail.supplier_id, detail.lines]);

  const run = async (operation: () => Promise<InvoiceDetail>, successMessage?: string): Promise<boolean> => {
    try {
      const updated = await operation();
      onUpdated(updated);
      if (successMessage) show(successMessage, "success");
      return true;
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : "Opération impossible.";
      show(message, "error");
      return false;
    }
  };

  const saveLine = async (line: InvoiceLine, payload: Record<string, unknown>) => {
    setSavingId(line.id);
    const ok = await run(() => api.updateLine(detail.id, line.id, payload));
    setSavingId(null);
    return ok;
  };

  const removeLine = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    const ok = await run(() => api.deleteLine(detail.id, target.id), "Ligne supprimée.");
    if (ok) setDeleteTarget(null);
  };

  const confirmProduct = async (productId: number) => {
    if (!productTarget) return;
    const target = productTarget;
    const ok = await run(() => api.matchLine(detail.id, target.id, productId), "Article rapproché.");
    if (ok) setProductTarget(null);
  };

  const pickProduct = async (line: InvoiceLine, productId: number) => {
    await run(() => api.matchLine(detail.id, line.id, productId), "Article rapproché.");
  };

  const createProduct = async (line: InvoiceLine, payload: Record<string, unknown>) => {
    const ok = await run(() => api.createLineProduct(detail.id, line.id, payload), "Nouvel article créé et rattaché.");
    if (ok) setNewProductTarget(null);
    return ok;
  };

  const addLine = async (payload: Record<string, unknown>) => {
    const ok = await run(() => api.addLine(detail.id, payload), "Ligne ajoutée.");
    if (ok) setAddOpen(false);
    return ok;
  };

  const calculatedSum = detail.lines.reduce((sum, line) => sum + (line.line_total_ht_calculated ?? 0), 0);

  return (
    <>
      <section className="panel lines-panel">
        <header className="panel-header">
          <div>
            <h2>Lignes de facture</h2>
            <p className="muted small">
              {detail.lines.length} ligne{detail.lines.length > 1 ? "s" : ""} · corrigez les quantités, prix, remises et
              rapprochez chaque article Tulip.
            </p>
          </div>
          <div className="panel-actions">
            <span className="muted small nowrap">
              Total lignes calculé : <strong className="mono">{formatMoney(calculatedSum, detail.currency)}</strong>
            </span>
            {!readOnly && (
              <button type="button" className="button button-sm" onClick={() => setAddOpen(true)}>
                <Icon name="plus" size={15} /> Ajouter une ligne
              </button>
            )}
          </div>
        </header>

        <div className="table-wrap lines-wrap">
          <table className="data-table lines-table">
            <thead>
              <tr>
                <th className="col-pos">#</th>
                <th className="col-ref">Réf.</th>
                <th className="col-designation">Désignation</th>
                <th className="col-lot">Lot</th>
                <th className="col-num">Colis</th>
                <th className="col-num">Qté</th>
                <th className="col-money">PU HT</th>
                <th className="col-money">Prix vente</th>
                <th className="col-num">Remise</th>
                <th className="col-num">TVA %</th>
                <th className="col-money">Total HT</th>
                <th className="col-product">Article Tulip</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {detail.lines.length === 0 ? (
                <tr>
                  <td colSpan={13}>
                    <div className="table-empty">
                      <p>Aucune ligne détectée.</p>
                      {!readOnly && (
                        <button type="button" className="button button-sm" onClick={() => setAddOpen(true)}>
                          Ajouter manuellement une ligne
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                detail.lines.map((line) => (
                  <LineRow
                    key={line.id}
                    line={line}
                    currency={detail.currency}
                    readOnly={readOnly}
                    selected={selectedLineId === line.id}
                    saving={savingId === line.id}
                    supplierId={detail.supplier?.id ?? null}
                    suggestions={suggestions[line.id] ?? line.match_candidates ?? []}
                    suggestionsLoading={suggestionsLoading && !(suggestions[line.id] ?? line.match_candidates ?? []).length}
                    onSelect={() => onSelectLine(line)}
                    onSave={(payload) => saveLine(line, payload)}
                    onDelete={() => setDeleteTarget(line)}
                    onMatch={() => setProductTarget(line)}
                    onPickProduct={(productId) => void pickProduct(line, productId)}
                    onNewProduct={() => setNewProductTarget(line)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <AddLineModal
        open={addOpen}
        currency={detail.currency}
        onClose={() => setAddOpen(false)}
        onSubmit={addLine}
      />

      <ProductMatchModal
        line={productTarget}
        supplierId={detail.supplier_id}
        onClose={() => setProductTarget(null)}
        onConfirm={confirmProduct}
      />

      <NewProductModal
        line={newProductTarget}
        onClose={() => setNewProductTarget(null)}
        onSubmit={createProduct}
      />

      <Modal
        open={deleteTarget !== null}
        title="Supprimer la ligne ?"
        subtitle={deleteTarget ? `Ligne ${deleteTarget.position} — ${deleteTarget.raw_designation}` : undefined}
        onClose={() => setDeleteTarget(null)}
        footer={
          <>
            <button type="button" className="button" onClick={() => setDeleteTarget(null)}>
              Annuler
            </button>
            <button type="button" className="button button-danger" onClick={removeLine}>
              <Icon name="trash" size={16} /> Supprimer
            </button>
          </>
        }
      >
        <p className="muted">
          La suppression est enregistrée dans l'historique. Les totaux et contrôles seront recalculés immédiatement.
        </p>
      </Modal>
    </>
  );
}

function AddLineModal({
  open,
  currency,
  onClose,
  onSubmit,
}: {
  open: boolean;
  currency: string;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState<AddDraft>(emptyAdd);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setDraft(emptyAdd);
      setError(null);
    }
  }, [open]);

  const set = (key: keyof AddDraft, value: string) => setDraft((current) => ({ ...current, [key]: value }));

  const submit = async () => {
    if (!draft.raw_designation.trim()) {
      setError("La désignation est obligatoire.");
      return;
    }
    for (const key of ["packages", "quantity", "unit_price_ht", "vat_rate", "line_total_ht_extracted"] as const) {
      if (draft[key].trim() !== "" && parseAmount(draft[key]) === null) {
        setError("Une valeur numérique est invalide.");
        return;
      }
    }
    const payload: Record<string, unknown> = {
      raw_designation: draft.raw_designation.trim(),
      raw_reference: draft.raw_reference.trim() || null,
      lot_number: draft.lot_number.trim() || null,
      packages: numberOrNull(draft.packages),
      quantity: numberOrNull(draft.quantity),
      unit_price_ht: numberOrNull(draft.unit_price_ht),
      vat_rate: numberOrNull(draft.vat_rate),
      line_total_ht_extracted: numberOrNull(draft.line_total_ht_extracted),
    };
    setSaving(true);
    setError(null);
    const ok = await onSubmit(payload);
    setSaving(false);
    if (ok) {
      // Réinitialiser le formulaire après succès
      setDraft(emptyAdd);
      setError(null);
    } else {
      setError("L'ajout a échoué. Veuillez réessayer.");
    }
  };

  return (
    <Modal
      open={open}
      title="Ajouter une ligne"
      subtitle="Saisie manuelle. L'article pourra être rapproché juste après."
      onClose={onClose}
      wide
      footer={
        <>
          <button type="button" className="button" onClick={onClose}>
            Annuler
          </button>
          <button type="button" className="button button-primary" onClick={submit} disabled={saving}>
            {saving ? <span className="spinner small light" /> : <Icon name="plus" size={16} />} Ajouter
          </button>
        </>
      }
    >
      <div className="form-grid">
        <label className="field">
          <span>Référence</span>
          <input value={draft.raw_reference} onChange={(event) => set("raw_reference", event.target.value)} />
        </label>
        <label className="field">
          <span>Désignation *</span>
          <input value={draft.raw_designation} onChange={(event) => set("raw_designation", event.target.value)} />
        </label>
        <label className="field">
          <span>Lot</span>
          <input value={draft.lot_number} onChange={(event) => set("lot_number", event.target.value)} />
        </label>
        <label className="field">
          <span>Colis</span>
          <input inputMode="decimal" value={draft.packages} onChange={(event) => set("packages", event.target.value)} />
        </label>
        <label className="field">
          <span>Quantité</span>
          <input inputMode="decimal" value={draft.quantity} onChange={(event) => set("quantity", event.target.value)} />
        </label>
        <label className="field">
          <span>Prix unitaire HT ({currency})</span>
          <input inputMode="decimal" value={draft.unit_price_ht} onChange={(event) => set("unit_price_ht", event.target.value)} />
        </label>
        <label className="field">
          <span>Taux TVA (%)</span>
          <input inputMode="decimal" value={draft.vat_rate} onChange={(event) => set("vat_rate", event.target.value)} />
        </label>
        <label className="field">
          <span>Total HT extrait</span>
          <input
            inputMode="decimal"
            value={draft.line_total_ht_extracted}
            onChange={(event) => set("line_total_ht_extracted", event.target.value)}
          />
        </label>
      </div>
      {error && <p className="inline-error">{error}</p>}
    </Modal>
  );
}

function ProductMatchModal({
  line,
  supplierId,
  onClose,
  onConfirm,
}: {
  line: InvoiceLine | null;
  supplierId: number | null;
  onClose: () => void;
  onConfirm: (productId: number) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<ProductCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  useEffect(() => {
    if (!line) return;
    setQuery(line.raw_designation);
    setCandidates(line.match_candidates ?? []);
    setError(null);
    const initial = async () => {
      if ((line.match_candidates ?? []).length > 0) return;
      setLoading(true);
      try {
        const result = await api.suggestProducts(line.raw_designation, supplierId, line.raw_reference);
        setCandidates(result.items);
      } catch {
        setCandidates([]);
      } finally {
        setLoading(false);
      }
    };
    void initial();
  }, [line, supplierId]);

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const result = await api.suggestProducts(query.trim(), supplierId, line?.raw_reference);
      setCandidates(result.items);
      if (result.items.length === 0) setError("Aucun article ne correspond. Vérifiez le référentiel articles.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Recherche impossible.");
    } finally {
      setSearching(false);
    }
  };

  const scanBarcode = async (barcode: string) => {
    setScanning(true);
    setScanError(null);
    try {
      const product = await api.getProductByBarcode(barcode);
      const candidate: ProductCandidate = {
        product_id: product.id,
        tulip_code: product.tulip_code,
        designation: product.designation,
        reference: product.reference,
        supplier_ref: product.supplier_ref,
        barcode: product.barcode,
        packaging: product.packaging,
        stock_unit: product.stock_unit,
        default_vat_rate: product.default_vat_rate !== null ? String(product.default_vat_rate) : null,
        score: 1,
        method: "code-barres scanné",
      };
      setCandidates((current) => [
        candidate,
        ...current.filter((item) => item.product_id !== product.id),
      ]);
    } catch (err) {
      // Repli : le produit existe peut-être sous un autre identifiant (code Tulip ou réf. fournisseur).
      try {
        const result = await api.suggestProducts(barcode);
        if (result.items.length > 0) {
          setCandidates((current) => [
            ...result.items.filter((item) => !current.some((c) => c.product_id === item.product_id)),
            ...current,
          ]);
          return;
        }
      } catch {
        setScanError(`Aucun article avec le code-barres ${barcode}.`);
        return;
      }
      setScanError(
        err instanceof ApiError && err.status === 404
          ? `Aucun article avec le code-barres ${barcode}.`
          : err instanceof Error
            ? err.message
            : "Recherche impossible.",
      );
    } finally {
      setScanning(false);
    }
  };

  const confirm = async (productId: number) => {
    setConfirming(productId);
    try {
      await onConfirm(productId);
    } finally {
      setConfirming(null);
    }
  };

  return (
    <Modal
      open={line !== null}
      title="Rapprocher un article Tulip"
      subtitle={line ? `Ligne ${line.position} — ${line.raw_designation}` : undefined}
      onClose={onClose}
      wide
      footer={
        <button type="button" className="button" onClick={onClose}>
          Fermer
        </button>
      }
    >
      <div className="search-row">
        <div className="search-input">
          <Icon name="search" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void search();
              }
            }}
            placeholder="Référence, code-barres, code Tulip ou désignation"
          />
        </div>
        <button type="button" className="button" onClick={search} disabled={searching}>
          {searching ? <span className="spinner small" /> : <Icon name="search" size={16} />} Rechercher
        </button>
      </div>

      <BarcodeScanInput onScan={scanBarcode} busy={scanning} placeholder="Scanner l'article avec la douchette…" />
      {scanError && <p className="inline-error">{scanError}</p>}

      {line?.raw_reference && (
        <p className="muted small">
          Référence fournisseur : <span className="mono">{line.raw_reference}</span>
        </p>
      )}

      {loading ? (
        <p className="muted small">Recherche de suggestions…</p>
      ) : candidates.length === 0 ? (
        <p className="muted small">Aucun candidat. Lancez une recherche ou complétez le référentiel articles.</p>
      ) : (
        <ul className="candidate-list">
          {candidates.map((candidate) => (
            <li key={candidate.product_id} className="candidate-row">
              <div className="candidate-main">
                <span className="product-code mono">{candidate.tulip_code}</span>
                <strong>{candidate.designation}</strong>
                <span className="muted small">
                  {[
                    candidate.reference ? `réf. art. ${candidate.reference}` : null,
                    candidate.supplier_ref ? `réf. four. ${candidate.supplier_ref}` : null,
                    candidate.barcode ? `code-barres ${candidate.barcode}` : null,
                    candidate.packaging,
                    candidate.stock_unit,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
              <div className="candidate-side">
                <span className="score-pill">{Math.round(candidate.score * 100)} %</span>
                <span className="muted tiny">{candidate.method}</span>
                <button
                  type="button"
                  className="button button-sm button-primary"
                  disabled={confirming !== null}
                  onClick={() => confirm(candidate.product_id)}
                >
                  {confirming === candidate.product_id ? <span className="spinner small light" /> : <Icon name="link" size={14} />}
                  Associer
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="inline-error">{error}</p>}
      <p className="muted tiny">
        L'association confirme le rapprochement pour cette ligne et mémorise la référence fournisseur pour les prochains
        imports.
      </p>
      {line?.tulip_product && (
        <p className="small">
          Article actuellement associé : <strong>{line.tulip_product.tulip_code}</strong> — {line.tulip_product.designation}
        </p>
      )}
    </Modal>
  );
}

function NewProductModal({
  line,
  onClose,
  onSubmit,
}: {
  line: InvoiceLine | null;
  onClose: () => void;
  onSubmit: (line: InvoiceLine, payload: Record<string, unknown>) => Promise<boolean>;
}) {
  const [designation, setDesignation] = useState("");
  const [tulipCode, setTulipCode] = useState("");
  const [reference, setReference] = useState("");
  const [supplierRef, setSupplierRef] = useState("");
  const [barcode, setBarcode] = useState("");
  const [supplierId, setSupplierId] = useState<number | null>(null);
  const [packaging, setPackaging] = useState("");
  const [stockUnit, setStockUnit] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!line) return;
    setDesignation(line.raw_designation ?? "");
    setTulipCode("");
    setReference(line.raw_reference ?? "");
    setSupplierRef("");
    setBarcode("");
    setSupplierId(null);
    setPackaging(line.packages !== null ? String(line.packages) : "");
    setStockUnit("");
    setError(null);
  }, [line]);

  const submit = async () => {
    if (!line) return;
    if (!designation.trim()) {
      setError("La désignation est obligatoire.");
      return;
    }
    setSaving(true);
    const ok = await onSubmit(line, {
      designation: designation.trim(),
      tulip_code: tulipCode.trim() || null,
      reference: reference.trim() || null,
      supplier_ref: supplierRef.trim() || null,
      barcode: barcode.trim() || null,
      packaging: packaging.trim() || null,
      stock_unit: stockUnit.trim() || null,
    });
    setSaving(false);
    if (!ok) setError("Création impossible. Vérifiez le code article (déjà utilisé ?).");
  };

  return (
    <Modal
      open={line !== null}
      title="Nouvel article"
      subtitle={line ? `Créé depuis la ligne ${line.position} — ${line.raw_designation}` : undefined}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="button" onClick={onClose}>
            Annuler
          </button>
          <button type="button" className="button button-primary" onClick={submit} disabled={saving}>
            {saving ? <span className="spinner small light" /> : <Icon name="plus" size={16} />} Créer et rattacher
          </button>
        </>
      }
    >
      <div className="form-stack">
        <label className="field">
          <span>Désignation *</span>
          <input value={designation} onChange={(event) => setDesignation(event.target.value)} />
        </label>

        <label className="field">
          <span>Fournisseur référent (optionnel)</span>
          <SupplierDropdown
            value={supplierId}
            onChange={(id) => setSupplierId(id)}
            disabled={saving}
          />
          <span className="muted tiny" style={{ display: "block", marginTop: "0.25rem" }}>
            Sélectionnez le fournisseur principal pour cet article (facilite le rapprochement automatique)
          </span>
        </label>

        <div className="form-grid">
          <label className="field">
            <span>Code Tulip (laisser vide = généré)</span>
            <input value={tulipCode} onChange={(event) => setTulipCode(event.target.value)} placeholder="ex. 10698" />
          </label>
          <label className="field">
            <span>Réf. article (Tulip)</span>
            <input
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              className="mono"
              placeholder="REF Tulip, préremplie avec la référence lue sur la facture"
            />
          </label>
          <label className="field">
            <span>Référence fournisseur</span>
            <input value={supplierRef} onChange={(event) => setSupplierRef(event.target.value)} placeholder="Référence du fournisseur" />
          </label>
          <label className="field">
            <span>Code-barres</span>
            <input value={barcode} onChange={(event) => setBarcode(event.target.value)} className="mono" placeholder="CODEBARRE" />
          </label>
          <label className="field">
            <span>Conditionnement</span>
            <input value={packaging} onChange={(event) => setPackaging(event.target.value)} placeholder="ex. 4X1" />
          </label>
          <label className="field">
            <span>Unité de stock</span>
            <input value={stockUnit} onChange={(event) => setStockUnit(event.target.value)} placeholder="ex. pièce, kg" />
          </label>
        </div>
      </div>
      {error && <p className="inline-error">{error}</p>}
      <p className="muted tiny">
        L'article est ajouté au référentiel local des articles Tulip, rattaché à cette ligne et mémorisé pour ce
        fournisseur.
      </p>
    </Modal>
  );
}
