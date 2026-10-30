export const STATUS_LABELS: Record<string, string> = {
  IMPORTEE: "Importée",
  EXTRACTION: "Extraction en cours",
  A_VERIFIER: "À vérifier",
  PRETE_A_VALIDER: "Prête à valider",
  VALIDEE: "Validée",
  EXPORTEE: "Exportée",
  ECHEC: "Échec",
};

export const STATUS_TONES: Record<string, string> = {
  IMPORTEE: "neutral",
  EXTRACTION: "info",
  A_VERIFIER: "warning",
  PRETE_A_VALIDER: "accent",
  VALIDEE: "success",
  EXPORTEE: "success",
  ECHEC: "danger",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(status: string): string {
  return STATUS_TONES[status] ?? "neutral";
}

export function formatMoney(value: number | string | null | undefined, currency = "DZD"): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = typeof value === "string" ? parseAmount(value) : value;
  if (number === null || Number.isNaN(number)) return "—";
  const formatted = new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(number);
  return `${formatted} ${currency === "DZD" ? "DA" : currency}`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  return new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function parseAmount(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const cleaned = value
    .replace(/\u00a0|\u202f|\s/g, "")
    .replace(/(DA|DZD|dinars?)$/i, "")
    .replace("%", "")
    .replace(",", ".");
  if (!cleaned || !/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatDateFR(value: string | null | undefined): string {
  if (!value) return "—";
  const datePart = value.slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(datePart);
  if (!match) return value;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

export function formatDateTimeFR(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

export function confidenceTone(score: number | null | undefined): "high" | "medium" | "low" | "none" {
  if (score === null || score === undefined) return "none";
  if (score >= 0.85) return "high";
  if (score >= 0.65) return "medium";
  return "low";
}

export function percent(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return `${Math.round(score * 100)} %`;
}

export function isProcessing(status: string): boolean {
  return status === "IMPORTEE" || status === "EXTRACTION";
}

export function isLocked(status: string): boolean {
  return status === "VALIDEE" || status === "EXPORTEE";
}

export const matchesStatus: Record<string, string> = {
  RAPPROCHE: "Rapproché",
  CONFIRME: "Confirmé",
  SUGGERE: "Suggestion",
  NON_RAPPROCHE: "Non rapproché",
};

export function matchLabel(status: string): string {
  return matchesStatus[status] ?? status;
}

export function buildQuery(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function todayISO(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

export function truncate(value: string, length = 60): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}
