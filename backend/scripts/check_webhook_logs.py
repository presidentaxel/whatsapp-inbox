"""
Script pour vérifier si les webhooks arrivent et à quoi ressemblent les logs
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase, supabase_execute

# Couleurs
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_section(title: str):
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")


def print_success(msg: str):
    print(f"{GREEN}✅ {msg}{RESET}")


def print_error(msg: str):
    print(f"{RED}❌ {msg}{RESET}")


def print_warning(msg: str):
    print(f"{YELLOW}⚠️  {msg}{RESET}")


def print_info(msg: str):
    print(f"{BLUE}ℹ️  {msg}{RESET}")


async def check_recent_messages_in_db():
    """Vérifie les messages récents dans la base"""
    print_section("1. MESSAGES EN BASE DE DONNÉES")
    
    try:
        # Messages entrants des dernières 24h
        yesterday = datetime.now().replace(tzinfo=None) - timedelta(days=1)
        
        result = await supabase_execute(
            supabase.table("messages")
            .select("id, direction, content_text, timestamp, wa_message_id, message_type, conversation_id")
            .eq("direction", "inbound")
            .gte("timestamp", yesterday.isoformat())
            .order("timestamp", desc=True)
            .limit(50)
        )
        
        messages = result.data or []
        
        if messages:
            print_success(f"{len(messages)} message(s) entrant(s) trouvé(s) dans les dernières 24h:")
            print()
            for msg in messages[:10]:
                timestamp = msg.get("timestamp", "")[:19] if msg.get("timestamp") else "N/A"
                msg_type = msg.get("message_type", "text")
                content = (msg.get("content_text", "") or "")[:60]
                wa_id = msg.get("wa_message_id", "N/A")[:20]
                print(f"  📨 {timestamp} | {msg_type:10} | {content}")
                print(f"      wa_message_id: {wa_id} | conversation_id: {msg.get('conversation_id', 'N/A')}")
                print()
            return True
        else:
            print_warning("Aucun message entrant trouvé dans les dernières 24h")
            print_info("Cela signifie que soit:")
            print_info("  1. Aucun message n'a été envoyé")
            print_info("  2. Les webhooks n'arrivent pas")
            print_info("  3. Les webhooks arrivent mais le traitement échoue")
            return False
            
    except Exception as e:
        print_error(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_all_recent_messages():
    """Vérifie TOUS les messages récents (entrants et sortants)"""
    print_section("2. TOUS LES MESSAGES RÉCENTS (ENTRANTS + SORTANTS)")
    
    try:
        yesterday = datetime.now().replace(tzinfo=None) - timedelta(days=1)
        
        result = await supabase_execute(
            supabase.table("messages")
            .select("id, direction, content_text, timestamp, wa_message_id, message_type")
            .gte("timestamp", yesterday.isoformat())
            .order("timestamp", desc=True)
            .limit(20)
        )
        
        messages = result.data or []
        
        if messages:
            print_info(f"{len(messages)} message(s) trouvé(s) dans les dernières 24h:")
            print()
            inbound_count = sum(1 for m in messages if m.get("direction") == "inbound")
            outbound_count = sum(1 for m in messages if m.get("direction") == "outbound")
            print(f"  📥 Entrants: {inbound_count}")
            print(f"  📤 Sortants: {outbound_count}")
            print()
            
            for msg in messages[:10]:
                direction = "📥" if msg.get("direction") == "inbound" else "📤"
                timestamp = msg.get("timestamp", "")[:19] if msg.get("timestamp") else "N/A"
                msg_type = msg.get("message_type", "text")
                content = (msg.get("content_text", "") or "")[:50]
                print(f"  {direction} {timestamp} | {msg_type:10} | {content}")
        else:
            print_warning("Aucun message trouvé dans les dernières 24h")
            
    except Exception as e:
        print_error(f"Erreur: {e}")


async def check_conversations_with_messages():
    """Vérifie les conversations qui ont des messages"""
    print_section("3. CONVERSATIONS AVEC MESSAGES")
    
    try:
        # Conversations mises à jour récemment
        yesterday = datetime.now().replace(tzinfo=None) - timedelta(days=1)
        
        result = await supabase_execute(
            supabase.table("conversations")
            .select("id, client_number, updated_at, unread_count, account_id")
            .gte("updated_at", yesterday.isoformat())
            .order("updated_at", desc=True)
            .limit(10)
        )
        
        conversations = result.data or []
        
        if conversations:
            print_success(f"{len(conversations)} conversation(s) mise(s) à jour récemment:")
            print()
            
            for conv in conversations:
                conv_id = conv.get("id")
                client = conv.get("client_number", "N/A")
                updated = conv.get("updated_at", "")[:19] if conv.get("updated_at") else "N/A"
                unread = conv.get("unread_count", 0)
                
                # Compter les messages de cette conversation
                msg_result = await supabase_execute(
                    supabase.table("messages")
                    .select("id", count="exact")
                    .eq("conversation_id", conv_id)
                )
                msg_count = msg_result.count if hasattr(msg_result, 'count') else len(msg_result.data) if msg_result.data else 0
                
                print(f"  💬 {client}")
                print(f"      Dernière mise à jour: {updated}")
                print(f"      Messages: {msg_count} | Non lus: {unread}")
                print()
        else:
            print_warning("Aucune conversation mise à jour récemment")
            
    except Exception as e:
        print_error(f"Erreur: {e}")


def show_expected_logs():
    """Montre à quoi ressemblent les logs quand un webhook arrive"""
    print_section("4. À QUOI RESSEMBLENT LES LOGS QUAND UN WEBHOOK ARRIVE")
    
    print_info("Quand un webhook WhatsApp arrive, vous devriez voir dans les logs:")
    print()
    print(f"{GREEN}INFO:     📥 POST /webhook/whatsapp received from <IP>{RESET}")
    print(f"{GREEN}INFO:     📥 POST /whatsapp webhook received: object=whatsapp_business_account, entries=1{RESET}")
    print(f"{GREEN}INFO:     📥 Webhook received: object=whatsapp_business_account, entries=1{RESET}")
    print(f"{GREEN}INFO:     📋 Processing entry 1/1{RESET}")
    print(f"{GREEN}INFO:     🔍 Looking for account with phone_number_id from metadata: <PHONE_NUMBER_ID>{RESET}")
    print(f"{GREEN}INFO:     ✅ Found account using metadata phone_number_id: <ACCOUNT_NAME>{RESET}")
    print(f"{GREEN}INFO:     📨 Processing 1 messages{RESET}")
    print(f"{GREEN}INFO:       Processing message 1/1: type=text, from=<NUMBER>{RESET}")
    print(f"{GREEN}INFO:       ✅ Message 1 processed successfully{RESET}")
    print()
    
    print_warning("Si vous NE VOYEZ PAS ces logs, cela signifie que:")
    print_warning("  1. Les webhooks n'arrivent pas du tout (problème de configuration Meta)")
    print_warning("  2. Le endpoint webhook n'est pas accessible (problème de réseau/firewall)")
    print_warning("  3. Les webhooks arrivent mais sont bloqués avant d'atteindre le backend")
    print()
    
    print_info("Les logs que vous avez partagés montrent uniquement des requêtes GET:")
    print_info("  - GET /messages/media/...")
    print_info("  - GET /conversations?...")
    print_info("  - GET /messages/...")
    print()
    print_error("❌ AUCUN log POST /webhook/whatsapp trouvé!")
    print_error("   Cela signifie que les webhooks n'arrivent PAS au backend")


def show_webhook_configuration_check():
    """Montre comment vérifier la configuration du webhook"""
    print_section("5. VÉRIFICATION DE LA CONFIGURATION DU WEBHOOK")
    
    print_info("Pour vérifier que les webhooks sont bien configurés:")
    print()
    print("1. Allez dans Meta for Developers:")
    print("   https://developers.facebook.com/apps/")
    print()
    print("2. Sélectionnez votre app")
    print()
    print("3. Allez dans: Webhooks > WhatsApp")
    print()
    print("4. Vérifiez que:")
    print("   ✅ Le statut est 'Actif' (cercle vert)")
    print("   ✅ L'URL est: https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp")
    print("   ✅ Les champs suivants sont cochés:")
    print("      - messages")
    print("      - message_status")
    print()
    print("5. Testez le webhook:")
    print("   - Cliquez sur 'Tester' ou 'Send test message'")
    print("   - Vérifiez les logs du backend pour voir si le webhook arrive")
    print()
    print("6. Vérifiez les logs de Meta:")
    print("   - Allez dans: Webhooks > WhatsApp > Logs")
    print("   - Vérifiez s'il y a des erreurs (codes 4xx ou 5xx)")
    print("   - Vérifiez les tentatives de livraison")


async def main():
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}VÉRIFICATION DES WEBHOOKS ET MESSAGES{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")
    
    # 1. Vérifier les messages en base
    has_messages = await check_recent_messages_in_db()
    
    # 2. Vérifier tous les messages
    await check_all_recent_messages()
    
    # 3. Vérifier les conversations
    await check_conversations_with_messages()
    
    # 4. Montrer les logs attendus
    show_expected_logs()
    
    # 5. Montrer comment vérifier la config
    show_webhook_configuration_check()
    
    # Résumé
    print_section("RÉSUMÉ")
    
    if has_messages:
        print_success("Des messages sont présents en base de données")
        print_info("Si les messages ne s'affichent pas dans l'interface:")
        print_info("  → Vérifiez que le frontend récupère bien les messages")
        print_info("  → Vérifiez les requêtes GET /messages/<conversation_id>")
    else:
        print_error("AUCUN message entrant trouvé dans les dernières 24h")
        print_error("ET aucun log POST /webhook/whatsapp dans les logs")
        print()
        print_warning("CONCLUSION: Les webhooks n'arrivent probablement PAS au backend")
        print()
        print_info("Actions à faire:")
        print_info("  1. Vérifier la configuration du webhook dans Meta")
        print_info("  2. Vérifier que l'URL du webhook est accessible")
        print_info("  3. Tester le webhook depuis Meta")
        print_info("  4. Vérifier les logs Meta pour voir les tentatives de livraison")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())

