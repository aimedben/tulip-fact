import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { HealthData, SettingsData, TulipStatus } from "../types";
import { PageHeader, Panel, Spinner } from "../components/Common";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";
import { formatDateTimeFR } from "../lib/format";

export function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [probe, setProbe] = useState<TulipStatus["probe"] | null>(null);
  const [probing, setProbing] = useState(false);
  const [backup, setBackup] = useState<{ filename: string; download_url: string; size: number } | null>(null);
  const [backingUp, setBackingUp] = useState(false);
  const [llmKey, setLlmKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmEnabled, setLlmEnabled] = useState(true);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmTesting, setLlmTesting] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<{ ok: boolean; detail: string } | null>(null);
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

  useEffect(() => {
    if (settings) {
      setLlmBaseUrl(settings.llm.base_url ?? "");
      setLlmModel(settings.llm.model ?? "");
      setLlmEnabled(true);
    }
  }, [settings]);

  const LLM_PRESETS: Record<string, { base_url: string; model: string }> = {
    groq: { base_url: "https://api.groq.com/openai/v1", model: "openai/gpt-oss-120b" },
    openai: { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
    openrouter: { base_url: "https://openrouter.ai/api/v1", model: "google/gemini-2.0-flash-001" },
    mistral: { base_url: "https://api.mistral.ai/v1", model: "mistral-small-latest" },
  };

  const applyPreset = (name: string) => {
    const preset = LLM_PRESETS[name];
    setLlmBaseUrl(preset.base_url);
    setLlmModel(preset.model);
    show(
      name === "groq"
        ? "Groq pré-rempli : colle ta clé gsk_… puis Enregistrer."
        : `Préréglage ${name} appliqué : colle ta clé API puis Enregistrer.`,
      "info",
    );
  };

  const saveLlm = async () => {
    setLlmSaving(true);
    try {
      const result = await api.updateLlmSettings({
        enabled: llmEnabled,
        api_key: llmKey.trim() ? llmKey.trim() : undefined,
        base_url: llmBaseUrl,
        model: llmModel,
      });
      setLlmKey("");
      await load();
      show(result.message, "success");
    } catch (err) {
      show(err instanceof Error ? err.message : "Enregistrement impossible.", "error");
    } finally {
      setLlmSaving(false);
    }
  };

  const testLlm = async () => {
    setLlmTesting(true);
    setLlmTestResult(null);
    try {
      const result = await api.testLlmSettings();
      setLlmTestResult({ ok: true, detail: `${result.model} — réponse : ${result.answer}` });
    } catch (err) {
      const detail =
        err instanceof ApiError ? `${err.status ?? ""} ${err.message}` : err instanceof Error ? err.message : "Erreur inconnue.";
      setLlmTestResult({ ok: false, detail });
    } finally {
      setLlmTesting(false);
    }
  };

  const runProbe = async () => {
    setProbing(true);
    try {
      const result = await api.tulipProbe();
      setProbe(result.probe ?? { performed: false, reason: result.message ?? "Aucun résultat renvoyé." });
      show("Test d'intégration exécuté. Aucune connexion Tulip n'est revendiquée.", "info");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Test impossible.";
      show(message, "error");
    } finally {
      setProbing(false);
    }
  };

  const createBackup = async () => {
    setBackingUp(true);
    try {
      const result = await api.createBackup();
      setBackup(result);
      show("Sauvegarde créée. Téléchargez l'archive et conservez-la hors du poste.", "success");
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Sauvegarde impossible.";
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
        subtitle="État réel du poste : OCR, stockage, LLM et intégration Tulip. Aucune capacité n'est simulée."
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

        <VisionPanel settings={settings} />

        <FirebirdPanel />

        <Panel title="Intelligence artificielle texte (complément)" subtitle="Clé API et fournisseur modifiables">
          <form
            className="llm-form"
            onSubmit={(event) => {
              event.preventDefault();
              void saveLlm();
            }}
          >
            <div className="llm-presets">
              <span className="muted small">Fournisseurs rapides :</span>
              <button type="button" className="button button-sm" onClick={() => applyPreset("groq")}>
                Groq (gratuit)
              </button>
              <button type="button" className="button button-sm" onClick={() => applyPreset("openai")}>
                OpenAI
              </button>
              <button type="button" className="button button-sm" onClick={() => applyPreset("openrouter")}>
                OpenRouter
              </button>
              <button type="button" className="button button-sm" onClick={() => applyPreset("mistral")}>
                Mistral
              </button>
            </div>
            <label className="field">
              <span>Clé API</span>
              <input
                type="password"
                value={llmKey}
                onChange={(e) => setLlmKey(e.target.value)}
                placeholder={settings.llm.configured ? "•••• (clé enregistrée, remplir pour remplacer)" : "gsk_… ou sk-…"}
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>URL du service (compatible OpenAI)</span>
              <input
                type="text"
                value={llmBaseUrl}
                onChange={(e) => setLlmBaseUrl(e.target.value)}
                placeholder="https://api.groq.com/openai/v1"
              />
            </label>
            <label className="field">
              <span>Modèle</span>
              <input
                type="text"
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                placeholder="openai/gpt-oss-120b"
              />
            </label>
            <div className="llm-actions-row">
              <label className="checkbox-row">
                <input type="checkbox" checked={llmEnabled} onChange={(e) => setLlmEnabled(e.target.checked)} />
                Utiliser l'IA pour l'analyse des factures
              </label>
              <button type="button" className="button" onClick={() => void testLlm()} disabled={llmTesting}>
                {llmTesting ? <span className="spinner small" /> : <Icon name="shield" size={15} />}
                Tester la connexion
              </button>
              <button type="submit" className="button button-primary" disabled={llmSaving}>
                {llmSaving ? <span className="spinner small light" /> : <Icon name="check" size={15} />}
                Enregistrer
              </button>
            </div>
            {llmTestResult && (
              <div className="probe-result">
                <span className={`status-badge tone-${llmTestResult.ok ? "success" : "danger"}`}>
                  {llmTestResult.ok ? "Connexion IA OK" : "Échec test IA"}
                </span>
                <p className="small">{llmTestResult.detail}</p>
              </div>
            )}
            <dl className="meta-list">
              <div>
                <dt>Modèle actif</dt>
                <dd className="mono">{settings.llm.model ?? "—"}</dd>
              </div>
              <div>
                <dt>Service actif</dt>
                <dd className="mono break-all small">{settings.llm.base_url ?? "—"}</dd>
              </div>
              <div>
                <dt>Données transmises</dt>
                <dd className="small">{settings.llm.data_transmitted}</dd>
              </div>
            </dl>
            <div className="note-box">
              <Icon name="shield" size={16} />
              <p>{settings.llm.note}</p>
            </div>
          </form>
        </Panel>

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

      <Panel
        title="Intégration Tulip Gestion commerciale V3.33"
        subtitle="État vérifiable de l'intégration, sans déclaration de connexion non testée"
        className="tulip-panel"
        actions={
          <span className="status-badge tone-danger">
            <Icon name="link" size={13} /> Non connecté
          </span>
        }
      >
        <div className="tulip-grid">
          <div>
            <div className="banner banner-warning">
              <Icon name="alert" size={18} />
              <div>
                <strong>{settings.tulip.message}</strong>
                <p>
                  Plateforme cible : {settings.tulip.platform ?? "Windows / Tulip"} · mode {settings.tulip.mode}. Aucune
                  écriture directe, aucun import API ni automatisation d'interface n'est activé.
                </p>
              </div>
            </div>

            <h3>Canaux d'intégration</h3>
            <table className="totals-table methods-table">
              <thead>
                <tr>
                  <th>Méthode</th>
                  <th>Support</th>
                  <th>Raison / état</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(settings.tulip.methods ?? {}).map(([method, info]) => (
                  <tr key={method}>
                    <td className="mono small">{method}</td>
                    <td>
                      <span className={`status-badge tone-${info.supported ? "success" : "neutral"}`}>
                        {info.supported ? "Actif" : "Non activé"}
                      </span>
                    </td>
                    <td className="small">{info.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="probe-box">
              <div>
                <strong>Test de présence de l'interface Tulip</strong>
                <p className="muted small">
                  Le test est en lecture seule et ne saisit aucune donnée. L'absence de fenêtre ne prouve pas l'absence de
                  Tulip.
                </p>
              </div>
              <button type="button" className="button button-sm" onClick={runProbe} disabled={probing}>
                {probing ? <span className="spinner small" /> : <Icon name="eye" size={15} />} Tester la présence
              </button>
            </div>
            {probe && (
              <div className="probe-result">
                <span className={`status-badge tone-${probe.performed ? "info" : "neutral"}`}>
                  {probe.performed ? "Test exécuté" : "Test non exécuté"}
                </span>
                <p className="small">{probe.reason ?? probe.note ?? "Aucune fenêtre Tulip détectée lors du test."}</p>
              </div>
            )}

            <h3>Informations manquantes pour une intégration réelle</h3>
            <ul className="missing-list">
              {settings.tulip.missing_information.map((item) => (
                <li key={item}>
                  <Icon name="alert" size={14} /> {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="stack">
            <div className="note-box">
              <Icon name="download" size={16} />
              <p>{settings.tulip.exports.note}</p>
            </div>
            <div className="safety-card">
              <h3>
                <Icon name="shield" size={16} /> Principe de sécurité
              </h3>
              <ul>
                <li>Aucune donnée n'est écrite dans Tulip depuis cette application.</li>
                <li>Les exports sont des fichiers locaux à contrôler manuellement.</li>
                <li>Le statut « connecté » restera faux tant qu'aucun test autorisé n'a réussi.</li>
                <li>Les factures validées ne peuvent plus être supprimées.</li>
              </ul>
            </div>
          </div>
        </div>
      </Panel>

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

type AccessData = {
  port: number;
  primary_url: string | null;
  primary_ip: string | null;
  candidates: { ip: string; url: string; reachable: boolean }[];
  local_url: string;
  hint: string;
};

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

const VISION_PROVIDER_LABELS: Record<string, string> = {
  gemini: "Google Gemini (gratuit)",
  openai: "OpenAI GPT-4o-mini / GPT-4o",
  groq: "Groq (texte/compatible)",
};

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
        isql_path: config.isql_path || undefined,
        fb_home: config.fb_home || undefined,
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

  const selectDatabase = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".tfe,.fdb,.gdb";
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file && config) {
        // @ts-expect-error webkitRelativePath existe sur les fichiers
        const path = file.path || file.webkitRelativePath || "";
        if (path) {
          setConfig({ ...config, database: path });
        } else {
          show("Impossible de récupérer le chemin du fichier. Collez le chemin manuellement.", "warning");
        }
      }
    };
    input.click();
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
      title="Base de données Firebird Tulip"
      subtitle="Sélectionnez la base de données Tulip (.TFE)"
      actions={
        <span className={`status-badge tone-${config.enabled && config.database ? "success" : "neutral"}`}>
          {config.enabled && config.database ? "Activé" : "Désactivé"}
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
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={config.enabled}
            onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
          />
          Activer la connexion Firebird
        </label>

        <label className="field">
          <span>Chemin de la base de données Tulip (.TFE)</span>
          <div style={{ display: "flex", gap: "8px" }}>
            <input
              type="text"
              value={config.database}
              onChange={(e) => setConfig({ ...config, database: e.target.value })}
              placeholder="E:\zjob\tulip\SUPERETTE.TFE"
              style={{ flex: 1 }}
            />
            <button type="button" className="button" onClick={selectDatabase}>
              <Icon name="folder" size={15} /> Parcourir
            </button>
          </div>
        </label>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <label className="field">
            <span>Hôte</span>
            <input
              type="text"
              value={config.host}
              onChange={(e) => setConfig({ ...config, host: e.target.value })}
              placeholder="localhost"
            />
          </label>
          <label className="field">
            <span>Port</span>
            <input
              type="number"
              value={config.port}
              onChange={(e) => setConfig({ ...config, port: parseInt(e.target.value, 10) || 3050 })}
              placeholder="3050"
            />
          </label>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <label className="field">
            <span>Utilisateur</span>
            <input
              type="text"
              value={config.user}
              onChange={(e) => setConfig({ ...config, user: e.target.value })}
              placeholder="SYSDBA"
            />
          </label>
          <label className="field">
            <span>Mot de passe</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Mot de passe Firebird"
              autoComplete="off"
            />
          </label>
        </div>

        <label className="field">
          <span>Chemin isql.exe (client Firebird 32 bits)</span>
          <input
            type="text"
            value={config.isql_path}
            onChange={(e) => setConfig({ ...config, isql_path: e.target.value })}
            placeholder="E:\zjob\firebird_2_5\bin\isql.exe"
          />
        </label>

        <label className="field">
          <span>Dossier Firebird Home</span>
          <input
            type="text"
            value={config.fb_home}
            onChange={(e) => setConfig({ ...config, fb_home: e.target.value })}
            placeholder="E:\zjob\firebird_2_5"
          />
        </label>

        <label className="field">
          <span>Charset</span>
          <input
            type="text"
            value={config.charset}
            onChange={(e) => setConfig({ ...config, charset: e.target.value })}
            placeholder="WIN1252"
          />
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={config.write_enabled}
            onChange={(e) => setConfig({ ...config, write_enabled: e.target.checked })}
          />
          Autoriser l'écriture dans la base (DANGER : à utiliser uniquement sur une copie de test)
        </label>

        <div className="llm-actions-row" style={{ justifyContent: "flex-end" }}>
          <button type="submit" className="button button-primary" disabled={saving}>
            {saving ? <span className="spinner small light" /> : <Icon name="check" size={15} />}
            Enregistrer la configuration
          </button>
        </div>

        <div className="note-box">
          <Icon name="alert" size={16} />
          <p>
            La base de données Tulip doit être accessible. L'écriture directe n'est pas validée en production.
            Utilisez toujours une copie de test pour valider la configuration avant de pointer vers la base réelle.
          </p>
        </div>
      </form>
    </Panel>
  );
}

function VisionPanel({ settings }: { settings: SettingsData }) {
  const vision = settings.vision;
  const [enabled, setEnabled] = useState(vision?.enabled ?? false);
  const [provider, setProvider] = useState(vision?.provider ?? "gemini");
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const { show } = useToast();

  useEffect(() => {
    if (!vision) return;
    setProvider(vision.provider);
    setEnabled(vision.enabled);
    const initialModels: Record<string, string> = {};
    Object.entries(vision.providers ?? {}).forEach(([name, info]) => {
      initialModels[name] = info.model ?? "";
    });
    setModels(initialModels);
  }, [vision]);

  const save = async (nextProvider?: string) => {
    setSaving(true);
    try {
      const target = nextProvider ?? provider;
      const result = await api.updateVisionSettings({
        enabled,
        provider: target,
        api_key: apiKeys[target]?.trim() ? apiKeys[target].trim() : undefined,
        model: models[target]?.trim() ? models[target].trim() : undefined,
      });
      setApiKeys((previous) => ({ ...previous, [target]: "" }));
      show(result.message, "success");
    } catch (err) {
      show(err instanceof Error ? err.message : "Enregistrement impossible.", "error");
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testVisionSettings();
      setTestResult({ ok: true, detail: `${result.model} — réponse : ${result.answer}` });
    } catch (err) {
      const detail =
        err instanceof ApiError ? `${err.status ?? ""} ${err.message}` : err instanceof Error ? err.message : "Erreur inconnue.";
      setTestResult({ ok: false, detail });
    } finally {
      setTesting(false);
    }
  };

  if (!vision) {
    return (
      <Panel title="IA vision (lecture des images)" subtitle="Mise à jour nécessaire du backend">
        <p className="muted small">Backend trop ancien : relance le serveur pour activer la lecture vision.</p>
      </Panel>
    );
  }

  return (
    <Panel
      title="IA vision — lecture directe des factures (images)"
      subtitle="Le moyen le plus fiable : l'IA lit la photo/scann comme un humain"
      actions={
        <span className={`status-badge tone-${enabled && vision.active_model ? "success" : "neutral"}`}>
          {enabled && vision.active_model ? "Active" : "Inactive"}
        </span>
      }
    >
      <div className="vision-grid">
        {Object.entries(vision.providers ?? {}).map(([name, info]) => (
          <div key={name} className={`vision-provider-card ${name === provider ? "active" : ""}`}>
            <div className="vision-provider-head">
              <input
                type="radio"
                name="vision-provider"
                checked={name === provider}
                onChange={() => {
                  setProvider(name);
                  void save(name);
                }}
                disabled={saving}
              />
              <strong>{VISION_PROVIDER_LABELS[name] ?? name}</strong>
              <span className={`status-badge tone-${info.configured ? "success" : "neutral"}`}>
                {info.configured ? "Clé enregistrée" : "Pas de clé"}
              </span>
              {name === vision.provider && vision.active_model && (
                <span className="status-badge tone-info">Actif : {vision.active_model}</span>
              )}
            </div>
            <div className="vision-provider-body">
              <label className="field">
                <span>Clé API</span>
                <input
                  type="password"
                  value={apiKeys[name] ?? ""}
                  onChange={(e) => setApiKeys((previous) => ({ ...previous, [name]: e.target.value }))}
                  placeholder={info.configured ? "•••• (clé enregistrée, remplir pour remplacer)" : "colle ta clé ici"}
                  autoComplete="off"
                />
              </label>
              <label className="field">
                <span>Modèle</span>
                <input
                  type="text"
                  value={models[name] ?? ""}
                  onChange={(e) => setModels((previous) => ({ ...previous, [name]: e.target.value }))}
                  placeholder="ex. gemini-3.8-flash"
                />
              </label>
              <div className="llm-actions-row">
                <button type="button" className="button" onClick={() => void save()} disabled={saving}>
                  {saving ? <span className="spinner small" /> : "Enregistrer"}
                </button>
                {name === provider && (
                  <button type="button" className="button button-primary" onClick={() => void test()} disabled={testing}>
                    {testing ? <span className="spinner small" /> : "Tester la connexion"}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {testResult && (
        <div className="probe-result">
          <span className={`status-badge tone-${testResult.ok ? "success" : "danger"}`}>
            {testResult.ok ? "Connexion eyes OK" : "Échec test vison"}
          </span>
          <p className="small">{testResult.detail}</p>
        </div>
      )}
      <label className="checkbox-row">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Utiliser la lecture vision des images lors du traitement
      </label>
      <div className="note-box" style={{ marginTop: 10 }}>
        <Icon name="shield" size={16} />
        <p>{vision.note}</p>
      </div>
    </Panel>
  );
}
