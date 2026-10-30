import type {
  DashboardData,
  ExportRecord,
  HealthData,
  ImportReport,
  InvoiceDetail,
  InvoiceSummary,
  Paged,
  Product,
  ProductCandidate,
  SettingsData,
  Supplier,
  SupplierCandidate,
  TulipLiveBeDocument,
  TulipLivePaged,
  TulipLiveStatus,
  TulipLiveSummary,
  TulipLiveSupplier,
  TulipStatus,
} from "../types";

export class ApiError extends Error {
  status: number;
  issues: { code?: string; message?: string; field?: string }[];

  constructor(message: string, status: number, issues: { code?: string; message?: string; field?: string }[] = []) {
    super(message);
    this.status = status;
    this.issues = issues;
  }
}

function detailMessage(payload: unknown, fallback: string): { message: string; issues: { code?: string; message?: string; field?: string }[] } {
  if (!payload || typeof payload !== "object") return { message: fallback, issues: [] };
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return { message: detail, issues: [] };
  if (detail && typeof detail === "object") {
    const record = detail as { message?: string; issues?: { code?: string; message?: string; field?: string }[] };
    return { message: record.message ?? fallback, issues: record.issues ?? [] };
  }
  return { message: fallback, issues: [] };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const parsed = detailMessage(payload, `Erreur HTTP ${response.status}`);
    throw new ApiError(parsed.message, response.status, parsed.issues);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function uploadInvoice(file: File, onProgress: (value: number) => void): Promise<InvoiceSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/invoices/import");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError("La connexion au serveur a échoué.", 0));
    xhr.onload = () => {
      let payload: unknown = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as InvoiceSummary);
      } else {
        const parsed = detailMessage(payload, `Erreur HTTP ${xhr.status}`);
        reject(new ApiError(parsed.message, xhr.status, parsed.issues));
      }
    };
    const data = new FormData();
    data.append("file", file);
    xhr.send(data);
  });
}

export function downloadFile(url: string, filename?: string): void {
  const anchor = document.createElement("a");
  anchor.href = url;
  if (filename) anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export const api = {
  dashboard: () => request<DashboardData>("/dashboard"),
  health: () => request<HealthData>("/health"),
  settings: () => request<SettingsData>("/settings"),
  updateLlmSettings: (payload: { enabled: boolean; api_key?: string; base_url?: string; model?: string }) =>
    request<{ message: string; enabled: boolean; model: string | null; base_url: string | null }>("/settings/llm", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testLlmSettings: () =>
    request<{ ok: boolean; model: string | null; base_url: string | null; answer: string }>("/settings/llm/test", {
      method: "POST",
    }),
  updateVisionSettings: (payload: { enabled: boolean; provider?: string; api_key?: string; base_url?: string; model?: string }) =>
    request<{ message: string; enabled: boolean; model: string | null; base_url: string | null }>("/settings/vision", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testVisionSettings: () =>
    request<{ ok: boolean; model: string | null; base_url: string | null; answer: string }>("/settings/vision/test", {
      method: "POST",
    }),
  getFirebirdSettings: () =>
    request<{
      enabled: boolean;
      database: string;
      host: string;
      port: number;
      user: string;
      isql_path: string;
      fb_home: string;
      charset: string;
      write_enabled: boolean;
    }>("/settings/firebird"),
  updateFirebirdSettings: (payload: {
    enabled: boolean;
    database?: string;
    host?: string;
    port?: number;
    user?: string;
    password?: string;
    isql_path?: string;
    fb_home?: string;
    charset?: string;
    write_enabled?: boolean;
  }) =>
    request<{ message: string; enabled: boolean; database: string }>("/settings/firebird", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  accessInfo: () =>
    request<{
      port: number;
      primary_url: string | null;
      primary_ip: string | null;
      candidates: { ip: string; url: string; reachable: boolean }[];
      local_url: string;
      hint: string;
    }>("/access"),
  tulipStatus: () => request<TulipStatus>("/tulip/status"),
  tulipProbe: () => request<TulipStatus>("/tulip/probe", { method: "POST" }),
  tulipLiveStatus: () => request<TulipLiveStatus>("/tulip/live/status"),
  tulipLiveSummary: () => request<TulipLiveSummary>("/tulip/live/summary"),
  tulipLiveSuppliers: (page_size = 10) =>
    request<TulipLivePaged<TulipLiveSupplier>>(`/tulip/live/suppliers?page=1&page_size=${page_size}`),
  tulipLiveBe: (page_size = 10, q?: string) => {
    const search = new URLSearchParams({ page: "1", page_size: String(page_size) });
    if (q) search.set("q", q);
    return request<TulipLivePaged<TulipLiveBeDocument>>(`/tulip/live/be?${search.toString()}`);
  },
  tulipSyncSuppliers: () =>
    request<{ created: number; updated: number; total: number; local_total: number }>(
      "/tulip/live/suppliers/sync",
      { method: "POST" },
    ),
  tulipPushSupplier: (supplierId: number, dryRun: boolean) =>
    request<Record<string, unknown>>(
      `/tulip/live/suppliers/${supplierId}/push?dry_run=${dryRun}`,
      { method: "POST" },
    ),
  tulipSyncProducts: () =>
    request<{ created: number; updated: number; total: number; local_total: number }>(
      "/tulip/live/products/sync",
      { method: "POST" },
    ),
  tulipCreateBe: (invoiceId: number, dryRun: boolean) =>
    request<Record<string, unknown>>(`/invoices/${invoiceId}/tulip/be?dry_run=${dryRun}`, { method: "POST" }),
  tulipTables: (withRows = true) =>
    request<{ items: Array<{ name: string; rows: number | null }> }>(
      `/tulip/live/tables${withRows ? "?with_rows=true" : ""}`,
    ),
  tulipTableRows: (name: string, page = 1, q?: string) => {
    const search = new URLSearchParams({ page: String(page), page_size: "50" });
    if (q) search.set("q", q);
    return request<Record<string, unknown>>(`/tulip/live/tables/${encodeURIComponent(name)}?${search.toString()}`);
  },

  dbTables: () => request<Array<{ name: string; rows: number; columns: Array<{ name: string; type: string }> }>>("/db/tables"),
  dbTableRows: (name: string, page = 1, q?: string) => {
    const search = new URLSearchParams({ page: String(page), page_size: "50" });
    if (q) search.set("q", q);
    return request<Record<string, unknown>>(`/db/tables/${encodeURIComponent(name)}?${search.toString()}`);
  },
  dbBackups: () =>
    request<{ directory: string; items: Array<{ name: string; size: number; created_at: string }> }>("/db/backups"),
  dbCreateBackup: () => request<{ created: string; size: number }>("/db/backups", { method: "POST" }),
  dbClearTable: (name: string) =>
    request<{ table: string; deleted: number }>(`/db/tables/${encodeURIComponent(name)}?confirm=true`, {
      method: "DELETE",
    }),

  listInvoices: (params: Record<string, string | number | null | undefined>) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
    });
    return request<Paged<InvoiceSummary>>(`/invoices?${search.toString()}`);
  },
  invoice: (id: number) => request<InvoiceDetail>(`/invoices/${id}`),
  updateHeader: (id: number, payload: Record<string, unknown>) =>
    request<InvoiceDetail>(`/invoices/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  confirmSupplier: (id: number, supplierId: number) =>
    request<InvoiceDetail>(`/invoices/${id}/supplier`, {
      method: "POST",
      body: JSON.stringify({ supplier_id: supplierId }),
    }),
  updateLine: (invoiceId: number, lineId: number, payload: Record<string, unknown>) =>
    request<InvoiceDetail>(`/invoices/${invoiceId}/lines/${lineId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  addLine: (invoiceId: number, payload: Record<string, unknown>) =>
    request<InvoiceDetail>(`/invoices/${invoiceId}/lines`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteLine: (invoiceId: number, lineId: number) =>
    request<InvoiceDetail>(`/invoices/${invoiceId}/lines/${lineId}`, { method: "DELETE" }),
  matchLine: (invoiceId: number, lineId: number, productId: number) =>
    request<InvoiceDetail>(`/invoices/${invoiceId}/lines/${lineId}/match`, {
      method: "POST",
      body: JSON.stringify({ product_id: productId }),
    }),
  createLineProduct: (
    invoiceId: number,
    lineId: number,
    payload: {
      designation?: string | null;
      tulip_code?: string | null;
      supplier_ref?: string | null;
      packaging?: string | null;
      stock_unit?: string | null;
      default_vat_rate?: number | null;
    },
  ) =>
    request<InvoiceDetail>(`/invoices/${invoiceId}/lines/${lineId}/new-product`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  validateInvoice: (
    id: number,
    payload: { actor: string; acknowledge_duplicate: boolean; acknowledge_totals: boolean; acknowledge_warnings: boolean },
  ) =>
    request<{ message: string; invoice: InvoiceDetail }>(`/invoices/${id}/validate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reprocess: (id: number) => request<InvoiceSummary>(`/invoices/${id}/reprocess`, { method: "POST" }),
  deleteInvoice: (id: number) =>
    request<{ message: string }>(`/invoices/${id}?confirm=true`, { method: "DELETE" }),
  deleteInvoicesBulk: (ids: number[]) =>
    request<{ message: string; deleted: number[]; refused: { invoice_id: number; reason: string }[] }>(
      "/invoices/delete-bulk",
      { method: "POST", body: JSON.stringify({ ids }) },
    ),

  exportInvoice: (id: number, formats: string[]) =>
    request<{ message: string; records: ExportRecord[]; invoice_status: string }>(`/invoices/${id}/export`, {
      method: "POST",
      body: JSON.stringify({ formats }),
    }),
  exports: (params: Record<string, string | number | null | undefined> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
    });
    return request<{ items: ExportRecord[] }>(`/exports?${search.toString()}`);
  },

  suppliers: (params: { q?: string; page?: number; page_size?: number } = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
    });
    return request<Paged<Supplier>>(`/suppliers?${search.toString()}`);
  },
  lookupSupplier: (name: string) =>
    request<{ items: SupplierCandidate[] }>(`/suppliers/lookup?name=${encodeURIComponent(name)}`),
  createSupplier: (payload: Record<string, unknown>) =>
    request<Supplier>("/suppliers", { method: "POST", body: JSON.stringify(payload) }),
  updateSupplier: (id: number, payload: Record<string, unknown>) =>
    request<Supplier>(`/suppliers/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  products: (params: { q?: string; page?: number; page_size?: number } = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
    });
    return request<Paged<Product>>(`/products?${search.toString()}`);
  },
  createProduct: (payload: Record<string, unknown>) =>
    request<Product>("/products", { method: "POST", body: JSON.stringify(payload) }),
  updateProduct: (id: number, payload: Record<string, unknown>) =>
    request<Product>(`/products/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  suggestProducts: (q: string, supplierId?: number | null) =>
    request<{ items: ProductCandidate[] }>(
      `/products/suggest?q=${encodeURIComponent(q)}${supplierId ? `&supplier_id=${supplierId}` : ""}`,
    ),
  getProductByBarcode: (barcode: string) =>
    request<Product>(`/products/barcode/${encodeURIComponent(barcode)}`),
  importCatalog: async (kind: "suppliers" | "products", file: File): Promise<ImportReport> => {
    const data = new FormData();
    data.append("file", file);
    return request<ImportReport>(`/${kind}/import`, { method: "POST", body: data });
  },
  createBackup: () =>
    request<{ message: string; filename: string; size: number; created_at: string; download_url: string }>(
      "/maintenance/backup",
      { method: "POST" },
    ),
};
