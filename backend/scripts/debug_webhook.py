"""
Script pour déboguer et afficher le contenu d'un webhook WhatsApp
Utile pour voir quelles données sont disponibles dans les webhooks
"""
import json
import sys

def print_webhook_structure(data, indent=0):
    """Affiche récursivement la structure d'un webhook"""
    prefix = "  " * indent
    
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                print(f"{prefix}{key}:")
                print_webhook_structure(value, indent + 1)
            else:
                print(f"{prefix}{key}: {value}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            print(f"{prefix}[{i}]:")
            print_webhook_structure(item, indent + 1)
    else:
        print(f"{prefix}{data}")


if __name__ == "__main__":
    print("📋 WhatsApp Webhook Structure Debugger\n")
    print("Collez le JSON du webhook ci-dessous (ou laissez vide pour un exemple):\n")
    
    webhook_json = input()
    
    if not webhook_json.strip():
        # Exemple de structure
        example = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{
                            "wa_id": "33783614530",
                            "profile": {
                                "name": "Louis VEDOVATO"
                                # Note: profile_picture_url n'est généralement pas ici
                            }
                        }],
                        "messages": [{
                            "from": "33783614530",
                            "id": "wamid.xxx",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {
                                "body": "Hello"
                            }
                        }]
                    }
                }]
            }]
        }
        print("\n📝 Exemple de structure de webhook:\n")
        print(json.dumps(example, indent=2))
        print("\n" + "="*60)
        print("Analyse de l'exemple:")
        print("="*60 + "\n")
        webhook_json = json.dumps(example)
    
    try:
        data = json.loads(webhook_json)
        
        print("\n🔍 Structure du webhook:\n")
        print_webhook_structure(data)
        
        print("\n" + "="*60)
        print("📸 Recherche d'images de profil:")
        print("="*60 + "\n")
        
        # Chercher dans les contacts
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = value.get("contacts", [])
                
                for contact in contacts:
                    wa_id = contact.get("wa_id")
                    profile = contact.get("profile", {})
                    profile_name = profile.get("name")
                    profile_picture = profile.get("profile_picture_url") or profile.get("profile_picture")
                    
                    print(f"Contact: {wa_id}")
                    print(f"  Name: {profile_name}")
                    print(f"  Profile picture URL: {profile_picture or '❌ Not found'}")
                    print(f"  Full profile data: {json.dumps(profile, indent=4)}")
                    print()
        
        print("="*60)
        print("💡 Note: WhatsApp ne fournit généralement PAS les images de profil")
        print("   dans les webhooks. Elles doivent être récupérées via l'API Graph")
        print("   avec des permissions spéciales.")
        print("="*60)
        
    except json.JSONDecodeError as e:
        print(f"❌ Erreur de parsing JSON: {e}")
    except Exception as e:
        print(f"❌ Erreur: {e}")

