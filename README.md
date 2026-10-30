# Factures fournisseurs — Tulip Gestion commerciale V3.33

Application locale Windows pour importer des factures fournisseurs (PDF, JPG, PNG), les OCRiser, extraire et contrôler les données, puis préparer un fichier d'entrée à contrôler avant saisie dans Tulip Gestion commerciale V3.33.

> **Statut Tulip : connexion Firebird en lecture seule validée, écriture non validée et désactivée.** La base `SUPERETTE.TFE` a été inspectée sans écriture. Les exports restent des fichiers locaux à contrôler manuellement tant que la création de BE n'a pas été validée sur une copie.

## Fonctionnalités

- Import PDF/JPG/PNG avec stockage local, empreinte SHA-256 et contrôle des doublons.
- OCR local Tesseract (`fra+eng`), sans envoi de document sur Internet par défaut.
- Extraction des champs d'en-tête, lignes, totaux, TVA et timbre.
- Rapprochement fournisseur et articles avec le référentiel local, scores et candidats.
- Recalcul indépendant des totaux et lignes ; les écarts sont signalés, jamais corrigés automatiquement.
- Revue visuelle du document à côté des données, correction historisée de l'en-tête et des lignes.
- Validation explicite avec verrouillage ; les factures validées ou exportées ne peuvent plus être supprimées.
- Exports CSV, XLSX, JSON et rapport de contrôle dans `data/exports`.
- Référentiels fournisseurs/articles avec import CSV/XLSX.
- Lecture optionnelle du catalogue réel Tulip/Firebird (fournisseurs et articles) via `isql` 32 bits.
- Sauvegarde locale ZIP de la base, des documents, pages et exports.
- Mode DEMO isolé du dossier de production.

## Prérequis

- Windows 10/11.
- Python 3.12 ou supérieur (testé avec Python 3.14.4).
- Node.js 20 ou supérieur (testé avec Node 25.9.0) pour reconstruire l'interface.
- Tesseract OCR 5.x installé, avec les langues française et anglaise.
- Un navigateur récent (Edge, Chrome, Firefox).

L'interface compilée est déjà présente dans `backend/app/static`. Node.js n'est nécessaire que pour la développement ou la reconstruction.

## Installation

Depuis PowerShell :

```powershell
cd C:\Users\Thinkpad\tulip-factures

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

cd frontend
npm install
npm run build
cd ..
```

Configurer ensuite l'environnement :

```powershell
Copy-Item .env.example .env
```

Vérifier au minimum :

- `TESSERACT_CMD` : chemin de `tesseract.exe`.
- `TESSDATA_PREFIX` : dossier contenant `fra.traineddata`, `eng.traineddata` et `osd.traineddata`.
- `TULIP_DATA_DIR` : laisser vide pour utiliser `data` (production) ou `data/demo`.

## Démarrage

### Mode DEMO

Le mode DEMO utilise `data/demo` et ne touche pas aux données de production.

```powershell
cd C:\Users\Thinkpad\tulip-factures\backend
$env:TULIP_APP_MODE = "demo"
python -m app.demo
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Ouvrir <http://127.0.0.1:8000>.

### Mode production

```powershell
cd C:\Users\Thinkpad\tulip-factures\backend
Remove-Item Env:TULIP_APP_MODE -ErrorAction SilentlyContinue
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Ouvrir <http://127.0.0.1:8000>. La documentation technique de l'API est disponible sur <http://127.0.0.1:8000/docs>.

L'application n'a pas d'authentification : la garder sur `127.0.0.1` et ne jamais l'exposer sur le réseau ou Internet.

### Développement de l'interface

```powershell
cd C:\Users\Thinkpad\tulip-factures\frontend
npm run dev
```

Vite sert l'interface sur <http://127.0.0.1:5173> et redirige `/api` vers le backend sur le port 8000.

## Tests

```powershell
cd C:\Users\Thinkpad\tulip-factures\backend
python -m pytest -q

cd ..\frontend
npm test
npm run build
```

Les tests backend couvrent l'import, l'OCR, l'extraction, le rapprochement, les doublons, la validation, les exports et la persistance. Les tests frontend couvrent les formats français et les montants.

## Données et sauvegarde

Par défaut :

```text
data/
  tulip_factures.db      base SQLite
  documents/             fichiers originaux
  pages/                 images de pages rendues
  exports/               CSV, XLSX, JSON et rapports
  backups/               archives ZIP
  logs/                  journaux applicatifs
```

Sauvegarde recommandée :

1. Arrêter l'application.
2. Copier tout le dossier `data` (ou utiliser « Créer une sauvegarde » dans Configuration).
3. Conserver une copie hors du disque de travail.

Restauration :

1. Arrêter l'application.
2. Remplacer le dossier `data` par la sauvegarde.
3. Redémarrer l'application et contrôler la page Configuration.

Les factures contiennent des données personnelles et commerciales : protéger les sauvegardes et limiter l'accès au poste.

## Limites connues

- La qualité OCR dépend de la numérisation, de l'orientation, du contraste et de la mise en page.
- Les écritures manuscrites, les tableaux complexes et les documents très dégradés peuvent nécessiter une correction manuelle.
- Le rapprochement fournisseur/article est assisté ; il doit être contrôlé.
- La détection de doublons est heuristique (empreinte du fichier et numéro fournisseur).
- Les exports ne sont pas garantis compatibles avec l'import Tulip tant que le format officiel n'a pas été validé.
- La lecture Firebird dépend du client `isql` 32 bits installé avec Tulip ; l'écriture BE n'est pas encore implémentée.
- Application mono-poste sans gestion multi-utilisateur ni rôles.
- L'extraction LLM est désactivée par défaut et n'est jamais utilisée sans configuration explicite.

## Intégration Tulip

Voir [docs/tulip-integration.md](docs/tulip-integration.md). En résumé :

- le connecteur Firebird est disponible en lecture seule, désactivé par défaut ;
- aucune écriture n'est effectuée dans Tulip ;
- l'écriture BE est préparée mais non activée ;
- l'automatisation de l'interface Windows reste désactivée ;
- les exports restent des propositions à contrôler avant toute saisie.

## Structure du projet

```text
backend/
  app/                 API FastAPI, modèles, OCR, extraction, contrôles, exports
  migrations/          migrations Alembic
  tests/               tests backend
  app/static/          interface compilée servie par FastAPI
frontend/
  src/                 interface React/TypeScript
docs/                  documentation d'intégration et d'exploitation
examples/              documents fictifs de démonstration
scripts/               génération de documents d'exemple
tessdata/              langues Tesseract embarquées
```
