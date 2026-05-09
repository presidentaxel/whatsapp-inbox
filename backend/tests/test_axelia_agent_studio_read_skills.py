"""Tests unitaires : skills Axelia lecture Agent Studio (liste + détail config)."""
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
        id="u-read-studio",
        email=None,
        is_active=True,
        app_profile={},
        permissions=pm,
        supabase_user=None,
    )


class TestAxeliaAgentStudioReadSkills(unittest.IsolatedAsyncioTestCase):
    async def test_list_primary_requires_account_or_scope(self):
        user = _user_studio_on({"acc-1"})
        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=user, perimeter_mode="single")
        )
        try:
            out = await ps.execute_skill("list_agent_studio_configs", {}, {})
            self.assertIn("error", out)
        finally:
            ps._axelia_skills_runtime.reset(token)

    async def test_list_primary_ok(self):
        user = _user_studio_on({"acc-1"})
        fake_rows = [
            {
                "id": "cfg-1",
                "account_id": "acc-1",
                "version": "v1",
                "is_default": True,
                "updated_at": "2026-01-01T00:00:00Z",
                "config": {
                    "name": "Agent A",
                    "objective": {"primary_goal": "Aider"},
                    "routing": {"intents": [{"key": "x"}]},
                    "deployment": {"status": "draft"},
                },
            }
        ]

        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=user, perimeter_mode="single")
        )
        try:
            with patch(
                "app.services.agent_studio_service.list_agent_configs",
                new=AsyncMock(return_value=fake_rows),
            ):
                out = await ps.execute_skill(
                    "list_agent_studio_configs",
                    {},
                    {"id": "acc-1", "name": "Line"},
                )
        finally:
            ps._axelia_skills_runtime.reset(token)

        self.assertEqual(out.get("account_scope"), "primary")
        self.assertEqual(out.get("total"), 1)
        self.assertEqual(out["agents"][0]["name"], "Agent A")
        self.assertEqual(out["agents"][0]["intents_count"], 1)

    async def test_get_config_denied_without_studio_perm(self):
        user = _user_studio_on(set())
        pm = user.permissions
        pm.grant(PermissionCodes.CONVERSATIONS_VIEW, "acc-x")
        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=user, perimeter_mode="single")
        )
        try:
            fake_row = {
                "id": "cfg-z",
                "account_id": "acc-x",
                "version": "v1",
                "is_default": False,
                "config": {"name": "N"},
            }
            with patch(
                "app.services.agent_studio_service.get_agent_config",
                new=AsyncMock(return_value=fake_row),
            ):
                out = await ps.execute_skill(
                    "get_agent_studio_config",
                    {"config_id": "cfg-z"},
                    {"id": "acc-x"},
                )
        finally:
            ps._axelia_skills_runtime.reset(token)

        self.assertIn("error", out)

    async def test_get_config_ok(self):
        user = _user_studio_on({"acc-x"})
        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=user, perimeter_mode="single")
        )
        try:
            fake_row = {
                "id": "cfg-z",
                "account_id": "acc-x",
                "version": "v1",
                "is_default": False,
                "updated_at": "2026-05-01T12:00:00Z",
                "created_at": "2026-04-01T08:00:00Z",
                "config": {"name": "N", "objective": {"primary_goal": "Test"}},
            }
            with patch(
                "app.services.agent_studio_service.get_agent_config",
                new=AsyncMock(return_value=fake_row),
            ):
                out = await ps.execute_skill(
                    "get_agent_studio_config",
                    {"config_id": "cfg-z"},
                    {},
                )
        finally:
            ps._axelia_skills_runtime.reset(token)

        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("id"), "cfg-z")
        self.assertIn("config", out)
        self.assertIsInstance(out.get("validation_issues"), list)


if __name__ == "__main__":
    unittest.main()
