import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import type { HealthData, SettingsData } from "../types";
import { Icon, type IconName } from "./Icon";

const navSections: { label: string; items: { to: string; label: string; icon: IconName }[] }[] = [
  {
    label: "Traitement",
    items: [
      { to: "/", label: "Tableau de bord", icon: "dashboard" },
      { to: "/import", label: "Importer", icon: "upload" },
      { to: "/history", label: "Historique & exports", icon: "history" },
    ],
  },
  {
    label: "Référentiels",
    items: [
      { to: "/suppliers", label: "Fournisseurs", icon: "suppliers" },
      { to: "/products", label: "Articles", icon: "products" },
    ],
  },
  {
    label: "Système",
    items: [
      { to: "/databases", label: "Bases de données", icon: "database" },
      { to: "/settings", label: "Configuration", icon: "settings" },
    ],
  },
];

const titles: { match: RegExp; title: string }[] = [
  { match: /^\/$/, title: "Tableau de bord" },
  { match: /^\/import/, title: "Importer des factures" },
  { match: /^\/invoices\/\d+/, title: "Vérification de facture" },
  { match: /^\/history/, title: "Historique & exports" },
  { match: /^\/suppliers/, title: "Référentiel fournisseurs" },
  { match: /^\/products/, title: "Référentiel articles" },
  { match: /^\/databases/, title: "Bases de données" },
  { match: /^\/settings/, title: "Configuration" },
];

export function Layout() {
  const location = useLocation();
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.settings().catch(() => null), api.health().catch(() => null)]).then(([settingsData, healthData]) => {
      if (cancelled) return;
      setSettings(settingsData);
      setHealth(healthData);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  const title = titles.find((entry) => entry.match.test(location.pathname))?.title ?? "Factures fournisseurs";
  const demo = settings?.app.demo ?? settings?.app.mode === "demo";

  return (
    <div className={`app-shell${menuOpen ? " menu-open" : ""}`}>
      <aside className="sidebar">
        <Link to="/" className="brand" aria-label="Retour au tableau de bord">
          <span className="brand-mark">
            <Icon name="invoice" size={21} />
          </span>
          <span className="brand-text">
            <strong>Factures</strong>
            <small>Tulip Gestion · V3.33</small>
          </span>
        </Link>
        <nav className="nav">
          {navSections.map((section) => (
            <div className="nav-section" key={section.label}>
              <div className="nav-label">{section.label}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
                >
                  <Icon name={item.icon} size={18} />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className={`online-dot${health?.status === "ok" ? " online" : ""}`} />
            <div>
              <strong>{health?.status === "ok" ? "Serveur local actif" : "Serveur indisponible"}</strong>
              <small>
                OCR {health?.ocr.available ? "prêt" : "indisponible"} · v{health?.version ?? settings?.app.version ?? "—"}
              </small>
            </div>
          </div>
          <div className="sidebar-note">
            <Icon name="shield" size={14} />
            <span>Export fichiers — aucune écriture directe dans Tulip.</span>
          </div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button
            type="button"
            className="icon-button mobile-menu"
            onClick={() => setMenuOpen((value) => !value)}
            aria-label="Ouvrir le menu"
          >
            <Icon name="menu" />
          </button>
          <div className="topbar-title">
            <span className="crumb">Factures fournisseurs</span>
            <span className="crumb-sep">/</span>
            <span>{title}</span>
          </div>
          <div className="topbar-actions">
            {demo && <span className="mode-chip">Mode démonstration</span>}
            <span className="tulip-chip" title="L'intégration directe à Tulip n'est pas activée.">
              <Icon name="link" size={14} /> Tulip non connecté
            </span>
            <Link to="/import" className="button button-primary button-sm">
              <Icon name="plus" size={16} />
              Importer
            </Link>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
