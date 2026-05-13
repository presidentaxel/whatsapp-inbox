"""
Script pour afficher EXACTEMENT ce que Gemini reçoit, mot pour mot.

Usage:
    python scripts/show_exact_gemini_prompt.py <conversation_id>
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


async def show_exact_prompt(conversation_id: str):
    """Affiche exactement ce qui est envoyé à Gemini, mot pour mot."""
    
    print("=" * 100)
    print("📋 PROMPT EXACT ENVOYÉ À GEMINI - MOT POUR MOT")
    print("=" * 100)
    print()
    
    # Récupérer la conversation
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
    
    if conversation.get("contacts"):
        contacts = conversation["contacts"]
        if isinstance(contacts, dict):
            contact_name = contacts.get("display_name") or contacts.get("whatsapp_number")
        elif isinstance(contacts, list) and len(contacts) > 0:
            contact_name = contacts[0].get("display_name") or contacts[0].get("whatsapp_number")
    
    # Récupérer le profil bot
    profile = await get_bot_profile(account_id)
    knowledge_text = _build_knowledge_text(profile, contact_name)
    
    # Instructions système
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
    
    # Récupérer l'historique
    history_rows = (
        await supabase_execute(
            supabase.table("messages")
            .select("direction, content_text, message_type, timestamp")
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
        
        # Parser les messages spéciaux
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
                pass
        
        if not content or content == "[status update]" or content.startswith("[status"):
            continue
            
        role = "user" if row.get("direction") == "inbound" else "model"
        conversation_parts.append({"role": role, "parts": [{"text": content}]})
    
    # Afficher le prompt exact
    print("=" * 100)
    print("1️⃣ SYSTEM INSTRUCTION (Ce que Gemini lit en premier)")
    print("=" * 100)
    print()
    print(system_instruction_text)
    print()
    print()
    
    print("=" * 100)
    print("2️⃣ HISTORIQUE DE CONVERSATION (Contents - dans l'ordre chronologique)")
    print("=" * 100)
    print()
    
    for i, part in enumerate(conversation_parts, 1):
        role = part["role"]
        text = part["parts"][0]["text"]
        print(f"[{i}] {role.upper()}:")
        print(text)
        print()
    
    print("=" * 100)
    print("3️⃣ CONFIGURATION (Generation Config)")
    print("=" * 100)
    print()
    print(f"Temperature: 0.4")
    print(f"Max Output Tokens: 250")
    print(f"Modèle: {settings.GEMINI_MODEL}")
    print()
    
    print("=" * 100)
    print("📊 RÉSUMÉ")
    print("=" * 100)
    print()
    print(f"System Instruction: {len(system_instruction_text)} caractères")
    print(f"Historique: {len(conversation_parts)} messages")
    total_chars = len(system_instruction_text) + sum(
        len(part["parts"][0]["text"]) for part in conversation_parts
    )
    print(f"Total: {total_chars:,} caractères (~{total_chars // 4:,} tokens)")
    print()
    
    print("=" * 100)
    print("💡 NOTE IMPORTANTE")
    print("=" * 100)
    print()
    print("Ce qui est affiché ci-dessus est EXACTEMENT ce que Gemini reçoit.")
    print("L'ordre est important :")
    print("1. Gemini lit d'abord le System Instruction (instructions + contexte)")
    print("2. Puis il lit l'historique dans l'ordre chronologique")
    print("3. Il génère une réponse en respectant les règles du System Instruction")
    print()
    print("=" * 100)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/show_exact_gemini_prompt.py <conversation_id>")
        sys.exit(1)
    
    conversation_id = sys.argv[1]
    asyncio.run(show_exact_prompt(conversation_id))

