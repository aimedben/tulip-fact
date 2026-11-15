#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour ajouter un article directement dans Firebird
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.database import SessionLocal
from app.models import Product
from app.normalization import name_key
from app.services.tulip.product_writer import ProductWriter
from app.services.tulip.firebird import FirebirdError

def main():
    # Article a ajouter d'apres vos donnees:
    # lk44 sassouf sim zazou 6555584258 11 Unite:u 10%

    tulip_code = "11"
    designation = "sassouf sim zazou"
    supplier_ref = "lk44"
    barcode = "6555584258"
    stock_unit = "u"
    default_vat_rate = 10.0

    print("=" * 60)
    print("AJOUT D'ARTICLE DANS FIREBIRD")
    print("=" * 60)
    print(f"Code Tulip: {tulip_code}")
    print(f"Designation: {designation}")
    print(f"Reference fournisseur: {supplier_ref}")
    print(f"Code-barres: {barcode}")
    print(f"Unite: {stock_unit}")
    print(f"TVA: {default_vat_rate}%")
    print()

    db = SessionLocal()
    try:
        # 1. Verifier si existe deja en local
        existing = db.query(Product).filter(Product.tulip_code == tulip_code).first()

        if not existing:
            # Creer en local
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
            print(f"[OK] Article cree en base locale (ID: {product.id})")
        else:
            print(f"[INFO] Article {tulip_code} existe deja en local")

        print()
        print("Insertion dans Firebird...")

        # 2. Inserer dans Firebird
        writer = ProductWriter()

        # Verifier d'abord si existe
        if writer._product_exists(tulip_code):
            print(f"[ERREUR] Article {tulip_code} existe deja dans Firebird")
            print("Utilisez un autre code ou supprimez l'article existant dans Tulip")
            return

        result = writer.create_product(
            code=tulip_code,
            designation=designation,
            ref=supplier_ref,
            barcode=barcode,
            stock_unit=stock_unit,
            default_vat_rate=default_vat_rate,
            dry_run=False
        )

        print()
        print("[SUCCES] Article insere dans Firebird !")
        print(f"Table: {result.get('table')}")
        print(f"Code: {result.get('code')}")
        print(f"Designation: {result.get('designation')}")

        if result.get('barcode_inserted'):
            print(f"Code-barres insere: {result.get('barcode')}")
        elif result.get('barcode_error'):
            print(f"[AVERTISSEMENT] Code-barres non insere: {result.get('barcode_error')}")

        print()
        print("[TERMINE] Operation reussie !")

    except FirebirdError as e:
        print(f"[ERREUR FIREBIRD] {e}")
        print()
        print("Verifications:")
        print("1. Le code existe-t-il deja dans Firebird ?")
        print("2. La connexion Firebird est-elle active ?")
        print("3. TULIP_FB_WRITE_ENABLED=true dans .env ?")

    except Exception as e:
        db.rollback()
        print(f"[ERREUR] {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    main()
