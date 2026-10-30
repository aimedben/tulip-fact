from __future__ import annotations

import importlib.util
import platform
from typing import Any

from ...config import settings
from .firebird import FirebirdConfig

MISSING_INFORMATION = [
    "Autorisation explicite de tester une écriture BE sur une copie ou un environnement de test.",
    "Validation du mapping des champs de facture vers BE/DETAILSBR sur un bon d'entrée de référence.",
    "Règles métier exactes de la case « BL = Facture », des avoirs, remises, timbres et taux de TVA.",
    "Compte Firebird dédié avec droits limités, à utiliser à la place de SYSDBA.",
    "Validation des cas BCF/DETAILSBCF si les commandes fournisseur doivent être utilisées.",
]

ULTRON = "L'intégration Tulip n'est pas confirmée. Aucune écriture dans Tulip n'est effectuée par l'application."


def _pywinauto_available() -> bool:
    return importlib.util.find_spec("pywinauto") is not None


def integration_status() -> dict[str, Any]:
    return {
        "mode": settings.tulip_integration_mode,
        "connected": False,
        "confirmed": False,
        "message": ULTRON,
        "platform": platform.platform(),
        "firebird": {
            **FirebirdConfig.from_settings().public_status(),
            "connected": False,
            "note": "Connecteur lecture seule. L'écriture BE n'est pas encore activée.",
        },
        "methods": {
            "import_officiel": {
                "supported": False,
                "reason": "Aucun format d'import officiel Tulip V3.33 n'a été fourni ni vérifié.",
            },
            "api_web_service": {
                "supported": False,
                "reason": "Aucune API Tulip documentée ou authentifiée n'est disponible.",
            },
            "automatisation_ui": {
                "supported": False,
                "enabled": settings.tulip_ui_enabled,
                "pywinauto_installed": _pywinauto_available(),
                "reason": (
                    "Adaptateur présent mais désactivé par défaut. Il faut identifier les contrôles réels "
                    "et valider la saisie sur un environnement de test."
                ),
            },
        },
        "exports": {
            "available": True,
            "note": (
                "Les fichiers CSV/XLSX/JSON produits sont des fichiers de travail. "
                "Ils ne sont pas déclarés importables dans Tulip sans vérification du format accepté."
            ),
        },
        "missing_information": MISSING_INFORMATION,
    }


def probe_ui() -> dict[str, Any]:
    status = integration_status()
    if not settings.tulip_ui_enabled:
        return {
            **status,
            "probe": {
                "performed": False,
                "reason": "TULIP_UI_AUTOMATION_ENABLED n'est pas activé. Aucune fenêtre n'a été inspectée.",
            },
        }
    if not _pywinauto_available():
        return {
            **status,
            "probe": {
                "performed": False,
                "reason": "pywinauto n'est pas installé. Installez-le uniquement sur un poste de test autorisé.",
            },
        }
    try:
        from pywinauto import Desktop

        windows: list[dict[str, Any]] = []
        for window in Desktop(backend="uia").windows():
            try:
                title = window.window_text()
            except Exception:
                continue
            if settings.tulip_ui_window_title.lower() in (title or "").lower():
                windows.append(
                    {
                        "title": title,
                        "class_name": window.class_name(),
                        "control_type": window.element_info.control_type,
                    }
                )
        return {
            **status,
            "probe": {
                "performed": True,
                "windows": windows,
                "note": "Inspection en lecture seule. Aucun champ n'a été saisi et aucun bouton n'a été cliqué.",
            },
        }
    except Exception as exc:
        return {
            **status,
            "probe": {
                "performed": False,
                "reason": f"Échec de l'inspection des fenêtres ({type(exc).__name__}).",
            },
        }
