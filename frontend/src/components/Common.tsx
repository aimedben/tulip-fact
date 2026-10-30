import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { formatDateTimeFR, percent } from "../lib/format";
import type { Check } from "../types";

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  back,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  back?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        {back}
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  flush = false,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-header">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p className="muted small">{subtitle}</p>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      <div className={flush ? "panel-body flush" : "panel-body"}>{children}</div>
    </section>
  );
}

export function EmptyState({
  icon = "folder",
  title,
  description,
  action,
}: {
  icon?: IconName;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon name={icon} size={22} />
      </div>
      <h3>{title}</h3>
      {description && <p className="muted">{description}</p>}
      {action}
    </div>
  );
}

export function ProgressBar({ value, tone = "accent" }: { value: number; tone?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="progress" role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
      <span className={`progress-fill tone-${tone}`} style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pagination">
      <span className="muted small">
        {total === 0 ? "Aucun résultat" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} sur ${total}`}
      </span>
      <div className="pagination-controls">
        <button type="button" className="icon-button" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Page précédente">
          <Icon name="chevronLeft" />
        </button>
        <span className="small">
          {page} / {pages}
        </span>
        <button type="button" className="icon-button" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Page suivante">
          <Icon name="chevronRight" />
        </button>
      </div>
    </div>
  );
}

export function ConfidenceDot({ value, source }: { value?: number | null; source?: string }) {
  const tone = value === null || value === undefined ? "none" : value >= 0.85 ? "high" : value >= 0.65 ? "medium" : "low";
  const title =
    value === null || value === undefined
      ? "Confiance non disponible"
      : `Confiance ${percent(value)}${source ? ` — ${source}` : ""}`;
  return <span className={`confidence-dot ${tone}`} title={title} aria-label={title} />;
}

export function CheckList({
  checks,
  emptyLabel = "Aucun contrôle enregistré.",
  compact = false,
}: {
  checks: Check[];
  emptyLabel?: string;
  compact?: boolean;
}) {
  if (checks.length === 0) return <p className="muted small">{emptyLabel}</p>;
  const sorted = [...checks].sort((a, b) => {
    const order: Record<string, number> = { error: 0, warning: 1, info: 2 };
    return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
  });
  return (
    <ul className={`check-list${compact ? " compact" : ""}`}>
      {sorted.map((check, index) => (
        <li key={`${check.code}-${index}`} className={`check-item severity-${check.severity}`}>
          <span className="check-icon">
            <Icon name={check.severity === "error" ? "alert" : check.severity === "warning" ? "alert" : "check"} size={15} />
          </span>
          <div className="check-content">
            <div className="check-message">{check.message}</div>
            {(check.expected || check.actual) && (
              <div className="check-meta small">
                {check.expected && <span>Attendu : {check.expected}</span>}
                {check.actual && <span>Constaté : {check.actual}</span>}
                {check.difference && <span>Écart : {check.difference}</span>}
              </div>
            )}
            <div className="check-meta small">
              <span className="mono">{check.code}</span>
              {check.related_invoice_id && <span>Facture liée #{check.related_invoice_id}</span>}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function MetaList({ entries }: { entries: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="meta-list">
      {entries.map((entry) => (
        <div key={entry.label}>
          <dt>{entry.label}</dt>
          <dd>{entry.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Timestamp({ value }: { value: string | null }) {
  return <span className="mono small">{formatDateTimeFR(value)}</span>;
}
