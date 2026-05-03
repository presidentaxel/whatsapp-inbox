"""Heuristique court-circuit du classifieur de difficulté Axelia."""

from app.services.axelia_chat_service import _maybe_difficulty_shortcut


def _msg(text: str, role: str = "user"):
    return {"role": role, "text": text}


def test_shortcut_short_polite_phrases():
    """Salutations / remerciements partent direct en fast (0.0)."""
    for phrase in ("Merci", "merci !", "ok", "Salut", "bonjour", "hello", "thanks"):
        assert _maybe_difficulty_shortcut([_msg(phrase)]) == 0.0, phrase


def test_shortcut_short_message_no_tool_keywords():
    """Phrase courte sans mot-clé outil → fast direct."""
    assert _maybe_difficulty_shortcut([_msg("Tu vas bien aujourd’hui ?")]) == 0.0


def test_shortcut_skipped_for_tool_keywords():
    """Mots-clés outils (template, inbox, contact…) → laisse le classifieur trancher."""
    assert _maybe_difficulty_shortcut([_msg("Liste mes templates Meta")]) is None
    assert _maybe_difficulty_shortcut([_msg("Cherche dans l'inbox")]) is None
    assert _maybe_difficulty_shortcut(
        [_msg("Résume mes derniers contacts")]
    ) is None


def test_shortcut_skipped_for_long_messages():
    """Au-delà de 70 caractères on laisse le classifieur évaluer (le texte peut être complexe)."""
    long_text = (
        "Peux-tu m’expliquer en détail comment fonctionne la fenêtre de 24 h sur "
        "WhatsApp Business et son impact sur l’automatisation ?"
    )
    assert _maybe_difficulty_shortcut([_msg(long_text)]) is None


def test_shortcut_no_user_message():
    """Conversation vide ou sans tour utilisateur récent → fast par défaut."""
    assert _maybe_difficulty_shortcut([]) == 0.0
    assert _maybe_difficulty_shortcut([_msg("réponse modèle", role="model")]) == 0.0


def test_shortcut_uses_last_user_turn():
    """Seul le DERNIER message utilisateur compte (pas l'historique global)."""
    msgs = [
        _msg("Liste mes templates"),
        _msg("ok merci"),
    ]
    # Le dernier user = "ok merci" → shortcut
    assert _maybe_difficulty_shortcut(msgs) == 0.0
