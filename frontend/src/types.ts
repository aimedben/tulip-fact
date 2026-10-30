export type InvoiceStatus =
  | "IMPORTEE"
  | "EXTRACTION"
  | "A_VERIFIER"
  | "PRETE_A_VALIDER"
  | "VALIDEE"
  | "EXPORTEE"
  | "ECHEC";

export interface Supplier {
  id: number;
  code: string;
  name: string;
  name_variants: string[];
  tax_id: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  notes: string | null;
  active: boolean;
}

export interface Product {
  id: number;
  tulip_code: string;
  supplier_ref: string | null;
  barcode: string | null;
  designation: string;
  brand: string | null;
  packaging: string | null;
  stock_unit: string | null;
  default_vat_rate: number | null;
  active: boolean;
}

export interface ProductCandidate {
  product_id: number;
  tulip_code: string;
  designation: string;
  supplier_ref?: string | null;
  barcode?: string | null;
  packaging?: string | null;
  stock_unit?: string | null;
  default_vat_rate?: string | null;
  score: number;
  method: string;
}

export interface SupplierCandidate {
  supplier_id: number;
  code: string;
  name: string;
  score: number;
  method: string;
  auto?: boolean;
  matched_text?: string;
}

export interface InvoicePage {
  id: number;
  page_number: number;
  image_url: string;
  ocr_engine: string | null;
  rotation: number;
  width: number | null;
  height: number | null;
  confidence: number | null;
}

export interface InvoiceLine {
  id: number;
  position: number;
  raw_reference: string | null;
  raw_designation: string;
  catalog_designation: string | null;
  tulip_product_id: number | null;
  tulip_product: Product | null;
  match_status: string;
  match_score: number | null;
  match_candidates: ProductCandidate[];
  lot_number: string | null;
  packages: number | null;
  quantity: number | null;
  unit: string | null;
  packaging: string | null;
  unit_price_ht: number | null;
  vat_rate: number | null;
  line_total_ht_extracted: number | null;
  line_total_ht_calculated: number | null;
  discount_value: number | null;
  discount_type: string | null;
  confidence: Record<string, number | boolean | string>;
  source_page: number | null;
  source_bbox: { x0: number; y0: number; x1: number; y1: number } | null;
  original_values: Record<string, unknown>;
  user_modified: boolean;
}

export type Totals = {
  total_ht?: string | null;
  discount_total?: string | null;
  vat_total?: string | null;
  vat_breakdown?: Record<string, string>;
  other_taxes?: string | null;
  timbre?: string | null;
  total_ttc?: string | null;
  raw?: Record<string, string>;
  confidence?: Record<string, number>;
};

export interface Check {
  code: string;
  severity: "error" | "warning" | "info" | string;
  message: string;
  field?: string;
  line_position?: number;
  expected?: string;
  actual?: string;
  difference?: string;
  source?: string;
  related_invoice_id?: number;
}

export interface AuditEntry {
  id: number;
  action: string;
  actor: string;
  entity_type: string;
  entity_id: number | null;
  details: Record<string, unknown>;
  created_at: string | null;
}

export interface ExportRecord {
  id: number;
  invoice_id: number;
  format: string;
  mode: string;
  status: string;
  note: string | null;
  created_at: string | null;
  download_url: string;
  sha256: string;
  invoice_number?: string | null;
  supplier_name?: string | null;
}

export interface Readiness {
  ready: boolean;
  can_validate: boolean;
  blocking: Check[];
  hard: Check[];
  accounting_errors: Check[];
  warnings: Check[];
  duplicate: Check | null;
  totals_ack_required: boolean;
  requires_acks: { duplicate: boolean; totals: boolean; warnings: boolean };
}

export interface InvoiceSummary {
  id: number;
  uuid: string;
  original_filename: string;
  status: InvoiceStatus;
  stage: string;
  progress: number;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_id: number | null;
  supplier_code: string | null;
  supplier_name: string | null;
  total_ttc: number | null;
  currency: string;
  is_duplicate: boolean;
  page_count: number;
  imported_at: string | null;
  processed_at: string | null;
  validated_at: string | null;
  exported_at: string | null;
  error_message: string | null;
  lines_count: number;
}

export interface InvoiceDetail extends InvoiceSummary {
  sha256: string;
  mime_type: string;
  file_size: number;
  document_type: string | null;
  bl_facture: boolean | null;
  bc_number: string | null;
  bc_date: string | null;
  bl_number: string | null;
  bl_date: string | null;
  notes: string | null;
  validation_user: string | null;
  supplier_name_raw: string | null;
  supplier: Supplier | null;
  supplier_match: {
    candidates?: SupplierCandidate[];
    score?: number;
    method?: string;
    confirmed?: boolean;
  };
  header_raw: Record<string, { value: number; source: string }>;
  totals_extracted: Totals;
  totals_calculated: Totals;
  checks: Check[];
  warnings: Check[];
  document_meta: Record<string, unknown>;
  duplicate_reason: string | null;
  duplicate_of_id: number | null;
  pages: InvoicePage[];
  lines: InvoiceLine[];
  audits: AuditEntry[];
  exports: ExportRecord[];
  readiness: Readiness;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardData {
  counts: {
    importees: number;
    en_attente_verification: number;
    a_verifier: number;
    pretes_a_valider: number;
    validees: number;
    exportees: number;
    en_echec: number;
    en_cours: number;
    doublons: number;
  };
  by_status: Record<string, number>;
  recent_invoices: InvoiceSummary[];
  recent_exports: ExportRecord[];
}

export interface ImportReport {
  id: number;
  kind: string;
  filename: string;
  total_rows: number;
  imported_rows: number;
  skipped_rows: number;
  errors: { row: number; field: string; message: string }[];
  created_at: string;
}

export interface TulipStatus {
  mode: string;
  connected: boolean;
  confirmed: boolean;
  message: string;
  platform?: string;
  methods: Record<
    string,
    { supported: boolean; reason: string; enabled?: boolean; pywinauto_installed?: boolean }
  >;
  exports: { available: boolean; note: string };
  missing_information: string[];
  probe?: { performed: boolean; reason?: string; windows?: unknown[]; note?: string };
}

export interface TulipLiveStatus {
  enabled: boolean;
  configured: boolean;
  connected?: boolean;
  database: string | null;
  host: string;
  port: number;
  charset: string;
  read_only: boolean;
  write_enabled: boolean;
  engine_version?: string | null;
  latency_ms?: number | null;
  error?: string | null;
}

export interface TulipLiveSummary {
  suppliers: number;
  products: number;
  be_total: number;
  be_dette: number;
}

export interface TulipLiveSupplier {
  id: number | null;
  tulip_code: string | null;
  code: string | null;
  name: string;
  tax_id: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
}

export interface TulipLiveBeDocument {
  id: number | null;
  numero: number | null;
  nbc: string | null;
  livfact: string | null;
  supplier_code: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  opdate: string | null;
  datebc: string | null;
  dette: boolean;
  stock: boolean;
  mht: number | null;
  mtva: number | null;
  ttc: number | null;
}

export interface TulipLivePaged<T> {
  source: string;
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface SettingsData {
  app: {
    name: string;
    version: string;
    mode: string;
    demo: boolean;
    data_dir: string;
    database: string;
    invoice_count: number;
  };
  ocr: {
    engine: string;
    tesseract_available: boolean;
    languages: string[];
    configured_languages: string;
    psm: number;
    render_dpi: number;
    note: string;
  };
  llm: {
    enabled: boolean;
    configured: boolean;
    model: string | null;
    base_url: string | null;
    data_transmitted: string;
    note: string;
  };
  vision?: {
    enabled: boolean;
    provider: string;
    providers: Record<string, { configured: boolean; model: string | null; available: boolean }>;
    active_model: string | null;
    active_base_url: string | null;
    note: string;
  };
  accounting: { amount_tolerance: number; currency_default: string };
  tulip: TulipStatus;
}

export interface HealthData {
  status: string;
  version: string;
  database: boolean;
  storage: boolean;
  ocr: { available: boolean; languages: string[] };
  demo: boolean;
}
