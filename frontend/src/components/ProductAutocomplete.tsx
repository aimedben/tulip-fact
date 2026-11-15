import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { ProductCandidate } from "../types";
import { Icon } from "./Icon";

interface ProductAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  /** Appelé quand l'utilisateur choisit une suggestion. */
  onPick: (candidate: ProductCandidate) => void;
  /** Optionnel : associer directement l'article (rapprochement ligne). */
  onAssociate?: (candidate: ProductCandidate) => void;
  supplierId?: number | null;
  reference?: string | null;
  className?: string;
  placeholder?: string;
  ariaLabel?: string;
  disabled?: boolean;
}

/** Suggestion d'une liste d'articles (code Tulip, réf. art., code-barres, score). */
export function ProductSuggestionRow({
  candidate,
  onPick,
  onAssociate,
  active,
  onHover,
}: {
  candidate: ProductCandidate;
  onPick: (candidate: ProductCandidate) => void;
  onAssociate?: (candidate: ProductCandidate) => void;
  active: boolean;
  onHover: () => void;
}) {
  return (
    <div
      className={`product-suggestion-item${active ? " active" : ""}`}
      onMouseEnter={onHover}
      role="option"
      aria-selected={active}
    >
      <button type="button" className="product-suggestion-main" onClick={() => onPick(candidate)}>
        <strong>{candidate.designation}</strong>
        <span className="muted tiny mono">
          {[
            candidate.tulip_code,
            candidate.reference ? `réf. art. ${candidate.reference}` : null,
            candidate.barcode ? `code-barres ${candidate.barcode}` : null,
            candidate.packaging ? `cond. ${candidate.packaging}` : null,
            candidate.stock_unit,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </button>
      <span className="product-suggestion-side">
        {candidate.score ? <span className="score-pill">{Math.round(candidate.score * 100)} %</span> : null}
        {onAssociate && (
          <button
            type="button"
            className="icon-button"
            title={`Associer ${candidate.tulip_code}`}
            onClick={() => onAssociate(candidate)}
          >
            <Icon name="link" size={14} />
          </button>
        )}
        <Icon name="plus" size={14} />
      </span>
    </div>
  );
}

/**
 * Champ de saisie avec autocomplétion produit : à chaque frappe (dès 1 lettre),
 * interroge le référentiel Tulip après un léger debounce et affiche une liste
 * de suggestions cliquables.
 */
export function ProductAutocomplete({
  value,
  onChange,
  onPick,
  onAssociate,
  supplierId = null,
  reference = null,
  className = "",
  placeholder,
  ariaLabel,
  disabled,
}: ProductAutocompleteProps) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ProductCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Fermer le dropdown au clic extérieur
  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const query = value.trim();
  useEffect(() => {
    if (disabled || query.length < 1) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    // Debounce : évite de solliciter l'API à chaque frappe
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.suggestProducts(query, supplierId, reference);
        setItems(result.items.slice(0, 8));
      } catch {
        setItems([]);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, supplierId, reference, disabled]);

  useEffect(() => {
    setHighlight(0);
  }, [items]);

  const pick = (candidate: ProductCandidate) => {
    onPick(candidate);
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || items.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => Math.min(current + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      pick(items[highlight]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="product-autocomplete" ref={wrapRef}>
      <input
        value={value}
        className={className}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          if (query.length > 0) setOpen(true);
        }}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={ariaLabel}
        autoComplete="off"
      />
      {open && !disabled && (loading || items.length > 0) && (
        <div className="product-suggestions-dropdown" role="listbox">
          {loading && items.length === 0 && (
            <div className="product-suggestion-note">
              <span className="spinner small" /> Recherche d'articles…
            </div>
          )}
          {items.map((candidate, index) => (
            <ProductSuggestionRow
              key={candidate.product_id}
              candidate={candidate}
              onPick={pick}
              onAssociate={onAssociate}
              active={index === highlight}
              onHover={() => setHighlight(index)}
            />
          ))}
        </div>
      )}
      {open && !disabled && !loading && query.length > 0 && items.length === 0 && (
        <div className="product-suggestions-dropdown">
          <div className="product-suggestion-note">Aucun article du référentiel ne correspond.</div>
        </div>
      )}
    </div>
  );
}
