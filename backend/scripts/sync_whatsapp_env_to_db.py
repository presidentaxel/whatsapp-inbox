"""
Script pour synchroniser les variables d'environnement WhatsApp avec la base de données.
Remplit automatiquement les champs waba_id et business_id dans whatsapp_accounts.
"""
import asyncio
import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour importer app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.db import supabase, supabase_execute


async def sync_env_to_accounts():
    """
    Synchronise les variables d'environnement avec tous les comptes WhatsApp.
    """
    print("Synchronisation des variables d'environnement WhatsApp...")
    
    # Récupérer tous les comptes WhatsApp
    result = await supabase_execute(
        supabase.table("whatsapp_accounts").select("*")
    )
    
    accounts = result.data if result.data else []
    
    if not accounts:
        print("ATTENTION: Aucun compte WhatsApp trouve dans la base de donnees")
        return
    
    print(f"{len(accounts)} compte(s) trouve(s)")
    
    # Variables à synchroniser depuis l'env
    updates_needed = []
    
    for account in accounts:
        account_id = account["id"]
        needs_update = False
        update_data = {}
        
        # Vérifier waba_id
        if not account.get("waba_id") and hasattr(settings, "WHATSAPP_BUSINESS_ACCOUNT_ID"):
            waba_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID
            if waba_id:
                update_data["waba_id"] = waba_id
                needs_update = True
                print(f"  OK Compte {account['name']}: Ajout de waba_id = {waba_id}")
        
        # Vérifier business_id
        if not account.get("business_id") and hasattr(settings, "META_BUSINESS_ID"):
            business_id = settings.META_BUSINESS_ID
            if business_id:
                update_data["business_id"] = business_id
                needs_update = True
                print(f"  OK Compte {account['name']}: Ajout de business_id = {business_id}")
        
        # Vérifier app_id
        if not account.get("app_id") and hasattr(settings, "META_APP_ID"):
            app_id = settings.META_APP_ID
            if app_id:
                update_data["app_id"] = app_id
                needs_update = True
                print(f"  OK Compte {account['name']}: Ajout de app_id = {app_id}")
        
        # Vérifier app_secret
        if not account.get("app_secret") and hasattr(settings, "META_APP_SECRET"):
            app_secret = settings.META_APP_SECRET
            if app_secret:
                update_data["app_secret"] = app_secret
                needs_update = True
                print(f"  OK Compte {account['name']}: Ajout de app_secret = ***")
        
        if needs_update:
            updates_needed.append((account_id, update_data))
    
    # Appliquer les mises à jour
    if updates_needed:
        print(f"\nApplication des mises a jour...")
        for account_id, update_data in updates_needed:
            await supabase_execute(
                supabase.table("whatsapp_accounts")
                .update(update_data)
                .eq("id", account_id)
            )
        print(f"OK: {len(updates_needed)} compte(s) mis a jour avec succes!")
    else:
        print("\nOK: Tous les comptes sont deja a jour!")
    
    # Afficher un résumé
    print("\nResume:")
    print("=" * 60)
    result = await supabase_execute(
        supabase.table("whatsapp_accounts").select("id, name, waba_id, business_id, app_id")
    )
    for account in result.data:
        print(f"\n[{account['name']}] ({account['id'][:8]}...)")
        print(f"   WABA ID: {account.get('waba_id', 'Non configure')}")
        print(f"   Business ID: {account.get('business_id', 'Non configure')}")
        print(f"   App ID: {account.get('app_id', 'Non configure')}")


async def main():
    print("Script de synchronisation WhatsApp")
    print("=" * 60)
    
    # Vérifier que la migration des colonnes a été appliquée
    try:
        result = await supabase_execute(
            supabase.table("whatsapp_accounts").select("waba_id, business_id").limit(1)
        )
    except Exception as e:
        print("ERREUR: Les colonnes waba_id et business_id n'existent pas!")
        print("   Veuillez d'abord appliquer la migration 011_whatsapp_extended_fields.sql")
        print(f"   Erreur: {e}")
        return
    
    # Afficher les variables d'environnement disponibles
    print("\nVariables d'environnement detectees:")
    if hasattr(settings, "WHATSAPP_BUSINESS_ACCOUNT_ID"):
        print(f"   WHATSAPP_BUSINESS_ACCOUNT_ID: {settings.WHATSAPP_BUSINESS_ACCOUNT_ID or 'Non defini'}")
    if hasattr(settings, "META_BUSINESS_ID"):
        print(f"   META_BUSINESS_ID: {settings.META_BUSINESS_ID or 'Non defini'}")
    if hasattr(settings, "META_APP_ID"):
        print(f"   META_APP_ID: {settings.META_APP_ID or 'Non defini'}")
    if hasattr(settings, "META_APP_SECRET"):
        print(f"   META_APP_SECRET: {'***' if settings.META_APP_SECRET else 'Non defini'}")
    
    print("\n")
    
    await sync_env_to_accounts()
    
    print("\nSynchronisation terminee!")


if __name__ == "__main__":
    asyncio.run(main())

