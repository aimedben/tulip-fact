# Plan d'implémentation — refonte senior

Référence : `docs/superpowers/specs/2026-11-14-refonte-senior-design.md`

## Tâche 1 — Backend : codes Tulip automatiques

Fichiers : `backend/app/schemas.py`, `backend/app/services/tulip/supplier_writer.py`,
`backend/app/services/tulip/product_writer.py`.

1. `SupplierCreate.code` devient `str | None = None` ; `ProductCreate.tulip_code`
   devient `str | None = None`.
2. `SupplierWriter.next_principal()` : `SELECT FIRST 1 PRINCIPAL FROM CLIENTS
   WHERE FRCLT = -1 AND PRINCIPAL SIMILAR TO '[0-9]*' ORDER BY PRINCIPAL DESC`,
   convertit en int, +1, formate `%06d`. Ignore les PRINCIPAL non numériques
   (`rrr`) et les codes déjà pris (boucle de vérification).
3. `ProductWriter.next_code()` : `SELECT MAX(CODE) FROM PRODUITS WHERE CODE > 0
   AND CODE <> 2147483647`, +1, vérifie l'absence de collision.

## Tâche 2 — Backend : création atomique

Fichier : `backend/app/api/catalogs.py`.

1. `create_supplier` : si `payload.code` absent → `next_principal()` ; écrire
   d'abord dans Firebird (`SupplierWriter.create_supplier(dry_run=False)`) ;
   en cas de `FirebirdError` → `HTTPException 422` sans rien créer localement ;
   sinon créer le `Supplier` avec le PRINCIPAL réel et `tulip_push` renseigné.
2. `create_product` : idem avec `next_code()` et `ProductWriter.create_product`.
   La REF générée par Tulip est recopiée dans la fiche locale.
3. Si les écritures Firebird sont désactivées, la création locale reste possible
   (`tulip_push.pushed = false`) et l'UI le dit — mais aucun faux succès.

## Tâche 3 — Frontend : style senior

Fichier : `frontend/src/styles.css` — ajouter une section « Confort senior » en fin
de fichier qui surcharge : `body`, `.button`, `.button-primary`, `.field input`,
`.field select`, `.field textarea`, `.label`, `.data-table`, `.nav-item`,
`.topbar-title`, `.panel`, `.page-header`, `.badge`, `.notice`.

## Tâche 4 — Frontend : libellés et navigation

Fichiers : `components/Layout.tsx`, `pages/Dashboard.tsx`.

1. Menu : Accueil, Ajouter une facture, Fournisseurs, Articles, Réglages.
2. Chip Tulip piloté par `/api/tulip/live/status`.
3. Dashboard : titre simple, suppression de « Mistral OCR »/« export fichier »,
   cartes d'action « Ajouter une facture », « Voir les fournisseurs », etc.

## Tâche 5 — Frontend : formulaires fournisseur et article

Fichiers : `pages/SuppliersPage.tsx`, `pages/ProductsPage.tsx`.

1. Champ code Tulip supprimé à la création (conservé en lecture seule en édition).
2. Message de succès vert avec le code retourné ; message d'erreur rouge réel.
3. Article : désignation + code-barres + TVA suffisent ; référence facultative.

## Tâche 6 — Frontend : résultat Tulip d'une facture

Fichier : `pages/InvoiceReview.tsx`.

1. Après `validate`, lire `tulip_export` : succès → « Enregistrée dans Tulip,
   bon d'entrée n° X » ; échec → message + bouton « Réessayer l'enregistrement ».

## Tâche 7 — Build et déploiement

1. `npm run build` (écrit dans `backend/app/static`).
2. Copier `backend/app/static` → `F:\zjob\TulipFactures-exe\backend\app\static`.
3. Vider le cache navigateur avant vérification.

## Tâche 8 — Tests réels et nettoyage

1. Créer un fournisseur et un article depuis l'interface (Playwright).
2. Vérifier `CLIENTS`, `PRODUITS`, `CODEBARRE` par isql.
3. Valider une facture, vérifier `BE` + `DETAILSBR`.
4. Supprimer toutes les lignes de test (Firebird + SQLite).
