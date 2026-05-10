"""Jalon M0 : catalogue noyau agent v1 (vide), schémas, erreurs normalisées."""

from app.services.agent_outbound.registry import (
    AGENT_KERNEL_V1_READ_TOOLS,
    AGENT_STUDIO_ALLOWLIST_SLUGS,
    AgentOutboundToolErrorCode,
    AgentOutboundToolSpec,
    agent_tool_error_for_model,
    agent_tool_error_payload,
    build_agent_kernel_v1_catalog,
    validate_agent_kernel_v1_args,
)


def test_agent_kernel_v1_is_strict_subset_of_allowlist():
    assert AGENT_KERNEL_V1_READ_TOOLS <= AGENT_STUDIO_ALLOWLIST_SLUGS


def test_agent_kernel_v1_and_allowlist_are_empty_for_now():
    assert AGENT_KERNEL_V1_READ_TOOLS == frozenset()
    assert AGENT_STUDIO_ALLOWLIST_SLUGS == frozenset()


def test_catalog_specs_cover_exactly_kernel_v1_tool_names():
    from app.services.agent_outbound import registry as reg

    spec_names = {s.name for s in reg._TOOL_SPECS_V1}
    assert spec_names == set(AGENT_KERNEL_V1_READ_TOOLS)


def test_build_catalog_intersection_and_order():
    specs, rejected = build_agent_kernel_v1_catalog(
        [
            "search_inbox_messages",
            "create_template",
            "unknown_xyz",
            "get_contact",
        ]
    )
    assert specs == []
    assert set(rejected) == {
        "create_template",
        "get_contact",
        "search_inbox_messages",
        "unknown_xyz",
    }


def test_build_catalog_empty_allowed():
    specs, rejected = build_agent_kernel_v1_catalog([])
    assert specs == []
    assert rejected == []


def test_validate_args_unknown_for_all_legacy_tools():
    assert (
        validate_agent_kernel_v1_args("list_templates", {})
        == AgentOutboundToolErrorCode.UNKNOWN_TOOL
    )
    assert (
        validate_agent_kernel_v1_args("get_whatsapp_business_profile", {})
        == AgentOutboundToolErrorCode.UNKNOWN_TOOL
    )
    assert (
        validate_agent_kernel_v1_args(
            "get_template_status", {"template_name": "hello_world"}
        )
        == AgentOutboundToolErrorCode.UNKNOWN_TOOL
    )


def test_validate_args_unknown_and_non_kernel():
    assert (
        validate_agent_kernel_v1_args("upsert_agent_studio_config", {})
        == AgentOutboundToolErrorCode.UNKNOWN_TOOL
    )
    assert (
        validate_agent_kernel_v1_args("create_template", {"name": "x"})
        == AgentOutboundToolErrorCode.UNKNOWN_TOOL
    )


def test_agent_tool_error_payload_shape():
    p = agent_tool_error_payload(
        AgentOutboundToolErrorCode.INVALID_ARGUMENTS,
        detail="x" * 3000,
        tool_name="get_contact",
    )
    assert p["code"] == "invalid_arguments"
    assert p["tool_name"] == "get_contact"
    assert len(p["detail"]) <= 2000


def test_agent_tool_error_for_model_french_strings():
    t = agent_tool_error_for_model(AgentOutboundToolErrorCode.NOT_ALLOWED_BY_POLICY)
    assert isinstance(t, str) and len(t) > 10


def test_tool_spec_dataclass_frozen():
    s = AgentOutboundToolSpec(
        name="n",
        description="d",
        parameters_json_schema={"type": "object"},
    )
    assert s.name == "n"
