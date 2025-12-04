"""
Script de diagnostic COMPLET pour identifier pourquoi les messages ne sont plus reçus.
Teste tous les aspects du système de réception de webhooks.
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import supabase, supabase_execute
from app.core.config import settings
from app.services.account_service import get_all_accounts, get_account_by_phone_number_id
from app.services.message_service import handle_incoming_message

# Couleurs pour la sortie
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


async def check_configuration():
    """Vérifie la configuration de base"""
    print_section("1. VÉRIFICATION DE LA CONFIGURATION")
    
    issues = []
    
    # Vérifier les variables d'environnement
    print_info("Variables d'environnement:")
    print(f"  SUPABASE_URL: {'✅ Configuré' if settings.SUPABASE_URL else '❌ Manquant'}")
    print(f"  SUPABASE_KEY: {'✅ Configuré' if settings.SUPABASE_KEY else '❌ Manquant'}")
    print(f"  WHATSAPP_TOKEN: {'✅ Configuré' if settings.WHATSAPP_TOKEN else '❌ Manquant'}")
    print(f"  WHATSAPP_PHONE_ID: {'✅ Configuré' if settings.WHATSAPP_PHONE_ID else '❌ Manquant'}")
    print(f"  WHATSAPP_VERIFY_TOKEN: {'✅ Configuré' if settings.WHATSAPP_VERIFY_TOKEN else '❌ Manquant'}")
    
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        issues.append("Configuration Supabase manquante")
    if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_ID:
        issues.append("Configuration WhatsApp manquante")
    
    if issues:
        for issue in issues:
            print_error(issue)
        return False
    else:
        print_success("Configuration de base OK")
        return True


async def check_database_connection():
    """Vérifie la connexion à la base de données"""
    print_section("2. VÉRIFICATION DE LA CONNEXION BASE DE DONNÉES")
    
    try:
        # Test simple de connexion
        result = await supabase_execute(
            supabase.table("whatsapp_accounts").select("id").limit(1)
        )
        print_success("Connexion à Supabase OK")
        return True
    except Exception as e:
        print_error(f"Erreur de connexion à Supabase: {e}")
        return False


async def check_accounts():
    """Vérifie les comptes WhatsApp configurés"""
    print_section("3. VÉRIFICATION DES COMPTES WHATSAPP")
    
    try:
        accounts = await get_all_accounts()
        
        if not accounts:
            print_error("Aucun compte WhatsApp trouvé dans la base de données")
            print_warning("Le système va créer un compte par défaut à partir des variables d'environnement")
            return None
        
        print_success(f"{len(accounts)} compte(s) trouvé(s):")
        for acc in accounts:
            status = "Actif" if acc.get("is_active") else "Inactif"
            status_icon = "✅" if acc.get("is_active") else "❌"
            print(f"  {status_icon} {acc.get('name')} (slug: {acc.get('slug')})")
            print(f"     phone_number_id: {acc.get('phone_number_id')}")
            print(f"     phone_number: {acc.get('phone_number', 'N/A')}")
            print(f"     is_active: {status}")
            print()
        
        # Vérifier que le phone_number_id de l'env correspond à un compte
        if settings.WHATSAPP_PHONE_ID:
            matching = [acc for acc in accounts if acc.get("phone_number_id") == settings.WHATSAPP_PHONE_ID]
            if matching:
                print_success(f"Le phone_number_id de l'environnement correspond au compte: {matching[0].get('name')}")
            else:
                print_warning(f"Le phone_number_id de l'environnement ({settings.WHATSAPP_PHONE_ID}) ne correspond à aucun compte")
                print_warning("Les webhooks pourraient ne pas être associés au bon compte")
        
        return accounts[0] if accounts else None
        
    except Exception as e:
        print_error(f"Erreur lors de la vérification des comptes: {e}")
        return None


async def check_recent_messages():
    """Vérifie les messages récents dans la base"""
    print_section("4. VÉRIFICATION DES MESSAGES RÉCENTS")
    
    try:
        # Vérifier avec "inbound" (valeur correcte)
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        result = await supabase_execute(
            supabase.table("messages")
            .select("id, direction, content_text, timestamp, wa_message_id, message_type")
            .eq("direction", "inbound")
            .gte("timestamp", yesterday.isoformat())
            .order("timestamp", desc=True)
            .limit(20)
        )
        
        messages = result.data or []
        
        if messages:
            print_success(f"{len(messages)} message(s) entrant(s) trouvé(s) dans les dernières 24h:")
            for msg in messages[:5]:
                timestamp = msg.get("timestamp", "")[:19] if msg.get("timestamp") else "N/A"
                msg_type = msg.get("message_type", "text")
                content = (msg.get("content_text", "") or "")[:50]
                print(f"  - {timestamp} | {msg_type} | {content}")
            return True
        else:
            print_warning("Aucun message entrant trouvé dans les dernières 24h")
            print_info("Cela peut signifier que:")
            print_info("  1. Aucun message n'a été envoyé")
            print_info("  2. Les webhooks ne sont pas reçus")
            print_info("  3. Les webhooks sont reçus mais le traitement échoue")
            return False
            
    except Exception as e:
        print_error(f"Erreur lors de la vérification des messages: {e}")
        return False


async def check_recent_conversations():
    """Vérifie les conversations récentes"""
    print_section("5. VÉRIFICATION DES CONVERSATIONS RÉCENTES")
    
    try:
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        result = await supabase_execute(
            supabase.table("conversations")
            .select("id, client_number, updated_at, unread_count, account_id")
            .gte("updated_at", yesterday.isoformat())
            .order("updated_at", desc=True)
            .limit(10)
        )
        
        conversations = result.data or []
        
        if conversations:
            print_success(f"{len(conversations)} conversation(s) mise(s) à jour dans les dernières 24h:")
            for conv in conversations[:5]:
                updated = conv.get("updated_at", "")[:19] if conv.get("updated_at") else "N/A"
                unread = conv.get("unread_count", 0)
                client = conv.get("client_number", "N/A")
                print(f"  - {updated} | Client: {client} | Non lus: {unread}")
            return True
        else:
            print_warning("Aucune conversation mise à jour dans les dernières 24h")
            return False
            
    except Exception as e:
        print_error(f"Erreur lors de la vérification des conversations: {e}")
        return False


async def test_webhook_processing(account):
    """Teste le traitement d'un webhook simulé"""
    print_section("6. TEST DU TRAITEMENT DE WEBHOOK")
    
    if not account:
        print_error("Pas de compte disponible pour le test")
        return False
    
    phone_number_id = account.get("phone_number_id")
    if not phone_number_id:
        print_error("Le compte n'a pas de phone_number_id")
        return False
    
    print_info(f"Test avec le compte: {account.get('name')}")
    print_info(f"phone_number_id: {phone_number_id}")
    
    # Créer un webhook de test au format réel
    test_webhook = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": phone_number_id,
                "changes": [
                    {
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
                                        "name": "Test Diagnostic User"
                                    },
                                    "wa_id": "16315551181"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "16315551181",
                                    "id": f"DIAG_TEST_{int(asyncio.get_event_loop().time())}",
                                    "timestamp": str(int(datetime.utcnow().timestamp())),
                                    "type": "text",
                                    "text": {
                                        "body": f"Message de test diagnostic - {datetime.utcnow().isoformat()}"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    
    message_id = test_webhook["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    print_info(f"Envoi d'un webhook de test avec message_id: {message_id}")
    
    try:
        # Traiter le webhook
        result = await handle_incoming_message(test_webhook)
        
        if result:
            print_success("Webhook traité avec succès (pas d'exception)")
            
            # Attendre un peu pour que le traitement se termine
            await asyncio.sleep(2)
            
            # Vérifier si le message a été stocké
            stored = await supabase_execute(
                supabase.table("messages")
                .select("id, content_text, timestamp")
                .eq("wa_message_id", message_id)
                .limit(1)
            )
            
            if stored.data:
                print_success(f"✅ Message stocké avec succès!")
                print(f"   ID en base: {stored.data[0].get('id')}")
                print(f"   Contenu: {stored.data[0].get('content_text', '')[:50]}")
                return True
            else:
                print_error("❌ Message NON stocké dans la base de données")
                print_warning("Le webhook a été accepté mais le traitement a échoué silencieusement")
                print_warning("Vérifiez les logs pour voir l'erreur exacte")
                return False
        else:
            print_error("Le traitement du webhook a retourné False")
            return False
            
    except Exception as e:
        print_error(f"Erreur lors du traitement du webhook: {e}")
        import traceback
        print(traceback.format_exc())
        return False


async def check_account_lookup(account):
    """Vérifie que la recherche de compte fonctionne"""
    print_section("7. VÉRIFICATION DE LA RECHERCHE DE COMPTE")
    
    if not account:
        print_error("Pas de compte disponible pour le test")
        return False
    
    phone_number_id = account.get("phone_number_id")
    if not phone_number_id:
        print_error("Le compte n'a pas de phone_number_id")
        return False
    
    print_info(f"Test de recherche avec phone_number_id: {phone_number_id}")
    
    try:
        found = await get_account_by_phone_number_id(phone_number_id)
        
        if found:
            print_success(f"✅ Compte trouvé: {found.get('name')} (id: {found.get('id')})")
            print(f"   phone_number_id: {found.get('phone_number_id')}")
            print(f"   is_active: {found.get('is_active')}")
            return True
        else:
            print_error(f"❌ Compte NON trouvé pour phone_number_id: {phone_number_id}")
            print_warning("C'est probablement la cause du problème!")
            print_warning("Les webhooks ne peuvent pas associer les messages à un compte")
            return False
            
    except Exception as e:
        print_error(f"Erreur lors de la recherche de compte: {e}")
        return False


async def check_webhook_endpoint_config():
    """Vérifie la configuration de l'endpoint webhook"""
    print_section("8. CONFIGURATION DE L'ENDPOINT WEBHOOK")
    
    print_info("URL du webhook:")
    print(f"  https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp")
    print()
    
    print_info("Verify token:")
    if settings.WHATSAPP_VERIFY_TOKEN:
        masked = settings.WHATSAPP_VERIFY_TOKEN[:10] + "..." + settings.WHATSAPP_VERIFY_TOKEN[-5:]
        print(f"  {masked}")
    else:
        print_error("  NON CONFIGURÉ")
    print()
    
    print_info("Vérifications à faire dans Meta Business Suite:")
    print("  1. Allez dans: Meta for Developers > Votre App > Webhooks > WhatsApp")
    print("  2. Vérifiez que le statut est 'Actif' (cercle vert)")
    print("  3. Vérifiez que l'URL est correcte")
    print("  4. Vérifiez que les champs suivants sont cochés:")
    print("     ✅ messages")
    print("     ✅ message_status")
    print("  5. Testez en envoyant un message depuis WhatsApp")


async def main():
    """Fonction principale de diagnostic"""
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}DIAGNOSTIC COMPLET DU SYSTÈME DE RÉCEPTION DE MESSAGES{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")
    
    results = {}
    
    # 1. Configuration
    results['config'] = await check_configuration()
    if not results['config']:
        print_error("\n❌ Configuration de base invalide. Corrigez les problèmes avant de continuer.")
        return
    
    # 2. Connexion DB
    results['db'] = await check_database_connection()
    if not results['db']:
        print_error("\n❌ Impossible de se connecter à la base de données.")
        return
    
    # 3. Comptes
    account = await check_accounts()
    results['accounts'] = account is not None
    
    # 4. Messages récents
    results['messages'] = await check_recent_messages()
    
    # 5. Conversations récentes
    results['conversations'] = await check_recent_conversations()
    
    # 6. Recherche de compte
    if account:
        results['account_lookup'] = await check_account_lookup(account)
    
    # 7. Test de traitement de webhook
    if account:
        results['webhook_test'] = await test_webhook_processing(account)
    
    # 8. Configuration webhook
    await check_webhook_endpoint_config()
    
    # Résumé final
    print_section("RÉSUMÉ DU DIAGNOSTIC")
    
    print(f"Configuration: {'✅' if results.get('config') else '❌'}")
    print(f"Connexion DB: {'✅' if results.get('db') else '❌'}")
    print(f"Comptes: {'✅' if results.get('accounts') else '❌'}")
    print(f"Messages récents: {'✅' if results.get('messages') else '❌'}")
    print(f"Conversations récentes: {'✅' if results.get('conversations') else '❌'}")
    if 'account_lookup' in results:
        print(f"Recherche de compte: {'✅' if results.get('account_lookup') else '❌'}")
    if 'webhook_test' in results:
        print(f"Test webhook: {'✅' if results.get('webhook_test') else '❌'}")
    
    print()
    print_section("PROCHAINES ÉTAPES")
    
    if not results.get('account_lookup', True):
        print_error("PROBLÈME CRITIQUE: La recherche de compte échoue")
        print("  → Vérifiez que le phone_number_id dans whatsapp_accounts correspond")
        print("  → Vérifiez que le compte est actif (is_active = true)")
        print("  → Vérifiez que le phone_number_id dans les webhooks correspond")
    
    if not results.get('webhook_test', True):
        print_error("PROBLÈME: Le traitement de webhook échoue")
        print("  → Vérifiez les logs du serveur pour voir l'erreur exacte")
        print("  → Vérifiez que handle_incoming_message ne lève pas d'exception")
        print("  → Vérifiez que _process_incoming_message fonctionne correctement")
    
    if results.get('messages') and results.get('webhook_test'):
        print_success("Le système semble fonctionner correctement")
        print("  → Si vous ne recevez toujours pas de messages, vérifiez:")
        print("     1. Que Meta envoie bien les webhooks (logs du serveur)")
        print("     2. Que le phone_number_id dans les webhooks correspond à un compte")
        print("     3. Que les webhooks ne sont pas bloqués par un firewall/proxy")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())

