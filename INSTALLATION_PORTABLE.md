# Tulip Factures — dossier portable (Windows 7, 8, 10, 11)

**Aucune installation. Aucun accès Internet. Tout est dans ce dossier.**

Copiez le dossier entier sur le PC, double-cliquez, c'est tout. Il contient déjà
Python 3.8 (32 bits), le serveur de l'application, l'interface, le moteur OCR et
ses modèles, le client Firebird 2.5, les runtimes C/C++ et un navigateur Firefox
portable. Rien n'est installé dans Windows, aucune clé de registre n'est écrite.

---

## 1. Prérequis

| Élément | Exigence |
|---|---|
| Windows | Windows 7 **SP1** ou plus récent (32 ou 64 bits) |
| Espace disque | ~600 Mo |
| Droits | Pouvoir écrire dans le dossier (évitez `C:\Program Files`) |
| Internet | **inutile** |
| Firebird | Le serveur Firebird du logiciel **Tulip/GCP** doit tourner sur le PC (port 3050) ou être joignable sur le réseau |
| Base Tulip | Le fichier `.TFE` existant (ex. `SUPERETTE.TFE`) |

> L'application **ne crée jamais** de base Firebird. Elle se contente de lire et
> d'écrire dans la base Tulip existante.

---

## 2. Mise en route (3 étapes)

1. **Copier** le dossier complet sur le disque local, par exemple
   `C:\TulipFactures` (pas dans `Program Files`, pas depuis une clé USB : c'est
   plus lent et le dossier doit rester inscriptible).

2. **Double-cliquer `1-REGLER-CONNEXION-TULIP.bat`**
   - la fenêtre « Configuration de la connexion Tulip » s'ouvre ;
   - elle détecte automatiquement la base `.TFE` et le client Firebird
     embarqué (`firebird\bin\isql.exe`) ;
   - si un champ reste vide, cliquez sur **Détecter automatiquement** : la base,
     le client Firebird et le serveur sont recherchés sur ce PC **et sur le
     réseau local** (aucun chemin à connaître) ;
   - cliquez **Tester la connexion** : le moteur doit s'afficher (ex. `2.5.9`) ;
   - cochez **Autoriser l'écriture dans Tulip** si nécessaire ;
   - cliquez **Enregistrer** : la configuration est écrite dans `.env`.

3. **Double-cliquer `TulipFactures.exe`**
   - la fenêtre du lanceur affiche l'état de la liaison Tulip ;
   - le tableau de bord s'ouvre dans le **Firefox portable** du dossier
     (`navigateur\firefox.exe`) ;
   - le bouton **Connexion Tulip…** permet de rouvrir la configuration à tout
     moment.

> Si la base ou `isql.exe` ne sont pas détectés, indiquez-les manuellement dans
> la fenêtre de configuration (bouton **Parcourir**). Le client Firebird embarqué
> est toujours proposé en premier.

---

## 3. Ce qui est embarqué (et pourquoi)

| Composant | Fichier / dossier | Rôle |
|---|---|---|
| Python 3.8.10 32 bits | `python38.dll`, `TulipFactures.exe` | exécute l'application sans Python installé |
| Runtime C universel (UCRT) | `ucrtbase.dll`, `api-ms-win-crt-*.dll` | Windows 7 sans KB2999226 ne l'a pas : il est fourni ici |
| Runtime C++ | `MSVCP140.dll` (14.30), `VCRUNTIME140.dll` | version compatible Windows 7 |
| Client Firebird 2.5 | `firebird\` (isql, fbclient, intl, assembly VC80) | joint la base Tulip sans installer Firebird |
| Navigateur | `navigateur\` (Firefox ESR 115) | IE11 ne sait pas afficher l'interface |
| OCR | `rapidocr_onnxruntime\models\*.onnx`, `tessdata\` | lecture des factures, 100 % hors ligne |
| Interface | `backend\app\static\` | pages compilées, aucune ressource externe |

Le dossier `firebird\` sert uniquement de **client** : le serveur Firebird reste
celui de Tulip. Si le PC Tulip est ailleurs sur le réseau, mettez son adresse IP
dans le champ **Serveur (hôte)** de la configuration.

---

## 4. Accès depuis un téléphone (QR)

- L'icône **QR** en haut du tableau de bord affiche l'adresse
  `http://<ip-du-pc>:8000`.
- Autorisez le port **8000** dans le pare-feu Windows (réseau privé).
- Le téléphone doit être sur le **même réseau local** (pas d'Internet requis).

---

## 5. Écriture dans Tulip

La case **Autoriser l'écriture dans Tulip** autorise la modification de la base
réelle (articles, fournisseurs, bons d'achat). Pour un premier essai, laissez-la
décochée : l'application fonctionne en lecture seule.

---

## 6. Dépannage

| Symptôme | Cause / solution |
|---|---|
| Page blanche dans le navigateur | Ne pas utiliser Internet Explorer 11. Utilisez le Firefox du dossier (ouvert automatiquement) |
| « api-ms-win-crt-… introuvable » alors que le dossier semble complet | La copie est incomplète : recopiez **tout** le dossier, y compris `ucrtbase.dll` et les `api-ms-win-*.dll` à la racine |
| « Connexion Firebird Tulip non configurée » | Relancez `1-REGLER-CONNEXION-TULIP.bat` et testez la connexion |
| « Serveur Firebird injoignable » | Lancez le logiciel Tulip/GCP (son serveur Firebird), vérifiez l'hôte et le port 3050 |
| « Utilisateur ou mot de passe refusé » | Identifiants Firebird (par défaut `SYSDBA` / `masterkey`) |
| Le port 8000 est déjà utilisé | Fermez l'autre application, ou modifiez `TULIP_PORT` dans `.env` |
| Le QR ne s'ouvre pas sur le téléphone | Pare-feu : autoriser le port 8000 en réseau privé |

Un journal est écrit dans `data\launcher-error.log` en cas d'échec au démarrage.

---

## 7. Données et sauvegarde

- Vos factures importées sont dans `data\tulip_factures.db` (base SQLite locale).
- Copiez le dossier `data\` pour sauvegarder ou transférer vos factures.
- Pour repartir de zéro : arrêtez l'application, renommez `data\` en
  `data-sauvegarde\`, puis **restaurez une copie de `data\tulip_factures.db`**
  (l'application ne crée jamais de base : sans ce fichier elle affiche
  « Base de données introuvable » et propose de relier une base existante).

## 8. Désinstallation

Arrêtez l'application, sauvegardez `data\` si besoin, puis supprimez le dossier.
Rien d'autre n'a été installé sur le PC.
