import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { ExportRecord, InvoiceDetail } from "../../types";
import { Modal } from "../Modal";
import { CheckList } from "../Common";
import { Icon } from "../Icon";
import { useToast } from "../Toast";

function dedupeChecks(checks: InvoiceDetail["checks"]) {
  const seen = new Set<string>();
  return checks.filter((check) => {
    const key = `${check.code}-${check.line_position ?? ""}-${check.field ?? ""}-${check.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function ValidationModal({
  detail,
  open,
  onClose,
  onValidated,
}: {
  detail: InvoiceDetail;
  open: boolean;
  onClose: () => void;
  onValidated: (detail: InvoiceDetail) => void;
}) {
  const readiness = detail.readiness;
  const [actor, setActor] = useState("utilisateur");
  const [ackDuplicate, setAckDuplicate] = useState(false);
  const [ackTotals, setAckTotals] = useState(false);
  const [ackWarnings, setAckWarnings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<{ code?: string; message?: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    if (!open) return;
    setAckDuplicate(false);
    setAckTotals(false);
    setAckWarnings(false);
    setError(null);
    setIssues([]);
  }, [open]);

  const hard = dedupeChecks(readiness.hard);
  const accounting = dedupeChecks(readiness.accounting_errors);
  const warnings = dedupeChecks(readiness.warnings);
  const blocked = hard.length > 0;
  const needsDuplicate = readiness.requires_acks.duplicate && !ackDuplicate;
  const needsTotals = readiness.requires_acks.totals && !ackTotals && accounting.length > 0;
  const canSubmit = !blocked && !needsDuplicate && !needsTotals && actor.trim().length > 0;

  const submit = async () => {
    setSaving(true);
    setError(null);
    setIssues([]);
    try {
      const result = await api.validateInvoice(detail.id, {
        actor: actor.trim(),
        acknowledge_duplicate: ackDuplicate,
        acknowledge_totals: ackTotals,
        acknowledge_warnings: ackWarnings,
      });
      onValidated(result.invoice);
      show("Facture validée. Elle est désormais verrouillée pour l'export.", "success");
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setIssues(err.issues.map((issue) => ({ code: issue.code, message: issue.message })));
      } else {
        setError(err instanceof Error ? err.message : "Validation impossible.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Valider la facture"
      subtitle={`Facture ${detail.invoice_number ?? `#${detail.id}`} · ${detail.supplier?.name ?? "fournisseur non confirmé"}`}
      onClose={onClose}
      wide
      footer={
        <>
          <button type="button" className="button" onClick={onClose}>
            Annuler
          </button>
          <button type="button" className="button button-primary" disabled={!canSubmit || saving} onClick={submit}>
            {saving ? <span className="spinner small light" /> : <Icon name="check" size={16} />}
            Valider la facture
          </button>
        </>
      }
    >
      {blocked ? (
        <div className="banner banner-danger">
          <Icon name="alert" size={18} />
          <div>
            <strong>Validation bloquée</strong>
            <p>Corrigez les informations obligatoires ci-dessous, puis enregistrez chaque modification.</p>
          </div>
        </div>
      ) : (
        <div className="banner banner-success">
          <Icon name="shield" size={18} />
          <div>
            <strong>Prête à être validée</strong>
            <p>
              La validation verrouille la facture et enregistre votre nom dans l'historique. Les totaux sont recalculés côté
              serveur.
            </p>
          </div>
        </div>
      )}

      {hard.length > 0 && (
        <div className="modal-section">
          <h3>Informations obligatoires manquantes</h3>
          <CheckList checks={hard} />
        </div>
      )}

      {readiness.duplicate && (
        <div className="modal-section">
          <h3>Doublon potentiel</h3>
          <CheckList checks={[readiness.duplicate]} />
          <label className="checkbox ack">
            <input type="checkbox" checked={ackDuplicate} onChange={(event) => setAckDuplicate(event.target.checked)} />
            <span>
              J'ai vérifié le document et je confirme qu'il ne s'agit pas d'un doublon, ou je choisis de le valider malgré
              l'alerte.
            </span>
          </label>
        </div>
      )}

      {accounting.length > 0 && (
        <div className="modal-section">
          <h3>Écarts comptables à examiner</h3>
          <CheckList checks={accounting} />
          <label className="checkbox ack">
            <input type="checkbox" checked={ackTotals} onChange={(event) => setAckTotals(event.target.checked)} />
            <span>J'ai examiné les écarts et je valide les montants tels qu'ils figurent sur la facture.</span>
          </label>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="modal-section">
          <h3>Avertissements</h3>
          <CheckList checks={warnings} />
          <label className="checkbox ack">
            <input type="checkbox" checked={ackWarnings} onChange={(event) => setAckWarnings(event.target.checked)} />
            <span>J'ai pris connaissance des avertissements (optionnel, conservé dans l'audit).</span>
          </label>
        </div>
      )}

      <div className="modal-section">
        <label className="field">
          <span>Validé par</span>
          <input value={actor} maxLength={128} onChange={(event) => setActor(event.target.value)} placeholder="Nom ou identifiant" />
        </label>
        <p className="muted tiny">
          Cette information est conservée dans l'historique d'audit. Aucune correction automatique des écarts n'est effectuée.
        </p>
      </div>

      {error && (
        <div className="inline-error-block">
          <strong>{error}</strong>
          {issues.length > 0 && (
            <ul>
              {issues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}>{issue.message ?? issue.code}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
}

const FORMATS = [
  { id: "csv", label: "CSV", description: "Lignes séparées, lisible par tableur ou script." },
  { id: "xlsx", label: "Excel (XLSX)", description: "Classeur de travail avec en-tête et lignes." },
  { id: "json", label: "JSON", description: "Structure complète pour intégration technique." },
  { id: "rapport", label: "Rapport de contrôle", description: "Synthèse lisible des contrôles et écarts." },
] as const;

export function ExportModal({
  detail,
  open,
  onClose,
  onExported,
}: {
  detail: InvoiceDetail;
  open: boolean;
  onClose: () => void;
  onExported: () => void;
}) {
  const [formats, setFormats] = useState<string[]>(["csv", "xlsx", "json", "rapport"]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [records, setRecords] = useState<ExportRecord[]>([]);
  const { show } = useToast();

  useEffect(() => {
    if (open) {
      setError(null);
      setRecords([]);
    }
  }, [open]);

  const toggle = (format: string) => {
    setFormats((current) => (current.includes(format) ? current.filter((entry) => entry !== format) : [...current, format]));
  };

  const submit = async () => {
    if (formats.length === 0) {
      setError("Sélectionnez au moins un format.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await api.exportInvoice(detail.id, formats);
      setRecords(result.records);
      onExported();
      show("Export généré. Contrôlez le fichier avant tout import dans Tulip.", "success");
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "Export impossible.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Exporter la facture"
      subtitle="Génération locale de fichiers préparatoires. Aucun import direct dans Tulip."
      onClose={onClose}
      wide
      footer={
        <>
          <button type="button" className="button" onClick={onClose}>
            Fermer
          </button>
          <button type="button" className="button button-primary" onClick={submit} disabled={saving || formats.length === 0}>
            {saving ? <span className="spinner small light" /> : <Icon name="download" size={16} />}
            Générer l'export
          </button>
        </>
      }
    >
      <div className="banner banner-warning">
        <Icon name="alert" size={18} />
        <div>
          <strong>Format Tulip non confirmé</strong>
          <p>
            Ces fichiers sont destinés à la vérification et à la préparation du bon d'entrée. Le format d'import réel de
            Tulip Gestion commerciale V3.33 n'a pas été validé sur un environnement autorisé.
          </p>
        </div>
      </div>

      <div className="modal-section">
        <h3>Formats à générer</h3>
        <div className="format-grid">
          {FORMATS.map((format) => (
            <label key={format.id} className={`format-option${formats.includes(format.id) ? " selected" : ""}`}>
              <input
                type="checkbox"
                checked={formats.includes(format.id)}
                onChange={() => toggle(format.id)}
              />
              <span>
                <strong>{format.label}</strong>
                <small>{format.description}</small>
              </span>
            </label>
          ))}
        </div>
      </div>

      {error && <p className="inline-error">{error}</p>}

      {records.length > 0 && (
        <div className="modal-section">
          <h3>Fichiers générés</h3>
          <ul className="export-list">
            {records.map((record) => (
              <li key={record.id}>
                <span className="format-chip">{record.format.toUpperCase()}</span>
                <span className="mono small">{record.sha256.slice(0, 16)}…</span>
                <a className="button button-sm" href={record.download_url}>
                  <Icon name="download" size={14} /> Télécharger
                </a>
              </li>
            ))}
          </ul>
          <p className="muted tiny">Les exports sont également disponibles dans l'historique et sur la fiche de la facture.</p>
        </div>
      )}
    </Modal>
  );
}
