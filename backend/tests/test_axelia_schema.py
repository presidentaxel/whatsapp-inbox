from pydantic import ValidationError
import pytest

from app.schemas.axelia import AxeliaChatRequest


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
