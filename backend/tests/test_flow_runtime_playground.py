"""Tests unitaires : helpers graphe Playground / bac à sable."""
import os
import sys
import unittest

# Exécution : depuis `backend/` → `python -m unittest discover -s tests -p "test_*.py"`
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services.flow_runtime_service import (
    _cosine_similarity_vec,
    _gemini_pick,
    _is_playground_audience_start_node,
    _pick_start_node_id,
    _sanitize_stale_flow_session_pointers,
    _should_pause_after_sendtext_for_successor,
    _start_allows_message,
)


class TestPlaygroundAudienceHelpers(unittest.TestCase):
    def test_is_playground_audience_start_node(self):
        nodes = {
            "aud": {
                "id": "aud",
                "type": "start",
                "data": {"triggerType": "playground_audience"},
            },
            "msg": {
                "id": "msg",
                "type": "start",
                "data": {"triggerType": "message_in"},
            },
        }
        self.assertTrue(_is_playground_audience_start_node(nodes, "aud"))
        self.assertFalse(_is_playground_audience_start_node(nodes, "msg"))
        self.assertFalse(_is_playground_audience_start_node(nodes, None))
        self.assertFalse(_is_playground_audience_start_node(nodes, "missing"))

    def test_pick_start_audience_only_with_any_matches(self):
        """Graphe uniquement « campagne » + messageMatch any (comme l’éditeur) : démarrage par message contact."""
        nodes = {
            "only": {
                "id": "only",
                "type": "start",
                "data": {"triggerType": "playground_audience"},
            },
        }
        self.assertEqual(_pick_start_node_id(nodes, "hello"), "only")

    def test_pick_start_audience_strict_keyword_no_match(self):
        nodes = {
            "only": {
                "id": "only",
                "type": "start",
                "data": {
                    "triggerType": "playground_audience",
                    "messageMatch": "equals",
                    "messageKeyword": "inscription",
                },
            },
        }
        self.assertIsNone(_pick_start_node_id(nodes, "hello"))

    def test_start_allows_audience_any(self):
        node = {"data": {"triggerType": "playground_audience", "messageMatch": "any"}}
        self.assertTrue(_start_allows_message(node, "bonjour"))

    def test_start_allows_audience_contains_keyword(self):
        node = {
            "data": {
                "triggerType": "playground_audience",
                "messageMatch": "contains",
                "messageKeyword": "suv",
            }
        }
        self.assertTrue(_start_allows_message(node, "je veux un SUV"))
        self.assertFalse(_start_allows_message(node, "bonjour"))

    def test_pick_start_prefers_message_in_when_both(self):
        nodes = {
            "aud": {
                "id": "aud",
                "type": "start",
                "data": {"triggerType": "playground_audience"},
            },
            "msg": {
                "id": "msg",
                "type": "start",
                "data": {"triggerType": "message_in", "messageMatch": "any"},
            },
        }
        self.assertEqual(_pick_start_node_id(nodes, "bonjour"), "msg")


class TestPauseAfterSendText(unittest.TestCase):
    def test_pauses_before_gemini_or_router(self):
        self.assertTrue(_should_pause_after_sendtext_for_successor("gemini"))
        self.assertTrue(_should_pause_after_sendtext_for_successor("routerNode"))

    def test_chains_sendtext_and_template_without_pause(self):
        self.assertFalse(_should_pause_after_sendtext_for_successor("sendText"))
        self.assertFalse(_should_pause_after_sendtext_for_successor("sendTemplate"))


class TestCosineSimilarity(unittest.TestCase):
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity_vec(v, v), 1.0)

    def test_orthogonal(self):
        self.assertAlmostEqual(
            _cosine_similarity_vec([1.0, 0.0], [0.0, 1.0]), 0.0
        )


class TestGeminiPick(unittest.TestCase):
    def test_matched_keyword_in_router_output(self):
        edges = [
            {"source": "g", "target": "a", "sourceHandle": "intent-0"},
            {"source": "g", "target": "b", "sourceHandle": "intent-unknown"},
        ]
        intents = [{"keyword": "location", "label": "Louer"}]
        nxt, reason, idx = _gemini_pick(intents, edges, "g", "LOCATION", "hello")
        self.assertEqual(reason, "matched")
        self.assertEqual(nxt, "a")
        self.assertEqual(idx, 0)

    def test_unknown_when_no_match(self):
        edges = [
            {"source": "g", "target": "a", "sourceHandle": "intent-0"},
            {"source": "g", "target": "unk", "sourceHandle": "intent-unknown"},
        ]
        intents = [{"keyword": "location", "label": "Louer"}]
        nxt, reason, idx = _gemini_pick(intents, edges, "g", "XYZ", "blabla")
        self.assertEqual(reason, "intent_unknown")
        self.assertEqual(nxt, "unk")
        self.assertIsNone(idx)

    def test_empty_keyword_reason(self):
        edges = [{"source": "g", "target": "unk", "sourceHandle": "intent-unknown"}]
        intents = [{"keyword": "a", "label": "A"}]
        nxt, reason, idx = _gemini_pick(intents, edges, "g", None, "not a greeting at all")
        self.assertEqual(reason, "empty_keyword")
        self.assertEqual(nxt, "unk")
        self.assertIsNone(idx)


class TestSanitizeStaleSessionPointers(unittest.TestCase):
    def test_clears_orphan_current_node_id(self):
        session = {
            "currentNodeId": "old-deleted-id",
            "afterInteractiveTarget": "next-1",
            "variables": {},
        }
        nodes = {"start-1": {"id": "start-1", "type": "start"}}
        _sanitize_stale_flow_session_pointers(session, nodes)
        self.assertIsNone(session.get("currentNodeId"))
        self.assertIsNone(session.get("afterInteractiveTarget"))

    def test_clears_delay_when_resume_missing(self):
        session = {
            "flowDelayUntil": "2099-01-01T00:00:00+00:00",
            "flowDelayResumeNodeId": "gone",
        }
        nodes = {"a": {"id": "a"}}
        _sanitize_stale_flow_session_pointers(session, nodes)
        self.assertIsNone(session.get("flowDelayUntil"))
        self.assertIsNone(session.get("flowDelayResumeNodeId"))

    def test_prunes_stale_gemini_clarify_keys(self):
        session = {"geminiClarifyByNode": {"gone": 1, "keep": 2}}
        nodes = {"keep": {"id": "keep"}}
        _sanitize_stale_flow_session_pointers(session, nodes)
        self.assertEqual(session.get("geminiClarifyByNode"), {"keep": 2})


if __name__ == "__main__":
    unittest.main()
