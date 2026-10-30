import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { Spinner } from "./Common";
import { Icon } from "./Icon";
import { Modal } from "./Modal";
import { useToast } from "./Toast";

interface BePreviewLine {
  product_code: number | string;
  lot_code?: number;
  puht: number | string;
  qte: number | string;
  remise?: number | string | null;
}

interface BePreview {
  numero: number | string;
  be_code: number | string;
  fournisseur: number | string;
  opdate: string;
  nbc?: string | null;
  lines?: BePreviewLine[];
  issues?: Array<{ message?: string; code?: string }>;
  skipped_lines?: Array<{ designation?: string; reason?: string }>;
}

export function TulipBeModal({
  invoiceId,
  invoiceNumber,
  open,
  onClose,
  onCreated,
}: {
  invoiceId: number;
  invoiceNumber: string;
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [preview, setPreview] = useState<BePreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const { show } = useToast();

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .tulipCreateBe(invoiceId, true)
      .then((payload) => {
        if (!cancelled)         setPreview(payload as unknown as BePreview);
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error instanceof ApiError || error instanceof Error ? error.message : "Aperçu impossible.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, invoiceId]);

  const create = async () => {
    setCreating(true);
    try {
      const result = (await api.tulipCreateBe(invoiceId, false)) as unknown as BePreview;
      show(`BE Tulip n°${result.numero} créé dans la base Tulip.`, "success");
      onCreated();
      onClose();
    } catch (error) {
      show(error instanceof ApiError || error instanceof Error ? error.message : "Création impossible.", "error");
    } finally {
      setCreating(false);
    }
  };

  const skipped = preview?.skipped_lines ?? [];
  const issues = preview?.issues ?? [];

  return (
    <Modal
      open={open}
      title="Créer le bon d'entrée Tulip"
      subtitle={`Facture ${invoiceNumber} — écriture dans la base Firebird Tulip`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="button" onClick={onClose}>
            Annuler
          </button>
          <button
            type="button"
            className="button button-primary"
            disabled={loading || creating || loadError !== null || (preview !== null && skipped.length > 0)}
            onClick={create}
          >
            {creating ? <span className="spinner small light" /> : <Icon name="check" size={16} />} Créer définitivement
          </button>
        </>
      }
    >
      {loading && <Spinner label="Préparation de l'aperçu du BE…" />}
      {!loading && loadError && <p className="text-danger">{loadError}</p>}
      {!loading && preview && (
        <div>
          {issues.length > 0 && (
            <ul className="be-issues">
              {issues.map((issue, index) => (
                <li key={index}>{issue.message ?? issue.code}</li>
              ))}
            </ul>
          )}
          {skipped.length > 0 && (
            <div className="banner banner-warning">
              <Icon name="alert" size={16} />
              <div>
                <strong>{skipped.length} ligne(s) ignorée(s) — produits non rapprochés.</strong>
                <ul>
                  {skipped.map((line, index) => (
                    <li key={index}>{line.designation ?? "—"}</li>
                  ))}
                </ul>
                <p>Créez d'abord le BE pour les lignes rapprochées après correction, ou rapprochez ces produits.</p>
              </div>
            </div>
          )}
          <ul className="be-preview">
            <li>
              <span>N° BE prévu</span>
              <strong className="mono">{preview.numero}</strong>
            </li>
            <li>
              <span>Fournisseur Tulip</span>
              <strong className="mono">{preview.fournisseur}</strong>
            </li>
            {preview.nbc && (
              <li>
                <span>N° bon de commande</span>
                <strong>{preview.nbc}</strong>
              </li>
            )}
            <li>
              <span>Date</span>
              <strong>{preview.opdate}</strong>
            </li>
            <li>
              <span>Lignes</span>
              <strong>{preview.lines?.length ?? 0}</strong>
            </li>
          </ul>
          {preview.lines && preview.lines.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Produit Tulip</th>
                  <th>Qté</th>
                  <th>Prix unitaire HT</th>
                  <th>Remise</th>
                </tr>
              </thead>
              <tbody>
                {preview.lines.map((line, index) => (
                  <tr key={index}>
                    <td className="mono">{line.product_code}</td>
                    <td>{line.qte}</td>
                    <td>{line.puht}</td>
                    <td>{line.remise ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small">
            Les montants (MHT, TVA, TTC), le stock et la dette fournisseur sont calculés automatiquement par Tulip
            après écriture.
          </p>
        </div>
      )}
    </Modal>
  );
}
