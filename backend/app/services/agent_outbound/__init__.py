"""Noyau « agent outbound » : catalogue d’outils séparé d’Axelia (jalons M0+)."""

from app.services.agent_outbound.kernel import run_agent_kernel_v1_tool_calls
from app.services.agent_outbound.registry import (
    AGENT_KERNEL_V1_READ_TOOLS,
    AGENT_STUDIO_ALLOWLIST_SLUGS,
    AgentOutboundToolErrorCode,
    AgentOutboundToolSpec,
    agent_tool_error_for_model,
    agent_tool_error_payload,
    build_agent_kernel_v1_catalog,
    build_effective_kernel_v1_allowlist,
    validate_agent_kernel_v1_args,
)

__all__ = [
    "AGENT_KERNEL_V1_READ_TOOLS",
    "AGENT_STUDIO_ALLOWLIST_SLUGS",
    "AgentOutboundToolErrorCode",
    "AgentOutboundToolSpec",
    "agent_tool_error_for_model",
    "agent_tool_error_payload",
    "build_agent_kernel_v1_catalog",
    "build_effective_kernel_v1_allowlist",
    "run_agent_kernel_v1_tool_calls",
    "validate_agent_kernel_v1_args",
]
