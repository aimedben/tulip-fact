import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AccessInfo, HealthData, SettingsData } from "../types";
import { PageHeader, Panel, Spinner } from "../components/Common";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";
import { formatDateTimeFR } from "../lib/format";

export function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backup, setBackup] = useState<{ filename: string; download_url: string; size: number } | null>(null);
  const [backingUp, setBackingUp] = useState(false);
  const { show } = useToast();

  const load = async () => {
    try {
      const [settingsData, healthData] = await Promise.all([api.settings(), api.health()]);
      setSettings(settingsData);
      setHealth(healthData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de charger la configuration.");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const createBackup = async () => {
    setBackingUp(true);
    try {
      const result = await api.createBackup();
      setBackup(result);
      show("Sauvegarde créée. Téléchargez l'archive et conservez-la hors du poste.", "success");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Sauvegarde impossible.";
      show(message, "error");
    } finally {
      setBackingUp(false);
    }
  };

  if (!settings) {
    return (
      <div className="loading-page">
        {error ? <p className="inline-error">{error}</p> : <Spinner label="Chargement de la configuration…" />}
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Configuration"
        subtitle="État réel du poste : OCR, stockage et connexion Tulip. Aucune capacité n'est simulée."
        actions={
          <button
            type="button"
            className="button"
            onClick={() => {
              void load();
              show("État du système actualisé.", "info");
            }}
          >
            <Icon name="refresh" size={16} /> Actualiser
          </button>
        }
      />

      <div className="settings-grid">
        <Panel
          title="Application & stockage"
          subtitle="Traitement local sur ce poste Windows"
          actions={
            <span className={`status-badge tone-${health?.status === "ok" ? "success" : "danger"}`}>
              {health?.status === "ok" ? "Opérationnel" : "Dégradé"}
            </span>
          }
        >
          <dl className="meta-list">
            <div>
              <dt>Version</dt>
              <dd className="mono">{settings.app.version}</dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>
                {settings.app.demo ? (
                  <span className="status-badge tone-warning">Démonstration</span>
                ) : (
                  <span className="status-badge tone-neutral">Production locale</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Base de données</dt>
              <dd>{settings.app.database}</dd>
            </div>
            <div>
              <dt>Factures enregistrées</dt>
              <dd className="mono">{settings.app.invoice_count}</dd>
            </div>
            <div>
              <dt>Dossier de données</dt>
              <dd className="mono break-all small">{settings.app.data_dir}</dd>
            </div>
            <div>
              <dt>Base accessible</dt>
              <dd>
                <StatusDot ok={Boolean(health?.database)} label={health?.database ? "Oui" : "Non"} />
              </dd>
            </div>
            <div>
              <dt>Stockage inscriptible</dt>
              <dd>
                <StatusDot ok={Boolean(health?.storage)} label={health?.storage ? "Oui" : "Non"} />
              </dd>
            </div>
          </dl>
        </Panel>

        <Panel
          title="OCR local"
          subtitle="Tesseract sur le poste, sans service cloud"
          actions={
            <span className={`status-badge tone-${settings.ocr.tesseract_available ? "success" : "danger"}`}>
              {settings.ocr.tesseract_available ? "Disponible" : "Indisponible"}
            </span>
          }
        >
          <dl className="meta-list">
            <div>
              <dt>Moteur</dt>
              <dd className="mono">{settings.ocr.engine}</dd>
            </div>
            <div>
              <dt>Langues configurées</dt>
              <dd className="mono">{settings.ocr.configured_languages}</dd>
            </div>
            <div>
              <dt>Langues installées</dt>
              <dd className="chips">
                {settings.ocr.languages.length === 0 ? (
                  <span className="muted">Aucune langue détectée</span>
                ) : (
                  settings.ocr.languages.map((language) => (
                    <span key={language} className="chip mono">
                      {language}
                    </span>
                  ))
                )}
              </dd>
            </div>
            <div>
              <dt>Mode de segmentation</dt>
              <dd className="mono">PSM {settings.ocr.psm}</dd>
            </div>
            <div>
              <dt>Rendu PDF</dt>
              <dd className="mono">{settings.ocr.render_dpi} dpi</dd>
            </div>
          </dl>
          <div className="note-box">
            <Icon name="alert" size={16} />
            <p>{settings.ocr.note}</p>
          </div>
        </Panel>

        <FirebirdPanel />

        <Panel title="Contrôle comptable" subtitle="Tolérances et devise par défaut">
          <dl className="meta-list">
            <div>
              <dt>Tolérance de montant</dt>
              <dd className="mono">{settings.accounting.amount_tolerance.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Devise par défaut</dt>
              <dd className="mono">{settings.accounting.currency_default}</dd>
            </div>
          </dl>
          <p className="muted small">
            Les contrôles comparent les totaux extraits aux recalculs indépendants. Un écart est signalé, jamais corrigé
            automatiquement.
          </p>
        </Panel>
      </div>

      <AccessPanel />

      <Panel title="Sauvegarde locale" subtitle="Archive ZIP de la base SQLite, des documents, pages et exports.">
        <div className="backup-row">
          <div>
            <p className="muted small">
              La sauvegarde est créée sur le poste dans le dossier de données. Conservez une copie hors du disque de travail.
              La restauration est manuelle et documentée dans le manifeste de l'archive.
            </p>
            {backup && (
              <div className="backup-result">
                <span className="status-badge tone-success">Sauvegarde créée</span>
                <span className="mono small">{backup.filename}</span>
                <span className="muted small">{(backup.size / (1024 * 1024)).toFixed(2)} Mo</span>
                <a className="button button-sm button-primary" href={backup.download_url}>
                  <Icon name="download" size={15} /> Télécharger
                </a>
              </div>
            )}
            <p className="muted tiny">Dernière actualisation de la configuration : {formatDateTimeFR(new Date().toISOString())}</p>
          </div>
          <button type="button" className="button button-primary" onClick={createBackup} disabled={backingUp}>
            {backingUp ? <span className="spinner small light" /> : <Icon name="database" size={16} />}
            Créer une sauvegarde
          </button>
        </div>
      </Panel>
    </>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-status tone-${ok ? "success" : "danger"}`}>
      <span className="dot" /> {label}
    </span>
  );
}

type AccessData = AccessInfo;

function AccessPanel() {
  const [data, setData] = useState<AccessData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { show } = useToast();

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.accessInfo());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de lire les adresses réseau.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const url = data?.primary_url ?? "";
  const qrSrc = url ? `/api/access/qr.svg?url=${encodeURIComponent(url)}&scale=7` : "";

  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      show("Lien copié dans le presse-papiers.", "success");
    } catch {
      window.prompt("Copiez ce lien :", url);
    }
  };

  return (
    <Panel
      title="Accès depuis le téléphone"
      subtitle="Scannez le QR code avec l'appareil photo du téléphone"
      actions={
        <button type="button" className="button button-sm" onClick={() => void load()} disabled={loading}>
          <Icon name="refresh" size={15} /> Actualiser
        </button>
      }
    >
      {loading && !data ? (
        <Spinner label="Recherche de l'adresse réseau…" />
      ) : error ? (
        <p className="inline-error">{error}</p>
      ) : (
        <div className="access-layout">
          {url ? (
            <div className="qr-frame">
              <img src={qrSrc} alt={`QR code vers ${url}`} width={196} height={196} />
            </div>
          ) : (
            <div className="qr-frame qr-empty">
              <Icon name="alert" size={24} />
              <span className="small muted">Aucune adresse réseau détectée</span>
            </div>
          )}
          <div className="stack">
            <div>
              <p className="muted tiny">Adresse à ouvrir sur le téléphone</p>
              <p className="access-url mono">{url || "—"}</p>
            </div>
            <div className="access-actions">
              <button type="button" className="button button-sm button-primary" onClick={() => void copy()} disabled={!url}>
                <Icon name="link" size={15} /> Copier le lien
              </button>
              {url && (
                <a className="button button-sm" href={url} target="_blank" rel="noreferrer">
                  <Icon name="external" size={15} /> Ouvrir
                </a>
              )}
            </div>
            {data && data.candidates.length > 1 && (
              <div>
                <p className="muted tiny">Autres adresses détectées</p>
                <ul className="access-list mono small">
                  {data.candidates
                    .filter((item) => item.url !== url)
                    .map((item) => (
                      <li key={item.ip}>
                        {item.url} {item.reachable ? "" : "(non joignable)"}
                      </li>
                    ))}
                </ul>
              </div>
            )}
            <div className="note-box">
              <Icon name="link" size={16} />
              <p>{data?.hint}</p>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

function FirebirdPanel() {
  const [config, setConfig] = useState<{
    enabled: boolean;
    database: string;
    host: string;
    port: number;
    user: string;
    isql_path: string;
    fb_home: string;
    charset: string;
    write_enabled: boolean;
  } | null>(null);
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const { show } = useToast();

  const loadConfig = async () => {
    setLoading(true);
    try {
      const data = await api.getFirebirdSettings();
      setConfig(data);
    } catch (err) {
      show(err instanceof Error ? err.message : "Impossible de charger la configuration Firebird.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadConfig();
  }, []);

  const save = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const result = await api.updateFirebirdSettings({
        enabled: config.enabled,
        database: config.database || undefined,
        host: config.host,
        port: config.port,
        user: config.user,
        password: password.trim() || undefined,
        charset: config.charset,
        write_enabled: config.write_enabled,
      });
      setPassword("");
      await loadConfig();
      show(result.message, "success");
    } catch (err) {
      show(err instanceof Error ? err.message : "Enregistrement impossible.", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !config) {
    return (
      <Panel title="Base de données Firebird Tulip" subtitle="Configuration de la connexion à Tulip">
        <Spinner label="Chargement de la configuration Firebird…" />
      </Panel>
    );
  }

  return (
    <Panel
      title="Base Tulip"
      subtitle="Connexion automatique à la base de données de Tulip."
      actions={
        <span className={`status-badge tone-${config.enabled && config.database ? "success" : "neutral"}`}>
          {config.enabled && config.database ? "Connectée" : "Non connectée"}
        </span>
      }
    >
      <form
        className="llm-form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <label className="field">
          <span>Base de données Tulip utilisée</span>
          <input type="text" value={config.database} readOnly className="mono" />
          <small className="muted">Détectée automatiquement sur cet ordinateur.</small>
        </label>

        <div className="note-box">
          <Icon name="check" size={16} />
          <p>
            Les fournisseurs et les articles sont enregistrés directement dans cette base.
            Aucun réglage n'est nécessaire.
          </p>
        </div>

        <div className="llm-actions-row" style={{ justifyContent: "flex-end" }}>
          <button
            type="button"
            className="button"
            onClick={async () => {
              try {
                const status = await api.tulipLiveStatus();
                show(
                  status.connected
                    ? `Tulip répond (version ${status.engine_version ?? "inconnue"}).`
                    : status.error ?? "Tulip ne répond pas.",
                  status.connected ? "success" : "error",
                );
              } catch (err) {
                show(err instanceof Error ? err.message : "Tulip ne répond pas.", "error");
              }
            }}
          >
            <Icon name="refresh" size={16} /> Vérifier la connexion
          </button>
          <button type="submit" className="button button-primary" disabled={saving}>
            {saving ? <span className="spinner small light" /> : <Icon name="save" size={16} />}
            Enregistrer
          </button>
        </div>
      </form>
    </Panel>
  );
}
