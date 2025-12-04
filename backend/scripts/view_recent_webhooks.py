"""
Script pour voir les derniers webhooks reçus
Affiche les derniers messages reçus depuis les webhooks WhatsApp
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Ajouter le répertoire backend au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# Charger les variables d'environnement
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

from app.core.db import supabase, supabase_execute


async def get_recent_messages(limit: int = 20):
    """Récupère les derniers messages reçus"""
    query = (
        supabase.table("messages")
        .select(
            """
            id,
            direction,
            content_text,
            timestamp,
            wa_message_id,
            message_type,
            status,
            conversations!inner(
                id,
                client_number,
                contacts!inner(
                    display_name,
                    whatsapp_number
                )
            )
        """
        )
        .eq("direction", "incoming")
        .order("timestamp", desc=True)
        .limit(limit)
    )
    
    result = await supabase_execute(query)
    return result.data if result.data else []


async def get_recent_statuses(limit: int = 20):
    """Récupère les derniers statuts de messages"""
    query = (
        supabase.table("messages")
        .select(
            """
            id,
            direction,
            content_text,
            timestamp,
            wa_message_id,
            message_type,
            status,
            conversations!inner(
                id,
                client_number,
                contacts!inner(
                    display_name,
                    whatsapp_number
                )
            )
        """
        )
        .eq("direction", "outgoing")
        .not_.is_("status", "null")
        .order("timestamp", desc=True)
        .limit(limit)
    )
    
    result = await supabase_execute(query)
    return result.data if result.data else []


def format_timestamp(ts: str | None) -> str:
    """Formate un timestamp pour l'affichage"""
    if not ts:
        return "N/A"
    try:
        if isinstance(ts, str):
            # Essayer de parser différents formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S%z",
            ]:
                try:
                    dt = datetime.strptime(ts, fmt)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    continue
        return str(ts)
    except:
        return str(ts)


def print_message(message: dict, index: int):
    """Affiche un message formaté"""
    conv = message.get("conversations", {})
    contact = conv.get("contacts", {}) if isinstance(conv, dict) else {}
    
    display_name = contact.get("display_name", "Inconnu") if isinstance(contact, dict) else "Inconnu"
    whatsapp_number = contact.get("whatsapp_number", "N/A") if isinstance(contact, dict) else "N/A"
    client_number = conv.get("client_number", "N/A") if isinstance(conv, dict) else "N/A"
    
    print(f"\n{'='*80}")
    print(f"Message #{index + 1}")
    print(f"{'='*80}")
    print(f"ID: {message.get('id')}")
    print(f"Timestamp: {format_timestamp(message.get('timestamp'))}")
    print(f"Type: {message.get('message_type', 'N/A')}")
    print(f"Status: {message.get('status', 'N/A')}")
    print(f"WA Message ID: {message.get('wa_message_id', 'N/A')}")
    print(f"\nContact:")
    print(f"  Nom: {display_name}")
    print(f"  Numéro: {whatsapp_number}")
    print(f"  Client: {client_number}")
    print(f"\nContenu:")
    content = message.get("content_text", "")
    if content:
        # Limiter la longueur pour l'affichage
        if len(content) > 200:
            print(f"  {content[:200]}...")
        else:
            print(f"  {content}")
    else:
        print("  (Pas de contenu texte)")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Voir les derniers webhooks reçus")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Nombre de messages à afficher (défaut: 10)"
    )
    parser.add_argument(
        "--statuses",
        action="store_true",
        help="Afficher les statuts de messages au lieu des messages entrants"
    )
    
    args = parser.parse_args()
    
    print("="*80)
    if args.statuses:
        print("DERNIERS STATUTS DE MESSAGES (Webhooks)")
    else:
        print("DERNIERS MESSAGES REÇUS (Webhooks)")
    print("="*80)
    
    if args.statuses:
        messages = await get_recent_statuses(args.limit)
        print(f"\n📊 Affichage des {len(messages)} derniers statuts de messages...")
    else:
        messages = await get_recent_messages(args.limit)
        print(f"\n📨 Affichage des {len(messages)} derniers messages reçus...")
    
    if not messages:
        print("\n⚠️ Aucun message trouvé dans la base de données.")
        print("   Cela peut signifier:")
        print("   - Aucun webhook n'a été reçu récemment")
        print("   - Les webhooks ne sont pas correctement traités")
        print("   - Il y a un problème de connexion à la base de données")
        return
    
    for idx, msg in enumerate(messages):
        print_message(msg, idx)
    
    print(f"\n{'='*80}")
    print(f"Total: {len(messages)} message(s)")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

