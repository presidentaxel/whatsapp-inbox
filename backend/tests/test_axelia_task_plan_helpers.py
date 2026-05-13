"""Helpers task_plan Axelia : normalisation et association tool_calls ↔ todos."""

from app.services.axelia_chat_service import (
    _augment_axelia_task_plan_for_safe_calls,
    _normalize_axelia_task_plan,
    _pick_task_indices_for_tools,
)


def test_normalize_task_plan_basic():
    raw = [
        {
            "id": "a",
            "title": "Lire templates",
            "thought": "Je consulte Meta…",
            "status": "pending",
            "skill": "list_templates",
        }
    ]
    out = _normalize_axelia_task_plan(raw)
    assert len(out) == 1
    assert out[0]["id"] == "a"
    assert out[0]["title"] == "Lire templates"
    assert out[0]["thought"] == "Je consulte Meta…"
    assert out[0]["status"] == "pending"
    assert out[0]["skill"] == "list_templates"


def test_normalize_invalid_status_fallback():
    raw = [{"title": "X", "status": "???"}]
    out = _normalize_axelia_task_plan(raw)
    assert out[0]["status"] == "pending"


def test_pick_tasks_by_skill():
    todos = [
        {"id": "1", "title": "T1", "status": "pending", "skill": "list_templates"},
        {"id": "2", "title": "T2", "status": "pending", "skill": "get_contact"},
    ]
    safe = [
        {"skill": "get_contact", "args": {}},
        {"skill": "list_templates", "args": {}},
    ]
    picked = _pick_task_indices_for_tools(todos, safe)
    assert picked == [1, 0]


def test_pick_tasks_order_when_no_skill_field():
    todos = [
        {"id": "1", "title": "A", "status": "pending"},
        {"id": "2", "title": "B", "status": "pending"},
    ]
    safe = [{"skill": "x", "args": {}}, {"skill": "y", "args": {}}]
    picked = _pick_task_indices_for_tools(todos, safe)
    assert picked == [0, 1]


def test_augment_empty_creates_rows():
    todos: list = []
    safe = [
        {"skill": "list_templates", "args": {}},
        {"skill": "get_contact", "args": {}},
    ]
    _augment_axelia_task_plan_for_safe_calls(todos, safe)
    assert len(todos) == 2
    assert todos[0]["skill"] == "list_templates"
    assert todos[0]["status"] == "pending"
    assert "Meta" in todos[0]["title"]
    assert todos[1]["skill"] == "get_contact"


def test_augment_fills_missing_skill_on_partial_model_plan():
    todos = [{"id": "1", "title": "?", "status": "pending"}]
    safe = [{"skill": "list_templates", "args": {}}]
    _augment_axelia_task_plan_for_safe_calls(todos, safe)
    assert len(todos) == 1
    assert todos[0]["skill"] == "list_templates"
    assert todos[0]["title"] == "?"


def test_augment_appends_when_uncovered():
    todos = [{"id": "1", "title": "Done", "status": "done", "skill": "list_templates"}]
    safe = [
        {"skill": "list_templates", "args": {}},
        {"skill": "get_contact", "args": {}},
    ]
    _augment_axelia_task_plan_for_safe_calls(todos, safe)
    assert len(todos) == 3
    assert todos[1]["skill"] == "list_templates"
    assert todos[2]["skill"] == "get_contact"
