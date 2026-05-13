from app.services.agent_studio_service import (
    agent_reply_suggests_human_handoff,
    agent_route_hint_triggers_human_handoff,
    can_deploy_agent_config,
    map_config_to_runtime_graph,
    metrics_reset_for_tests,
    metrics_snapshot,
    normalize_agent_config,
    simulate_agent_route,
    validate_agent_config,
)


def test_normalize_agent_config_merges_defaults():
    cfg = normalize_agent_config({"name": "Support Agent", "routing": {"fallback": "safe_reply"}})
    assert cfg["name"] == "Support Agent"
    assert cfg["routing"]["fallback"] == "safe_reply"
    assert cfg["routing"]["confidence_threshold"] == 0.72
    assert isinstance(cfg["tests"], list)


def test_normalize_agent_config_parses_json_string():
    """Colonne jsonb parfois relue comme chaîne JSON - ne doit pas effacer le contenu."""
    blob = '{"name": "Agent SAV", "objective": {"primary_goal": "SAV", "kpi": [], "audience": null}}'
    cfg = normalize_agent_config(blob)
    assert cfg["name"] == "Agent SAV"
    assert cfg["objective"]["primary_goal"] == "SAV"


def test_validate_agent_config_requires_primary_goal():
    issues = validate_agent_config(
        {
            "name": "A",
            "objective": {"primary_goal": ""},
            "routing": {"confidence_threshold": 0.7, "fallback": "human", "intents": []},
        }
    )
    assert any(i["message"] == "primary_goal_required" for i in issues)


def test_validate_agent_config_detects_duplicate_intent_keys():
    issues = validate_agent_config(
        {
            "objective": {"primary_goal": "Répondre clients"},
            "routing": {
                "confidence_threshold": 0.75,
                "fallback": "human",
                "intents": [
                    {"key": "support", "handler": "SupportAgent"},
                    {"key": "support", "handler": "SupportAgentV2"},
                ],
            },
        }
    )
    assert any(i["message"] == "intent_1_duplicate_key" for i in issues)


def test_map_config_to_runtime_graph_creates_expected_nodes():
    graph = map_config_to_runtime_graph(
        {
            "objective": {"primary_goal": "Traiter support niveau 1"},
            "routing": {
                "fallback": "human",
                "intents": [
                    {"key": "refund", "handler": "RefundAgent"},
                    {"key": "facturation", "handler": "human"},
                ],
            },
        }
    )
    node_types = {n["type"] for n in graph["nodes"]}
    assert "start" in node_types
    assert "gemini" in node_types
    assert "handoffNode" in node_types
    assert graph["v"] == 2
    handles = {e.get("sourceHandle") for e in graph["edges"]}
    assert "fallback" in handles
    assert "facturation" in handles


def test_simulate_agent_route_matches_intent():
    out = simulate_agent_route(
        {
            "routing": {
                "fallback": "human",
                "intents": [
                    {"key": "refund", "description": "demande remboursement", "handler": "RefundAgent"}
                ],
            }
        },
        "Je veux un refund sur ma commande",
    )
    assert out["route"] == "refund"
    assert out["handler"] == "RefundAgent"


def test_simulate_agent_route_fallback_when_no_match():
    out = simulate_agent_route(
        {"routing": {"fallback": "ask_clarification", "intents": [{"key": "support", "handler": "SupportAgent"}]}},
        "bonjour",
    )
    assert out["route"] == "fallback"
    assert out["handler"] == "ask_clarification"


def test_agent_route_hint_triggers_human_handoff_for_matched_intent():
    assert agent_route_hint_triggers_human_handoff(
        {"route": "facturation", "handler": "human", "confidence": 0.72}
    )


def test_agent_route_hint_triggers_human_handoff_false_for_fallback():
    assert not agent_route_hint_triggers_human_handoff(
        {"route": "fallback", "handler": "human", "confidence": 0.0}
    )


def test_agent_route_hint_triggers_human_handoff_false_for_safe_reply():
    assert not agent_route_hint_triggers_human_handoff(
        {"route": "documents_administratifs", "handler": "safe_reply", "confidence": 0.72}
    )


def test_agent_reply_suggests_human_handoff_transfer_to_colleague():
    text = (
        "Je comprends votre réaction. Je vous transfère à un collègue "
        "qui pourra vous répondre plus en détail."
    )
    assert agent_reply_suggests_human_handoff(text)


def test_agent_reply_suggests_human_handoff_false_on_negation():
    assert not agent_reply_suggests_human_handoff(
        "Je ne peux pas vous transférer pour le moment, merci de rappeler demain."
    )


def test_agent_reply_suggests_human_handoff_false_when_short():
    assert not agent_reply_suggests_human_handoff("merci")


def test_format_agent_studio_playbook_includes_native_handoff_skill():
    from app.services.bot_service import _format_agent_studio_inbox_playbook

    text = _format_agent_studio_inbox_playbook(
        {
            "name": "Agent test",
            "objective": {"primary_goal": "Répondre aux clients"},
            "routing": {"intents": [], "fallback": "safe_reply"},
            "policies": {},
            "capabilities": {"allowed_tools": []},
        },
        {"route": "fallback", "handler": "safe_reply", "confidence": 0.0},
    )
    assert "Skill natif" in text
    assert "transfert" in text.lower()


def test_validate_agent_config_rejects_unknown_tools():
    issues = validate_agent_config(
        {
            "objective": {"primary_goal": "Répondre clients"},
            "routing": {"confidence_threshold": 0.8, "fallback": "human", "intents": []},
            "capabilities": {
                "allowed_tools": ["search_contacts", "unknown_tool_x"],
                "require_approval_for": [],
            },
        }
    )
    assert any(i["message"] == "unknown_allowed_tools" for i in issues)


def test_validate_agent_config_rejects_approval_outside_allowlist():
    issues = validate_agent_config(
        {
            "objective": {"primary_goal": "Répondre clients"},
            "routing": {"confidence_threshold": 0.8, "fallback": "human", "intents": []},
            "capabilities": {
                "allowed_tools": ["search_contacts"],
                "require_approval_for": ["meta_block_contact"],
            },
        }
    )
    assert any(i["message"] == "require_approval_not_in_allowed_tools" for i in issues)


def test_validate_agent_config_requires_approval_for_sensitive_tools():
    issues = validate_agent_config(
        {
            "objective": {"primary_goal": "Répondre clients"},
            "routing": {"confidence_threshold": 0.8, "fallback": "human", "intents": []},
            "capabilities": {
                "allowed_tools": ["create_template"],
                "require_approval_for": [],
            },
        }
    )
    assert any(i["message"] == "sensitive_tools_must_require_approval" for i in issues)


def test_can_deploy_agent_config_blocks_on_errors():
    ok, issues = can_deploy_agent_config(
        {
            "objective": {"primary_goal": ""},
            "routing": {"confidence_threshold": 0.8, "fallback": "human", "intents": []},
            "capabilities": {
                "allowed_tools": ["search_contacts"],
                "require_approval_for": [],
            },
        }
    )
    assert ok is False
    assert any(i["message"] == "primary_goal_required" for i in issues)


def test_agent_outbound_allowlist_matches_agent_studio_allowed_tools():
    """Le noyau agent (M0) duplique la liste blanche Agent Studio sans import DB au chargement."""
    from app.services.agent_outbound.registry import AGENT_STUDIO_ALLOWLIST_SLUGS
    from app.services.agent_studio_service import ALLOWED_AGENT_TOOLS

    assert AGENT_STUDIO_ALLOWLIST_SLUGS == ALLOWED_AGENT_TOOLS


def test_agent_studio_metrics_validate_and_simulate():
    metrics_reset_for_tests()
    _ = validate_agent_config(
        {
            "objective": {"primary_goal": ""},
            "routing": {"confidence_threshold": 0.8, "fallback": "human", "intents": []},
            "capabilities": {"allowed_tools": [], "require_approval_for": []},
        }
    )
    _ = simulate_agent_route(
        {
            "objective": {"primary_goal": "ok"},
            "routing": {
                "fallback": "human",
                "confidence_threshold": 0.8,
                "intents": [{"key": "support", "handler": "SupportAgent"}],
            },
        },
        "bonjour",
    )
    snap = metrics_snapshot()
    counters = snap["counters"]
    assert counters["validate_calls"] >= 1
    assert counters["validate_errors"] >= 1
    assert counters["simulate_calls"] >= 1
    assert counters["simulate_fallbacks"] >= 1

