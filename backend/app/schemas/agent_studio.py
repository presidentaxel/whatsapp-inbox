from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudioBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AgentIntent(StudioBaseModel):
    key: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=600)
    handler: str = Field(min_length=1, max_length=120)
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AgentRouting(StudioBaseModel):
    fallback: Literal["human", "safe_reply", "ask_clarification"] = "human"
    confidence_threshold: float = Field(
        default=0.72, ge=0.0, le=1.0, alias="confidenceThreshold"
    )
    intents: List[AgentIntent] = Field(default_factory=list, max_length=100)


class AgentEscalationRule(StudioBaseModel):
    when: str = Field(min_length=1, max_length=400)
    then: Literal["handoff_human", "require_approval", "block"]


class AgentPolicies(StudioBaseModel):
    tone: Literal["pro", "friendly", "custom"] = "pro"
    forbidden_actions: List[str] = Field(
        default_factory=list, max_length=100, alias="forbiddenActions"
    )
    escalation_rules: List[AgentEscalationRule] = Field(
        default_factory=list, max_length=60, alias="escalationRules"
    )


class AgentCapabilities(StudioBaseModel):
    allowed_tools: List[str] = Field(default_factory=list, max_length=200, alias="allowedTools")
    require_approval_for: List[str] = Field(
        default_factory=list, max_length=200, alias="requireApprovalFor"
    )


class AgentObjective(StudioBaseModel):
    primary_goal: str = Field(default="", max_length=2000, alias="primaryGoal")
    kpi: List[str] = Field(default_factory=list, max_length=40)
    audience: Optional[str] = Field(default=None, max_length=200)


class AgentTestCase(StudioBaseModel):
    id: str = Field(min_length=1, max_length=120)
    input: str = Field(min_length=1, max_length=5000)
    expected_behavior: str = Field(min_length=1, max_length=5000, alias="expectedBehavior")
    expected_route: Optional[str] = Field(default=None, max_length=120, alias="expectedRoute")


class AgentDeployment(StudioBaseModel):
    status: Literal["draft", "canary", "active", "paused"] = "draft"
    canary_percent: Optional[int] = Field(default=None, ge=1, le=100, alias="canaryPercent")

    @field_validator("canary_percent")
    @classmethod
    def validate_canary_percent(cls, v: Optional[int], info):
        status = (info.data or {}).get("status")
        if status == "canary" and v is None:
            raise ValueError("canary_percent_required_for_canary_status")
        return v


class AgentStudioConfigPayload(StudioBaseModel):
    name: str = Field(min_length=1, max_length=200)
    objective: AgentObjective = Field(default_factory=AgentObjective)
    routing: AgentRouting = Field(default_factory=AgentRouting)
    policies: AgentPolicies = Field(default_factory=AgentPolicies)
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    tests: List[AgentTestCase] = Field(default_factory=list, max_length=200)
    deployment: AgentDeployment = Field(default_factory=AgentDeployment)


class AgentStudioConfigUpsert(StudioBaseModel):
    account_id: str = Field(min_length=1)
    config: AgentStudioConfigPayload


class AgentStudioConfigOut(StudioBaseModel):
    id: str
    account_id: str
    version: Literal["v1"] = "v1"
    config: Dict[str, Any]
    is_default: bool = False
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentStudioValidateResult(StudioBaseModel):
    ok: bool
    issues: List[Dict[str, str]] = Field(default_factory=list)


class AgentStudioSimulateRequest(StudioBaseModel):
    account_id: str = Field(min_length=1)
    input_text: str = Field(min_length=1, max_length=5000)

