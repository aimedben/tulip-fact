import type { ReactNode } from "react";
import { statusLabel, statusTone } from "../lib/format";

export function StatusBadge({ status, compact = false }: { status: string; compact?: boolean }) {
  return (
    <span className={`status-badge tone-${statusTone(status)}${compact ? " compact" : ""}`}>
      <span className="status-dot" />
      {statusLabel(status)}
    </span>
  );
}

export function ToneBadge({
  tone,
  children,
}: {
  tone: "neutral" | "info" | "success" | "warning" | "danger" | "accent";
  children: ReactNode;
}) {
  return <span className={`status-badge tone-${tone}`}>{children}</span>;
}
