from app.services.axelia_inbox_tools import (
    _INBOUND_THEMES_PROMPT_MESSAGES_MAX,
    _chunk_inbound_theme_lines,
    _inbound_themes_prompt_text,
    build_inbound_themes_cache_key,
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


def test_chunk_inbound_theme_lines_splits_batches():
    lines = [f"message {i}" for i in range(125)]
    batches = _chunk_inbound_theme_lines(lines, 50)
    assert len(batches) == 3
    assert len(batches[0]) == 50
    assert len(batches[1]) == 50
    assert len(batches[2]) == 25


def test_build_inbound_themes_cache_key_is_stable():
    kwargs = {
        "account_scope": "primary",
        "account_id": "acc-1",
        "user_id": "user-1",
        "since": "2026-05-01",
        "until": "2026-05-12",
        "sample_limit": 320,
        "max_themes": 12,
        "model_id": "gemini-2.5-flash",
    }
    assert build_inbound_themes_cache_key(**kwargs) == build_inbound_themes_cache_key(**kwargs)
    changed = dict(kwargs)
    changed["sample_limit"] = 280
    assert build_inbound_themes_cache_key(**kwargs) != build_inbound_themes_cache_key(**changed)
