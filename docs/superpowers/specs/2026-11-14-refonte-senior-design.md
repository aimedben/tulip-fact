# Refonte « senior » de l'interface Tulip Factures

Date : 2026-11-14
Statut : approuvé (refonte ciblée)

## Problème

L'application est fonctionnelle mais l'interface est faite pour un informaticien :
texte 13-14 px, boutons de 32 px, jargon (« Référentiel », « CU », « Sync Firebird »,
« Bon d'entrée »), codes Tulip à saisir à la main, et un bandeau « Tulip non connecté »
faux. Le risque métier majeur : l'interface annonce « créé » même quand l'écriture
dans la base Tulip a échoué.

## Objectif

Un commerçant senior qui connaît Tulip mais pas l'informatique doit pouvoir, sans
explication : ajouter un fournisseur, ajouter un article, vérifier une facture.
Chaque donnée créée doit être réellement écrite dans la base Tulip, et l'écran doit
le dire clairement.

## Décisions

1. **Style global senior** (un seul fichier `styles.css`, surcharge en fin de fichier)
   - corps de texte 16 px minimum, libellés 16 px, titres 24-28 px ;
   - boutons 48 px de haut minimum, texte 17 px, gras ;
   - champs de formulaire 48 px, texte 17 px ;
   - contraste renforcé, focus visible (anneau 3 px) ;
   - tableaux 15-16 px, lignes aérées ;
   - une action principale évidente par écran (bouton vert plein).

2. **Libellés simples**
   - Accueil, Ajouter une facture, Fournisseurs, Articles, Réglages ;
   - « Mettre à jour depuis Tulip » au lieu de « Sync Firebird » ;
   - « Bon d'entrée » → « écriture dans Tulip » dans les messages visibles.

3. **Codes Tulip générés automatiquement**
   - Fournisseur : prochain PRINCIPAL = `MAX(PRINCIPAL)` numérique + 1, format `%06d`.
   - Article : prochain CODE = `MAX(CODE)` positif hors sentinelle `2147483647`, + 1.
   - L'utilisateur ne saisit plus aucun code technique.

4. **Création atomique**
   - L'ordre devient : calcul du code Tulip → écriture Firebird → écriture SQLite.
   - Si Firebird échoue : aucun enregistrement local, erreur 422 en français.
   - Si Firebird réussit : l'enregistrement local porte le code Tulip réel, et la
     réponse contient `tulip_push.pushed = true` avec le code.

5. **Vérité à l'écran**
   - Bandeau Tulip alimenté par `/api/tulip/live/status` (état réel).
   - Après création : bandeau vert « Enregistré dans Tulip — n° … ».
   - En cas d'échec : bandeau rouge avec le message, rien n'est créé.

6. **Facture**
   - La validation affiche le résultat réel de l'export Tulip (`tulip_export`) :
     numéro de BE en cas de succès, message clair et bouton « Réessayer » sinon.

## Hors périmètre

- Refonte complète en assistants plein écran.
- Modification des écrans d'import OCR et de base de données (hors habillage).

## Preuve d'acceptation

Tests réels contre `E:\zjob\tulip\SUPERETTE.TFE`, puis nettoyage :
créer un fournisseur et un article depuis l'interface, vérifier les lignes dans
`CLIENTS` / `PRODUITS` / `CODEBARRE` par SQL, valider une facture, vérifier le
`BE` et `DETAILSBR`, puis supprimer les enregistrements de test.
