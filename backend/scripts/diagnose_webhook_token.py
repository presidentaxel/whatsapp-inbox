"""
Script de diagnostic pour vérifier la configuration du token webhook
Vérifie le token local vs le token sur le serveur de production
"""

from __future__ import annotations

import httpx
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

DEFAULT_WEBHOOK_URL = "https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp"


def read_token_from_env() -> str | None:
    """Lit le token depuis le fichier .env local"""
    if not ENV_PATH.exists():
        return None
    
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("WHATSAPP_VERIFY_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def test_token_on_server(webhook_url: str, token: str) -> dict:
    """Teste si le token fonctionne sur le serveur"""
    challenge = "diagnostic_test_12345"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": token,
        "hub.challenge": challenge
    }
    
    try:
        response = httpx.get(webhook_url, params=params, timeout=10.0)
        
        return {
            "success": response.status_code == 200 and response.text == challenge,
            "status_code": response.status_code,
            "response": response.text[:200],
            "expected_challenge": challenge,
            "got_challenge": response.text
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def main():
    print("="*60)
    print("DIAGNOSTIC DU TOKEN WEBHOOK")
    print("="*60)
    
    # Lire le token local
    local_token = read_token_from_env()
    if not local_token:
        print("✗ Aucun token trouvé dans le fichier .env local")
        print(f"  Fichier: {ENV_PATH}")
        return
    
    print(f"\n✓ Token local trouvé:")
    print(f"  Fichier: {ENV_PATH}")
    print(f"  Token: {local_token}")
    
    # Tester sur le serveur
    print(f"\n{'='*60}")
    print("TEST SUR LE SERVEUR DE PRODUCTION")
    print("="*60)
    print(f"URL: {DEFAULT_WEBHOOK_URL}")
    
    result = test_token_on_server(DEFAULT_WEBHOOK_URL, local_token)
    
    if result.get("success"):
        print("✓ Le token fonctionne sur le serveur de production !")
        print(f"  Challenge retourné: {result['got_challenge']}")
    else:
        print("✗ Le token ne fonctionne PAS sur le serveur de production")
        print(f"  Status code: {result.get('status_code', 'N/A')}")
        print(f"  Réponse: {result.get('response', result.get('error', 'N/A'))}")
        print(f"\n  Raisons possibles:")
        print(f"  1. Le serveur n'a pas encore le nouveau token dans son .env")
        print(f"  2. Le serveur n'a pas été redémarré après la mise à jour du token")
        print(f"  3. Le token dans la base de données (whatsapp_accounts) est différent")
        print(f"\n  Actions à faire:")
        print(f"  1. Vérifier que WHATSAPP_VERIFY_TOKEN={local_token} est dans le .env du serveur")
        print(f"  2. Redémarrer le serveur")
        print(f"  3. Vérifier les logs du serveur pour voir les tentatives de vérification")
    
    # Afficher les informations pour Meta
    print(f"\n{'='*60}")
    print("INFORMATIONS POUR META DEVELOPERS")
    print("="*60)
    print(f"URL de rappel:")
    print(f"  {DEFAULT_WEBHOOK_URL}")
    print(f"\nVérifier le token:")
    print(f"  {local_token}")
    print(f"\n⚠️  IMPORTANT: Assurez-vous que le serveur a ce token avant de configurer dans Meta!")


if __name__ == "__main__":
    main()

