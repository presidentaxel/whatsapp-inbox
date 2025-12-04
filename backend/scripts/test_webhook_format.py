"""
Script pour tester le format du webhook et diagnostiquer pourquoi les messages ne sont pas stockés
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Ajouter le répertoire backend au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# Charger les variables d'environnement
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_all_accounts


async def get_phone_number_ids():
    """Récupère tous les phone_number_id des comptes"""
    accounts = await get_all_accounts()
    return [acc.get("phone_number_id") for acc in accounts if acc.get("phone_number_id")]


async def test_webhook_format_v24():
    """Teste avec le format v24.0 de Meta (format du test)"""
    print("="*80)
    print("TEST 1: Format v24.0 (format du test Meta)")
    print("="*80)
    
    accounts = await get_all_accounts()
    if not accounts:
        print("❌ Aucun compte trouvé dans la base de données")
        return
    
    # Utiliser le premier compte actif
    account = accounts[0]
    phone_number_id = account.get("phone_number_id")
    
    print(f"Utilisation du compte: {account.get('name')} (phone_number_id: {phone_number_id})")
    
    # Format du test Meta (v24.0) - format simplifié
    payload_test_format = {
        "field": "messages",
        "value": {
            "messaging_product": "whatsapp",
            "metadata": {
                "display_phone_number": "16505551111",
                "phone_number_id": phone_number_id
            },
            "contacts": [
                {
                    "profile": {
                        "name": "test user name"
                    },
                    "wa_id": "16315551181"
                }
            ],
            "messages": [
                {
                    "from": "16315551181",
                    "id": "ABGGFlA5Fpa_TEST",
                    "timestamp": "1504902988",
                    "type": "text",
                    "text": {
                        "body": "this is a test message from Meta test button"
                    }
                }
            ]
        }
    }
    
    print("\nFormat du payload (format test Meta):")
    print(json.dumps(payload_test_format, indent=2, ensure_ascii=False))
    
    # Tester avec l'endpoint de production
    webhook_url = "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"
    
    try:
        response = httpx.post(
            webhook_url,
            json=payload_test_format,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        print(f"\n✓ Requête envoyée")
        print(f"Status: {response.status_code}")
        print(f"Réponse: {response.text}")
        
        if response.status_code == 200:
            print("\n⚠️ Le serveur a accepté la requête, mais le format n'est peut-être pas correct")
            print("   Le format du test Meta est différent du format réel des webhooks")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")


async def test_webhook_format_real():
    """Teste avec le format réel des webhooks (format production)"""
    print("\n" + "="*80)
    print("TEST 2: Format réel des webhooks (format production)")
    print("="*80)
    
    accounts = await get_all_accounts()
    if not accounts:
        print("❌ Aucun compte trouvé dans la base de données")
        return
    
    # Utiliser le premier compte actif
    account = accounts[0]
    phone_number_id = account.get("phone_number_id")
    entry_id = account.get("phone_number_id")  # ou WABA_ID si disponible
    
    print(f"Utilisation du compte: {account.get('name')} (phone_number_id: {phone_number_id})")
    
    # Format réel des webhooks (format production)
    payload_real_format = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": entry_id,
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "16505551111",
                                "phone_number_id": phone_number_id
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "test user name"
                                    },
                                    "wa_id": "16315551181"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "16315551181",
                                    "id": "ABGGFlA5Fpa_REAL",
                                    "timestamp": "1504902988",
                                    "type": "text",
                                    "text": {
                                        "body": "this is a test message with real webhook format"
                                    }
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }
    
    print("\nFormat du payload (format réel):")
    print(json.dumps(payload_real_format, indent=2, ensure_ascii=False))
    
    # Tester avec l'endpoint de production
    webhook_url = "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"
    
    try:
        response = httpx.post(
            webhook_url,
            json=payload_real_format,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        print(f"\n✓ Requête envoyée")
        print(f"Status: {response.status_code}")
        print(f"Réponse: {response.text}")
        
        if response.status_code == 200:
            print("\n✓ Le serveur a accepté la requête")
            print("   Vérifiez maintenant dans la base de données si le message a été stocké")
            
            # Attendre un peu puis vérifier
            await asyncio.sleep(2)
            result = await supabase_execute(
                supabase.table("messages")
                .select("id, content_text, timestamp, wa_message_id")
                .eq("wa_message_id", "ABGGFlA5Fpa_REAL")
                .limit(1)
            )
            
            if result.data:
                print(f"\n✅ Message stocké avec succès!")
                print(f"   ID: {result.data[0].get('id')}")
                print(f"   Contenu: {result.data[0].get('content_text')}")
            else:
                print(f"\n⚠️ Message non trouvé dans la base de données")
                print("   Vérifiez les logs du serveur pour voir ce qui s'est passé")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")


async def check_accounts():
    """Vérifie les comptes configurés"""
    print("\n" + "="*80)
    print("COMPTES CONFIGURÉS")
    print("="*80)
    
    accounts = await get_all_accounts()
    if not accounts:
        print("❌ Aucun compte trouvé")
        return
    
    print(f"✓ {len(accounts)} compte(s) trouvé(s):\n")
    for acc in accounts:
        print(f"  - {acc.get('name')}")
        print(f"    phone_number_id: {acc.get('phone_number_id')}")
        print(f"    Actif: {'✓' if acc.get('is_active') else '✗'}")
        print()


async def main():
    print("="*80)
    print("DIAGNOSTIC DU FORMAT DES WEBHOOKS")
    print("="*80)
    
    # Vérifier les comptes
    await check_accounts()
    
    # Tester les deux formats
    await test_webhook_format_v24()
    await test_webhook_format_real()
    
    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("Le format du test Meta (v24.0) est différent du format réel des webhooks.")
    print("Le format réel utilise 'object' et 'entry', tandis que le test utilise 'field' et 'value'.")
    print("\nPour que les messages soient stockés, Meta doit envoyer le format réel,")
    print("pas le format du test. Les tests Meta servent juste à vérifier que l'URL répond.")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

