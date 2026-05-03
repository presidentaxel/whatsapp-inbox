"""Tests légers : prompt périmètre Axelia (sans appel Gemini)."""

from app.services.axelia_chat_service import format_perimeter_context_prompt


def test_perimeter_single_contains_name_and_phone():
    s = format_perimeter_context_prompt(
        {
            "mode": "single",
            "primary": {
                "id": "abc-uuid",
                "name": "Boutique Test",
                "phone_number": "+33123456789",
            },
        }
    )
    assert "Boutique Test" in s
    assert "+33123456789" in s
    assert "abc-uuid" in s
    assert "search_inbox_messages" in s


def test_perimeter_all_lists_accounts():
    s = format_perimeter_context_prompt(
        {
            "mode": "all",
            "all_accounts_preview": [
                {"id": "a1", "name": "Line A", "phone_number": "+110"},
                {"id": "a2", "name": "Line B", "phone_number": "+220"},
            ],
        }
    )
    assert "tous les comptes" in s.lower()
    assert "Line A" in s
    assert "Line B" in s


def test_perimeter_empty():
    assert format_perimeter_context_prompt(None) == ""
    assert format_perimeter_context_prompt({}) == ""
