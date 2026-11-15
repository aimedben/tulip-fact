import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { InvoiceDetail, Supplier, SupplierCandidate } from "../types";
import { Icon } from "./Icon";
import { useToast } from "./Toast";

interface SupplierInputWithSuggestionsProps {
  value: string;
  onChange: (value: string) => void;
  onSupplierConfirmed?: (supplierId: number, supplierName: string, updated?: InvoiceDetail) => void;
  disabled?: boolean;
  invoiceId?: number;
}

export function SupplierInputWithSuggestions({
  value,
  onChange,
  onSupplierConfirmed,
  disabled,
  invoiceId,
}: SupplierInputWithSuggestionsProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<SupplierCandidate[]>([]);
  const [allSuppliers, setAllSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createData, setCreateData] = useState({ code: "", name: "", phone: "", tax_id: "" });
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { show } = useToast();

  // Charger tous les fournisseurs pour l'auto-complétion
  useEffect(() => {
    api
      .suppliers({ page_size: 500 })
      .then((result) => setAllSuppliers(result.items))
      .catch(() => setAllSuppliers([]));
  }, []);

  // Charger les suggestions quand la valeur change
  useEffect(() => {
    if (value.trim().length >= 2) {
      loadSuggestions(value.trim());
    } else {
      setSuggestions([]);
    }
  }, [value]);

  // Fermer le dropdown en cliquant ailleurs
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setShowCreateForm(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const loadSuggestions = async (query: string) => {
    setLoading(true);
    try {
      const result = await api.lookupSupplier(query);
      setSuggestions(result.items);
    } catch (err) {
      console.error("Erreur chargement suggestions:", err);
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  };

  const confirmSupplier = async (supplierId: number, supplierName: string) => {
    if (!invoiceId) {
      onChange(supplierName);
      setIsOpen(false);
      return;
    }

    setConfirming(true);
    try {
      const updated = await api.confirmSupplier(invoiceId, supplierId);
      // Le texte OCR d'origine (supplier_name_raw) est préservé : la valeur
      // affichée vient du rafraîchissement serveur, pas du nom catalogue.
      setIsOpen(false);
      setShowCreateForm(false);
      show(`Fournisseur "${supplierName}" confirmé.`, "success");
      if (onSupplierConfirmed) {
        onSupplierConfirmed(supplierId, supplierName, updated);
      }
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Confirmation impossible.";
      show(message, "error");
    } finally {
      setConfirming(false);
    }
  };

  const handleCreateNew = () => {
    setShowCreateForm(true);
    setCreateData({
      code: `F${Date.now().toString().slice(-8)}`,
      name: value || "",
      phone: "",
      tax_id: "",
    });
  };

  const submitCreate = async () => {
    if (!createData.code.trim() || !createData.name.trim()) {
      show("Le code et le nom sont obligatoires.", "error");
      return;
    }
    setConfirming(true);
    try {
      const created = await api.createSupplier({
        code: createData.code.trim(),
        name: createData.name.trim(),
        phone: createData.phone.trim() || null,
        tax_id: createData.tax_id.trim() || null,
      });

      if (invoiceId) {
        await confirmSupplier(created.id, created.name);
      } else {
        onChange(created.name);
        setIsOpen(false);
        setShowCreateForm(false);
      }

      show(`Fournisseur "${created.name}" créé${invoiceId ? " et confirmé" : ""}.`, "success");
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Création impossible.";
      show(message, "error");
      setConfirming(false);
    }
  };

  // Filtrer les fournisseurs localement
  const filteredSuppliers = allSuppliers
    .filter((s) => s.name.toLowerCase().includes(value.toLowerCase()) || s.code.toLowerCase().includes(value.toLowerCase()))
    .slice(0, 5);

  const hasResults = suggestions.length > 0 || filteredSuppliers.length > 0;

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setIsOpen(true);
          setShowCreateForm(false);
        }}
        onFocus={() => {
          if (value.trim()) {
            setIsOpen(true);
          }
        }}
        disabled={disabled}
        placeholder="Nom du fournisseur (tapez pour rechercher)"
      />

      {isOpen && !disabled && value.trim().length >= 2 && (
        <div ref={dropdownRef} className="supplier-suggestions-dropdown">
          {showCreateForm ? (
            <div className="supplier-create-form">
              <div className="create-header">
                <h4>➕ Nouveau fournisseur</h4>
                <button type="button" className="text-link small" onClick={() => setShowCreateForm(false)}>
                  <Icon name="x" size={14} /> Annuler
                </button>
              </div>
              <div className="form-stack">
                <label className="field">
                  <span>Code *</span>
                  <input
                    value={createData.code}
                    onChange={(e) => setCreateData({ ...createData, code: e.target.value })}
                    className="mono"
                  />
                </label>
                <label className="field">
                  <span>Nom / Raison sociale *</span>
                  <input
                    value={createData.name}
                    onChange={(e) => setCreateData({ ...createData, name: e.target.value })}
                  />
                </label>
                <label className="field">
                  <span>NIF</span>
                  <input
                    value={createData.tax_id}
                    onChange={(e) => setCreateData({ ...createData, tax_id: e.target.value })}
                  />
                </label>
                <label className="field">
                  <span>Téléphone</span>
                  <input
                    value={createData.phone}
                    onChange={(e) => setCreateData({ ...createData, phone: e.target.value })}
                  />
                </label>
                <button
                  type="button"
                  className="button button-primary button-small"
                  onClick={submitCreate}
                  disabled={confirming}
                  style={{ width: "100%" }}
                >
                  {confirming ? <span className="spinner small light" /> : <Icon name="check" size={16} />}
                  Créer{invoiceId ? " et confirmer" : ""}
                </button>
              </div>
            </div>
          ) : (
            <>
              {suggestions.length > 0 && (
                <div className="dropdown-section">
                  <div className="dropdown-section-header">
                    <Icon name="sparkles" size={14} />
                    <span>Suggestions (basées sur le document)</span>
                  </div>
                  {suggestions.map((candidate) => (
                    <button
                      key={candidate.supplier_id}
                      type="button"
                      className="dropdown-item"
                      onClick={() => confirmSupplier(candidate.supplier_id, candidate.name)}
                      disabled={confirming}
                    >
                      <div className="dropdown-item-main">
                        <strong>{candidate.name}</strong>
                        <div className="muted tiny">
                          Code: {candidate.code} • {Math.round(candidate.score * 100)}%
                        </div>
                      </div>
                      <Icon name="arrow-right" size={16} />
                    </button>
                  ))}
                </div>
              )}

              {filteredSuppliers.length > 0 && (
                <div className="dropdown-section">
                  <div className="dropdown-section-header">
                    <Icon name="list" size={14} />
                    <span>Autres fournisseurs</span>
                  </div>
                  {filteredSuppliers.map((supplier) => (
                    <button
                      key={supplier.id}
                      type="button"
                      className="dropdown-item"
                      onClick={() => confirmSupplier(supplier.id, supplier.name)}
                      disabled={confirming}
                    >
                      <div className="dropdown-item-main">
                        <strong>{supplier.name}</strong>
                        <div className="muted tiny">Code: {supplier.code}</div>
                      </div>
                      <Icon name="arrow-right" size={16} />
                    </button>
                  ))}
                </div>
              )}

              <div className="dropdown-section">
                <button type="button" className="dropdown-item dropdown-item-create" onClick={handleCreateNew}>
                  <Icon name="plus-circle" size={18} />
                  <span>
                    <strong>Créer un nouveau fournisseur</strong>
                    <div className="muted tiny">Avec le nom : "{value}"</div>
                  </span>
                </button>
              </div>

              {!hasResults && !loading && (
                <div className="dropdown-empty">
                  <p>Aucun fournisseur trouvé pour "{value}"</p>
                  <button type="button" className="button button-small" onClick={handleCreateNew}>
                    <Icon name="plus" size={14} /> Créer ce fournisseur
                  </button>
                </div>
              )}

              {loading && (
                <div className="dropdown-loading">
                  <span className="spinner small" />
                  <span>Recherche...</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      <style>{`
        .supplier-suggestions-dropdown {
          position: absolute;
          top: calc(100% + 4px);
          left: 0;
          right: 0;
          background: white;
          border: 1px solid var(--color-border);
          border-radius: 6px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
          max-height: 350px;
          overflow-y: auto;
          z-index: 1000;
        }

        .dropdown-section {
          border-bottom: 1px solid var(--color-border-light);
        }

        .dropdown-section:last-child {
          border-bottom: none;
        }

        .dropdown-section-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem 0.75rem;
          background: var(--color-bg-subtle);
          font-size: 0.8125rem;
          font-weight: 500;
          color: var(--color-text-muted);
        }

        .dropdown-item {
          width: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.75rem;
          padding: 0.625rem 0.75rem;
          border: none;
          background: white;
          text-align: left;
          cursor: pointer;
          transition: background 0.15s;
        }

        .dropdown-item:hover {
          background: var(--color-bg-hover);
        }

        .dropdown-item:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .dropdown-item-main {
          flex: 1;
        }

        .dropdown-item-create {
          gap: 0.75rem;
          background: var(--color-primary-bg);
          color: var(--color-primary);
        }

        .dropdown-item-create:hover {
          background: var(--color-primary-bg-hover);
        }

        .dropdown-empty {
          padding: 1.5rem 0.75rem;
          text-align: center;
          color: var(--color-text-muted);
        }

        .dropdown-empty p {
          margin: 0 0 0.75rem;
          font-size: 0.875rem;
        }

        .dropdown-loading {
          padding: 1rem;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          color: var(--color-text-muted);
          font-size: 0.875rem;
        }

        .supplier-create-form {
          padding: 0.75rem;
        }

        .create-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 0.75rem;
        }

        .create-header h4 {
          margin: 0;
          font-size: 0.9375rem;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
