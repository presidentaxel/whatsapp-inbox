from pydantic import ValidationError
import pytest

from app.schemas.axelia import AxeliaChatRequest, AxeliaConversationPatch


def test_axelia_chat_request_response_depth_default():
    req = AxeliaChatRequest(account_id="a1", conversation_id="c1")
    assert req.response_depth == "standard"


def test_axelia_chat_request_response_depth_accepts_expert():
    req = AxeliaChatRequest(
        account_id="a1",
        conversation_id="c1",
        response_depth="expert",
    )
    assert req.response_depth == "expert"


def test_axelia_chat_request_response_depth_rejects_unknown():
    with pytest.raises(ValidationError):
        AxeliaChatRequest(
            account_id="a1",
            conversation_id="c1",
            response_depth="deep",
        )


def test_axelia_conversation_patch_account_context_optional():
    p = AxeliaConversationPatch()
    assert p.model_dump(exclude_unset=True) == {}
    q = AxeliaConversationPatch(account_context="acc-1")
    assert q.model_dump(exclude_unset=True) == {"account_context": "acc-1"}
