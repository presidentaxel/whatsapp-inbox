"""Tests : agrégation inbox Axelia multi-lignes (conversations.view)."""
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
from app.services.axelia_inbox_tools import (  # noqa: E402
    summarize_contact_inbox_all_accessible_accounts,
)


def _user_with_view_on(allowed_ids: set[str]) -> CurrentUser:
    """Utilisateur avec conversations.view uniquement sur allowed_ids (pas de permission globale)."""
    pm = PermissionMatrix()
    for aid in allowed_ids:
        pm.grant(PermissionCodes.CONVERSATIONS_VIEW, aid)
    return CurrentUser(
        id="test-u1",
        email=None,
        is_active=True,
        app_profile={},
        permissions=pm,
        supabase_user=None,
    )


class TestAxeliaInboxMulti(unittest.IsolatedAsyncioTestCase):
    async def test_summarize_all_accessible_skips_accounts_without_view(self):
        user = _user_with_view_on({"acc-ok"})

        async def fake_list(u):
            self.assertIs(u, user)
            return [
                {"id": "acc-ok", "name": "Line A", "phone_number": "+111"},
                {"id": "acc-nope", "name": "Line B", "phone_number": "+222"},
            ]

        async def fake_summarize(account_id: str, contact_query: str, **kwargs):
            return {
                "contact_query": contact_query,
                "threads_matched": 1,
                "bundles": [{"conversation_id": f"conv-{account_id}"}],
            }

        with patch(
            "app.services.axelia_inbox_tools.list_accessible_account_rows_for_inbox",
            new=fake_list,
        ):
            with patch(
                "app.services.axelia_inbox_tools.summarize_contact_inbox_for_account",
                new=AsyncMock(side_effect=fake_summarize),
            ) as m_sum:
                out = await summarize_contact_inbox_all_accessible_accounts(
                    user,
                    "Jean Dupont",
                    max_accounts=10,
                )

        self.assertEqual(out["account_scope"], "all_accessible")
        self.assertEqual(len(out["accounts"]), 1)
        self.assertEqual(out["accounts"][0]["account_id"], "acc-ok")
        m_sum.assert_awaited_once()

    def test_skill_args_implicit_all_when_perimeter_all_and_no_account_id(self):
        args: dict = {}
        account: dict = {}
        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=None, perimeter_mode="all")
        )
        try:
            self.assertTrue(ps._skill_args_want_all_accessible(args, account))
        finally:
            ps._axelia_skills_runtime.reset(token)

    def test_skill_args_primary_when_line_uuid_present(self):
        args = {"account_scope": "primary"}
        account = {"id": "acc-1"}
        token = ps._axelia_skills_runtime.set(
            ps.AxeliaSkillsRuntime(acting_user=None, perimeter_mode="all")
        )
        try:
            self.assertFalse(ps._skill_args_want_all_accessible(args, account))
        finally:
            ps._axelia_skills_runtime.reset(token)


if __name__ == "__main__":
    unittest.main()
