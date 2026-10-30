import { useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { ImportReport } from "../types";
import { Icon } from "./Icon";
import { useToast } from "./Toast";

export function CatalogImport({
  kind,
  onImported,
}: {
  kind: "suppliers" | "products";
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { show } = useToast();

  const run = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.importCatalog(kind, file);
      setReport(result);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onImported();
      show(`Import terminé : ${result.imported_rows} ligne(s) importée(s).`, "success");
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "Import impossible.";
      setError(message);
      show(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const downloadTemplate = () => {
    const header =
      kind === "suppliers"
        ? "code;nom;variantes;nif;telephone;email;adresse;notes"
        : "code_tulip;designation;reference_fournisseur;code_barres;marque;conditionnement;unite_stock;taux_tva";
    const example =
      kind === "suppliers"
        ? '"000123";"Fournisseur Exemple SARL";"Fournisseur Exemple|FE SARL";"123456789012345";"0550123456";"contact@exemple.dz";"Alger";""'
        : '"ART-0001";"Article exemple 1 L";"REF-EX-01";"6131234567890";"Marque";"12 x 1 L";"UNITE";"19"';
    const blob = new Blob([`\uFEFF${header}\n${example}\n`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = kind === "suppliers" ? "modele-fournisseurs.csv" : "modele-articles.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="catalog-import">
      <div className="catalog-import-row">
        <label className="file-picker">
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setReport(null);
              setError(null);
            }}
          />
          <Icon name="folder" size={17} />
          <span>{file ? file.name : "Choisir un fichier CSV ou XLSX"}</span>
        </label>
        <button type="button" className="button button-sm button-primary" onClick={run} disabled={!file || loading}>
          {loading ? <span className="spinner small light" /> : <Icon name="upload" size={15} />} Importer
        </button>
        <button type="button" className="button button-sm" onClick={downloadTemplate}>
          <Icon name="download" size={15} /> Modèle CSV
        </button>
      </div>
      <p className="muted tiny">
        Colonnes attendues :{" "}
        <span className="mono">
          {kind === "suppliers"
            ? "code, nom, variantes (séparées par |), nif, telephone, email, adresse, notes"
            : "code_tulip, designation, reference_fournisseur, code_barres, marque, conditionnement, unite_stock, taux_tva"}
        </span>
        . Les codes sont conservés tels quels, zéros initiaux compris.
      </p>

      {error && <p className="inline-error">{error}</p>}

      {report && (
        <div className="import-report">
          <div className="import-report-head">
            <strong>Rapport d'import — {report.filename}</strong>
            <span className="small">
              {report.imported_rows} importée(s) · {report.skipped_rows} ignorée(s) · {report.total_rows} ligne(s) lue(s)
            </span>
          </div>
          {report.errors.length > 0 ? (
            <ul className="report-errors">
              {report.errors.slice(0, 12).map((entry, index) => (
                <li key={`${entry.row}-${index}`}>
                  <span className="mono">Ligne {entry.row}</span>
                  {entry.field && <span className="mono"> · {entry.field}</span>} — {entry.message}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">Aucune erreur de ligne.</p>
          )}
          {report.errors.length > 12 && (
            <p className="muted tiny">… et {report.errors.length - 12} autre(s) erreur(s).</p>
          )}
        </div>
      )}
    </div>
  );
}
