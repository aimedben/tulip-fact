#!/usr/bin/env python3
"""
Script pour ajouter un nouvel article dans la base Firebird Tulip
"""
import sys
import os

# Ajouter le répertoire backend au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.database import SessionLocal
from app.models import Product
from app.normalization import name_key
from app.services.tulip.product_writer import ProductWriter
from app.services.tulip.firebird import FirebirdError

def add_product():
    """Ajoute un nouvel article dans la base locale et Firebird"""

    # Informations de l'article
    # D'après vos données : lk44 sassouf sim zazou 6555584258 11 Unité:u 10%
    # Je comprends :
    # - Code Tulip: 11 (doit être numérique)
    # - Désignation: sassouf sim zazou
    # - Référence fournisseur: lk44
    # - Code-barres: 6555584258
    # - Unité: u (unité)
    # - TVA: 10%

    tulip_code = "11"
    designation = "sassouf sim zazou"
    supplier_ref = "lk44"
    barcode = "6555584258"
    stock_unit = "u"
    default_vat_rate = 10.0

    print(f"🔧 Ajout de l'article:")
    print(f"   Code Tulip: {tulip_code}")
    print(f"   Désignation: {designation}")
    print(f"   Référence fournisseur: {supplier_ref}")
    print(f"   Code-barres: {barcode}")
    print(f"   Unité: {stock_unit}")
    print(f"   TVA: {default_vat_rate}%")
    print()

    # 1. Créer l'article dans la base locale (SQLite)
    db = SessionLocal()
    try:
        # Vérifier si l'article existe déjà en local
        existing = db.query(Product).filter(Product.tulip_code == tulip_code).first()
        if existing:
            print(f"⚠️  Article {tulip_code} existe déjà en base locale.")
            print(f"   Désignation actuelle: {existing.designation}")
            response = input("   Voulez-vous quand même essayer de l'insérer dans Firebird ? (o/n): ")
            if response.lower() != 'o':
                print("❌ Opération annulée.")
                return
        else:
            # Créer l'article en local
            product = Product(
                tulip_code=tulip_code,
                designation=designation,
                normalized_designation=name_key(designation),
                supplier_ref=supplier_ref,
                barcode=barcode,
                stock_unit=stock_unit,
                default_vat_rate=default_vat_rate,
                active=True
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            print(f"✅ Article créé en base locale (ID: {product.id})")

        # 2. Insérer dans Firebird
        print()
        print("🔥 Insertion dans Firebird Tulip...")

        try:
            writer = ProductWriter()
            result = writer.create_product(
                code=tulip_code,
                designation=designation,
                ref=supplier_ref,
                barcode=barcode,
                stock_unit=stock_unit,
                default_vat_rate=default_vat_rate,
                dry_run=False  # Vraie insertion, pas de simulation
            )

            print(f"✅ Article inséré dans Firebird !")
            print(f"   Table: {result.get('table')}")
            print(f"   Code: {result.get('code')}")
            print(f"   Désignation: {result.get('designation')}")
            if result.get('barcode_inserted'):
                print(f"   Code-barres inséré: {result.get('barcode')}")
            elif result.get('barcode_error'):
                print(f"   ⚠️  Code-barres NON inséré: {result.get('barcode_error')}")

            print()
            print("🎉 Opération terminée avec succès !")

        except FirebirdError as e:
            print(f"❌ Erreur Firebird: {e}")
            print()
            print("💡 Vérifications à faire:")
            print("   1. Le code article '11' existe-t-il déjà dans Firebird ?")
            print("   2. La connexion Firebird est-elle active ?")
            print("   3. Les écritures sont-elles activées ? (TULIP_FB_WRITE_ENABLED=true)")
            return

    except Exception as e:
        db.rollback()
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("  AJOUT D'ARTICLE DANS FIREBIRD TULIP")
    print("=" * 60)
    print()

    add_product()
