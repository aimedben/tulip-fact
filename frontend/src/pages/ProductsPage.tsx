import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Paged, Product } from "../types";
import { EmptyState, PageHeader, Pagination, Panel, Spinner } from "../components/Common";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { CatalogImport } from "../components/CatalogImport";
import { BarcodeScanInput } from "../components/BarcodeScanInput";
import { useToast } from "../components/Toast";
import { parseAmount } from "../lib/format";

interface ProductForm {
  tulip_code: string;
  designation: string;
  reference: string;
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
  reference: "",
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
  const [scanOpen, setScanOpen] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [pendingBarcode, setPendingBarcode] = useState("");
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

  const lookupBarcode = async (barcode: string) => {
    setScanLoading(true);
    setScanError(null);
    try {
      const product = await api.getProductByBarcode(barcode);
      setScanOpen(false);
      setEditing(product);
      setFormOpen(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setScanOpen(false);
        setEditing(null);
        setPendingBarcode(barcode);
        setFormOpen(true);
      } else {
        setScanError(err instanceof Error ? err.message : "Recherche impossible.");
      }
    } finally {
      setScanLoading(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Articles"
        subtitle="Chaque article ajouté ici est enregistré dans Tulip en même temps."
        actions={
          <>
            <button type="button" className="button" disabled={syncing} onClick={syncFromTulip}>
              {syncing ? <Spinner label="Mise à jour…" /> : <Icon name="download" size={16} />} Mettre à jour depuis Tulip
            </button>
            <button type="button" className="button" onClick={() => setShowImport((value) => !value)}>
              <Icon name="upload" size={16} /> Importer une liste
            </button>
            <button
              type="button"
              className="button"
              onClick={() => {
                setScanError(null);
                setScanOpen(true);
              }}
            >
              <Icon name="barcode" size={16} /> Scanner un code-barres
            </button>
            <button type="button" className="button button-primary" onClick={openCreate}>
              <Icon name="plus" size={16} /> Ajouter un article
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
            title={appliedQuery ? "Aucun article trouvé" : "Aucun article"}
            description={
              appliedQuery
                ? "Essayez un autre mot, ou mettez à jour depuis Tulip."
                : "Cliquez sur « Ajouter un article » pour commencer."
            }
            action={
              <button type="button" className="button button-primary" onClick={openCreate}>
                <Icon name="plus" size={16} /> Ajouter un article
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
                  <th>Réf. article</th>
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
                    <td className="mono small">{product.reference ?? "—"}</td>
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
        initialBarcode={pendingBarcode}
        onClose={() => {
          setFormOpen(false);
          setPendingBarcode("");
        }}
        onSaved={() => {
          setFormOpen(false);
          setPendingBarcode("");
          refresh();
        }}
      />

      <Modal
        open={scanOpen}
        title="Scanner un code-barres"
        subtitle="Douchette USB ou saisie manuelle : le produit est recherché dans le référentiel."
        onClose={() => {
          setScanOpen(false);
          setScanError(null);
        }}
        footer={
          <button type="button" className="button" onClick={() => setScanOpen(false)}>
            Fermer
          </button>
        }
      >
        <BarcodeScanInput onScan={lookupBarcode} busy={scanLoading} />
        {scanError && <p className="inline-error">{scanError}</p>}
        <p className="muted tiny">
          Scannez un article : s'il existe, sa fiche s'ouvre pour consultation. Sinon, le formulaire de création est
          prérempli avec le code-barres.
        </p>
      </Modal>
    </>
  );
}

function ProductFormModal({
  open,
  product,
  initialBarcode = "",
  onClose,
  onSaved,
}: {
  open: boolean;
  product: Product | null;
  initialBarcode?: string;
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
        reference: product.reference ?? "",
        supplier_ref: product.supplier_ref ?? "",
        barcode: product.barcode ?? "",
        brand: product.brand ?? "",
        packaging: product.packaging ?? "",
        stock_unit: product.stock_unit ?? "",
        default_vat_rate: product.default_vat_rate !== null ? String(product.default_vat_rate).replace(".", ",") : "",
        active: product.active,
      });
    } else {
      setForm({ ...emptyForm, barcode: initialBarcode });
    }
  }, [open, product, initialBarcode]);

  const set = (key: keyof ProductForm, value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = async () => {
    if (!form.designation.trim()) {
      setError("Le nom de l'article est obligatoire.");
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
      reference: form.reference.trim() || null,
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
        onSaved();
      } else {
        const result = await api.createProduct(payload);
        if (result.tulip_push?.pushed) {
          show(
            `Enregistré dans Tulip — article n° ${result.tulip_push?.code ?? result.tulip_code}.`,
            "success",
          );
        } else {
          show(result.tulip_push?.reason ?? "Article enregistré dans l'application.", "warning");
        }
        onSaved();
      }
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
      title={product ? "Modifier l'article" : "Ajouter un article"}
      subtitle={
        product
          ? `${product.tulip_code} — ${product.designation}`
          : "Le numéro d'article est attribué automatiquement par Tulip."
      }
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
        {product && (
          <label className="field">
            <span>Numéro Tulip</span>
            <input value={form.tulip_code} readOnly className="mono" />
            <small className="muted">Attribué par Tulip, non modifiable.</small>
          </label>
        )}
        <label className={`field${product ? "" : " full"}`}>
          <span>Nom de l'article *</span>
          <input
            value={form.designation}
            onChange={(event) => set("designation", event.target.value)}
            placeholder="Ex. : HUILE FLEUR 1L"
            autoFocus
          />
        </label>
        <label className="field">
          <span>Code-barres</span>
          <input value={form.barcode} onChange={(event) => set("barcode", event.target.value)} className="mono" />
        </label>
        <label className="field">
          <span>Taux de TVA (%)</span>
          <input
            inputMode="decimal"
            value={form.default_vat_rate}
            onChange={(event) => set("default_vat_rate", event.target.value)}
            placeholder="19"
          />
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
          <span>Réf. article (Tulip)</span>
          <input
            value={form.reference}
            onChange={(event) => set("reference", event.target.value)}
            className="mono"
            placeholder="Laissez vide : Tulip la crée"
          />
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
        {product && (
          <label className="checkbox full">
            <input type="checkbox" checked={form.active} onChange={(event) => set("active", event.target.checked)} />
            <span>Article actif</span>
          </label>
        )}
      </div>
      {error && <p className="inline-error">{error}</p>}
      <p className="muted tiny">
        Le nom suffit : Tulip attribue le numéro d'article et la référence.
      </p>
    </Modal>
  );
}
