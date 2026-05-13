"""Sanitation des resultats d'outils avant reinjection au modele (anti-fuite)."""

from app.services.agent_outbound.sanitize import (
    sanitize_kernel_tool_results_for_model,
    sanitize_tool_result_object,
    sanitize_tool_results_json_blob,
)


def test_sanitize_redacts_sensitive_keys():
    out = sanitize_tool_result_object(
        {
            "items": [{"name": "a"}],
            "access_token": "secret-value",
            "nested": {"api_key": "x"},
        }
    )
    assert out["access_token"] == "[masqué]"
    assert out["nested"]["api_key"] == "[masqué]"
    assert out["items"][0]["name"] == "a"


def test_sanitize_strings_redacts_email_and_jwtish():
    out = sanitize_tool_result_object({"msg": "Contact foo@example.com et bearer abc"})
    assert "foo@example.com" not in out["msg"]
    assert "[masqué]" in out["msg"]


def test_sanitize_kernel_tool_results_preserves_skill():
    rows = sanitize_kernel_tool_results_for_model(
        [
            {"skill": "list_templates", "result": {"access_token": "x", "ok": True}},
        ]
    )
    assert rows[0]["skill"] == "list_templates"
    assert rows[0]["result"]["access_token"] == "[masqué]"
    assert rows[0]["result"]["ok"] is True


def test_sanitize_tool_results_json_blob_roundtrip():
    blob = '[{"skill":"x","result":{"mail":"a@b.co"}}]'
    out = sanitize_tool_results_json_blob(blob)
    assert "a@b.co" not in out
    assert "[masqué]" in out
