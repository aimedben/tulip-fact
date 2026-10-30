import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { TulipLiveBeDocument, TulipLiveStatus, TulipLiveSummary, TulipLiveSupplier } from "../types";
import { EmptyState, Panel, Spinner } from "./Common";
import { Icon } from "./Icon";
import { formatDateFR, formatMoney } from "../lib/format";

interface LiveState {
  status?: TulipLiveStatus;
  summary?: TulipLiveSummary;
  suppliers?: TulipLiveSupplier[];
  beDocuments?: TulipLiveBeDocument[];
  unavailable: boolean;
}

type Outcome<T> = PromiseSettledResult<T>;

export function TulipLivePanel() {
  const [state, setState] = useState<LiveState | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const next: LiveState = { unavailable: false };
      const [status, summary, suppliers, be]: [
        Outcome<TulipLiveStatus>,
        Outcome<TulipLiveSummary>,
        Outcome<{ items: TulipLiveSupplier[] }>,
        Outcome<{ items: TulipLiveBeDocument[] }>,
      ] = await Promise.allSettled([
        api.tulipLiveStatus(),
        api.tulipLiveSummary(),
        api.tulipLiveSuppliers(6),
        api.tulipLiveBe(8),
      ] as const);
      if (cancelled) return;
      if (status.status === "fulfilled") {
        next.status = status.value;
        next.unavailable = !(status.value.enabled && status.value.configured);
      } else {
        next.unavailable = true;
      }
      if (summary.status === "fulfilled") next.summary = summary.value;
      if (suppliers.status === "fulfilled") next.suppliers = suppliers.value.items;
      if (be.status === "fulfilled") next.beDocuments = be.value.items;
      setState(next);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!state) {
    return (
      <Panel title="Base Tulip" subtitle="Connexion à la base de données Firebird.">
        <div className="loading-inline">
          <Spinner label="Connexion à Tulip…" />
        </div>
      </Panel>
    );
  }

  if (state.unavailable || !state.status) {
    return (
      <Panel title="Base Tulip" subtitle="Connexion à la base de données Firebird.">
        <EmptyState
          icon="database"
          title="Base Tulip non connectée"
          description="Configurez la connexion Firebird dans la page Réglages pour afficher les fournisseurs et les bons d'achat."
          action={
            <Link to="/settings" className="button">
              <Icon name="settings" size={16} /> Ouvrir les réglages
            </Link>
          }
        />
      </Panel>
    );
  }

  const status = state.status;
  const connected = status.connected !== false;
  const summary = state.summary;
  const be = state.beDocuments ?? [];

  return (
    <Panel
      title="Base Tulip"
      subtitle={status.database ? `${status.host}/${status.port} · ${status.database}` : `${status.host}/${status.port}`}
      actions={
        <span className={`status-badge ${connected ? "tone-success" : "tone-danger"}`}>
          {connected ? "Connectée" : "Hors ligne"}
        </span>
      }
    >
      <div className="tulip-summary-grid">
        <div className="tulip-stat">
          <span className="tulip-stat-label">Fournisseurs</span>
          <strong>{summary ? summary.suppliers : "—"}</strong>
        </div>
        <div className="tulip-stat">
          <span className="tulip-stat-label">Articles</span>
          <strong>{summary ? summary.products : "—"}</strong>
        </div>
        <div className="tulip-stat">
          <span className="tulip-stat-label">Bons d'achat</span>
          <strong>{summary ? summary.be_total : "—"}</strong>
        </div>
        <div className="tulip-stat">
          <span className="tulip-stat-label">Dettes comptabilisées</span>
          <strong>{summary ? summary.be_dette : "—"}</strong>
        </div>
        <div className="tulip-stat">
          <span className="tulip-stat-label">Moteur</span>
          <strong>{status.engine_version ?? "—"}</strong>
        </div>
        <div className="tulip-stat">
          <span className="tulip-stat-label">Mode</span>
          <strong>{status.write_enabled ? "Lecture / écriture" : "Lecture seule"}</strong>
        </div>
      </div>

      <div className="tulip-columns">
        <section>
          <h3 className="wide-heading">
            Derniers fournisseurs
            {state.suppliers ? <Link to="/suppliers" className="text-link">Tout voir</Link> : null}
          </h3>
          {state.suppliers && state.suppliers.length > 0 ? (
            <ul className="tulip-suppliers">
              {state.suppliers.map((supplier) => (
                <li key={supplier.tulip_code ?? supplier.name}>
                  <div>
                    <div className="primary-cell">{supplier.name}</div>
                    <div className="muted small mono">{supplier.tulip_code ?? "—"}</div>
                  </div>
                  <div className="muted small">{supplier.tax_id ?? "—"}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucun fournisseur lisible.</p>
          )}
        </section>

        <section>
          <h3 className="wide-heading">
            Derniers bons d'achat
          </h3>
          {be.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table compact-table">
                <thead>
                  <tr>
                    <th>N°</th>
                    <th>Fournisseur</th>
                    <th>Date</th>
                    <th className="align-right">TTC</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {be.map((document) => (
                    <tr key={document.id ?? `${document.numero}`}>
                      <td className="mono">{document.numero ?? "—"}</td>
                      <td>
                        <div>{document.supplier_name ?? document.supplier_code ?? "—"}</div>
                        {(document.nbc || document.livfact) && (
                          <div className="muted small mono">{document.nbc ?? document.livfact}</div>
                        )}
                      </td>
                      <td className="nowrap">{formatDateFR(document.opdate)}</td>
                      <td className="align-right mono nowrap">{formatMoney(document.ttc, "DZD")}</td>
                      <td>
                        <span className={`status-badge ${document.dette ? "tone-success" : "tone-neutral"}`}>
                          {document.dette ? "Comptabilisé" : "En cours"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted small">Aucun bon d'achat lisible.</p>
          )}
        </section>
      </div>
      {status.error && <p className="muted small panel-padded">{status.error}</p>}
    </Panel>
  );
}
