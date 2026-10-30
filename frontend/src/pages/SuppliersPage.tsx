import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Paged, Supplier } from "../types";
import { EmptyState, PageHeader, Pagination, Panel, Spinner } from "../components/Common";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { CatalogImport } from "../components/CatalogImport";
import { useToast } from "../components/Toast";

interface SupplierForm {
  code: string;
  name: string;
  name_variants: string;
  tax_id: string;
  phone: string;
  email: string;
  address: string;
  notes: string;
  active: boolean;
}

const emptyForm: SupplierForm = {
  code: "",
  name: "",
  name_variants: "",
  tax_id: "",
  phone: "",
  email: "",
  address: "",
  notes: "",
  active: true,
};

export function SuppliersPage() {
  const [data, setData] = useState<Paged<Supplier> | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [page, setPage] = useState(1);
  const [reloadToken, setReloadToken] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const { show: toast } = useToast();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .suppliers({ q: appliedQuery, page, page_size: 50 })
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Impossible de charger les fournisseurs.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [appliedQuery, page, reloadToken]);

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (supplier: Supplier) => {
    setEditing(supplier);
    setFormOpen(true);
  };

  const refresh = () => setReloadToken((value) => value + 1);

  const syncFromTulip = async () => {
    setSyncing(true);
    try {
      const result = await api.tulipSyncSuppliers();
      toast(`${result.created} créé${result.created > 1 ? "s" : ""}, ${result.updated} mis à jour — ${result.local_total} en base locale.`);
      refresh();
    } catch (err) {
      toast(err instanceof Error ? `Récupération impossible : ${err.message}` : "Récupération impossible.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Référentiel fournisseurs"
        subtitle="Les codes et noms de ce référentiel servent au rapprochement des factures et à la préparation des bons d'entrée."
        actions={
          <>
            <button type="button" className="button" disabled={syncing} onClick={syncFromTulip}>
              {syncing ? <Spinner label="Récupération…" /> : <Icon name="download" size={16} />} Récupérer depuis Tulip
            </button>
            <button type="button" className="button" onClick={() => setShowImport((value) => !value)}>
              <Icon name="upload" size={16} /> Import CSV / XLSX
            </button>
            <button type="button" className="button button-primary" onClick={openCreate}>
              <Icon name="plus" size={16} /> Nouveau fournisseur
            </button>
          </>
        }
      />

      {showImport && (
        <Panel title="Importer le référentiel" subtitle="Import par fichier, avec rapport des lignes rejetées.">
          <CatalogImport kind="suppliers" onImported={refresh} />
        </Panel>
      )}

      <Panel
        title="Fournisseurs"
        subtitle={data ? `${data.total} fiche${data.total > 1 ? "s" : ""}` : "Chargement…"}
        actions={loading ? <Spinner /> : undefined}
        flush
      >
        <div className="table-toolbar">
          <form
            className="search-row compact"
            onSubmit={(event) => {
              event.preventDefault();
              setPage(1);
              setAppliedQuery(query.trim());
            }}
          >
            <div className="search-input">
              <Icon name="search" size={16} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Rechercher un code, un nom ou un alias"
              />
            </div>
            <button type="submit" className="button button-sm">
              Rechercher
            </button>
            {(appliedQuery || query) && (
              <button
                type="button"
                className="button button-sm"
                onClick={() => {
                  setQuery("");
                  setAppliedQuery("");
                  setPage(1);
                }}
              >
                Effacer
              </button>
            )}
          </form>
        </div>

        {error && <p className="inline-error panel-padded">{error}</p>}

        {data && data.items.length === 0 ? (
          <EmptyState
            icon="suppliers"
            title={appliedQuery ? "Aucun fournisseur trouvé" : "Référentiel vide"}
            description={
              appliedQuery
                ? "Essayez un autre terme ou importez le référentiel depuis un fichier."
                : "Créez une fiche ou importez votre liste de fournisseurs pour commencer le rapprochement."
            }
            action={
              <button type="button" className="button button-primary" onClick={openCreate}>
                <Icon name="plus" size={16} /> Nouveau fournisseur
              </button>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Fournisseur</th>
                  <th>Alias</th>
                  <th>Contact</th>
                  <th>NIF</th>
                  <th>État</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {(data?.items ?? []).map((supplier) => (
                  <tr key={supplier.id}>
                    <td className="mono">{supplier.code}</td>
                    <td>
                      <strong>{supplier.name}</strong>
                      {supplier.address && <div className="muted small">{supplier.address}</div>}
                    </td>
                    <td>
                      {supplier.name_variants.length === 0 ? (
                        <span className="muted small">—</span>
                      ) : (
                        <div className="alias-list">
                          {supplier.name_variants.slice(0, 3).map((variant) => (
                            <span className="chip" key={variant}>
                              {variant}
                            </span>
                          ))}
                          {supplier.name_variants.length > 3 && (
                            <span className="muted small">+{supplier.name_variants.length - 3}</span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="small">
                      {supplier.phone && <div>{supplier.phone}</div>}
                      {supplier.email && <div className="muted">{supplier.email}</div>}
                      {!supplier.phone && !supplier.email && <span className="muted">—</span>}
                    </td>
                    <td className="mono small">{supplier.tax_id ?? "—"}</td>
                    <td>
                      <span className={`status-badge tone-${supplier.active ? "success" : "neutral"}`}>
                        {supplier.active ? "Actif" : "Inactif"}
                      </span>
                    </td>
                    <td className="align-right">
                      <button type="button" className="button button-sm" onClick={() => openEdit(supplier)}>
                        Modifier
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.items.length > 0 && (
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
        )}
      </Panel>

      <SupplierFormModal
        open={formOpen}
        supplier={editing}
        onClose={() => setFormOpen(false)}
        onSaved={(savedName) => {
          setFormOpen(false);
          if (savedName) {
            setQuery(savedName);
            setAppliedQuery(savedName);
            setPage(1);
          }
          refresh();
        }}
      />
    </>
  );
}

function SupplierFormModal({
  open,
  supplier,
  onClose,
  onSaved,
}: {
  open: boolean;
  supplier: Supplier | null;
  onClose: () => void;
  onSaved: (savedName?: string) => void;
}) {
  const [form, setForm] = useState<SupplierForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [pushing, setPushing] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    if (!open) return;
    setPushing(false);
    setError(null);
    if (supplier) {
      setForm({
        code: supplier.code,
        name: supplier.name,
        name_variants: supplier.name_variants.join(" | "),
        tax_id: supplier.tax_id ?? "",
        phone: supplier.phone ?? "",
        email: supplier.email ?? "",
        address: supplier.address ?? "",
        notes: supplier.notes ?? "",
        active: supplier.active,
      });
    } else {
      setForm(emptyForm);
    }
  }, [open, supplier]);

  const set = (key: keyof SupplierForm, value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = async () => {
    if (!form.code.trim() || !form.name.trim()) {
      setError("Le code et le nom sont obligatoires.");
      return;
    }
    setSaving(true);
    setError(null);
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      name_variants: form.name_variants
        .split("|")
        .map((entry) => entry.trim())
        .filter(Boolean),
      tax_id: form.tax_id.trim() || null,
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      address: form.address.trim() || null,
      notes: form.notes.trim() || null,
    };
    try {
      if (supplier) {
        payload.active = form.active;
        await api.updateSupplier(supplier.id, payload);
        show("Fournisseur mis à jour.", "success");
        onSaved(form.name.trim());
      } else {
        await api.createSupplier({ ...payload, code: form.code.trim() });
        show("Fournisseur créé.", "success");
        onSaved(form.name.trim());
      }
      onSaved();
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Enregistrement impossible.";
      setError(message);
      show(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const pushToTulip = async () => {
    if (!supplier) return;
    setPushing(true);
    setError(null);
    try {
      const result = (await api.tulipPushSupplier(supplier.id, false)) as { code?: number };
      show(
        typeof result.code === "number"
          ? `Fournisseur créé dans Tulip (code interne ${result.code}).`
          : "Fournisseur créé dans Tulip.",
        "success",
      );
      onClose();
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Envoi vers Tulip impossible.";
      setError(message);
      show(message, "error");
    } finally {
      setPushing(false);
    }
  };

  return (
    <Modal
      open={open}
      title={supplier ? "Modifier le fournisseur" : "Nouveau fournisseur"}
      subtitle={supplier ? `${supplier.code} — ${supplier.name}` : "Le code doit correspondre au code fournisseur Tulip."}
      onClose={onClose}
      wide
      footer={
        <>
          {supplier && (
            <button
              type="button"
              className="button"
              onClick={pushToTulip}
              disabled={pushing || saving}
              title="Créer ce fournisseur dans la base Tulip (table CLIENTS). Refusé si le code principal existe déjà."
            >
              {pushing ? <span className="spinner small" /> : <Icon name="upload" size={16} />} Créer dans Tulip
            </button>
          )}
          <div className="spacer" />
          <button type="button" className="button" onClick={onClose}>
            Annuler
          </button>
          <button type="button" className="button button-primary" onClick={submit} disabled={saving}>
            {saving ? <span className="spinner small light" /> : <Icon name="save" size={16} />} Enregistrer
          </button>
        </>
      }
    >
      <div className="form-grid">
        <label className="field">
          <span>Code Tulip *</span>
          <input
            value={form.code}
            onChange={(event) => set("code", event.target.value)}
            disabled={Boolean(supplier)}
            placeholder="000123"
            className="mono"
          />
        </label>
        <label className="field">
          <span>Nom *</span>
          <input value={form.name} onChange={(event) => set("name", event.target.value)} />
        </label>
        <label className="field full">
          <span>Alias / variantes</span>
          <input
            value={form.name_variants}
            onChange={(event) => set("name_variants", event.target.value)}
            placeholder="Variante 1 | Variante 2"
          />
          <small className="muted">Séparez les variantes par une barre verticale « | ».</small>
        </label>
        <label className="field">
          <span>NIF</span>
          <input value={form.tax_id} onChange={(event) => set("tax_id", event.target.value)} className="mono" />
        </label>
        <label className="field">
          <span>Téléphone</span>
          <input value={form.phone} onChange={(event) => set("phone", event.target.value)} />
        </label>
        <label className="field">
          <span>E-mail</span>
          <input type="email" value={form.email} onChange={(event) => set("email", event.target.value)} />
        </label>
        <label className="field">
          <span>Adresse</span>
          <input value={form.address} onChange={(event) => set("address", event.target.value)} />
        </label>
        <label className="field full">
          <span>Notes</span>
          <textarea rows={2} value={form.notes} onChange={(event) => set("notes", event.target.value)} />
        </label>
        {supplier && (
          <label className="checkbox full">
            <input type="checkbox" checked={form.active} onChange={(event) => set("active", event.target.checked)} />
            <span>Fournisseur actif</span>
          </label>
        )}
      </div>
      {error && <p className="inline-error">{error}</p>}
      <p className="muted tiny">
        Les alias confirmés lors de la vérification d'une facture sont automatiquement ajoutés et réutilisés.
      </p>
    </Modal>
  );
}
