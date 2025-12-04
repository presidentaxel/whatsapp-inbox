"""
Script de diagnostic pour identifier pourquoi les webhooks ne stockent pas les messages
Vérifie les logs et teste le flux complet
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

PRODUCTION_URL = "https://whatsapp.lamaisonduchauffeurvtc.fr"


async def check_recent_messages():
    """Vérifie s'il y a des messages récents dans la base"""
    print("="*80)
    print("1. VÉRIFICATION DES MESSAGES EN BASE")
    print("="*80)
    
    try:
        # Messages entrants des dernières 24h
        result = await supabase_execute(
            supabase.table("messages")
            .select("id, direction, content_text, timestamp, wa_message_id")
            .eq("direction", "incoming")
            .order("timestamp", desc=True)
            .limit(10)
        )
        
        messages = result.data if result.data else []
        
        if messages:
            print(f"✅ {len(messages)} message(s) entrant(s) trouvé(s) récemment:")
            for msg in messages[:5]:
                print(f"   - {msg.get('timestamp')}: {msg.get('content_text', '')[:50]}")
        else:
            print("❌ Aucun message entrant trouvé dans la base de données")
            print("   Cela confirme que les webhooks ne stockent pas les messages")
        
        return len(messages) > 0
    except Exception as e:
        print(f"❌ Erreur lors de la vérification: {e}")
        return False


async def check_accounts():
    """Vérifie les comptes configurés"""
    print("\n" + "="*80)
    print("2. VÉRIFICATION DES COMPTES")
    print("="*80)
    
    try:
        accounts = await get_all_accounts()
        if not accounts:
            print("❌ Aucun compte trouvé dans la base de données")
            return None
        
        print(f"✅ {len(accounts)} compte(s) trouvé(s):")
        for acc in accounts:
            status = "✓ Actif" if acc.get("is_active") else "✗ Inactif"
            print(f"   - {acc.get('name')}: phone_number_id={acc.get('phone_number_id')} {status}")
        
        return accounts[0] if accounts else None
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None


async def test_webhook_format_real(account):
    """Teste avec le format réel des webhooks"""
    print("\n" + "="*80)
    print("3. TEST DU WEBHOOK AVEC FORMAT RÉEL")
    print("="*80)
    
    if not account:
        print("⚠️ Pas de compte disponible pour le test")
        return False
    
    phone_number_id = account.get("phone_number_id")
    
    # Format réel des webhooks (format production)
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": phone_number_id,  # Utiliser phone_number_id comme entry.id
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
                                        "name": "Test User Diagnostic"
                                    },
                                    "wa_id": "16315551181"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "16315551181",
                                    "id": "DIAGNOSTIC_TEST_" + str(int(asyncio.get_event_loop().time())),
                                    "timestamp": "1504902988",
                                    "type": "text",
                                    "text": {
                                        "body": "Message de test diagnostic - " + str(int(asyncio.get_event_loop().time()))
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
    
    print(f"Envoi du webhook avec phone_number_id: {phone_number_id}")
    print(f"Message ID: {payload['entry'][0]['changes'][0]['value']['messages'][0]['id']}")
    
    try:
        response = httpx.post(
            f"{PRODUCTION_URL}/webhook/whatsapp",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        print(f"\nStatus: {response.status_code}")
        print(f"Réponse: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook accepté par le serveur")
            print("\n⏳ Attente de 3 secondes pour que le traitement se termine...")
            await asyncio.sleep(3)
            
            # Vérifier si le message a été stocké
            message_id = payload['entry'][0]['changes'][0]['value']['messages'][0]['id']
            result = await supabase_execute(
                supabase.table("messages")
                .select("id, content_text, timestamp")
                .eq("wa_message_id", message_id)
                .limit(1)
            )
            
            if result.data:
                print(f"✅ Message stocké avec succès!")
                print(f"   ID: {result.data[0].get('id')}")
                print(f"   Contenu: {result.data[0].get('content_text')}")
                return True
            else:
                print(f"❌ Message NON stocké dans la base de données")
                print(f"   Le webhook a été accepté mais le traitement a échoué")
                print(f"   Vérifiez les logs du serveur pour voir l'erreur exacte")
                return False
        else:
            print(f"❌ Webhook rejeté: status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
        return False


async def test_webhook_format_meta_test(account):
    """Teste avec le format du test Meta (v24.0)"""
    print("\n" + "="*80)
    print("4. TEST DU WEBHOOK AVEC FORMAT TEST META (v24.0)")
    print("="*80)
    
    if not account:
        print("⚠️ Pas de compte disponible pour le test")
        return False
    
    phone_number_id = account.get("phone_number_id")
    
    # Format du test Meta (simplifié)
    payload = {
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
                        "name": "Test User Meta Format"
                    },
                    "wa_id": "16315551181"
                }
            ],
            "messages": [
                {
                    "from": "16315551181",
                    "id": "META_TEST_" + str(int(asyncio.get_event_loop().time())),
                    "timestamp": "1504902988",
                    "type": "text",
                    "text": {
                        "body": "Test format Meta - " + str(int(asyncio.get_event_loop().time()))
                    }
                }
            ]
        }
    }
    
    print(f"Envoi du webhook avec format test Meta")
    print(f"Message ID: {payload['value']['messages'][0]['id']}")
    
    try:
        response = httpx.post(
            f"{PRODUCTION_URL}/webhook/whatsapp",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        print(f"\nStatus: {response.status_code}")
        print(f"Réponse: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook accepté par le serveur")
            print("\n⏳ Attente de 3 secondes pour que le traitement se termine...")
            await asyncio.sleep(3)
            
            # Vérifier si le message a été stocké
            message_id = payload['value']['messages'][0]['id']
            result = await supabase_execute(
                supabase.table("messages")
                .select("id, content_text, timestamp")
                .eq("wa_message_id", message_id)
                .limit(1)
            )
            
            if result.data:
                print(f"✅ Message stocké avec succès!")
                return True
            else:
                print(f"❌ Message NON stocké")
                print(f"   Le format test Meta n'est peut-être pas encore supporté")
                return False
        else:
            print(f"❌ Webhook rejeté: status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
        return False


async def main():
    print("="*80)
    print("DIAGNOSTIC COMPLET DES WEBHOOKS")
    print("="*80)
    print(f"Backend URL: {PRODUCTION_URL}")
    print()
    
    # 1. Vérifier les messages existants
    has_messages = await check_recent_messages()
    
    # 2. Vérifier les comptes
    account = await check_accounts()
    
    if not account:
        print("\n❌ Impossible de continuer sans compte configuré")
        return
    
    # 3. Tester avec le format réel
    test1_ok = await test_webhook_format_real(account)
    
    # 4. Tester avec le format test Meta
    test2_ok = await test_webhook_format_meta_test(account)
    
    # Résumé
    print("\n" + "="*80)
    print("RÉSUMÉ DU DIAGNOSTIC")
    print("="*80)
    print(f"Messages existants en base: {'✅ Oui' if has_messages else '❌ Non'}")
    print(f"Format réel des webhooks: {'✅ Fonctionne' if test1_ok else '❌ Échoue'}")
    print(f"Format test Meta (v24.0): {'✅ Fonctionne' if test2_ok else '❌ Échoue'}")
    print()
    print("="*80)
    print("PROCHAINES ÉTAPES")
    print("="*80)
    
    if not test1_ok and not test2_ok:
        print("❌ Les deux formats échouent")
        print("   → Vérifiez les logs dans Render Dashboard → Logs")
        print("   → Cherchez les lignes avec '❌' pour voir les erreurs")
        print("   → Vérifiez que le phone_number_id correspond bien à un compte")
    elif test1_ok and not test2_ok:
        print("✅ Le format réel fonctionne")
        print("⚠️ Le format test Meta ne fonctionne pas (normal, c'est juste pour tester)")
        print("   → Les vrais webhooks de Meta devraient fonctionner")
    elif not test1_ok and test2_ok:
        print("⚠️ Le format test Meta fonctionne mais pas le format réel")
        print("   → Il y a peut-être un problème avec entry.id vs phone_number_id")
    else:
        print("✅ Les deux formats fonctionnent")
        print("   → Si vous ne recevez toujours pas de messages, vérifiez:")
        print("     1. Que Meta envoie bien les webhooks (logs Render)")
        print("     2. Que le phone_number_id dans les webhooks correspond à un compte")
    
    print()
    print("Pour voir les logs en temps réel:")
    print("  1. https://dashboard.render.com")
    print("  2. Service 'whatsapp-inbox-backend'")
    print("  3. Onglet 'Logs'")
    print("  4. Cherchez '📥 POST /webhook/whatsapp' pour voir les webhooks reçus")
    print("  5. Cherchez '❌' pour voir les erreurs")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
