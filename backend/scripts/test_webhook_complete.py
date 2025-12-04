"""
Script complet pour tester et configurer le webhook WhatsApp
- Génère un nouveau token de vérification
- Teste l'endpoint de vérification (GET)
- Teste l'endpoint de réception (POST) avec un payload exemple
- Affiche les informations pour configurer dans Meta
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Dict, Optional

import httpx
from dotenv import load_dotenv

# Charger les variables d'environnement
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

KEY_NAME = "WHATSAPP_VERIFY_TOKEN"
DEFAULT_WEBHOOK_URL = "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"


def read_env(path: Path) -> Dict[str, str]:
    """Lit le fichier .env et retourne un dictionnaire"""
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(path: Path, values: Dict[str, str]) -> None:
    """Écrit les valeurs dans le fichier .env"""
    lines = []
    existing_keys = set()
    
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                existing_keys.add(key)
                if key in values:
                    lines.append(f"{key}={values[key]}")
                    continue
            lines.append(line)

    for key, value in values.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_token(length: int = 43) -> str:
    """
    Génère un token URL-safe
    Meta recommande des tokens de 43 caractères minimum
    """
    return secrets.token_urlsafe(length)


def get_or_create_token(force: bool = False) -> str:
    """Récupère le token existant ou en crée un nouveau"""
    env_values = read_env(ENV_PATH)
    
    if KEY_NAME in env_values and not force:
        existing = env_values[KEY_NAME]
        print(f"✓ Token existant trouvé dans {ENV_PATH}")
        print(f"  Valeur actuelle: {existing}")
        return existing
    
    token = generate_token()
    env_values[KEY_NAME] = token
    write_env(ENV_PATH, env_values)
    
    print(f"✓ Nouveau token généré et sauvegardé dans {ENV_PATH}")
    print(f"  Token: {token}")
    return token


def test_verification_endpoint(webhook_url: str, verify_token: str) -> bool:
    """Teste l'endpoint GET de vérification"""
    print("\n" + "="*60)
    print("TEST 1: Vérification du webhook (GET)")
    print("="*60)
    
    challenge = "test_challenge_12345"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": verify_token,
        "hub.challenge": challenge
    }
    
    try:
        response = httpx.get(webhook_url, params=params, timeout=10.0)
        
        print(f"URL appelée: {webhook_url}")
        print(f"Paramètres: mode=subscribe, token=***, challenge={challenge}")
        print(f"Status code: {response.status_code}")
        print(f"Réponse: {response.text[:200]}")
        
        if response.status_code == 200 and response.text == challenge:
            print("✓ Vérification réussie ! Le serveur a retourné le challenge.")
            return True
        else:
            print("✗ Échec de la vérification")
            print(f"  Attendu: status 200 avec le challenge '{challenge}'")
            print(f"  Reçu: status {response.status_code} avec '{response.text[:100]}'")
            return False
            
    except httpx.RequestError as e:
        print(f"✗ Erreur de connexion: {e}")
        return False
    except Exception as e:
        print(f"✗ Erreur inattendue: {e}")
        return False


def test_webhook_reception(webhook_url: str) -> bool:
    """Teste l'endpoint POST avec un payload exemple (format v24.0)"""
    print("\n" + "="*60)
    print("TEST 2: Réception d'un message (POST)")
    print("="*60)
    
    # Payload basé sur l'exemple fourni par Meta (v24.0)
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID_TEST",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "16505551111",
                                "phone_number_id": "123456123"
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
                                        "body": "this is a text message"
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
    
    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0
        )
        
        print(f"URL appelée: {webhook_url}")
        print(f"Payload envoyé:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\nStatus code: {response.status_code}")
        print(f"Réponse: {response.text[:500]}")
        
        if response.status_code == 200:
            print("✓ Message reçu avec succès !")
            return True
        else:
            print(f"✗ Échec: status {response.status_code}")
            return False
            
    except httpx.RequestError as e:
        print(f"✗ Erreur de connexion: {e}")
        return False
    except Exception as e:
        print(f"✗ Erreur inattendue: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Génère un token et teste le webhook WhatsApp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Générer un nouveau token et tester
  python scripts/test_webhook_complete.py --url https://votre-domaine.com/webhook/whatsapp
  
  # Forcer la génération d'un nouveau token
  python scripts/test_webhook_complete.py --force
  
  # Tester sans générer de token
  python scripts/test_webhook_complete.py --no-generate --url https://votre-domaine.com/webhook/whatsapp
        """
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_WEBHOOK_URL,
        help=f"URL du webhook (défaut: {DEFAULT_WEBHOOK_URL})"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forcer la génération d'un nouveau token (écrase l'existant)"
    )
    parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Ne pas générer de token, utiliser celui existant"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Ne pas exécuter les tests, juste générer/afficher le token"
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("CONFIGURATION WEBHOOK WHATSAPP")
    print("="*60)
    
    # Générer ou récupérer le token
    if not args.no_generate:
        token = get_or_create_token(force=args.force)
    else:
        env_values = read_env(ENV_PATH)
        if KEY_NAME not in env_values:
            print(f"✗ Aucun token trouvé dans {ENV_PATH}")
            print("  Utilisez --no-generate pour générer un token")
            sys.exit(1)
        token = env_values[KEY_NAME]
        print(f"✓ Utilisation du token existant: {token}")
    
    # Afficher les informations de configuration
    print("\n" + "="*60)
    print("INFORMATIONS POUR META DEVELOPERS")
    print("="*60)
    print(f"URL de rappel (Callback URL):")
    print(f"  {args.url}")
    print(f"\nVérifier le token (Verify token):")
    print(f"  {token}")
    print("\n" + "-"*60)
    print("ÉTAPES:")
    print("1. Allez sur https://developers.facebook.com/apps")
    print("2. Sélectionnez votre app WhatsApp Business")
    print("3. Allez dans Webhooks > WhatsApp > Configurer")
    print("4. Collez l'URL et le token ci-dessus")
    print("5. Cliquez sur 'Vérifier et enregistrer'")
    print("-"*60)
    
    # Exécuter les tests si demandé
    if not args.skip_tests:
        print("\n" + "="*60)
        print("EXÉCUTION DES TESTS")
        print("="*60)
        
        test1_ok = test_verification_endpoint(args.url, token)
        test2_ok = test_webhook_reception(args.url)
        
        print("\n" + "="*60)
        print("RÉSUMÉ DES TESTS")
        print("="*60)
        print(f"Vérification (GET): {'✓ RÉUSSI' if test1_ok else '✗ ÉCHEC'}")
        print(f"Réception (POST):  {'✓ RÉUSSI' if test2_ok else '✗ ÉCHEC'}")
        
        if test1_ok and test2_ok:
            print("\n✓ Tous les tests sont passés !")
            sys.exit(0)
        else:
            print("\n✗ Certains tests ont échoué. Vérifiez votre configuration.")
            sys.exit(1)
    else:
        print("\n✓ Configuration terminée. Tests ignorés (--skip-tests)")
        sys.exit(0)


if __name__ == "__main__":
    main()

