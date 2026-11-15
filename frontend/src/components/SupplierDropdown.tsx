import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Supplier } from "../types";
import { Icon } from "./Icon";

interface SupplierDropdownProps {
  value: number | null;
  onChange: (supplierId: number | null, supplierName: string) => void;
  disabled?: boolean;
  preSelectedId?: number | null;
}

export function SupplierDropdown({ value, onChange, disabled, preSelectedId }: SupplierDropdownProps) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .suppliers({ page_size: 500 })
      .then((result) => {
        setSuppliers(result.items);

        // Présélectionner si fourni
        if (preSelectedId) {
          const selected = result.items.find((s) => s.id === preSelectedId);
          if (selected) {
            onChange(selected.id, selected.name);
          }
        }
      })
      .catch((err) => {
        console.error("Erreur chargement fournisseurs:", err);
        setSuppliers([]);
      })
      .finally(() => setLoading(false));
  }, [preSelectedId]);

  const handleChange = (supplierId: string) => {
    if (supplierId === "") {
      onChange(null, "");
      return;
    }
    const id = parseInt(supplierId, 10);
    const supplier = suppliers.find((s) => s.id === id);
    if (supplier) {
      onChange(supplier.id, supplier.name);
    }
  };

  const filteredSuppliers = searchQuery.trim()
    ? suppliers.filter((s) =>
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.code.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : suppliers;

  return (
    <div className="supplier-dropdown-container">
      <div className="supplier-dropdown-search">
        <Icon name="search" size={14} />
        <input
          type="text"
          placeholder="Rechercher un fournisseur..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          disabled={disabled || loading}
          style={{
            flex: 1,
            padding: "0.5rem 0.5rem 0.5rem 2rem",
            border: "1px solid var(--color-border)",
            borderRadius: "4px",
            fontSize: "0.875rem",
          }}
        />
      </div>

      <select
        value={value || ""}
        onChange={(e) => handleChange(e.target.value)}
        disabled={disabled || loading}
        style={{
          width: "100%",
          padding: "0.5rem",
          border: "1px solid var(--color-border)",
          borderRadius: "4px",
          marginTop: "0.5rem",
        }}
      >
        <option value="">— Aucun fournisseur spécifique —</option>
        {loading ? (
          <option disabled>Chargement...</option>
        ) : filteredSuppliers.length === 0 ? (
          <option disabled>Aucun fournisseur trouvé</option>
        ) : (
          filteredSuppliers.map((supplier) => (
            <option key={supplier.id} value={supplier.id}>
              {supplier.name} ({supplier.code})
            </option>
          ))
        )}
      </select>

      <style>{`
        .supplier-dropdown-container {
          width: 100%;
        }

        .supplier-dropdown-search {
          position: relative;
          display: flex;
          align-items: center;
        }

        .supplier-dropdown-search svg {
          position: absolute;
          left: 0.5rem;
          color: var(--color-text-muted);
          pointer-events: none;
        }
      `}</style>
    </div>
  );
}
