"""Tests : skill Axelia upsert_agent_studio_routing (règles / intents)."""
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.core.permissions import (  # noqa: E402
    CurrentUser,
    PermissionCodes,
    PermissionMatrix,
)
from app.services import playground_skills as ps  # noqa: E402


def _user_studio_on(account_ids: set[str]) -> CurrentUser:
    pm = PermissionMatrix()
    for aid in account_ids:
        pm.grant(PermissionCodes.CONVERSATIONS_VIEW, aid)
        pm.grant(PermissionCodes.AGENT_STUDIO_ACCESS, aid)
    return CurrentUser(
        id="u-routing",
        email=None,
        is_active=True,
        app_profile={},
        permissions=pm,
        supabase_user=None,
    )


def _minimal_row(aid: str, cid: str) -> dict:
    return {
        "id": cid,
        "account_id": aid,
        "version": "v1",
        "config": {
            "name": "Agent Test",
            "objective": {"primary_goal": "Support", "kpi": [], "audience": None},
            "routing": {"fallback": "human", "confidence_threshold": 0.72, "intents": []},
            "policies": {"tone": "pro", "forbidden_actions": [], "escalation_rules": []},
            "capabilities": {"allowed_tools": [], "require_approval_for": []},
            "deployment": {"status": "draft", "canary_percent": None},
            "tests": [],
        },
    }


class TestAxeliaAgentStudioRoutingSkill(unittest.IsolatedAsyncioTestCase):
    async def test_routing_requires_patch_field(self):
        user = _user_studio_on({"acc-1"})
        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=user, perimeter_mode="single")
        )
        try:
            out = await ps.execute_skill(
                "upsert_agent_studio_routing",
                {"config_id": "cfg-1"},
                {"id": "acc-1"},
            )
        finally:
            ps._axelia_skills_runtime.reset(token)
        self.assertIn("error", out)
        self.assertIn("au moins un champ", out["error"].lower())

    async def test_routing_updates_intents(self):
        user = _user_studio_on({"acc-1"})
        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=user, perimeter_mode="single")
        )
        try:
            base = _minimal_row("acc-1", "cfg-1")
            saved = {
                **base,
                "config": {
                    **base["config"],
                    "routing": {
                        "fallback": "human",
                        "confidence_threshold": 0.72,
                        "intents": [
                            {
                                "key": "colis",
                                "handler": "SuiviColis",
                                "description": "Où est mon colis ?",
                            }
                        ],
                    },
                },
            }
            with patch(
                "app.services.agent_studio_service.get_agent_config",
                new=AsyncMock(return_value=base),
            ):
                with patch(
                    "app.services.agent_studio_service.update_agent_config",
                    new=AsyncMock(return_value=saved),
                ) as m_up:
                    out = await ps.execute_skill(
                        "upsert_agent_studio_routing",
                        {
                            "config_id": "cfg-1",
                            "intents": [
                                {
                                    "key": "colis",
                                    "handler": "SuiviColis",
                                    "description": "Où est mon colis ?",
                                }
                            ],
                        },
                        {"id": "acc-1"},
                    )
        finally:
            ps._axelia_skills_runtime.reset(token)

        self.assertTrue(out.get("ok"))
        self.assertEqual(len(out["routing"]["intents"]), 1)
        m_up.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
