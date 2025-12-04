"""
Script pour mettre à jour les images de profil de tous les contacts
Usage: python -m scripts.update_profile_pictures <account_id> [--limit N]
"""
import asyncio
import sys
import argparse

# Ajouter le chemin du projet
sys.path.insert(0, '.')

from app.services.profile_picture_service import update_all_contacts_profile_pictures


async def main():
    parser = argparse.ArgumentParser(description='Update profile pictures for all contacts')
    parser.add_argument('account_id', help='WhatsApp account ID')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of contacts to process')
    
    args = parser.parse_args()
    
    print(f"Starting profile picture update for account {args.account_id}")
    print(f"Limit: {args.limit} contacts")
    
    await update_all_contacts_profile_pictures(args.account_id, args.limit)
    
    # Attendre un peu pour que les tâches se lancent
    await asyncio.sleep(5)
    
    print("Profile picture update queued. Processing in background...")


if __name__ == "__main__":
    asyncio.run(main())

