import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "dashboard"
  | "upload"
  | "invoice"
  | "history"
  | "suppliers"
  | "products"
  | "settings"
  | "search"
  | "chevronLeft"
  | "chevronRight"
  | "zoomIn"
  | "zoomOut"
  | "rotate"
  | "check"
  | "alert"
  | "close"
  | "plus"
  | "trash"
  | "link"
  | "download"
  | "refresh"
  | "external"
  | "arrowLeft"
  | "clock"
  | "database"
  | "shield"
  | "eye"
  | "save"
  | "folder"
  | "spark"
  | "barcode"
  | "menu"
  | "spinner"
  | "x"
  | "sparkles"
  | "arrow-right"
  | "list"
  | "plus-circle"
  | "alert-triangle"
  | "check-circle"
  | "edit"
  | "qr";

const paths: Record<IconName, ReactNode> = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </>
  ),
  invoice: (
    <>
      <path d="M6 2h9l5 5v15l-3-2-3 2-3-2-3 2-2-1.5V2Z" />
      <path d="M14 2v6h6" />
      <path d="M9 13h7M9 17h5" />
    </>
  ),
  history: (
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  suppliers: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20c0-3 2.5-5 6-5s6 2 6 5" />
      <path d="M16 5a3 3 0 0 1 0 6" />
      <path d="M18 15c2 .6 3 2.2 3 5" />
    </>
  ),
  products: (
    <>
      <path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z" />
      <path d="M4 6.5 12 11l8-4.5" />
      <path d="M12 11v11" />
    </>
  ),
  settings: (
    <>
      <path d="M4 6h16M4 12h16M4 18h16" />
      <circle cx="9" cy="6" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="8" cy="18" r="2" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  chevronLeft: <path d="m15 18-6-6 6-6" />,
  chevronRight: <path d="m9 18 6-6-6-6" />,
  zoomIn: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M11 8v6M8 11h6M20 20l-4-4" />
    </>
  ),
  zoomOut: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M8 11h6M20 20l-4-4" />
    </>
  ),
  rotate: (
    <>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 3v6h-6" />
    </>
  ),
  check: <path d="m4 12 5 5L20 6" />,
  alert: (
    <>
      <path d="M10.3 3.6 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </>
  ),
  close: <path d="M18 6 6 18M6 6l12 12" />,
  plus: <path d="M12 5v14M5 12h14" />,
  trash: (
    <>
      <path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14" />
      <path d="M10 11v6M14 11v6" />
    </>
  ),
  link: (
    <>
      <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" />
      <path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M4 19h16" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 11a8 8 0 1 0-2 6" />
      <path d="M20 4v7h-7" />
    </>
  ),
  external: (
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4 11 13" />
      <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </>
  ),
  arrowLeft: (
    <>
      <path d="M19 12H5" />
      <path d="m11 18-6-6 6-6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </>
  ),
  shield: (
    <>
      <path d="M12 2 4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5l-8-3Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  save: (
    <>
      <path d="M5 3h12l4 4v14H3V3h2Z" />
      <path d="M7 3v6h9V3M7 21v-7h10v7" />
    </>
  ),
  folder: (
    <>
      <path d="M3 6a1 1 0 0 1 1-1h6l2 2h8a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6Z" />
    </>
  ),
  spark: (
    <>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
      <path d="m6 6 3 3M15 15l3 3M18 6l-3 3M9 15l-3 3" />
    </>
  ),
  barcode: (
    <>
      <path d="M4 5v14M7 5v14M10 5v10M13 5v14M16 5v10M19 5v14" />
    </>
  ),
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  spinner: (
    <>
      <path d="M12 2v4" />
      <path d="m16.2 7.8 2.9-2.9" />
      <path d="M18 12h4" />
      <path d="m16.2 16.2 2.9 2.9" />
      <path d="M12 18v4" />
      <path d="m4.9 19.1 2.9-2.9" />
      <path d="M2 12h4" />
      <path d="m4.9 4.9 2.9 2.9" />
    </>
  ),
  // Alias utilisés par les sélecteurs de fournisseur (noms lucide).
  x: <path d="M18 6 6 18M6 6l12 12" />,
  sparkles: (
    <>
      <path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3Z" />
      <path d="M19 15l.8 1.9 1.9.8-1.9.8L19 20.4l-.8-1.9-1.9-.8 1.9-.8L19 15Z" />
      <path d="M5 14l.7 1.6 1.6.7-1.6.7L5 18.6l-.7-1.6-1.6-.7 1.6-.7L5 14Z" />
    </>
  ),
  "arrow-right": (
    <>
      <path d="M5 12h14" />
      <path d="m13 18 6-6-6-6" />
    </>
  ),
  list: <path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />,
  "plus-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </>
  ),
  "alert-triangle": (
    <>
      <path d="M10.3 3.6 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </>
  ),
  "check-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </>
  ),
  edit: (
    <>
      <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 3 21l.5-4.5L17 3Z" />
    </>
  ),
  qr: (
    <>
      <rect x="3" y="3" width="5" height="5" rx="1" />
      <rect x="16" y="3" width="5" height="5" rx="1" />
      <rect x="3" y="16" width="5" height="5" rx="1" />
      <path d="M21 16h-3a2 2 0 0 0-2 2v3" />
      <path d="M21 21v.01" />
      <path d="M12 7v3a2 2 0 0 1-2 2H7" />
      <path d="M3 12h.01" />
      <path d="M12 3h.01" />
      <path d="M12 16v.01" />
      <path d="M16 12h1" />
      <path d="M21 12v.01" />
      <path d="M12 21v-1" />
    </>
  ),
};

export function Icon({
  name,
  size = 18,
  ...props
}: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
