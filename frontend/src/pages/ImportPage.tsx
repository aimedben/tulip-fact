import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, uploadInvoice } from "../lib/api";
import { formatFileSize, isProcessing } from "../lib/format";
import type { InvoiceDetail, InvoiceSummary } from "../types";
import { EmptyState, PageHeader, Panel, ProgressBar } from "../components/Common";
import { StatusBadge } from "../components/StatusBadge";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";

type QueueStatus = "pending" | "uploading" | "processing" | "done" | "error";

interface QueueItem {
  localId: string;
  file: File;
  status: QueueStatus;
  progress: number;
  stage: string;
  invoice: InvoiceSummary | null;
  detail: InvoiceDetail | null;
  error: string | null;
  rotation: number;
}

const ACCEPTED = [".pdf", ".jpg", ".jpeg", ".png"];
const MAX_SIZE = 25 * 1024 * 1024;

function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

export function ImportPage() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [recent, setRecent] = useState<InvoiceSummary[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const mountedRef = useRef(true);
  const { show } = useToast();

  useEffect(() => {
    mountedRef.current = true;
    api
      .listInvoices({ page: 1, page_size: 6 })
      .then((result) => mountedRef.current && setRecent(result.items))
      .catch(() => undefined);
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const updateItem = (localId: string, patch: Partial<QueueItem>) => {
    setItems((current) => current.map((entry) => (entry.localId === localId ? { ...entry, ...patch } : entry)));
  };

  const addFiles = (files: FileList | File[]) => {
    const accepted: QueueItem[] = [];
    for (const file of Array.from(files)) {
      const extension = fileExtension(file.name);
      if (!ACCEPTED.includes(extension)) {
        show(`${file.name} : format non pris en charge (PDF, JPG ou PNG uniquement).`, "error");
        continue;
      }
      if (file.size === 0) {
        show(`${file.name} : le fichier est vide.`, "error");
        continue;
      }
      if (file.size > MAX_SIZE) {
        show(`${file.name} : fichier trop volumineux (limite 25 Mo).`, "error");
        continue;
      }
      accepted.push({
        localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        file,
        status: "pending",
        progress: 0,
        stage: "en attente",
        invoice: null,
        detail: null,
        error: null,
        rotation: 0,
      });
    }
    if (accepted.length > 0) {
      setItems((current) => [...current, ...accepted]);
      show(
        `${accepted.length} fichier${accepted.length > 1 ? "s" : ""} ajouté${accepted.length > 1 ? "s" : ""} à la file.`,
        "success",
      );
    }
  };

  useEffect(() => {
    if (busyRef.current) return;
    const next = items.find((item) => item.status === "pending");
    if (!next) return;

    const process = async () => {
      busyRef.current = true;
      updateItem(next.localId, { status: "uploading", progress: 2, stage: "envoi du fichier" });
      try {
        const summary = await uploadInvoice(next.file, (value) => {
          updateItem(next.localId, { progress: Math.max(2, Math.round(value * 0.4)), stage: `envoi ${value} %` });
        });
        updateItem(next.localId, {
          status: "processing",
          progress: Math.max(42, summary.progress),
          stage: summary.stage || "traitement",
          invoice: summary,
        });

        let detail: InvoiceDetail | null = null;
        for (let attempt = 0; attempt < 240; attempt += 1) {
          detail = await api.invoice(summary.id);
          if (!mountedRef.current) return;
          updateItem(next.localId, {
            invoice: detail,
            detail,
            progress: Math.max(42, detail.progress),
            stage: detail.stage,
          });
          if (!isProcessing(detail.status)) break;
          await new Promise((resolve) => window.setTimeout(resolve, 1500));
        }

        if (!detail) throw new Error("Le traitement n'a pas renvoyé de résultat.");
        if (detail.status === "ECHEC") {
          updateItem(next.localId, {
            status: "error",
            progress: 100,
            stage: "échec du traitement",
            error: detail.error_message ?? "Le traitement a échoué.",
            detail,
          });
        } else {
          updateItem(next.localId, {
            status: "done",
            progress: 100,
            stage: "traitement terminé",
            detail,
          });
          show(`${next.file.name} : extraction terminée, vérification requise.`, "success");
        }
        api.listInvoices({ page: 1, page_size: 6 }).then((result) => {
          if (mountedRef.current) setRecent(result.items);
        }).catch(() => undefined);
      } catch (error) {
        const message =
          error instanceof ApiError || error instanceof Error ? error.message : "Erreur inconnue pendant l'import.";
        if (mountedRef.current) {
          updateItem(next.localId, { status: "error", progress: 100, stage: "échec", error: message });
          show(message, "error");
        }
      } finally {
        busyRef.current = false;
        if (mountedRef.current) setItems((current) => [...current]);
      }
    };

    void process();
  }, [items, show]);

  const retry = (item: QueueItem) => {
    updateItem(item.localId, {
      status: "pending",
      progress: 0,
      stage: "en attente",
      error: null,
      detail: null,
      invoice: null,
    });
  };

  const remove = (localId: string) => {
    setItems((current) => current.filter((entry) => entry.localId !== localId));
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files?.length) addFiles(event.dataTransfer.files);
  };

  const activeCount = items.filter((item) => item.status === "pending" || item.status === "uploading" || item.status === "processing").length;

  return (
    <>
      <PageHeader
        title="Importer des factures"
        subtitle="Déposez des PDF ou des photos. Le traitement reste local et les fichiers sont traités dans l'ordre de la file."
        actions={
          activeCount > 0 ? (
            <span className="pill">
              <span className="spinner small" /> {activeCount} en cours
            </span>
          ) : undefined
        }
      />

      <div className="import-layout">
        <div className="stack">
          <div
            className={`dropzone${dragging ? " dragging" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
            }}
          >
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              capture="environment"
              className="visually-hidden"
              onChange={(event) => {
                if (event.target.files) addFiles(event.target.files);
                event.target.value = "";
              }}
            />
            <div className="dropzone-icon">
              <Icon name="upload" size={30} />
            </div>
            <h2>Glissez vos factures ici</h2>
            <p className="muted">ou cliquez pour parcourir vos fichiers</p>
            <div className="dropzone-meta">
              <span>PDF</span>
              <span>JPG</span>
              <span>PNG</span>
              <span>25 Mo max.</span>
            </div>
          </div>

          <Panel
            title={items.length > 0 ? `File d'import (${items.length})` : "File d'import"}
            subtitle="Chaque document est lu automatiquement sur cet ordinateur."
            actions={
              items.some((item) => item.status === "done" || item.status === "error") ? (
                <button
                  type="button"
                  className="button button-sm"
                  onClick={() => setItems((current) => current.filter((item) => item.status !== "done" && item.status !== "error"))}
                >
                  Retirer les terminés
                </button>
              ) : undefined
            }
            flush
          >
            {items.length === 0 ? (
              <EmptyState
                icon="invoice"
                title="Aucun fichier sélectionné"
                description="Les documents ajoutés apparaîtront ici avec leur progression et un aperçu de la première page."
              />
            ) : (
              <ul className="import-queue">
                {items.map((item) => {
                  const done = item.status === "done";
                  const failed = item.status === "error";
                  const imageUrl = item.detail?.pages?.[0]?.image_url;
                  return (
                    <li key={item.localId} className={`queue-item${failed ? " failed" : ""}`}>
                      <div className="queue-thumb">
                        {imageUrl ? (
                          <img
                            src={imageUrl}
                            alt={`Aperçu de ${item.file.name}`}
                            style={{ transform: `rotate(${item.rotation}deg)` }}
                          />
                        ) : (
                          <span className="queue-file-icon">
                            <Icon name={fileExtension(item.file.name) === ".pdf" ? "invoice" : "eye"} size={20} />
                          </span>
                        )}
                        {imageUrl && (
                          <button
                            type="button"
                            className="thumb-rotate"
                            title="Faire pivoter l'aperçu"
                            onClick={() => updateItem(item.localId, { rotation: (item.rotation + 90) % 360 })}
                          >
                            <Icon name="rotate" size={13} />
                          </button>
                        )}
                      </div>

                      <div className="queue-main">
                        <div className="queue-title">
                          <strong title={item.file.name}>{item.file.name}</strong>
                          <span className="muted small">{formatFileSize(item.file.size)}</span>
                          {item.invoice && <StatusBadge status={item.invoice.status} compact />}
                        </div>
                        <div className="queue-progress">
                          <ProgressBar
                            value={item.progress}
                            tone={failed ? "danger" : done ? "success" : "accent"}
                          />
                          <span className="small muted">
                            {failed ? item.error : `${item.stage}${item.status !== "done" ? ` · ${item.progress} %` : ""}`}
                          </span>
                        </div>
                        {failed && item.detail?.error_message && (
                          <p className="inline-error small">{item.detail.error_message}</p>
                        )}
                      </div>

                      <div className="queue-actions">
                        {done && item.invoice && (
                          <Link to={`/invoices/${item.invoice.id}`} className="button button-sm button-primary">
                            Vérifier <Icon name="chevronRight" size={14} />
                          </Link>
                        )}
                        {failed && item.invoice && (
                          <Link to={`/invoices/${item.invoice.id}`} className="button button-sm">
                            Ouvrir
                          </Link>
                        )}
                        {(failed || done) && (
                          <button type="button" className="icon-button" title="Retirer de la file" onClick={() => remove(item.localId)}>
                            <Icon name="close" size={16} />
                          </button>
                        )}
                        {failed && (
                          <button type="button" className="icon-button" title="Réessayer" onClick={() => retry(item)}>
                            <Icon name="refresh" size={16} />
                          </button>
                        )}
                        {(item.status === "pending" || item.status === "uploading" || item.status === "processing") && (
                          <span className="queue-wait">
                            {item.status === "pending" ? "En attente" : <span className="spinner small" />}
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </div>

        <div className="stack">
          <Panel title="Conseils pour un OCR fiable">
            <ul className="tip-list">
              <li>
                <Icon name="check" size={15} />
                <span>Scannez à 300 dpi, page entière et bien à plat.</span>
              </li>
              <li>
                <Icon name="check" size={15} />
                <span>Évitez les ombres, les reflets et les pages coupées.</span>
              </li>
              <li>
                <Icon name="check" size={15} />
                <span>Une facture par fichier, dans le bon sens de lecture.</span>
              </li>
              <li>
                <Icon name="check" size={15} />
                <span>Les PDF texte natifs sont lus sans OCR, avec une meilleure fidélité.</span>
              </li>
              <li>
                <Icon name="check" size={15} />
                <span>Vérifiez toujours les quantités, prix et numéros proposés.</span>
              </li>
            </ul>
            <div className="note-box">
              <Icon name="shield" size={16} />
              <p>
                Les documents restent sur ce poste. Aucun envoi vers un service externe n'est effectué par défaut. Le LLM est
                désactivé sauf configuration explicite.
              </p>
            </div>
          </Panel>

          <Panel title="Reprendre un import" subtitle="Derniers documents traités sur ce poste." flush>
            {recent.length === 0 ? (
              <p className="muted small panel-padded">Aucune facture pour le moment.</p>
            ) : (
              <ul className="side-list">
                {recent.map((invoice) => (
                  <li key={invoice.id}>
                    <Link to={`/invoices/${invoice.id}`} className="side-list-item">
                      <span className="side-list-icon">
                        <Icon name="invoice" size={16} />
                      </span>
                      <span className="side-list-text">
                        <strong>{invoice.invoice_number ?? invoice.original_filename}</strong>
                        <small>{invoice.supplier_name ?? "Fournisseur non identifié"}</small>
                      </span>
                      <StatusBadge status={invoice.status} compact />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <div className="panel-footer-link">
              <Link to="/history" className="text-link">
                Voir tout l'historique <Icon name="chevronRight" size={15} />
              </Link>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
