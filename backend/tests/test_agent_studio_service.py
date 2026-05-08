from app.services.agent_studio_service import (
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

