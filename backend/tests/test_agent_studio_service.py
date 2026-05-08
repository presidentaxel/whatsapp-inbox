from app.services.agent_studio_service import (
    map_config_to_runtime_graph,
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
            "routing": {"fallback": "human", "intents": [{"key": "refund", "handler": "RefundAgent"}]},
        }
    )
    node_types = {n["type"] for n in graph["nodes"]}
    assert "start" in node_types
    assert "gemini" in node_types
    assert "handoffNode" in node_types
    assert graph["v"] == 2


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

