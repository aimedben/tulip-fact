# Intégration Tulip Gestion commerciale V3.33

## Statut

**Connexion Firebird en lecture seule validée. Écriture BE validée sur copie uniquement.**

Le connecteur Firebird a été testé sur la base réelle :

- moteur Firebird `2.5.9.27139` ;
- base `E:\zjob\tulip\SUPERETTE.TFE` ;
- client `isql.exe` 32 bits fourni avec Tulip ;
- lecture des fournisseurs, articles, lots, codes-barres et documents BE.

Aucune écriture n'a été effectuée dans la base de production. La séquence d'écriture BE a été validée sur une copie (`D:\Temp\SUPERETTE.TEST.TFE`) avec autorisation explicite du titulaire du poste, et l'écriture reste verrouillée en environnement réel par `TULIP_FB_WRITE_ENABLED=false`.

## Ce qui a été vérifié

| Élément | Constat |
| --- | --- |
| Tables principales | `BE`, `DETAILSBR`, `BCF`, `DETAILSBCF`, `CHARGESBE`, `PRODUITS`, `LOTS`, `CLIENTS`, `CODEBARRE`, `FOURPRODUITS`, `IO`, `INPUTOUTPUT` |
| BE | 5 563 lignes, toutes `CMP=0` et `STOCK=1` ; 5 561 avec `DETTE=1` |
| Détail BE | 31 441 lignes ; `PARENT` pointe vers `BE.CODE` |
| BCF | Vide ; `DETAILSBCF` contient une ligne |
| Articles | 7 112 produits, 7 108 actifs (`ETAT=0`, `NATURE IN (1,2,4,5,10)`) |
| Lots | 7 098 lots, un lot principal par produit |
| Codes-barres | 10 951 codes, unicité vérifiée |
| Fournisseurs | 303 fournisseurs actifs (`FRCLT=-1`, `ETAT=0`) |
| Totaux BE | `TTC = MHT - REMISE + MTVA + TIC + TIMBRE`, écart nul sur les 5 563 BE |
| Numérotation | Séries par `SFX`/`CMP` ; série courante `SFX=-32765`, prochain `NUMERO=2392` |

Triggers et procédures analysés :

- `BE_BI`, `BE_BU`, `BE_AU`, `BE_BD` ;
- `DETAILSBR_BI`, `DETAILSBR_AI`, `DETAILSBR_AU`, `DETAILSBR_AD` ;
- `CALCULER_BE`, `INSERT_E`, `UPDATE_E`, `DELETE_E`, `IO_INSERT`, `IO_UPDATE`, `SET_PMP`, `PRIX_REF`.

Points importants :

- `BE_AU` met à jour la dette fournisseur dans `CLIENTS.MOUVEMENT` (delta de `TTC` quand `DETTE=1`, changement de fournisseur géré) ;
- `DETAILSBR_AI` alimente `FOURPRODUITS`, exécute `INSERT_E` pour le stock, puis `CALCULER_BE` ;
- `DETAILSBR_AU` et `DETAILSBR_AD` mettent à jour le stock via `UPDATE_E`/`DELETE_E` ;
- aucun trigger n'écrit directement dans `STOCK` ;
- aucune procédure stockée ne crée un BE : l'application doit insérer l'en-tête et les lignes.

## Activation de la lecture seule

Renseigner ces variables dans `.env` local, sans jamais versionner le mot de passe :

```dotenv
TULIP_FB_ENABLED=true
TULIP_FB_HOST=localhost
TULIP_FB_PORT=3050
TULIP_FB_DATABASE=E:\zjob\tulip\SUPERETTE.TFE
TULIP_FB_USER=SYSDBA
TULIP_FB_PASSWORD=
TULIP_FB_ISQL_PATH=E:\zjob\firebird_2_5\bin\isql.exe
TULIP_FB_HOME=E:\zjob\firebird_2_5
TULIP_FB_CHARSET=WIN1252
TULIP_FB_WRITE_ENABLED=false
```

Le client `isql.exe` doit rester en 32 bits : le client Firebird installé est en 32 bits et aucun Python 32 bits n'est disponible sur le poste.

Endpoints de lecture :

- `GET /api/tulip/live/status`
- `GET /api/tulip/live/summary` : compteurs fournisseurs, articles, BE, dettes
- `GET /api/tulip/live/suppliers?q=&page=&page_size=`
- `GET /api/tulip/live/products?q=&page=&page_size=`
- `GET /api/tulip/live/products/{code}`
- `GET /api/tulip/live/be?q=&page=&page_size=` : bons d'achat (`BE`) les plus récents
- `GET /api/tulip/live/be/{code}` : détail d'un BE (lignes `DETAILSBR`)

Le tableau de bord de l'interface affiche ces données dans le panneau « Base Tulip » : statut de connexion, compteurs, derniers fournisseurs et derniers bons d'achat.

Endpoint d'écriture (verrouillé tant que `TULIP_FB_WRITE_ENABLED=false`) :

- `POST /api/tulip/live/be?dry_run=true` : prévisualisation des codes générés sans écriture ;
- `POST /api/tulip/live/be?dry_run=false` : insertion réelle `BE` + `DETAILSBR` dans la base pointée par `TULIP_FB_DATABASE`.

Le connecteur utilise un sous-processus `isql` par requête. Il n'y a pas encore de pool de connexions ni de cache persistant.

## Écriture BE : validée sur copie

Séquence effective, validée sur la copie `D:\Temp\SUPERETTE.TEST.TFE` (BE 2407, 1 ligne, PCA produit `MO...`) :

1. `INSERT BE` avec `DETTE=0`, agrégats à 0. Les colonnes `TTC`, `STOCK`, `INVOICE`, `INVOICEDATE` sont **calculées** (`RDB$COMPUTED_BLR`) : les inclure dans l'INSERT provoque l'erreur `attempted update of read-only column`.
2. `UPDATE BE SET DETTE=1` pendant que `TTC` vaut encore 0 : le trigger `BE_AU` comptabilise un delta nul sur `CLIENTS.MOUVEMENT`.
3. `INSERT DETAILSBR` : le trigger `DETAILSBR_BI` normalise `LOT=0` → `PRODUIT`, `ITEM=32767` → numérotation auto (`-32768`, `-32767`, …), et
   `ECART`/`OPDATE` ; `DETAILSBR_AI` exécute `INSERT_E` (mouvements stock `IO`/`INPUTOUTPUT`, `SET_PMP`, `PRIX_REF`), met à jour `FOURPRODUITS`, puis `CALCULER_BE` recalcule `MHT`/`REMISE`/`TTC`.
4. `BE_AU` voit alors le `TTC` passer de 0 à sa valeur définitive et porte la dette fournisseur : `CLIENTS.MOUVEMENT = MOUVEMENT - TTC`.
5. Les colonnes calculées de `DETAILSBR` (`QX`, `QE`, `PRIXHT`, `BALANCE`, `HT`) sont remplies par le moteur : interdites dans l'INSERT. `AUTRES` doit être 0 (jamais NULL), sinon la formule de `PRIXHT` devient NULL et `MHT` reste faux.

Vérifications faites sur BE 2407 (produit 12,5 DA x2, remise 10 %) :

- `MHT=25.00`, `REMISE=2.50`, `TTC=22.50`, `DETTE=1`, `STOCK=1` ;
- `CLIENTS.MOUVEMENT` : -9087.50 → -9110.00 (delta TTC exact) ;
- `IO.MOVEMENT` et `INPUTOUTPUT.ENTREES` incrémentés de 2 ; `SET_PMP` exécuté ;
- `DETAILSBR.ITEM=-32768`, `LOT` = lot principal du produit, `PRIXHT=11.25`.

L'en-tête, l'activation de la dette et toutes les lignes partent dans un seul script `isql` avec `SET BAIL ON` : en cas d'échec, la transaction est intégralement annulée. Les générateurs `BE`/`LINEBE` sont avancés avec contrôle d'existence (anti-collision PK). Le `NUMERO` reste calculé par série (`SFX=-32765`, `CMP=0`), confirmé par la série réelle en production.

## Informations encore nécessaires

- Validation du mapping des champs réels de facture (timbre, avoir, TVA multiple, BL distinct) vers `BE`/`DETAILSBR` sur des BE de référence saisis dans Tulip.
- Compte Firebird dédié, avec droits limités, à la place de `SYSDBA`.
- Validation des cas BCF/DETAILSBCF si les commandes fournisseur doivent être utilisées.
- Nettoyage des lignes test connues sur la copie (`NUMERO` ≥ 2402, `NBC` `TEST-API-*` / `OCR-FACT-*`) si la copie doit servir de référence.

## Procédure de validation recommandée

1. Obtenir un jeu de factures représentatif et une copie de la base.
2. Faire valider manuellement un bon d'entrée de référence par le client.
3. Comparer chaque champ avec la saisie de référence.
4. Tester les cas limites : remise, timbre, plusieurs taux de TVA, BL distinct, avoir, doublon.
5. Faire signer un procès-verbal de conformité avant tout traitement en production.
6. Conserver les fichiers sources, les exports et les journaux d'audit pour la traçabilité.

## Principes de sécurité

- Aucune écriture dans Tulip tant que la validation sur copie n'a pas réussi.
- Les exports restent des fichiers locaux à contrôler manuellement.
- Le statut « connecté » n'est affiché qu'après un test de lecture réussi.
- Le mot de passe Firebird ne doit jamais apparaître dans les logs, l'interface ou le code.
- Les factures validées ou exportées ne peuvent plus être supprimées.
- Les corrections sont historisées ; aucun écart comptable n'est corrigé silencieusement.

## Formats exportés

L'application génère, selon la demande :

- CSV lisible et contrôlable ;
- XLSX pour vérification tabulaire ;
- JSON structuré pour un futur adaptateur ;
- rapport de contrôle.

Ces formats ne doivent pas être présentés comme officiellement compatibles avec Tulip tant que le format cible n'a pas été confirmé.

## Pont facture scannee -> BE Tulip (implémente)

`POST /api/invoices/{id}/tulip/be?dry_run=true|false` reproduit la saisie manuelle Tulip d'un bon d'entrée à partir d'une facture scannée et validée :

Mapping appliqué (`services/tulip/invoice_be.py`) :
- BE.SFX = -32765, CMP = 0 ; DETTE = 1 posé par le writer après INSERT (TTC encore 0).
- FOURNISSEUR = `Supplier.code` (code Tulip négatif, issu de la sync fournisseurs).
- OPDATE = date facture ; NBC = n° BC (sinon n° facture) ; DATEBC = date BC ; LIVFACT = n° BL (sinon n° facture) ; DATEFACT = date facture.
- DETAILSBR par facture ligne rapprochée : PRODUIT = code Tulip numérique résolu via
  `TulipCatalog.product_by_code(product.tulip_code)` (REF ou code direct) ; QTE = quantité ;
  PUHT = prix unitaire HT facture ; TVA = taux ligne ; REMISE/TREMISE = remise ligne
  (percent -> 0, value -> 1). Les champs non fournis (MQX, ECART, UTIC…) sontisesti par le
  trigger DETAILSBR_BI depuis PRODUITS, et CALCULER_BE/SET_PMP recalcule les agrégats.

Sécurités :
- La facture doit être VALIDEE ou EXPORTEE ; toute ligne non rapprochée est signalée
  (`skipped_lines`) et refuse la création si aucune ligne exploitable.
- dry_run=true (défaut) calcule un aperçu (n° BE, fournisseur, lignes) sans écrire.
- L'écriture réelle exige `TULIP_FB_WRITE_ENABLED=true`, recommandé uniquement sur copie de test.
- Si un audit + ExportRecord « tulip_be » est tracé.

Tests : `backend/tests/test_tulip_invoice_be.py` (aperçu, refus facture non validée, lignes non rapprochées, garde write_enabled).
Validation E2E réelle : aperçu BE n°2392 (fournisseur 1004 LEGUMES, produit BE72 x2 à 25.00) sur la base de production en lecture seule, écriture refusée par le drapeau.
