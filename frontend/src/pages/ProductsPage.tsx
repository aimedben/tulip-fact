import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Paged, Product } from "../types";
import { EmptyState, PageHeader, Pagination, Panel, Spinner } from "../components/Common";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { CatalogImport } from "../components/CatalogImport";
import { useToast } from "../components/Toast";
import { parseAmount } from "../lib/format";

interface ProductForm {
  tulip_code: string;
  designation: string;
  supplier_ref: string;
  barcode: string;
  brand: string;
  packaging: string;
  stock_unit: string;
  default_vat_rate: string;
  active: boolean;
}

const emptyForm: ProductForm = {
  tulip_code: "",
  designation: "",
  supplier_ref: "",
  barcode: "",
  brand: "",
  packaging: "",
  stock_unit: "",
  default_vat_rate: "",
  active: true,
};

export function ProductsPage() {
  const [data, setData] = useState<Paged<Product> | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [page, setPage] = useState(1);
  const [reloadToken, setReloadToken] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const { show: toast } = useToast();

  const syncFromTulip = async () => {
    setSyncing(true);
    try {
      const result = await api.tulipSyncProducts();
      toast(
        `${result.created} article(s) créé(s), ${result.updated} mis à jour — ${result.local_total} en base locale.`,
        "success",
      );
      refresh();
    } catch (err) {
      toast(err instanceof Error ? `Récupération impossible : ${err.message}` : "Récupération impossible.", "error");
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .products({ q: appliedQuery, page, page_size: 50 })
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Impossible de charger les articles.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [appliedQuery, page, reloadToken]);

  const refresh = () => setReloadToken((value) => value + 1);

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (product: Product) => {
    setEditing(product);
    setFormOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Référentiel articles"
        subtitle="Le rapprochement s'appuie sur le code Tulip, la référence fournisseur, le code-barres et la désignation."
        actions={
          <>
            <button type="button" className="button" disabled={syncing} onClick={syncFromTulip}>
              {syncing ? <Spinner label="Récupération…" /> : <Icon name="download" size={16} />} Récupérer depuis Tulip
            </button>
            <button type="button" className="button" onClick={() => setShowImport((value) => !value)}>
              <Icon name="upload" size={16} /> Import CSV / XLSX
            </button>
            <button type="button" className="button button-primary" onClick={openCreate}>
              <Icon name="plus" size={16} /> Nouvel article
            </button>
          </>
        }
      />

      {showImport && (
        <Panel title="Importer le référentiel articles" subtitle="Import par fichier, avec rapport des lignes rejetées.">
          <CatalogImport kind="products" onImported={refresh} />
        </Panel>
      )}

      <Panel
        title="Articles"
        subtitle={data ? `${data.total} article${data.total > 1 ? "s" : ""}` : "Chargement…"}
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
                placeholder="Code Tulip, référence, code-barres ou désignation"
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
            icon="products"
            title={appliedQuery ? "Aucun article trouvé" : "Référentiel articles vide"}
            description={
              appliedQuery
                ? "Essayez un autre terme ou importez le référentiel depuis un fichier."
                : "Importez les articles Tulip ou créez une fiche pour activer le rapprochement automatique."
            }
            action={
              <button type="button" className="button button-primary" onClick={openCreate}>
                <Icon name="plus" size={16} /> Nouvel article
              </button>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Code Tulip</th>
                  <th>Désignation</th>
                  <th>Réf. fournisseur</th>
                  <th>Code-barres</th>
                  <th>Conditionnement</th>
                  <th className="align-right">TVA</th>
                  <th>État</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {(data?.items ?? []).map((product) => (
                  <tr key={product.id}>
                    <td className="mono">{product.tulip_code}</td>
                    <td>
                      <strong>{product.designation}</strong>
                      {product.brand && <div className="muted small">{product.brand}</div>}
                    </td>
                    <td className="mono small">{product.supplier_ref ?? "—"}</td>
                    <td className="mono small">{product.barcode ?? "—"}</td>
                    <td className="small">
                      {product.packaging ?? "—"}
                      {product.stock_unit && <div className="muted tiny">Unité : {product.stock_unit}</div>}
                    </td>
                    <td className="align-right mono">{product.default_vat_rate !== null ? `${product.default_vat_rate} %` : "—"}</td>
                    <td>
                      <span className={`status-badge tone-${product.active ? "success" : "neutral"}`}>
                        {product.active ? "Actif" : "Inactif"}
                      </span>
                    </td>
                    <td className="align-right">
                      <button type="button" className="button button-sm" onClick={() => openEdit(product)}>
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

      <ProductFormModal
        open={formOpen}
        product={editing}
        onClose={() => setFormOpen(false)}
        onSaved={() => {
          setFormOpen(false);
          refresh();
        }}
      />
    </>
  );
}

function ProductFormModal({
  open,
  product,
  onClose,
  onSaved,
}: {
  open: boolean;
  product: Product | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ProductForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (product) {
      setForm({
        tulip_code: product.tulip_code,
        designation: product.designation,
        supplier_ref: product.supplier_ref ?? "",
        barcode: product.barcode ?? "",
        brand: product.brand ?? "",
        packaging: product.packaging ?? "",
        stock_unit: product.stock_unit ?? "",
        default_vat_rate: product.default_vat_rate !== null ? String(product.default_vat_rate).replace(".", ",") : "",
        active: product.active,
      });
    } else {
      setForm(emptyForm);
    }
  }, [open, product]);

  const set = (key: keyof ProductForm, value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = async () => {
    if (!form.tulip_code.trim() || !form.designation.trim()) {
      setError("Le code Tulip et la désignation sont obligatoires.");
      return;
    }
    const rate = form.default_vat_rate.trim() === "" ? null : parseAmount(form.default_vat_rate);
    if (form.default_vat_rate.trim() !== "" && (rate === null || rate < 0 || rate > 100)) {
      setError("Le taux de TVA doit être un nombre entre 0 et 100.");
      return;
    }
    setSaving(true);
    setError(null);
    const payload: Record<string, unknown> = {
      designation: form.designation.trim(),
      supplier_ref: form.supplier_ref.trim() || null,
      barcode: form.barcode.trim() || null,
      brand: form.brand.trim() || null,
      packaging: form.packaging.trim() || null,
      stock_unit: form.stock_unit.trim() || null,
      default_vat_rate: rate,
    };
    try {
      if (product) {
        payload.active = form.active;
        await api.updateProduct(product.id, payload);
        show("Article mis à jour.", "success");
      } else {
        await api.createProduct({ ...payload, tulip_code: form.tulip_code.trim() });
        show("Article créé.", "success");
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

  return (
    <Modal
      open={open}
      title={product ? "Modifier l'article" : "Nouvel article"}
      subtitle={product ? `${product.tulip_code} — ${product.designation}` : "Le code doit correspondre au code article Tulip."}
      onClose={onClose}
      wide
      footer={
        <>
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
            value={form.tulip_code}
            onChange={(event) => set("tulip_code", event.target.value)}
            disabled={Boolean(product)}
            className="mono"
          />
        </label>
        <label className="field">
          <span>Désignation *</span>
          <input value={form.designation} onChange={(event) => set("designation", event.target.value)} />
        </label>
        <label className="field">
          <span>Référence fournisseur</span>
          <input
            value={form.supplier_ref}
            onChange={(event) => set("supplier_ref", event.target.value)}
            className="mono"
          />
        </label>
        <label className="field">
          <span>Code-barres</span>
          <input value={form.barcode} onChange={(event) => set("barcode", event.target.value)} className="mono" />
        </label>
        <label className="field">
          <span>Marque</span>
          <input value={form.brand} onChange={(event) => set("brand", event.target.value)} />
        </label>
        <label className="field">
          <span>Conditionnement</span>
          <input value={form.packaging} onChange={(event) => set("packaging", event.target.value)} placeholder="12 x 1 L" />
        </label>
        <label className="field">
          <span>Unité de stock</span>
          <input value={form.stock_unit} onChange={(event) => set("stock_unit", event.target.value)} placeholder="UNITE, CARTON…" />
        </label>
        <label className="field">
          <span>Taux de TVA par défaut (%)</span>
          <input
            inputMode="decimal"
            value={form.default_vat_rate}
            onChange={(event) => set("default_vat_rate", event.target.value)}
            placeholder="19"
          />
        </label>
        {product && (
          <label className="checkbox full">
            <input type="checkbox" checked={form.active} onChange={(event) => set("active", event.target.checked)} />
            <span>Article actif</span>
          </label>
        )}
      </div>
      {error && <p className="inline-error">{error}</p>}
      <p className="muted tiny">
        Une référence fournisseur confirmée lors du rapprochement est réutilisée automatiquement pour les prochaines factures
        du même fournisseur.
      </p>
    </Modal>
  );
}
