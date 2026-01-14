"""
Script de diagnostic pour identifier pourquoi les nouveaux messages ne s'affichent plus.

Vérifie:
1. Si les messages sont bien sauvegardés dans Supabase
2. Si le compte est bien trouvé lors de la réception du webhook
3. Si les messages sont bien récupérés par l'API
4. Les logs récents du webhook
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_all_accounts, get_account_by_phone_number_id


async def check_recent_messages():
    """Vérifie les messages récents dans la base de données"""
    print("\n" + "="*80)
    print("1. VÉRIFICATION DES MESSAGES RÉCENTS DANS SUPABASE")
    print("="*80)
    
    # Récupérer les 20 derniers messages entrants
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    
    result = await supabase_execute(
        supabase.table("messages")
        .select("id, conversation_id, direction, content_text, timestamp, wa_message_id, message_type")
        .eq("direction", "inbound")
        .gte("timestamp", one_hour_ago)
        .order("timestamp", desc=True)
        .limit(20)
    )
    
    if not result.data:
        print("❌ AUCUN MESSAGE ENTRANT TROUVÉ DANS LA DERNIÈRE HEURE")
        print("   → Cela confirme que les messages ne sont pas sauvegardés")
        return
    
    print(f"✅ {len(result.data)} message(s) entrant(s) trouvé(s) dans la dernière heure:")
    for msg in result.data[:10]:  # Afficher les 10 premiers
        print(f"   - {msg['timestamp']}: {msg['content_text'][:50]}... (conversation_id: {msg['conversation_id']})")
    
    return result.data


async def check_accounts():
    """Vérifie que les comptes sont bien configurés"""
    print("\n" + "="*80)
    print("2. VÉRIFICATION DES COMPTES WHATSAPP")
    print("="*80)
    
    accounts = await get_all_accounts()
    
    if not accounts:
        print("❌ AUCUN COMPTE TROUVÉ DANS LA BASE DE DONNÉES")
        print("   → C'est probablement la cause du problème!")
        print("   → Les webhooks ne peuvent pas trouver le compte et skip les messages")
        return None
    
    print(f"✅ {len(accounts)} compte(s) trouvé(s):")
    for acc in accounts:
        status = "✅ ACTIF" if acc.get('is_active') else "❌ INACTIF"
        print(f"   {status} - {acc.get('name')}:")
        print(f"      - ID: {acc.get('id')}")
        print(f"      - phone_number_id: {acc.get('phone_number_id')}")
        print(f"      - verify_token: {'***' + str(acc.get('verify_token'))[-5:] if acc.get('verify_token') else 'MANQUANT'}")
    
    return accounts


async def check_conversations():
    """Vérifie les conversations récentes"""
    print("\n" + "="*80)
    print("3. VÉRIFICATION DES CONVERSATIONS RÉCENTES")
    print("="*80)
    
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    
    result = await supabase_execute(
        supabase.table("conversations")
        .select("id, account_id, client_number, updated_at, unread_count")
        .gte("updated_at", one_hour_ago)
        .order("updated_at", desc=True)
        .limit(10)
    )
    
    if not result.data:
        print("⚠️ Aucune conversation mise à jour dans la dernière heure")
    else:
        print(f"✅ {len(result.data)} conversation(s) mise(s) à jour dans la dernière heure:")
        for conv in result.data:
            print(f"   - {conv['client_number']}: updated_at={conv['updated_at']}, unread_count={conv.get('unread_count', 0)}")
    
    return result.data


async def check_webhook_logs():
    """Vérifie les logs récents du webhook (si disponibles)"""
    print("\n" + "="*80)
    print("4. VÉRIFICATION DES LOGS WEBHOOK")
    print("="*80)
    
    print("ℹ️ Pour voir les logs du webhook en temps réel, utilisez:")
    print("   docker logs -f <container_name> | grep webhook")
    print("   ou")
    print("   journalctl -u <service_name> -f | grep webhook")
    print("\n   Cherchez les messages contenant:")
    print("   - '📥 Webhook received'")
    print("   - '❌ CRITICAL: Cannot find account'")
    print("   - '📨 Processing X messages'")
    print("   - '✅ Message processed successfully'")


async def test_account_lookup():
    """Teste la recherche de compte par phone_number_id"""
    print("\n" + "="*80)
    print("5. TEST DE RECHERCHE DE COMPTE")
    print("="*80)
    
    accounts = await get_all_accounts()
    if not accounts:
        print("❌ Aucun compte disponible pour le test")
        return
    
    # Tester avec le premier compte
    test_account = accounts[0]
    phone_number_id = test_account.get('phone_number_id')
    
    if not phone_number_id:
        print(f"⚠️ Le compte '{test_account.get('name')}' n'a pas de phone_number_id")
        return
    
    print(f"🔍 Test de recherche avec phone_number_id: {phone_number_id}")
    found_account = await get_account_by_phone_number_id(phone_number_id)
    
    if found_account:
        print(f"✅ Compte trouvé: {found_account.get('name')} (ID: {found_account.get('id')})")
    else:
        print(f"❌ PROBLÈME: Le compte n'a pas pu être trouvé par phone_number_id!")
        print("   → C'est probablement la cause du problème")
        print("   → Les webhooks ne peuvent pas trouver le compte et skip les messages")


async def check_message_insertion():
    """Vérifie si les messages sont bien insérés avec les bons champs"""
    print("\n" + "="*80)
    print("6. VÉRIFICATION DE LA STRUCTURE DES MESSAGES")
    print("="*80)
    
    # Récupérer un message récent pour vérifier sa structure
    result = await supabase_execute(
        supabase.table("messages")
        .select("*")
        .eq("direction", "inbound")
        .order("timestamp", desc=True)
        .limit(1)
    )
    
    if not result.data:
        print("⚠️ Aucun message entrant trouvé pour vérifier la structure")
        return
    
    msg = result.data[0]
    print("✅ Structure d'un message entrant récent:")
    print(f"   - id: {msg.get('id')}")
    print(f"   - conversation_id: {msg.get('conversation_id')}")
    print(f"   - direction: {msg.get('direction')}")
    print(f"   - wa_message_id: {msg.get('wa_message_id')}")
    print(f"   - message_type: {msg.get('message_type')}")
    print(f"   - timestamp: {msg.get('timestamp')}")
    print(f"   - content_text: {msg.get('content_text', '')[:50]}...")


async def main():
    print("\n" + "="*80)
    print("DIAGNOSTIC: MESSAGES MANQUANTS")
    print("="*80)
    print(f"Date: {datetime.now(timezone.utc).isoformat()}")
    
    # 1. Vérifier les messages récents
    recent_messages = await check_recent_messages()
    
    # 2. Vérifier les comptes
    accounts = await check_accounts()
    
    # 3. Vérifier les conversations
    await check_conversations()
    
    # 4. Vérifier les logs webhook
    await check_webhook_logs()
    
    # 5. Tester la recherche de compte
    await test_account_lookup()
    
    # 6. Vérifier la structure des messages
    await check_message_insertion()
    
    # Résumé
    print("\n" + "="*80)
    print("RÉSUMÉ ET RECOMMANDATIONS")
    print("="*80)
    
    if not accounts:
        print("❌ PROBLÈME CRITIQUE: Aucun compte WhatsApp trouvé")
        print("   → Les webhooks ne peuvent pas traiter les messages")
        print("   → SOLUTION: Vérifiez que les comptes sont bien créés dans la table whatsapp_accounts")
    elif not recent_messages:
        print("❌ PROBLÈME: Aucun message entrant dans la dernière heure")
        print("   → Soit aucun message n'a été reçu")
        print("   → Soit les messages ne sont pas sauvegardés (vérifiez les logs webhook)")
        print("   → SOLUTION: Vérifiez les logs du backend pour voir si les webhooks arrivent")
    else:
        print("✅ Les messages sont bien sauvegardés dans Supabase")
        print("   → Le problème est probablement côté frontend ou dans la récupération")
        print("   → Vérifiez:")
        print("     1. Les subscriptions Supabase Realtime fonctionnent")
        print("     2. Le polling fonctionne (toutes les 4.5 secondes)")
        print("     3. Les permissions RLS dans Supabase")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(main())

