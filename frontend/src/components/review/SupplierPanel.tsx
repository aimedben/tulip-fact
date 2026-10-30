import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import type { InvoiceDetail, Supplier, SupplierCandidate } from "../../types";
import { Icon } from "../Icon";
import { Modal } from "../Modal";
import { useToast } from "../Toast";

export function SupplierPanel({
  detail,
  readOnly,
  onUpdated,
}: {
  detail: InvoiceDetail;
  readOnly: boolean;
  onUpdated: (detail: InvoiceDetail) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(detail.supplier_name_raw ?? detail.supplier?.name ?? "");
  const [candidates, setCandidates] = useState<SupplierCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dropdown, setDropdown] = useState<Supplier[]>([]);
  const [selection, setSelection] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [creating, setCreating] = useState(false);
  const { show } = useToast();

  const inlineCandidates = (detail.supplier_match?.candidates ?? []).slice(0, 4);

  useEffect(() => {
    if (!open) return;
    const initial = query.trim() || detail.supplier_name_raw || "";
    if (!initial) return;
    setLoading(true);
    setError(null);
    api
      .lookupSupplier(initial)
      .then((result) => setCandidates(result.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Recherche impossible."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const loadDropdown = () => {
    api
      .suppliers({ page_size: 500 })
      .then((result) => setDropdown(result.items))
      .catch(() => setDropdown([]));
  };

  useEffect(() => {
    if (!open) {
      setSelection("");
      setShowCreate(false);
      return;
    }
    loadDropdown();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.lookupSupplier(query.trim());
      setCandidates(result.items);
      if (result.items.length === 0) setError("Aucun fournisseur trouvé. Vérifiez le référentiel ou créez une fiche.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Recherche impossible.");
    } finally {
      setLoading(false);
    }
  };

  const confirm = async (supplierId: number) => {
    setConfirming(supplierId);
    try {
      const updated = await api.confirmSupplier(detail.id, supplierId);
      onUpdated(updated);
      setOpen(false);
      show("Fournisseur confirmé. Les lignes et contrôles ont été mis à jour.", "success");
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Confirmation impossible.";
      show(message, "error");
    } finally {
      setConfirming(null);
    }
  };

  const onPick = (value: string) => {
    setSelection(value);
    if (value === "NEW") {
      setShowCreate(true);
      setNewName((previous) => previous || query || detail.supplier_name_raw || "");
      setNewCode(`F${Date.now().toString().slice(-8)}`);
      return;
    }
    if (value !== "") {
      setShowCreate(false);
      void confirm(Number(value));
    }
  };

  const createAndConfirm = async () => {
    if (!newName.trim() || !newCode.trim()) {
      show("Code et nom du fournisseur obligatoires.", "error");
      return;
    }
    setCreating(true);
    try {
      const created = await api.createSupplier({
        code: newCode.trim(),
        name: newName.trim(),
        phone: newPhone.trim() || undefined,
      });
      const updated = await api.confirmSupplier(detail.id, created.id);
      onUpdated(updated);
      setOpen(false);
      show(`Fournisseur ${created.name} créé puis confirmé sur cette facture.`, "success");
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Création impossible.";
      show(message, "error");
    } finally {
      setCreating(false);
    }
  };

  const SupplierSelect = (
    <label className="field supplier-select-field">
      <span>Fournisseur (liste Tulip / référentiel)</span>
      <select value={selection} onChange={(event) => onPick(event.target.value)} disabled={readOnly || confirming !== null}>
        <option value="">➕ Ajouter un fournisseur…</option>
        {dropdown.map((supplier) => (
          <option key={supplier.id} value={supplier.id}>
            {supplier.name} — {supplier.code}
          </option>
        ))}
      </select>
    </label>
  );

  const CreateForm = (
    <div className="supplier-create-box">
      <h3>➕ Nouveau fournisseur</h3>
      <label className="field create-field">
        <span>Code *</span>
        <input type="text" value={newCode} onChange={(e) => setNewCode(e.target.value)} className="mono" />
      </label>
      <label className="field create-field">
        <span>Nom / raison sociale *</span>
        <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} />
      </label>
      <label className="field create-field">
        <span>Téléphone</span>
        <input type="text" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} />
      </label>
      <div className="supplier-actions">
        <button type="button" className="button button-sm button-primary" onClick={createAndConfirm} disabled={creating}>
          {creating && <span className="spinner small" />} Créer et confirmer
        </button>
        <button type="button" className="text-link small" onClick={() => setShowCreate(false)}>
          Annuler
        </button>
      </div>
    </div>
  );

  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h2>Fournisseur</h2>
          <p className="muted small">Rapprochement avec le référentiel Tulip</p>
        </div>
        {!readOnly && detail.supplier && (
          <button type="button" className="button button-sm" onClick={() => setOpen(true)}>
            Changer
          </button>
        )}
      </header>
      <div className="panel-body">
        {detail.supplier ? (
          <div className="supplier-card confirmed">
            <span className="supplier-icon">
              <Icon name="suppliers" size={20} />
            </span>
            <div>
              <strong>{detail.supplier.name}</strong>
              <div className="muted small">
                Code Tulip <span className="mono">{detail.supplier.code}</span>
                {detail.supplier.tax_id ? ` · NIF ${detail.supplier.tax_id}` : ""}
              </div>
              {detail.supplier_name_raw && detail.supplier_name_raw !== detail.supplier.name && (
                <div className="muted tiny">Mention sur le document : {detail.supplier_name_raw}</div>
              )}
            </div>
            <span className="status-badge tone-success">
              <Icon name="check" size={13} /> Confirmé
            </span>
          </div>
        ) : (
          <>
            <div className="supplier-card unconfirmed">
              <span className="supplier-icon">
                <Icon name="alert" size={20} />
              </span>
              <div>
                <strong>Aucun fournisseur confirmé</strong>
                <div className="muted small">
                  {detail.supplier_name_raw ? `Mention lue : « ${detail.supplier_name_raw} »` : "Aucun nom détecté sur le document."}
                </div>
              </div>
            </div>

            {inlineCandidates.length > 0 && (
              <div className="candidate-inline-list">
                <span className="label">Suggestions</span>
                {inlineCandidates.map((candidate) => (
                  <div className="candidate-inline" key={candidate.supplier_id}>
                    <div>
                      <strong>{candidate.name}</strong>
                      <span className="muted small mono"> {candidate.code}</span>
                      <div className="muted tiny">
                        {Math.round(candidate.score * 100)} % · {candidate.method}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="button button-sm"
                      disabled={readOnly || confirming !== null}
                      onClick={() => confirm(candidate.supplier_id)}
                    >
                      {confirming === candidate.supplier_id ? <span className="spinner small" /> : "Confirmer"}
                    </button>
                  </div>
                ))}
              </div>
            )}

            {!readOnly && (
              <div className="supplier-actions-stack">
                {SupplierSelect}
                {showCreate && CreateForm}
                <div className="supplier-actions">
                  <button type="button" className="button button-sm" onClick={() => setOpen(true)}>
                    <Icon name="search" size={15} /> Rechercher un fournisseur
                  </button>
                  <Link to="/suppliers" className="text-link small">
                    Gérer le référentiel
                  </Link>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <Modal
        open={open}
        title="Choisir le fournisseur"
        subtitle="La confirmation mémorise le nom du document comme alias pour les prochains imports."
        onClose={() => setOpen(false)}
        wide
        footer={
          <button type="button" className="button" onClick={() => setOpen(false)}>
            Fermer
          </button>
        }
      >
        <div className="supplier-actions-stack">{SupplierSelect}</div>
        {showCreate && CreateForm}

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
              placeholder="Nom, code ou alias fournisseur"
            />
          </div>
          <button type="button" className="button" onClick={search} disabled={loading}>
            {loading ? <span className="spinner small" /> : <Icon name="search" size={16} />} Rechercher
          </button>
        </div>

        {loading ? (
          <p className="muted small">Recherche en cours…</p>
        ) : candidates.length === 0 ? (
          <p className="muted small">Aucun candidat.</p>
        ) : (
          <ul className="candidate-list">
            {candidates.map((candidate) => (
              <li key={candidate.supplier_id} className="candidate-row">
                <div className="candidate-main">
                  <span className="product-code mono">{candidate.code}</span>
                  <strong>{candidate.name}</strong>
                  <span className="muted small">
                    {Math.round(candidate.score * 100)} % · {candidate.method}
                  </span>
                </div>
                <div className="candidate-side">
                  <button
                    type="button"
                    className="button button-sm button-primary"
                    disabled={confirming !== null}
                    onClick={() => confirm(candidate.supplier_id)}
                  >
                    {confirming === candidate.supplier_id ? <span className="spinner small light" /> : null}
                    Confirmer
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {error && <p className="inline-error">{error}</p>}
        <p className="muted tiny">
          Fournisseur absent ? Choisis « ➕ Ajouter un fournisseur… » ci-dessus, ou <Link to="/suppliers">créez la fiche dans le référentiel</Link>.
        </p>
      </Modal>
    </section>
  );
}
