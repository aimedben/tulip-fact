from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.synthetic import create_invoice_pdf, create_invoice_png  # noqa: E402


def main() -> int:
    target = PROJECT_ROOT / "examples" / "documents"
    target.mkdir(parents=True, exist_ok=True)
    create_invoice_pdf(target / "facture-fictive-001.pdf", "DEMO-FA-2026-001")
    create_invoice_pdf(target / "facture-fictive-multipage.pdf", "DEMO-FA-2026-003", split_pages=True)
    create_invoice_png(target / "facture-fictive-002.png", "DEMO-FA-2026-002")
    print(f"Documents fictifs créés dans {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
