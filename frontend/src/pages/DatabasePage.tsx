import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { Pagination, Panel, Spinner } from "../components/Common";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";

type Row = Record<string, string | number | boolean | null>;

interface TableInfo {
  name: string;
  rows: number | null;
}

interface TablePreview {
  table: string;
  columns: string[];
  total: number | null;
  page: number;
  page_size: number;
  items: Row[];
}

interface BackupInfo {
  name: string;
  size: number;
  created_at: string;
}

interface LocalTableInfo extends TableInfo {
  columns: Array<{ name: string; type: string }>;
}

function ValueCell({ value }: { value: string | number | boolean | null }) {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  return <span className="mono">{String(value)}</span>;
}

function RowTable({ preview }: { preview: TablePreview }) {
  const columns = preview.columns.slice(0, 16);
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.items.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>
                  <ValueCell value={row[column] ?? null} />
                </td>
              ))}
            </tr>
          ))}
          {preview.items.length === 0 && (
            <tr>
              <td colSpan={columns.length}>Aucune ligne.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function TableBrowser({
  title,
  subtitle,
  tables,
  loading,
  seedError,
  adapter,
}: {
  title: string;
  subtitle: string;
  tables: LocalTableInfo[];
  loading: boolean;
  seedError: string | null;
  actions?: import("react").ReactNode;
  adapter: (name: string, page: number, q?: string) => Promise<TablePreview>;
}) {
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<TablePreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [rowPage, setRowPage] = useState(1);
  const [rowQuery, setRowQuery] = useState("");
  const { show } = useToast();

  const load = useCallback(
    (name: string, page: number, q?: string) => {
      setSelected(name);
      setRowPage(page);
      setPreviewing(true);
      adapter(name, page, q || undefined)
        .then((payload) => {
          setPreview(payload);
        })
        .catch((err) => show(err instanceof Error ? err.message : "Aperçu impossible.", "error"))
        .finally(() => setPreviewing(false));
    },
    [adapter, show],
  );

  const filtered = tables.filter((table) => table.name.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <Panel
      title={title}
      subtitle={loading ? "Chargement…" : subtitle}
      actions={loading ? <Spinner /> : undefined}
      flush
    >
      {seedError && !loading && (
        <div className="banner banner-warning">
          <Icon name="alert" size={18} /> {seedError}
        </div>
      )}
      <div className="table-toolbar">
        <input
          type="search"
          className="search-input"
          placeholder="Filtrer les tables…"
          value={filter}
          onChange={(event) => {
            setFilter(event.target.value);
            setPreview(null);
            setSelected(null);
          }}
        />
      </div>

      {tables.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Table</th>
                <th className="right">Lignes</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((table) => (
                <tr
                  key={table.name}
                  className={selected === table.name ? "selected-row" : undefined}
                  style={{ cursor: "pointer" }}
                  onClick={() => {
                    setRowQuery("");
                    load(table.name, 1);
                  }}
                >
                  <td>
                    <Icon name="folder" size={14} /> {table.name}
                  </td>
                  <td className="right mono">{(table.rows ?? 0).toLocaleString("fr-FR")}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={2}>Aucune table.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="table-preview">
          <form
            className="search-row compact"
            onSubmit={(event) => {
              event.preventDefault();
              load(selected, 1, rowQuery.trim());
            }}
          >
            <input
              type="search"
              className="search-input"
              placeholder="Rechercher dans toutes les colonnes…"
              value={rowQuery}
              onChange={(event) => setRowQuery(event.target.value)}
            />
            <button className="button" type="submit">
              <Icon name="search" size={14} /> Filtrer
            </button>
          </form>
          {previewing ? (
            <Spinner label="Chargement des lignes…" />
          ) : preview && preview.table === selected ? (
            <>
              <RowTable preview={preview} />
              {preview.items.length > 0 && (
                <Pagination
                  page={preview.page}
                  pageSize={preview.page_size}
                  total={preview.total ?? 0}
                  onPage={(target) => load(selected, target, rowQuery.trim() || undefined)}
                />
              )}
            </>
          ) : null}
        </div>
      )}
    </Panel>
  );
}

function TulipExplorer() {
  const [tables, setTables] = useState<LocalTableInfo[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .tulipTables()
      .then((payload) => {
        if (!cancelled)
          setTables(
            (payload.items as Array<{ name: string; rows: number | null }>).map((item) => ({
              name: item.name,
              rows: item.rows,
              columns: [],
            })),
          );
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Base Tulip indisponible.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const adapter = useCallback(
    (name: string, page: number, q?: string) =>
      api.tulipTableRows(name, page, q).then((payload) => payload as unknown as TablePreview),
    [],
  );

  return (
    <TableBrowser
      title="Base Tulip — SUPERETTE.TFE"
      subtitle={tables ? `${tables.length} tables · lecture seule via Firebird` : ""}
      tables={tables ?? []}
      loading={loading}
      seedError={error}
      adapter={adapter}
    />
  );
}

function LocalExplorer() {
  const [tables, setTables] = useState<LocalTableInfo[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [backingUp, setBackingUp] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    let cancelled = false;
    api
      .dbTables()
      .then((payload) => {
        if (!cancelled) setTables(payload as unknown as LocalTableInfo[]);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Base locale indisponible.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    api
      .dbBackups()
      .then((payload) => setBackups(payload.items ?? []))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const adapter = useCallback(
    (name: string, page: number, q?: string) =>
      api.dbTableRows(name, page, q).then((payload) => payload as unknown as TablePreview),
    [],
  );

  const backup = async () => {
    setBackingUp(true);
    try {
      const payload = await api.dbCreateBackup();
      show(`Sauvegarde créée : ${payload.created}`, "success");
      setBackups((await api.dbBackups()).items ?? []);
    } catch (err) {
      show(err instanceof Error ? err.message : "Sauvegarde impossible.", "error");
    } finally {
      setBackingUp(false);
    }
  };

  return (
    <div>
      <TableBrowser
        title="Base locale de suivi"
        subtitle={tables ? `${tables.length} tables · factures, lignes, audit, exports` : ""}
        tables={tables ?? []}
        loading={loading}
        seedError={error}
        adapter={adapter}
      />
      <div className="backup-strip">
        <button type="button" className="button" onClick={backup} disabled={backingUp}>
          {backingUp ? <Spinner label="Sauvegarde…" /> : <Icon name="save" size={16} />} Sauvegarder la base locale
        </button>
        <ul className="be-preview">
          {backups.map((entry) => (
            <li key={entry.name}>
              <span>{entry.created_at}</span>
              <strong className="mono">
                {entry.name} — {(entry.size / 1024).toFixed(0)} ko
              </strong>
            </li>
          ))}
          {backups.length === 0 && <li className="muted">Aucune sauvegarde pour le moment.</li>}
        </ul>
      </div>
    </div>
  );
}

export function DatabasePage() {
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Bases de données</h1>
          <p className="page-subtitle">
            Vue directe sur la base Tulip (Firebird, lecture seule) et sur la base locale de suivi
            (factures, lignes, exports, audit), avec sauvegarde locale.
          </p>
        </div>
      </div>

      <div className="grid-2">
        <TulipExplorer />
        <LocalExplorer />
      </div>
    </>
  );
}
