import { useEffect, useState } from "react";
import type { InvoiceDetail, InvoiceLine } from "../../types";
import { Icon } from "../Icon";
import { EmptyState } from "../Common";
import { confidenceTone, percent } from "../../lib/format";

export function DocumentViewer({
  detail,
  selectedLine,
  onSelectLine,
}: {
  detail: InvoiceDetail;
  selectedLine: InvoiceLine | null;
  onSelectLine: (line: InvoiceLine) => void;
}) {
  const pages = [...detail.pages].sort((a, b) => a.page_number - b.page_number);
  const [pageNumber, setPageNumber] = useState(selectedLine?.source_page ?? pages[0]?.page_number ?? 1);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [showBoxes, setShowBoxes] = useState(true);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);

  useEffect(() => {
    setPageNumber(pages[0]?.page_number ?? 1);
    setZoom(1);
    setRotation(0);
  }, [detail.id]);

  useEffect(() => {
    if (selectedLine?.source_page && selectedLine.source_page !== pageNumber) {
      setPageNumber(selectedLine.source_page);
    }
  }, [selectedLine, pageNumber]);

  const page = pages.find((entry) => entry.page_number === pageNumber) ?? pages[0];
  const pageLines = detail.lines.filter((line) => line.source_page === page?.page_number && line.source_bbox);

  return (
    <section className="panel viewer-panel">
      <header className="panel-header viewer-header">
        <div>
          <h2>Document original</h2>
          <p className="muted small mono">{detail.original_filename}</p>
        </div>
        <div className="viewer-header-actions">
          <label className="checkbox compact">
            <input type="checkbox" checked={showBoxes} onChange={(event) => setShowBoxes(event.target.checked)} />
            <span>Zones</span>
          </label>
          {page && (
            <a className="icon-button" href={page.image_url} target="_blank" rel="noreferrer" title="Ouvrir l'image en grand">
              <Icon name="external" size={17} />
            </a>
          )}
        </div>
      </header>

      {!page ? (
        <EmptyState icon="eye" title="Aperçu indisponible" description="Les pages apparaîtront à la fin du traitement." />
      ) : (
        <>
          <div className="viewer-toolbar">
            <div className="viewer-pager">
              <button
                type="button"
                className="icon-button"
                disabled={pageNumber <= 1}
                onClick={() => setPageNumber((value) => Math.max(1, value - 1))}
                aria-label="Page précédente"
              >
                <Icon name="chevronLeft" />
              </button>
              <span className="small nowrap">
                Page {page.page_number} / {pages.length}
              </span>
              <button
                type="button"
                className="icon-button"
                disabled={pageNumber >= pages.length}
                onClick={() => setPageNumber((value) => Math.min(pages.length, value + 1))}
                aria-label="Page suivante"
              >
                <Icon name="chevronRight" />
              </button>
            </div>
            <div className="viewer-tools">
              <button
                type="button"
                className="icon-button"
                onClick={() => setZoom((value) => Math.max(0.5, Math.round((value - 0.15) * 100) / 100))}
                title="Réduire"
              >
                <Icon name="zoomOut" />
              </button>
              <span className="small mono zoom-label">{Math.round(zoom * 100)} %</span>
              <button
                type="button"
                className="icon-button"
                onClick={() => setZoom((value) => Math.min(2.5, Math.round((value + 0.15) * 100) / 100))}
                title="Agrandir"
              >
                <Icon name="zoomIn" />
              </button>
              <button
                type="button"
                className="icon-button"
                onClick={() => setRotation((value) => (value + 90) % 360)}
                title="Rotation d'affichage uniquement"
              >
                <Icon name="rotate" />
              </button>
              <div className="viewer-pan-controls">
                <button
                  type="button"
                  className="icon-button small"
                  onClick={() => setPanY((v) => v + 20)}
                  title="Haut"
                >
                  <Icon name="chevronLeft" size={14} style={{ transform: 'rotate(90deg)' } as any} />
                </button>
                <div style={{ display: "flex", gap: "4px" }}>
                  <button
                    type="button"
                    className="icon-button small"
                    onClick={() => setPanX((v) => v - 20)}
                    title="Gauche"
                  >
                    <Icon name="chevronLeft" size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-button small"
                    onClick={() => { setPanX(0); setPanY(0); }}
                    title="Réinitialiser"
                  >
                    <Icon name="rotate" size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-button small"
                    onClick={() => setPanX((v) => v + 20)}
                    title="Droite"
                  >
                    <Icon name="chevronRight" size={14} />
                  </button>
                </div>
                <button
                  type="button"
                  className="icon-button small"
                  onClick={() => setPanY((v) => v - 20)}
                  title="Bas"
                >
                  <Icon name="chevronLeft" size={14} style={{ transform: 'rotate(-90deg)' } as any} />
                </button>
              </div>
            </div>
          </div>

          <div className="viewer-canvas">
            <div
              className="page-stage"
              style={{
                width: `${zoom * 100}%`,
                transform: `translate(${panX}px, ${panY}px) rotate(${rotation}deg)`,
                transformOrigin: 'center',
              }}
            >
              <img src={page.image_url} alt={`Page ${page.page_number} de ${detail.original_filename}`} draggable={false} />
              {showBoxes &&
                pageLines.map((line) => {
                  const box = line.source_bbox!;
                  const selected = selectedLine?.id === line.id;
                  return (
                    <button
                      type="button"
                      key={line.id}
                      className={`line-box${selected ? " selected" : ""}`}
                      style={{
                        left: `${box.x0 * 100}%`,
                        top: `${box.y0 * 100}%`,
                        width: `${(box.x1 - box.x0) * 100}%`,
                        height: `${(box.y1 - box.y0) * 100}%`,
                      }}
                      title={`Ligne ${line.position} — ${line.raw_designation}`}
                      onClick={() => onSelectLine(line)}
                    >
                      <span>{line.position}</span>
                    </button>
                  );
                })}
            </div>
          </div>

          <footer className="viewer-footer">
            <span>
              Moteur <strong>{page.ocr_engine ?? "inconnu"}</strong>
            </span>
            <span className={`confidence-text ${confidenceTone(page.confidence)}`}>
              Confiance OCR {percent(page.confidence)}
            </span>
            {rotation !== 0 && <span className="muted small">Rotation d'affichage {rotation}° (sans effet sur les données)</span>}
          </footer>
        </>
      )}
    </section>
  );
}
