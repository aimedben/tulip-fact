import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { DashboardData } from "../types";
import { EmptyState, PageHeader, Panel, Spinner } from "../components/Common";
import { StatusBadge } from "../components/StatusBadge";
import { Icon } from "../components/Icon";
import { TulipLivePanel } from "../components/TulipLivePanel";
import { formatDateFR, formatDateTimeFR, formatMoney } from "../lib/format";

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = async (quiet = false) => {
      if (!quiet) setLoading(true);
      try {
        const result = await api.dashboard();
        if (cancelled) return;
        setData(result);
        setError(null);
        if (result.counts.en_cours > 0) {
          timer = window.setTimeout(() => load(true), 4000);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Impossible de charger le tableau de bord.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  if (loading && !data) {
    return (
      <div className="loading-page">
        <Spinner label="Chargement du tableau de bord…" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <EmptyState
        icon="clock"
        title="Serveur local inaccessible"
        description={error}
        action={
          <button type="button" className="button" onClick={() => window.location.reload()}>
            <Icon name="refresh" size={16} /> Réessayer
          </button>
        }
      />
    );
  }

  if (!data) return null;

  const counts = data.counts;
  const toReview = counts.a_verifier + counts.pretes_a_valider;

  return (
    <>
      <PageHeader
        title="Accueil"
        subtitle="Vos factures fournisseurs, du scan jusqu'à l'enregistrement dans Tulip."
        actions={
          <>
            <Link to="/history" className="button">
              <Icon name="history" size={16} /> Historique
            </Link>
            <Link to="/import" className="button button-primary">
              <Icon name="upload" size={16} /> Ajouter une facture
            </Link>
          </>
        }
      />

      {counts.en_cours > 0 && (
        <div className="banner banner-info">
          <Spinner />
          <span>
            {counts.en_cours} document{counts.en_cours > 1 ? "s" : ""} en cours de traitement. Les statuts se mettent à jour
            automatiquement.
          </span>
        </div>
      )}

      <div className="kpi-grid">
        <Link to="/history?status=A_VERIFIER,PRETE_A_VALIDER" className="kpi-card kpi-accent">
          <div className="kpi-top">
            <span className="kpi-label">À contrôler</span>
            <span className="kpi-icon">
              <Icon name="eye" size={18} />
            </span>
          </div>
          <div className="kpi-value">{toReview}</div>
          <div className="kpi-foot">
            {counts.pretes_a_valider} prête{counts.pretes_a_valider > 1 ? "s" : ""} à valider · {counts.a_verifier} à compléter
          </div>
        </Link>
        <Link to="/history?status=EXTRACTION,IMPORTEE" className="kpi-card">
          <div className="kpi-top">
            <span className="kpi-label">En traitement</span>
            <span className="kpi-icon">
              <Icon name="clock" size={18} />
            </span>
          </div>
          <div className="kpi-value">{counts.en_cours}</div>
          <div className="kpi-foot">Lecture des factures en cours</div>
        </Link>
        <Link to="/history?status=VALIDEE" className="kpi-card">
          <div className="kpi-top">
            <span className="kpi-label">Validées</span>
            <span className="kpi-icon">
              <Icon name="shield" size={18} />
            </span>
          </div>
          <div className="kpi-value">{counts.validees}</div>
          <div className="kpi-foot">Contrôlées et verrouillées</div>
        </Link>
        <Link to="/history?status=EXPORTEE" className="kpi-card">
          <div className="kpi-top">
            <span className="kpi-label">Terminées</span>
            <span className="kpi-icon">
              <Icon name="download" size={18} />
            </span>
          </div>
          <div className="kpi-value">{counts.exportees}</div>
          <div className="kpi-foot">Validées et enregistrées dans Tulip</div>
        </Link>
      </div>

      <TulipLivePanel />

      <div className="dashboard-grid">
        <Panel
          title="File de travail"
          subtitle="Les dernières factures importées, les plus récentes d'abord."
          actions={
            <Link to="/history" className="text-link">
              Tout voir <Icon name="chevronRight" size={15} />
            </Link>
          }
          flush
          className="span-2"
        >
          {data.recent_invoices.length === 0 ? (
            <EmptyState
              title="Aucune facture importée"
              description="Ajoutez un PDF ou une photo de facture pour démarrer. Les champs sont lus automatiquement."
              action={
                <Link to="/import" className="button button-primary">
                  <Icon name="upload" size={16} /> Ajouter une première facture
                </Link>
              }
            />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Facture</th>
                    <th>Fournisseur</th>
                    <th>Date</th>
                    <th className="align-right">TTC</th>
                    <th>Statut</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {data.recent_invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>
                        <Link to={`/invoices/${invoice.id}`} className="primary-cell">
                          {invoice.invoice_number ?? "Numéro à compléter"}
                        </Link>
                        <div className="muted small mono">{invoice.original_filename}</div>
                      </td>
                      <td>
                        <div>{invoice.supplier_name ?? "Fournisseur non identifié"}</div>
                        {invoice.supplier_code && <div className="muted small mono">{invoice.supplier_code}</div>}
                      </td>
                      <td className="nowrap">{formatDateFR(invoice.invoice_date)}</td>
                      <td className="align-right mono nowrap">
                        {formatMoney(invoice.total_ttc, invoice.currency)}
                      </td>
                      <td>
                        <StatusBadge status={invoice.status} compact />
                        {invoice.is_duplicate && <span className="mini-flag">doublon</span>}
                      </td>
                      <td className="align-right">
                        <Link to={`/invoices/${invoice.id}`} className="icon-button" aria-label="Ouvrir la facture">
                          <Icon name="chevronRight" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="stack">
          <Panel title="Points d'attention">
            <div className="attention-list">
              <Link to="/history?status=A_VERIFIER" className="attention-row">
                <span className="attention-icon tone-warning">
                  <Icon name="alert" size={17} />
                </span>
                <span>
                  <strong>{counts.a_verifier}</strong>
                  <small>facture{counts.a_verifier > 1 ? "s" : ""} à compléter</small>
                </span>
                <Icon name="chevronRight" size={15} />
              </Link>
              <Link to="/history?duplicates=1" className="attention-row">
                <span className="attention-icon tone-danger">
                  <Icon name="alert" size={17} />
                </span>
                <span>
                  <strong>{counts.doublons}</strong>
                  <small>doublon{counts.doublons > 1 ? "s" : ""} potentiel{counts.doublons > 1 ? "s" : ""}</small>
                </span>
                <Icon name="chevronRight" size={15} />
              </Link>
              <Link to="/history?status=ECHEC" className="attention-row">
                <span className="attention-icon tone-neutral">
                  <Icon name="refresh" size={17} />
                </span>
                <span>
                  <strong>{counts.en_echec}</strong>
                  <small>échec{counts.en_echec > 1 ? "s" : ""} de traitement</small>
                </span>
                <Icon name="chevronRight" size={15} />
              </Link>
            </div>
          </Panel>

          <Panel title="Comment ça marche">
            <ol className="flow-list">
              <li>
                <span className="flow-step">1</span>
                <div>
                  <strong>Ajouter</strong>
                  <small>PDF, JPG ou PNG. Tout reste sur cet ordinateur.</small>
                </div>
              </li>
              <li>
                <span className="flow-step">2</span>
                <div>
                  <strong>Vérifier</strong>
                  <small>Corriger les champs, choisir le fournisseur et les articles.</small>
                </div>
              </li>
              <li>
                <span className="flow-step">3</span>
                <div>
                  <strong>Valider</strong>
                  <small>La facture est enregistrée directement dans Tulip.</small>
                </div>
              </li>
            </ol>
          </Panel>
        </div>
      </div>

      <Panel
        title="Derniers enregistrements"
        subtitle="Factures envoyées dans Tulip."
        actions={
          <Link to="/history" className="text-link">
            Consulter <Icon name="chevronRight" size={15} />
          </Link>
        }
        flush
      >
        {data.recent_exports.length === 0 ? (
          <p className="muted small panel-padded">Aucun enregistrement pour le moment.</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table compact-table">
              <thead>
                <tr>
                  <th>Facture</th>
                  <th>Fournisseur</th>
                  <th>Format</th>
                  <th>Date</th>
                  <th aria-label="Téléchargement" />
                </tr>
              </thead>
              <tbody>
                {data.recent_exports.map((record) => (
                  <tr key={record.id}>
                    <td>{record.invoice_number ?? `Facture #${record.invoice_id}`}</td>
                    <td>{record.supplier_name ?? "—"}</td>
                    <td>
                      <span className="format-chip">{record.format.toUpperCase()}</span>
                    </td>
                    <td className="nowrap muted small">{formatDateTimeFR(record.created_at)}</td>
                    <td className="align-right">
                      <a className="icon-button" href={record.download_url} aria-label={`Télécharger ${record.format}`}>
                        <Icon name="download" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
