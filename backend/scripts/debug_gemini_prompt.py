"""
Script pour visualiser exactement ce qui est envoyé à Gemini.

Usage:
    python scripts/debug_gemini_prompt.py <conversation_id>
    
Exemple:
    python scripts/debug_gemini_prompt.py abc123-def456-ghi789
"""

import asyncio
import json
import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.services.bot_service import (
    get_bot_profile,
    _build_knowledge_text,
    _render_template_sections,
)


async def debug_prompt(conversation_id: str):
    """Affiche exactement ce qui serait envoyé à Gemini."""
    
    print("=" * 80)
    print(f"🔍 DEBUG PROMPT GEMINI - Conversation: {conversation_id}")
    print("=" * 80)
    print()
    
    # 1. Récupérer la conversation avec jointure sur contacts
    conv_result = await supabase_execute(
        supabase.table("conversations")
        .select("account_id, contact_id, contacts(display_name, whatsapp_number)")
        .eq("id", conversation_id)
        .limit(1)
    )
    
    if not conv_result.data:
        print(f"❌ Conversation {conversation_id} non trouvée")
        return
    
    conversation = conv_result.data[0]
    account_id = conversation["account_id"]
    contact_name = None
    
    # Récupérer le nom du contact depuis la jointure
    if conversation.get("contacts"):
        contacts = conversation["contacts"]
        # contacts peut être un dict ou une liste selon Supabase
        if isinstance(contacts, dict):
            contact_name = contacts.get("display_name") or contacts.get("whatsapp_number")
        elif isinstance(contacts, list) and len(contacts) > 0:
            contact_name = contacts[0].get("display_name") or contacts[0].get("whatsapp_number")
    
    print(f"📋 Account ID: {account_id}")
    print(f"👤 Contact: {contact_name or 'Non spécifié'}")
    print()
    
    # 2. Récupérer le profil bot
    profile = await get_bot_profile(account_id)
    print("=" * 80)
    print("📦 PROFIL BOT")
    print("=" * 80)
    print(json.dumps(profile, indent=2, ensure_ascii=False))
    print()
    
    # 3. Construire le knowledge text
    knowledge_text = _build_knowledge_text(profile, contact_name)
    print("=" * 80)
    print("📚 KNOWLEDGE TEXT (Contexte entreprise)")
    print("=" * 80)
    print(knowledge_text)
    print()
    print(f"📊 Longueur: {len(knowledge_text)} caractères")
    print()
    
    # 4. Instructions système
    instruction = (
        "Tu es un assistant WhatsApp francophone pour l'entreprise décrite ci-dessous. "
        "Réponds uniquement en texte. "
        "Si un utilisateur envoie une image, vidéo, audio ou tout contenu non textuel, réponds : "
        "\"Je ne peux pas lire ce type de contenu, peux-tu me l'écrire ?\" "
        "N'invente jamais de données. "
        "Si une information manque dans le contexte, indique simplement que tu dois la vérifier et pose des questions pour avancer. "
        "N'interromps pas la conversation tant que tu peux guider l'utilisateur ou collecter des détails utiles. "
        "Ne promets jamais de tarifs, délais, disponibilités ou réservations sans confirmation explicite dans le contexte."
    )
    
    system_instruction_text = f"{instruction}\n\nContexte entreprise:\n{knowledge_text}".strip()
    
    print("=" * 80)
    print("🎯 SYSTEM INSTRUCTION (Complet)")
    print("=" * 80)
    print(system_instruction_text)
    print()
    print(f"📊 Longueur: {len(system_instruction_text)} caractères")
    print()
    
    # 5. Récupérer l'historique
    history_rows = (
        await supabase_execute(
            supabase.table("messages")
            .select("direction, content_text, timestamp")
            .eq("conversation_id", conversation_id)
            .order("timestamp", desc=True)
            .limit(10)
        )
    ).data
    
    history_rows.reverse()
    
    conversation_parts = []
    for row in history_rows:
        content = (row.get("content_text") or "").strip()
        message_type = row.get("message_type") or "text"
        
        # Parser les messages spéciaux pour affichage lisible
        if message_type == "order" and content.startswith("{"):
            try:
                order_data = json.loads(content)
                order = order_data.get("order", {})
                items = order.get("product_items", [])
                if items:
                    readable = f"Commande reçue:\n"
                    for item in items:
                        product_id = item.get("product_retailer_id", "N/A")
                        quantity = item.get("quantity", 1)
                        price = item.get("item_price", 0)
                        currency = item.get("currency", "EUR")
                        readable += f"- {quantity}x produit {product_id}: {price} {currency}\n"
                    content = readable.strip()
                else:
                    content = "Commande reçue (détails non disponibles)"
            except:
                pass  # Garder le JSON si parsing échoue
        
        # Ignorer les status updates et messages vides
        if not content or content == "[status update]" or content.startswith("[status"):
            continue
            
        role = "user" if row.get("direction") == "inbound" else "model"
        conversation_parts.append({"role": role, "parts": [{"text": content}]})
    
    print("=" * 80)
    print("💬 HISTORIQUE DE CONVERSATION (Contents)")
    print("=" * 80)
    for i, part in enumerate(conversation_parts, 1):
        role = part["role"]
        text = part["parts"][0]["text"]
        print(f"\n[{i}] {role.upper()}:")
        print(f"    {text[:200]}{'...' if len(text) > 200 else ''}")
    print()
    print(f"📊 Nombre de messages: {len(conversation_parts)}")
    print()
    
    # 6. Payload complet
    payload = {
        "system_instruction": {
            "role": "system",
            "parts": [
                {"text": system_instruction_text}
            ],
        },
        "contents": conversation_parts,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 250,
        },
    }
    
    print("=" * 80)
    print("📦 PAYLOAD COMPLET (JSON)")
    print("=" * 80)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()
    
    # 7. Estimation des tokens
    total_chars = len(system_instruction_text) + sum(
        len(part["parts"][0]["text"]) for part in conversation_parts
    )
    estimated_tokens = total_chars // 4  # Approximation: 1 token ≈ 4 caractères
    
    print("=" * 80)
    print("📊 STATISTIQUES")
    print("=" * 80)
    print(f"Total caractères: {total_chars:,}")
    print(f"Tokens estimés: ~{estimated_tokens:,}")
    print(f"Temperature: 0.4")
    print(f"Max output tokens: 250")
    print(f"Modèle: {settings.GEMINI_MODEL}")
    print()
    
    # 8. Endpoint
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent"
    )
    print("=" * 80)
    print("🔗 ENDPOINT")
    print("=" * 80)
    print(f"POST {endpoint}")
    print(f"Paramètre: key={settings.GEMINI_API_KEY[:20]}...")
    print()
    
    print("=" * 80)
    print("💡 RECOMMANDATIONS POUR AMÉLIORER LES PERFORMANCES")
    print("=" * 80)
    
    # Vérifier si le profil est vide
    is_empty = (
        not profile.get("business_name") and
        not profile.get("description") and
        not profile.get("address") and
        not profile.get("knowledge_base") and
        not any(profile.get("template_config", {}).get("system_rules", {}).values()) and
        not any(profile.get("template_config", {}).get("company", {}).values())
    )
    
    if is_empty:
        print("⚠️  PROBLÈME: Le profil bot est VIDE !")
        print("")
        print("Pour améliorer les réponses de Gemini, configurez le bot profile :")
        print("1. Allez dans l'interface web → Assistant Gemini")
        print("2. Remplissez au minimum :")
        print("   - Nom de l'entreprise")
        print("   - Description de l'activité")
        print("   - Adresse")
        print("   - Horaires")
        print("   - Règles système (rôle, mission, ton)")
        print("")
        print("3. Optionnel mais recommandé :")
        print("   - FAQ")
        print("   - Offres/Services")
        print("   - Procédures")
        print("   - Cas spéciaux")
        print("")
        print("📝 Actuellement, Gemini ne reçoit que :")
        print(f"   - Le nom du contact: {contact_name or 'Non spécifié'}")
        print("   - Les instructions de base (très génériques)")
        print("")
        print("💡 Avec un profil rempli, Gemini aura beaucoup plus de contexte")
        print("   pour répondre de manière pertinente et personnalisée.")
    else:
        print("✅ Le profil bot contient des informations")
        print("💡 Pour encore améliorer, ajoutez :")
        print("   - Plus de détails dans les sections")
        print("   - Des FAQ fréquentes")
        print("   - Des exemples de réponses dans 'Cas spéciaux'")
    
    print("")
    print("=" * 80)
    print("✅ DEBUG TERMINÉ")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_gemini_prompt.py <conversation_id>")
        sys.exit(1)
    
    conversation_id = sys.argv[1]
    asyncio.run(debug_prompt(conversation_id))

