# Guide de Migration : Tesseract → Mistral OCR

## Vue d'ensemble

Ce guide explique comment remplacer Tesseract par Mistral OCR pour une meilleure précision d'extraction de données de factures.

## Avantages de Mistral OCR

✅ **Précision maximale** : Modèle vision pixtral-large spécialisé pour les documents comptables
✅ **Extraction structurée** : Retour JSON structuré directement exploitable
✅ **Pas de preprocessing** : Mistral gère les images brutes (rotation, bruit, qualité)
✅ **Tableaux complexes** : Meilleure gestion des tableaux et mises en page
✅ **Tous formats** : PDF et images (PNG, JPEG) supportés

## Étape 1 : Configuration

### 1.1 Obtenir une clé API Mistral

1. Créer un compte sur https://console.mistral.ai/
2. Générer une clé API
3. Copier la clé API

### 1.2 Configurer les variables d'environnement

Ajouter à votre fichier `.env` :

```bash
# Obligatoire
MISTRAL_API_KEY=votre_cle_api_mistral_ici

# Optionnel (valeurs par défaut)
MISTRAL_API_BASE=https://api.mistral.ai/v1
MISTRAL_OCR_MODEL=pixtral-large-latest

# Mode OCR (auto utilisera Mistral si disponible)
TULIP_OCR_ENGINE=auto
```

### 1.3 Installer les dépendances

```bash
cd backend
pip install -r requirements.txt
```

## Étape 2 : Modes de fonctionnement

### Mode automatique (recommandé)

```bash
TULIP_OCR_ENGINE=auto
MISTRAL_API_KEY=votre_cle
```

**Comportement** :
- Si `MISTRAL_API_KEY` est définie → Utilise Mistral OCR
- Sinon → Fallback sur RapidOCR ou Tesseract

### Mode explicite Mistral

```bash
TULIP_OCR_ENGINE=mistral
MISTRAL_API_KEY=votre_cle
```

**Comportement** :
- Force l'utilisation de Mistral OCR
- Erreur si la clé API n'est pas configurée

### Mode fallback (sans Mistral)

```bash
TULIP_OCR_ENGINE=rapidocr
# ou
TULIP_OCR_ENGINE=tesseract
```

**Comportement** :
- Utilise RapidOCR ou Tesseract
- Mistral OCR non utilisé même si la clé est présente

## Étape 3 : Désinstallation de Tesseract (optionnel)

Si vous n'utilisez plus Tesseract comme fallback :

### Windows

```powershell
# Désinstaller Tesseract via les paramètres système
# ou via Chocolatey
choco uninstall tesseract

# Supprimer les données tessdata
Remove-Item -Recurse -Force C:\Program Files\Tesseract-OCR
```

### Linux

```bash
sudo apt-get remove tesseract-ocr
sudo apt-get autoremove
```

### macOS

```bash
brew uninstall tesseract
```

## Étape 4 : Test de l'intégration

### 4.1 Vérifier la configuration

```bash
cd backend
python -c "from app.services.ocr.mistral_engine import engine; print('Mistral disponible:', engine.available())"
```

Résultat attendu :
```
Mistral disponible: True
```

### 4.2 Scanner une facture test

1. Lancer l'application : `python -m app.main`
2. Accéder à http://localhost:8000
3. Uploader une facture
4. Vérifier que le moteur utilisé est "mistral-ocr" dans les logs

## Étape 5 : Monitoring et logs

Les logs indiqueront quel moteur OCR est utilisé :

```
INFO - Appel Mistral OCR pour /path/to/image.png (page 1)
INFO - Mistral OCR: 12 lignes extraites avec confiance 0.95
```

## Structure JSON retournée par Mistral

```json
{
  "fournisseur": {
    "nom": "Nom du fournisseur",
    "code": "CODE123",
    "adresse": "Adresse complète"
  },
  "facture": {
    "numero": "FAC-2024-001",
    "date": "01/11/2024",
    "type_document": "FACTURE",
    "devise": "EUR"
  },
  "totaux": {
    "total_ht": 1000.00,
    "total_tva": 200.00,
    "total_ttc": 1200.00
  },
  "lignes": [
    {
      "position": 1,
      "reference": "ART-001",
      "designation": "Article 1",
      "quantite": 10,
      "prix_unitaire_ht": 100.00,
      "montant_ht": 1000.00
    }
  ]
}
```

## Coûts estimés (Mistral OCR)

- **Modèle** : pixtral-large-latest
- **Prix** : ~0.0001€ par image (estimation)
- **Facture de 3 pages** : ~0.0003€

Bien plus précis que Tesseract gratuit mais avec un coût négligeable.

## Dépannage

### Erreur : "MISTRAL_API_KEY non configurée"

**Solution** : Vérifier que la variable d'environnement est bien définie dans `.env`

### Erreur : "Mistral n'a pas retourné un JSON valide"

**Cause** : Le modèle a retourné du texte au lieu de JSON

**Solution** :
1. Vérifier que vous utilisez `pixtral-large-latest` (meilleur pour la structuration)
2. L'image est peut-être illisible → Améliorer la qualité du scan

### Fallback automatique vers Tesseract

**Comportement normal** : Si Mistral échoue, le système utilise automatiquement RapidOCR ou Tesseract

### Performance lente

**Cause** : Mistral OCR fait un appel API réseau

**Solution** :
- Augmenter le timeout : `MISTRAL_TIMEOUT=180` dans `.env`
- Vérifier la connexion internet
- Utiliser un modèle plus léger : `MISTRAL_OCR_MODEL=pixtral-12b-latest`

## Rollback vers Tesseract

Si vous souhaitez revenir à Tesseract :

```bash
# Dans .env
TULIP_OCR_ENGINE=tesseract
# ou supprimer MISTRAL_API_KEY
```

Le système utilisera automatiquement Tesseract comme avant.

## Support

Pour toute question :
- Documentation Mistral : https://docs.mistral.ai/
- Issues GitHub du projet
