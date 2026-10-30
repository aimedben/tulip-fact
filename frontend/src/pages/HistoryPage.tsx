import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { ExportRecord, InvoiceSummary, Paged, Supplier } from "../types";
import { EmptyState, PageHeader, Pagination, Panel, Spinner } from "../components/Common";
import { StatusBadge } from "../components/StatusBadge";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { useToast } from "../components/Toast";
import { formatDateFR, formatDateTimeFR, formatMoney, statusLabel } from "../lib/format";

const STATUSES = ["IMPORTEE", "EXTRACTION", "A_VERIFIER", "PRETE_A_VALIDER", "VALIDEE", "EXPORTEE", "ECHEC"];

interface Filters {
  q: string;
  statuses: string[];
  supplierId: string;
  dateFrom: string;
  dateTo: string;
  duplicates: boolean;
}

function filtersFromParams(params: URLSearchParams): Filters {
  return {
    q: params.get("q") ?? "",
    statuses: (params.get("status") ?? "").split(",").filter(Boolean),
    supplierId: params.get("supplier_id") ?? "",
    dateFrom: params.get("date_from") ?? "",
    dateTo: params.get("date_to") ?? "",
    duplicates: params.get("duplicates") === "1",
  };
}

export function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => filtersFromParams(searchParams));
  const [applied, setApplied] = useState<Filters>(() => filtersFromParams(searchParams));
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paged<InvoiceSummary> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [tab, setTab] = useState<"invoices" | "exports">("invoices");
  const [exportsList, setExportsList] = useState<ExportRecord[] | null>(null);
  const [exportsLoading, setExportsLoading] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<InvoiceSummary | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const { show: toast } = useToast();

  useEffect(() => {
    api
      .suppliers({ page: 1, page_size: 200 })
      .then((result) => setSuppliers(result.items))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listInvoices({
        q: applied.q,
        status: applied.statuses.join(","),
        supplier_id: applied.supplierId,
        date_from: applied.dateFrom,
        date_to: applied.dateTo,
        duplicates: applied.duplicates ? 1 : undefined,
        page,
        page_size: 25,
      })
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Impossible de charger l'historique.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applied, page, reloadToken]);

  useEffect(() => {
    if (tab !== "exports" || exportsList !== null) return;
    setExportsLoading(true);
    api
      .exports({ limit: 200 })
      .then((result) => setExportsList(result.items))
      .catch(() => setExportsList([]))
      .finally(() => setExportsLoading(false));
  }, [tab, exportsList]);

  const apply = () => {
    setPage(1);
    setApplied(filters);
    const params = new URLSearchParams();
    if (filters.q) params.set("q", filters.q);
    if (filters.statuses.length > 0) params.set("status", filters.statuses.join(","));
    if (filters.supplierId) params.set("supplier_id", filters.supplierId);
    if (filters.dateFrom) params.set("date_from", filters.dateFrom);
    if (filters.dateTo) params.set("date_to", filters.dateTo);
    if (filters.duplicates) params.set("duplicates", "1");
    setSearchParams(params);
  };

  const reset = () => {
    const empty: Filters = { q: "", statuses: [], supplierId: "", dateFrom: "", dateTo: "", duplicates: false };
    setFilters(empty);
    setApplied(empty);
    setPage(1);
    setSearchParams(new URLSearchParams());
  };

  const toggleStatus = (status: string) => {
    setFilters((current) => ({
      ...current,
      statuses: current.statuses.includes(status)
        ? current.statuses.filter((entry) => entry !== status)
        : [...current.statuses, status],
    }));
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteInvoice(deleteTarget.id);
      toast("Facture supprimée.", "success");
      setDeleteTarget(null);
      setSelectedIds((current) => current.filter((id) => id !== deleteTarget.id));
      setReloadToken((value) => value + 1);
    } catch (error) {
      const message =
        error instanceof ApiError || error instanceof Error ? error.message : "Suppression impossible.";
      toast(message, "error");
    } finally {
      setDeleting(false);
    }
  };

  const toggleSelect = (invoiceId: number) => {
    setSelectedIds((current) =>
      current.includes(invoiceId) ? current.filter((id) => id !== invoiceId) : [...current, invoiceId],
    );
  };

  const toggleSelectAll = () => {
    const items = data?.items ?? [];
    const allSelected = items.length > 0 && items.every((invoice) => selectedIds.includes(invoice.id));
    setSelectedIds(allSelected ? [] : items.map((invoice) => invoice.id));
  };

  const confirmBulkDelete = async () => {
    setBulkDeleting(true);
    try {
      const result = await api.deleteInvoicesBulk(selectedIds);
      const suffix = result.refused.length > 0 ? ` (${result.refused.length} ignorée(s))` : "";
      toast(`${result.deleted.length} facture(s) supprimée(s)${suffix}.`, "success");
      setBulkOpen(false);
      setSelectedIds([]);
      setExportsList(null);
      setReloadToken((value) => value + 1);
    } catch (error) {
      const message =
        error instanceof ApiError || error instanceof Error ? error.message : "Suppression en masse impossible.";
      toast(message, "error");
    } finally {
      setBulkDeleting(false);
    }
  };

  const activeFilterCount =
    (filters.q ? 1 : 0) +
    filters.statuses.length +
    (filters.supplierId ? 1 : 0) +
    (filters.dateFrom ? 1 : 0) +
    (filters.dateTo ? 1 : 0) +
    (filters.duplicates ? 1 : 0);

  return (
    <>
      <PageHeader
        title="Historique & exports"
        subtitle="Retrouvez les factures traitées, filtrez par statut, fournisseur ou période, et téléchargez les fichiers générés."
        actions={
          <>
            {selectedIds.length > 0 && (
              <button
                type="button"
                className="button button-danger"
                onClick={() => setBulkOpen(true)}
                title="Supprimer toutes les factures sélectionnées"
              >
                <Icon name="trash" size={16} /> Supprimer la sélection ({selectedIds.length})
              </button>
            )}
            <Link to="/import" className="button button-primary">
              <Icon name="upload" size={16} /> Importer
            </Link>
          </>
        }
      />

      <div className="tabs">
        <button type="button" className={`tab${tab === "invoices" ? " active" : ""}`} onClick={() => setTab("invoices")}>
          Factures {data ? <span className="tab-count">{data.total}</span> : null}
        </button>
        <button type="button" className={`tab${tab === "exports" ? " active" : ""}`} onClick={() => setTab("exports")}>
          Exports {exportsList ? <span className="tab-count">{exportsList.length}</span> : null}
        </button>
      </div>

      {tab === "invoices" ? (
        <>
          <section className="panel filter-panel">
            <form
              className="filter-grid"
              onSubmit={(event) => {
                event.preventDefault();
                apply();
              }}
            >
              <label className="field search-field">
                <span>Recherche</span>
                <div className="search-input">
                  <Icon name="search" size={16} />
                  <input
                    value={filters.q}
                    onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
                    placeholder="Numéro, fournisseur ou nom de fichier"
                  />
                </div>
              </label>
              <label className="field">
                <span>Fournisseur</span>
                <select
                  value={filters.supplierId}
                  onChange={(event) => setFilters((current) => ({ ...current, supplierId: event.target.value }))}
                >
                  <option value="">Tous les fournisseurs</option>
                  {suppliers.map((supplier) => (
                    <option key={supplier.id} value={supplier.id}>
                      {supplier.code} — {supplier.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Du</span>
                <input
                  type="date"
                  value={filters.dateFrom}
                  onChange={(event) => setFilters((current) => ({ ...current, dateFrom: event.target.value }))}
                />
              </label>
              <label className="field">
                <span>Au</span>
                <input
                  type="date"
                  value={filters.dateTo}
                  onChange={(event) => setFilters((current) => ({ ...current, dateTo: event.target.value }))}
                />
              </label>
              <div className="filter-buttons">
                <button type="submit" className="button button-primary">
                  <Icon name="search" size={15} /> Appliquer
                </button>
                <button type="button" className="button" onClick={reset} disabled={activeFilterCount === 0}>
                  Réinitialiser
                </button>
              </div>
            </form>

            <div className="filter-status-row">
              <span className="muted small">Statut :</span>
              <div className="chip-toggles">
                {STATUSES.map((status) => (
                  <button
                    key={status}
                    type="button"
                    className={`filter-chip${filters.statuses.includes(status) ? " active" : ""}`}
                    onClick={() => toggleStatus(status)}
                  >
                    {statusLabel(status)}
                  </button>
                ))}
                <label className={`filter-chip${filters.duplicates ? " active danger" : ""}`}>
                  <input
                    type="checkbox"
                    checked={filters.duplicates}
                    onChange={(event) => setFilters((current) => ({ ...current, duplicates: event.target.checked }))}
                  />
                  Doublons uniquement
                </label>
              </div>
            </div>
          </section>

          {error && (
            <div className="banner banner-danger">
              <Icon name="alert" size={18} />
              <span>{error}</span>
            </div>
          )}

          <Panel
            title="Factures"
            subtitle={data ? `${data.total} résultat${data.total > 1 ? "s" : ""}` : "Chargement…"}
            actions={loading ? <Spinner /> : undefined}
            flush
          >
            {data && data.items.length === 0 ? (
              <EmptyState
                icon="search"
                title="Aucune facture ne correspond aux filtres"
                description="Modifiez la recherche ou réinitialisez les filtres pour afficher toutes les factures."
                action={
                  activeFilterCount > 0 ? (
                    <button type="button" className="button" onClick={reset}>
                      Réinitialiser les filtres
                    </button>
                  ) : (
                    <Link to="/import" className="button button-primary">
                      Importer une facture
                    </Link>
                  )
                }
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>
                        <input
                          type="checkbox"
                          aria-label="Tout sélectionner sur la page"
                          checked={(data?.items ?? []).length > 0 && (data?.items ?? []).every((invoice) => selectedIds.includes(invoice.id))}
                          onChange={toggleSelectAll}
                        />
                      </th>
                      <th>Facture</th>
                      <th>Fournisseur</th>
                      <th>Date facture</th>
                      <th className="align-right">Total TTC</th>
                      <th>Statut</th>
                      <th>Importée le</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.items ?? []).map((invoice) => (
                      <tr key={invoice.id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Sélectionner ${invoice.invoice_number ?? invoice.id}`}
                            checked={selectedIds.includes(invoice.id)}
                            onChange={() => toggleSelect(invoice.id)}
                          />
                        </td>
                        <td>
                          <Link to={`/invoices/${invoice.id}`} className="primary-cell">
                            {invoice.invoice_number ?? `Facture #${invoice.id}`}
                          </Link>
                          <div className="muted small mono">{invoice.original_filename}</div>
                        </td>
                        <td>
                          <div>{invoice.supplier_name ?? "Non identifié"}</div>
                          {invoice.supplier_code && <div className="muted small mono">{invoice.supplier_code}</div>}
                        </td>
                        <td className="nowrap">{formatDateFR(invoice.invoice_date)}</td>
                        <td className="align-right mono nowrap">{formatMoney(invoice.total_ttc, invoice.currency)}</td>
                        <td>
                          <StatusBadge status={invoice.status} compact />
                          {invoice.is_duplicate && <div className="mini-flag">doublon</div>}
                        </td>
                        <td className="muted small nowrap">{formatDateTimeFR(invoice.imported_at)}</td>
                        <td className="align-right nowrap">
                          <Link to={`/invoices/${invoice.id}`} className="button button-sm">
                            Ouvrir
                          </Link>
                          <button
                            type="button"
                            className="button button-sm"
                            title="Supprimer cette facture"
                            onClick={() => setDeleteTarget(invoice)}
                          >
                            <Icon name="trash" size={14} />
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
        </>
      ) : (
        <Panel
          title="Fichiers exportés"
          subtitle="CSV, Excel, JSON et rapports de contrôle générés localement."
          actions={
            <button
              type="button"
              className="button button-sm"
              onClick={() => {
                setExportsList(null);
                setExportsLoading(true);
                api
                  .exports({ limit: 200 })
                  .then((result) => setExportsList(result.items))
                  .catch(() => setExportsList([]))
                  .finally(() => setExportsLoading(false));
              }}
            >
              <Icon name="refresh" size={15} /> Actualiser
            </button>
          }
          flush
        >
          {exportsLoading && exportsList === null ? (
            <div className="panel-padded">
              <Spinner label="Chargement des exports…" />
            </div>
          ) : !exportsList || exportsList.length === 0 ? (
            <EmptyState
              icon="download"
              title="Aucun export"
              description="Validez une facture puis générez un export depuis sa fiche pour le retrouver ici."
            />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Facture</th>
                    <th>Fournisseur</th>
                    <th>Format</th>
                    <th>Date</th>
                    <th>Empreinte</th>
                    <th aria-label="Téléchargement" />
                  </tr>
                </thead>
                <tbody>
                  {exportsList.map((record) => (
                    <tr key={record.id}>
                      <td>
                        <Link to={`/invoices/${record.invoice_id}`} className="primary-cell">
                          {record.invoice_number ?? `Facture #${record.invoice_id}`}
                        </Link>
                      </td>
                      <td>{record.supplier_name ?? "—"}</td>
                      <td>
                        <span className="format-chip">{record.format.toUpperCase()}</span>
                      </td>
                      <td className="muted small nowrap">{formatDateTimeFR(record.created_at)}</td>
                      <td className="mono tiny muted">{record.sha256.slice(0, 16)}…</td>
                      <td className="align-right">
                        <a className="button button-sm" href={record.download_url}>
                          <Icon name="download" size={15} /> Télécharger
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="panel-padded muted tiny">
            Le format d'import direct de Tulip Gestion commerciale n'étant pas confirmé, ces fichiers doivent être contrôlés
            avant toute utilisation.
          </div>
        </Panel>
      )}

      <Modal
        open={deleteTarget !== null}
        title="Supprimer la facture ?"
        subtitle={deleteTarget ? `${deleteTarget.original_filename} — action définitive` : ""}
        onClose={() => setDeleteTarget(null)}
        footer={
          <>
            <button type="button" className="button" onClick={() => setDeleteTarget(null)}>
              Annuler
            </button>
            <button type="button" className="button button-danger" onClick={confirmDelete} disabled={deleting}>
              {deleting ? <span className="spinner small light" /> : <Icon name="trash" size={16} />} Supprimer
            </button>
          </>
        }
      >
        <p className="muted">
          Le document, ses pages et ses données extraites seront supprimés définitivement. Une trace d'audit
          (facture_supprimee) est conservée, y compris pour une facture validée ou exportée.
        </p>
      </Modal>

      <Modal
        open={bulkOpen}
        title="Supprimer la sélection ?"
        subtitle={selectedIds.length > 0 ? `${selectedIds.length} facture(s) — action définitive` : ""}
        onClose={() => setBulkOpen(false)}
        footer={
          <>
            <button type="button" className="button" onClick={() => setBulkOpen(false)}>
              Annuler
            </button>
            <button type="button" className="button button-danger" onClick={confirmBulkDelete} disabled={bulkDeleting}>
              {bulkDeleting ? <span className="spinner small light" /> : <Icon name="trash" size={16} />} Tout supprimer
            </button>
          </>
        }
      >
        <p className="muted">
          Le document, les pages et les données extraites de chaque facture sélectionnée seront supprimés
          définitivement, y compris les factures déjà validées ou exportées. Une trace d'audit est conservée pour chaque
          suppression.
        </p>
      </Modal>
    </>
  );
}
