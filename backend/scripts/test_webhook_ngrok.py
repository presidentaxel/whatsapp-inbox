"""
Script pour tester les webhooks avec ngrok
Permet de créer un tunnel ngrok et tester si les webhooks arrivent
"""
import asyncio
import json
import sys
import subprocess
import time
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from app.core.config import settings

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


def check_ngrok_installed():
    """Vérifie si ngrok est installé"""
    try:
        result = subprocess.run(
            ["ngrok", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print_success(f"ngrok est installé: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        print_error("ngrok n'est pas installé")
        print_info("Installez ngrok depuis: https://ngrok.com/download")
        return False
    except Exception as e:
        print_error(f"Erreur lors de la vérification de ngrok: {e}")
        return False


def start_ngrok_tunnel(port: int = 8000):
    """Démarre un tunnel ngrok"""
    print_section("DÉMARRAGE DU TUNNEL NGROK")
    
    print_info(f"Démarrage de ngrok sur le port {port}...")
    print_info("Le tunnel sera accessible publiquement via une URL ngrok")
    print()
    
    try:
        # Démarrer ngrok en arrière-plan
        process = subprocess.Popen(
            ["ngrok", "http", str(port), "--log=stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Attendre un peu pour que ngrok démarre
        time.sleep(3)
        
        # Vérifier si le processus est toujours actif
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            print_error(f"ngrok n'a pas pu démarrer: {stderr}")
            return None, None
        
        # Récupérer l'URL publique depuis l'API ngrok
        try:
            response = httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=5)
            if response.status_code == 200:
                data = response.json()
                tunnels = data.get("tunnels", [])
                if tunnels:
                    public_url = tunnels[0].get("public_url")
                    print_success(f"Tunnel ngrok créé avec succès!")
                    print_success(f"URL publique: {public_url}")
                    print()
                    webhook_url = f"{public_url}/webhook/whatsapp"
                    print_info(f"URL du webhook: {webhook_url}")
                    return process, webhook_url
        except Exception as e:
            print_warning(f"Impossible de récupérer l'URL depuis l'API ngrok: {e}")
            print_info("Vous pouvez récupérer l'URL manuellement sur: http://127.0.0.1:4040")
            return process, None
        
        return process, None
        
    except Exception as e:
        print_error(f"Erreur lors du démarrage de ngrok: {e}")
        return None, None


def test_webhook_endpoint(webhook_url: str):
    """Teste l'endpoint webhook avec un payload de test"""
    print_section("TEST DE L'ENDPOINT WEBHOOK")
    
    if not webhook_url:
        print_error("URL du webhook non disponible")
        return False
    
    print_info(f"Test de l'endpoint: {webhook_url}")
    print()
    
    # Créer un payload de test similaire à celui de Meta
    test_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": settings.WHATSAPP_PHONE_ID or "TEST_PHONE_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "16505551111",
                                "phone_number_id": settings.WHATSAPP_PHONE_ID or "TEST_PHONE_ID"
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "Test User Ngrok"
                                    },
                                    "wa_id": "16315551181"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "16315551181",
                                    "id": f"NGROK_TEST_{int(time.time())}",
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {
                                        "body": f"Test webhook via ngrok - {time.strftime('%Y-%m-%d %H:%M:%S')}"
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
    
    print_info("Envoi d'un webhook de test...")
    print_info(f"Message ID: {test_payload['entry'][0]['changes'][0]['value']['messages'][0]['id']}")
    print()
    
    try:
        response = httpx.post(
            webhook_url,
            json=test_payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        print_info(f"Status code: {response.status_code}")
        print_info(f"Réponse: {response.text}")
        print()
        
        if response.status_code == 200:
            print_success("✅ Webhook accepté par le serveur!")
            print_info("Vérifiez les logs du backend pour voir si le message a été traité")
            return True
        else:
            print_error(f"❌ Webhook rejeté: status {response.status_code}")
            return False
            
    except httpx.ConnectError:
        print_error("❌ Impossible de se connecter au serveur")
        print_warning("Vérifiez que le backend est démarré sur le port 8000")
        return False
    except Exception as e:
        print_error(f"❌ Erreur lors du test: {e}")
        return False


def show_meta_configuration_instructions(webhook_url: str, verify_token: str):
    """Affiche les instructions pour configurer Meta"""
    print_section("CONFIGURATION META")
    
    if not webhook_url:
        print_warning("URL ngrok non disponible, instructions génériques:")
        webhook_url = "https://xxxxx.ngrok.io/webhook/whatsapp"
    
    print_info("Pour configurer le webhook dans Meta:")
    print()
    print("1. Allez dans Meta for Developers:")
    print("   https://developers.facebook.com/apps/")
    print()
    print("2. Sélectionnez votre app")
    print()
    print("3. Allez dans: Webhooks > WhatsApp")
    print()
    print("4. Configurez le webhook:")
    print(f"   URL de rappel: {webhook_url}")
    print(f"   Vérifier le token: {verify_token}")
    print()
    print("5. Cliquez sur 'Vérifier et enregistrer'")
    print()
    print("6. Vérifiez que le champ 'messages' est abonné (Abonné(e))")
    print()
    print("7. Testez avec le bouton 'Test' ou 'Envoyer au serveur v24.0'")
    print()
    print("8. Regardez les logs du backend pour voir si le webhook arrive")
    print()


def main():
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}TEST DES WEBHOOKS AVEC NGROK{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")
    
    # 1. Vérifier ngrok
    if not check_ngrok_installed():
        print()
        print_error("Installez ngrok avant de continuer:")
        print("  Windows: choco install ngrok")
        print("  Ou téléchargez depuis: https://ngrok.com/download")
        return
    
    # 2. Vérifier la configuration
    print_section("VÉRIFICATION DE LA CONFIGURATION")
    
    if not settings.WHATSAPP_VERIFY_TOKEN:
        print_error("WHATSAPP_VERIFY_TOKEN n'est pas configuré")
        return
    
    if not settings.WHATSAPP_PHONE_ID:
        print_warning("WHATSAPP_PHONE_ID n'est pas configuré (utilisé pour les tests)")
    
    print_success("Configuration OK")
    print_info(f"Verify token: {settings.WHATSAPP_VERIFY_TOKEN[:10]}...")
    print()
    
    # 3. Vérifier que le backend est démarré
    print_section("VÉRIFICATION DU BACKEND")
    
    try:
        response = httpx.get("http://127.0.0.1:8000/", timeout=5)
        if response.status_code == 200:
            print_success("Backend accessible sur http://127.0.0.1:8000")
        else:
            print_warning(f"Backend répond avec le status {response.status_code}")
    except httpx.ConnectError:
        print_error("❌ Backend non accessible sur http://127.0.0.1:8000")
        print_warning("Démarrez le backend avec: uvicorn app.main:app --reload --port 8000")
        return
    except Exception as e:
        print_error(f"Erreur: {e}")
        return
    
    print()
    
    # 4. Démarrer ngrok
    ngrok_process, webhook_url = start_ngrok_tunnel(8000)
    
    if not ngrok_process:
        print_error("Impossible de démarrer ngrok")
        return
    
    if not webhook_url:
        print_warning("URL ngrok non récupérée automatiquement")
        print_info("Récupérez l'URL manuellement sur: http://127.0.0.1:4040")
        print_info("Puis utilisez-la pour configurer Meta")
        webhook_url = input("\nEntrez l'URL ngrok (ex: https://xxxxx.ngrok.io): ")
        if webhook_url:
            webhook_url = f"{webhook_url}/webhook/whatsapp"
        else:
            print_error("URL non fournie")
            ngrok_process.terminate()
            return
    
    print()
    
    # 5. Afficher les instructions Meta
    show_meta_configuration_instructions(webhook_url, settings.WHATSAPP_VERIFY_TOKEN)
    
    # 6. Tester l'endpoint
    print()
    input("Appuyez sur Entrée pour tester l'endpoint webhook...")
    test_webhook_endpoint(webhook_url)
    
    # 7. Instructions finales
    print_section("PROCHAINES ÉTAPES")
    
    print_info("1. Configurez le webhook dans Meta avec l'URL ngrok ci-dessus")
    print_info("2. Testez depuis Meta (bouton 'Test' ou 'Envoyer au serveur')")
    print_info("3. Regardez les logs du backend pour voir si les webhooks arrivent")
    print_info("4. Envoyez un vrai message depuis WhatsApp")
    print()
    print_warning("⚠️  IMPORTANT: ngrok doit rester actif pendant les tests")
    print_warning("   L'URL ngrok change à chaque redémarrage (sauf avec un compte payant)")
    print()
    print_info("Pour arrêter ngrok, appuyez sur Ctrl+C")
    print()
    
    try:
        # Attendre que l'utilisateur arrête ngrok
        ngrok_process.wait()
    except KeyboardInterrupt:
        print()
        print_info("Arrêt de ngrok...")
        ngrok_process.terminate()
        print_success("ngrok arrêté")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterruption par l'utilisateur")
    except Exception as e:
        print_error(f"Erreur: {e}")
        import traceback
        traceback.print_exc()

