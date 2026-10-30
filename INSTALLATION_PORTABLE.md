# Guide d'Installation Portable - Tulip Factures

## Installation sur Clé USB

### Prérequis sur le PC cible
- Windows 10/11
- Python 3.12 ou supérieur
- Tesseract OCR 5.x avec langues française et anglaise

### Étapes d'installation

1. **Copier les fichiers sur la clé USB**
   - Copiez tout le dossier `tulip-factures` sur votre clé USB
   - Assurez-vous d'avoir au moins 2 GB d'espace libre

2. **Installation automatique**
   - Sur le PC cible, ouvrez PowerShell en tant qu'administrateur
   - Naviguez vers la clé USB : `cd E:\tulip-factures` (remplacez E: par votre lettre de lecteur)
   - Exécutez : `.\install.ps1`
   - Pour une installation portable (reste sur la clé) : `.\install.ps1 -Portable`
   - Pour choisir le dossier : `.\install.ps1 -InstallPath "C:\MesApplications\TulipFactures"`

3. **Configuration**
   - Éditez le fichier `.env` pour personnaliser les chemins
   - Important : Mettez à jour `TESSERACT_CMD` avec le chemin correct sur le PC cible
   - Configurez `TULIP_FB_DATABASE` pour pointer vers votre base Tulip

4. **Démarrage**
   - Double-cliquez sur le raccourci "Tulip Factures" créé sur le Bureau
   - OU exécutez `.\demarrer.ps1` depuis le dossier d'installation

## Installation Manuelle

Si le script automatique ne fonctionne pas :

```powershell
# 1. Créer l'environnement virtuel
python -m venv .venv

# 2. Activer l'environnement
.\.venv\Scripts\Activate.ps1

# 3. Installer les dépendances
pip install -r backend\requirements.txt

# 4. Copier la configuration
Copy-Item .env.example .env

# 5. Éditer .env avec vos paramètres

# 6. Compiler le frontend (optionnel, déjà compilé)
cd frontend
npm install
npm run build
cd ..

# 7. Démarrer l'application
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Vérification de l'installation

1. Ouvrez http://127.0.0.1:8000 dans votre navigateur
2. Allez dans Configuration (menu)
3. Vérifiez que :
   - ✓ OCR est disponible (langues fra et eng détectées)
   - ✓ Base de données est accessible
   - ✓ Stockage est inscriptible

## Sélection de la base de données Tulip

1. Dans l'interface, allez dans **Configuration**
2. Section **Base de données Firebird Tulip**
3. Cliquez sur **Parcourir** pour sélectionner votre fichier `.TFE`
4. Remplissez les autres champs :
   - Hôte : `localhost` (ou IP du serveur Firebird)
   - Port : `3050` (port par défaut)
   - Utilisateur : `SYSDBA`
   - Mot de passe : votre mot de passe Firebird
   - Chemin isql.exe : `E:\zjob\firebird_2_5\bin\isql.exe` (selon votre installation)
5. Cochez **Activer la connexion Firebird**
6. Cliquez sur **Enregistrer la configuration**

⚠️ **Important** : Laissez "Autoriser l'écriture" DÉSACTIVÉ sauf pour des tests sur une copie de la base.

## Sauvegarde et restauration

### Créer une sauvegarde
1. Dans Configuration, section "Sauvegarde locale"
2. Cliquez sur "Créer une sauvegarde"
3. Téléchargez le fichier ZIP créé
4. Conservez-le sur un support externe

### Restaurer une sauvegarde
1. Arrêtez l'application
2. Remplacez le dossier `data` par le contenu de votre sauvegarde
3. Redémarrez l'application

## Désinstallation

1. Arrêtez l'application
2. Sauvegardez le dossier `data` si vous souhaitez conserver vos factures
3. Supprimez le dossier d'installation
4. Supprimez le raccourci du Bureau

## Dépannage

### L'OCR ne fonctionne pas
- Vérifiez que Tesseract est installé : `tesseract --version`
- Vérifiez le chemin dans `.env` : `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`
- Vérifiez que les langues sont installées dans `tessdata`

### La base Firebird n'est pas accessible
- Vérifiez que le service Firebird est démarré
- Vérifiez le chemin du fichier `.TFE` dans la configuration
- Vérifiez que le client `isql.exe` est bien en 32 bits (fourni avec Tulip)
- Testez la connexion manuellement avec `isql`

### Port 8000 déjà utilisé
- Changez le port dans `.env` : `TULIP_PORT=8001`
- Redémarrez l'application
- Accédez à http://127.0.0.1:8001

### Erreur de permission PowerShell
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Support

- Documentation complète : `README.md`
- Documentation technique : `docs/`
- Exemples : `examples/`

## Sécurité

- L'application ne doit JAMAIS être exposée sur Internet
- Utilisez uniquement sur `127.0.0.1` (localhost)
- Les factures contiennent des données sensibles : protégez vos sauvegardes
- N'activez l'écriture Firebird que sur une copie de test
