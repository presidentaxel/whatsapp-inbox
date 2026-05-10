"""Parse JSON thèmes inbox (sans appel Gemini)."""

import json

from app.services.axelia_inbox_tools import _parse_themes_json_blob


def test_parse_themes_plain_json():
    payload = {
        "themes": [{"rank": 1, "title": "T", "description": "d", "relative_frequency": "élevée", "example_customer_messages": ["a"]}],
        "methodology_note": "n",
    }
    assert _parse_themes_json_blob(json.dumps(payload)) == payload


def test_parse_themes_markdown_fence():
    payload = {"themes": [], "methodology_note": "x"}
    raw = 'Voici le résultat :\n```json\n' + json.dumps(payload, ensure_ascii=False) + "\n```"
    assert _parse_themes_json_blob(raw) == payload


def test_parse_themes_preamble_and_balanced_extract():
    payload = {"themes": [], "methodology_note": "y"}
    inner = json.dumps(payload, ensure_ascii=False)
    raw = "Sure — here is JSON.\n" + inner + "\nThanks."
    assert _parse_themes_json_blob(raw) == payload


def test_parse_themes_string_with_braces_does_not_break_balance():
    payload = {
        "themes": [
            {
                "rank": 1,
                "title": "T}",
                "description": "d",
                "relative_frequency": "faible",
                "example_customer_messages": ['say "{" ok'],
            }
        ],
        "methodology_note": "n",
    }
    raw = json.dumps(payload, ensure_ascii=False)
    assert _parse_themes_json_blob(raw) == payload


def test_parse_themes_invalid_returns_none():
    assert _parse_themes_json_blob("") is None
    assert _parse_themes_json_blob("not json") is None


def test_parse_themes_repair_invalid_backslash_apostrophe():
    """Les modèles émettent parfois \\' (invalide en JSON) pour d'affaires."""
    note = "mot d" + chr(92) + "'" + "affaires"
    raw = '{"themes":[],"methodology_note":"' + note + '"}'
    got = _parse_themes_json_blob(raw)
    assert got is not None
    assert got["methodology_note"] == "mot d'affaires"
