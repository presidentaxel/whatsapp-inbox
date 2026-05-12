from app.services.axelia_inbox_tools import (
    _INBOUND_THEMES_PROMPT_MESSAGES_MAX,
    _inbound_themes_prompt_text,
)


def test_inbound_themes_prompt_text_keeps_short_samples():
    lines = [f"message {i}" for i in range(20)]
    prompt = _inbound_themes_prompt_text(lines)
    assert prompt.splitlines() == [f"{i + 1}. message {i}" for i in range(20)]


def test_inbound_themes_prompt_text_caps_large_samples():
    lines = [f"message {i}" for i in range(_INBOUND_THEMES_PROMPT_MESSAGES_MAX + 40)]
    prompt = _inbound_themes_prompt_text(lines)
    assert len(prompt.splitlines()) == _INBOUND_THEMES_PROMPT_MESSAGES_MAX
    assert prompt.startswith("1. message 0")
    assert prompt.endswith(f"{_INBOUND_THEMES_PROMPT_MESSAGES_MAX}. message {_INBOUND_THEMES_PROMPT_MESSAGES_MAX - 1}")
