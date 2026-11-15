import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import type { AccessInfo, HealthData, SettingsData, TulipLiveStatus } from "../types";
import { Icon, type IconName } from "./Icon";

const navSections: { label: string; items: { to: string; label: string; icon: IconName }[] }[] = [
  {
    label: "Factures",
    items: [
      { to: "/", label: "Accueil", icon: "dashboard" },
      { to: "/import", label: "Ajouter une facture", icon: "upload" },
      { to: "/history", label: "Historique", icon: "history" },
    ],
  },
  {
    label: "Mon commerce",
    items: [
      { to: "/suppliers", label: "Fournisseurs", icon: "suppliers" },
      { to: "/products", label: "Articles", icon: "products" },
    ],
  },
  {
    label: "Options",
    items: [
      { to: "/databases", label: "Données", icon: "database" },
      { to: "/settings", label: "Réglages", icon: "settings" },
    ],
  },
];

const titles: { match: RegExp; title: string }[] = [
  { match: /^\/$/, title: "Accueil" },
  { match: /^\/import/, title: "Ajouter une facture" },
  { match: /^\/invoices\/\d+/, title: "Vérifier la facture" },
  { match: /^\/history/, title: "Historique" },
  { match: /^\/suppliers/, title: "Fournisseurs" },
  { match: /^\/products/, title: "Articles" },
  { match: /^\/databases/, title: "Données" },
  { match: /^\/settings/, title: "Réglages" },
];

/**
 * Petit panneau QR de la barre du haut : même adresse et même QR que la
 * section « Accès depuis le téléphone » de la page Configuration.
 */
function PhoneQrPopover({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<AccessInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .accessInfo()
      .then((info) => {
        if (!cancelled) setData(info);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Adresse réseau introuvable.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const url = data?.primary_url ?? "";
  const qrSrc = url ? `/api/access/qr.svg?url=${encodeURIComponent(url)}&scale=7` : "";

  const copy = useCallback(async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copiez ce lien :", url);
    }
  }, [url]);

  return (
    <div className="qr-popover" role="dialog" aria-label="Accès depuis le téléphone">
      <div className="qr-popover-head">
        <strong>Accès depuis le téléphone</strong>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
          <Icon name="close" size={15} />
        </button>
      </div>
      {error ? (
        <p className="inline-error small">{error}</p>
      ) : !data ? (
        <p className="muted small">Recherche de l'adresse réseau…</p>
      ) : url ? (
        <>
          <div className="qr-frame qr-popover-frame">
            <img src={qrSrc} alt={`QR code vers ${url}`} width={168} height={168} />
          </div>
          <p className="qr-popover-url mono small">{url}</p>
          <div className="qr-popover-actions">
            <button type="button" className="button button-sm" onClick={() => void copy()}>
              <Icon name={copied ? "check" : "link"} size={14} /> {copied ? "Copié" : "Copier"}
            </button>
            <a className="button button-sm" href={url} target="_blank" rel="noreferrer">
              <Icon name="external" size={14} /> Ouvrir
            </a>
          </div>
          <p className="muted tiny">{data.hint}</p>
        </>
      ) : (
        <p className="muted small">{data.hint}</p>
      )}
    </div>
  );
}

export function Layout() {
  const location = useLocation();
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [tulipLive, setTulipLive] = useState<TulipLiveStatus | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const qrRef = useRef<HTMLDivElement | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string>("");

  // Fermeture du panneau QR au clic extérieur ou sur Échap.
  useEffect(() => {
    if (!qrOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (qrRef.current && !qrRef.current.contains(event.target as Node)) setQrOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setQrOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [qrOpen]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.settings().catch(() => null), api.health().catch(() => null)]).then(([settingsData, healthData]) => {
      if (cancelled) return;
      setSettings(settingsData);
      setHealth(healthData);
    });
    api
      .tulipLiveStatus()
      .then((status) => {
        if (!cancelled) setTulipLive(status);
      })
      .catch(() => {
        if (!cancelled) setTulipLive(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    setSyncStatus("Lecture des fournisseurs dans Tulip…");
    try {
      // Synchroniser les fournisseurs
      const suppliersRes = await fetch("/api/tulip/live/suppliers/sync?page_size=500", { method: "POST" });
      if (!suppliersRes.ok) {
        throw new Error(`Erreur fournisseurs: ${suppliersRes.status}`);
      }
      const suppliersData = await suppliersRes.json();

      setSyncStatus("Lecture des articles dans Tulip…");

      // Synchroniser les articles
      const productsRes = await fetch("/api/tulip/live/products/sync?page_size=500", { method: "POST" });
      if (!productsRes.ok) {
        throw new Error(`Erreur articles: ${productsRes.status}`);
      }
      const productsData = await productsRes.json();

      const totalSuppliers = (suppliersData.created || 0) + (suppliersData.updated || 0);
      const totalProducts = (productsData.created || 0) + (productsData.updated || 0);

      setSyncStatus(`Mise à jour terminée : ${totalSuppliers} fournisseurs, ${totalProducts} articles.`);
      setTimeout(() => setSyncStatus(""), 6000);
    } catch (error) {
      console.error("Erreur de synchronisation:", error);
      setSyncStatus(
        `Mise à jour impossible : ${error instanceof Error ? error.message : "Tulip ne répond pas."}`,
      );
      setTimeout(() => setSyncStatus(""), 9000);
    } finally {
      setSyncing(false);
    }
  };

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
            <strong>Tulip Factures</strong>
            <small>Fournisseurs &amp; articles</small>
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
        <div className="sync-section">
          <button
            type="button"
            className="sync-button"
            onClick={handleSync}
            disabled={syncing}
            title="Synchroniser les fournisseurs et articles vers Firebird"
          >
            <Icon name={syncing ? "spinner" : "refresh"} size={16} />
            <span>{syncing ? "Mise à jour…" : "Mettre à jour depuis Tulip"}</span>
          </button>
          {syncStatus && (
            <div className="sync-status">
              <small>{syncStatus}</small>
            </div>
          )}
        </div>
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
            <span>
              {tulipLive?.connected
                ? "Vos fiches sont enregistrées dans Tulip."
                : "Tulip n'est pas joignable pour le moment."}
            </span>
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
            <div className="qr-access" ref={qrRef}>
              <button
                type="button"
                className={`icon-button${qrOpen ? " active" : ""}`}
                onClick={() => setQrOpen((value) => !value)}
                aria-label="Afficher le QR code d'accès depuis le téléphone"
                aria-expanded={qrOpen}
                title="Accès depuis le téléphone (QR code)"
              >
                <Icon name="qr" size={18} />
              </button>
              {qrOpen && <PhoneQrPopover onClose={() => setQrOpen(false)} />}
            </div>
            {demo && <span className="mode-chip">Mode démonstration</span>}
            {tulipLive && (
              <span
                className={`tulip-chip${tulipLive.connected ? " connected" : " offline"}`}
                title={
                  tulipLive.connected
                    ? `Base Tulip : ${tulipLive.database ?? "connectée"}`
                    : tulipLive.error ?? "Tulip ne répond pas."
                }
              >
                <Icon name={tulipLive.connected ? "check" : "alert"} size={14} />
                {tulipLive.connected
                  ? tulipLive.write_enabled
                    ? "Tulip connecté"
                    : "Tulip en lecture seule"
                  : "Tulip non connecté"}
              </span>
            )}
            <Link to="/import" className="button button-primary button-sm">
              <Icon name="plus" size={16} />
              Ajouter une facture
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
