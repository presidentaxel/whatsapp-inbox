"""Jalon M3 : formatage des notes de réflexion post-outils."""

from app.services.agent_outbound.parsing import format_reflection_notes


def test_format_reflection_notes_full():
    text = format_reflection_notes(
        {
            "sufficiency": "partial",
            "brief": "Les templates listés ne couvrent pas la demande marketing.",
            "caveats": ["search_inbox_messages a expiré sur timeout", "Vérifier manuellement"],
        }
    )
    assert "partial" in text
    assert "Les templates listés" in text
    assert "search_inbox_messages" in text


def test_format_reflection_notes_invalid_sufficiency_defaults_partial():
    out = format_reflection_notes({"sufficiency": "bogus", "brief": "x", "caveats": []})
    assert "partial" in out.splitlines()[0]


def test_format_reflection_notes_truncates_long_brief():
    long_b = "a" * 1200
    out = format_reflection_notes(
        {"sufficiency": "sufficient", "brief": long_b, "caveats": []},
        max_brief=100,
    )
    assert len(out) < len(long_b)
    assert "…" in out or len((long_b[:100])) >= 90


def test_format_reflection_notes_non_dict_returns_empty():
    assert format_reflection_notes("nope") == ""  # type: ignore[arg-type]


def test_format_reflection_notes_missing_sufficiency_defaults_partial():
    assert "partial" in format_reflection_notes({"brief": "only brief", "caveats": []})
