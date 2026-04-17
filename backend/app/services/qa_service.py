"""
RAG Q&A service: extracts Q&A pairs from human operator conversations,
stores them with vector embeddings (pgvector), and retrieves the most
relevant ones at query time to inject into the Gemini prompt.

Uses Gemini text-embedding-004 (free tier: 1500 req/min, 768-dim vectors).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.db import supabase, supabase_execute
from app.core.http_client import get_http_client
from app.core.pg import get_pool, fetch_one, fetch_all, execute

logger = logging.getLogger(__name__)

_EMBED_MODEL = "gemini-embedding-001"
_EMBED_DIM = 768
_EMBED_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_EMBED_MODEL}:embedContent"
)

# ──────────────────────────────────────────────────────────────────
# Embedding
# ──────────────────────────────────────────────────────────────────

async def embed_text(text: str) -> Optional[List[float]]:
    """Call Gemini text-embedding-004 and return a 768-d vector, or None on failure."""
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set - skipping embedding")
        return None
    text = (text or "").strip()
    if not text:
        return None

    client = await get_http_client()
    payload = {
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": _EMBED_DIM,
    }
    try:
        resp = await client.post(
            _EMBED_ENDPOINT,
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        )
        resp.raise_for_status()
        values = resp.json().get("embedding", {}).get("values")
        if values and len(values) == _EMBED_DIM:
            return values
        logger.warning("Embedding response missing or wrong dim: %s", len(values) if values else "None")
        return None
    except Exception as exc:
        logger.error("embed_text failed: %s", exc, exc_info=True)
        return None


async def _embed_batch(texts: List[str], batch_size: int = 20) -> List[Optional[List[float]]]:
    """Embed multiple texts, returns list aligned with input (None on failure)."""
    results: List[Optional[List[float]]] = [None] * len(texts)
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        for i, t in enumerate(chunk):
            vec = await embed_text(t)
            results[start + i] = vec
    return results


# ──────────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────────

async def search_similar_qa(
    account_id: str,
    query_text: str,
    limit: int = 5,
    min_similarity: float = 0.35,
) -> List[Dict[str, Any]]:
    """Embed query_text then find the most similar Q&A pairs for this account.

    The query is embedded as "Q: {text}" to align with the stored embeddings
    which encode both question and answer context.
    When several Q&A pairs match with close similarity, the most recently
    updated answer is returned first (tie-break by updated_at DESC).
    A dedup window ensures that near-duplicate questions only keep the
    freshest answer.
    """
    vec = await embed_text(f"Q: {query_text}")
    if not vec:
        return []

    # Fetch more candidates than needed so we can dedup by question similarity
    fetch_limit = limit * 3

    pool = get_pool()
    if pool:
        vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
        rows = await fetch_all(
            """
            SELECT id, question, answer, category,
                   1 - (embedding <=> $1::vector) AS similarity,
                   updated_at
            FROM qa_pairs
            WHERE account_id = $2::uuid
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) >= $3
            ORDER BY embedding <=> $1::vector, updated_at DESC
            LIMIT $4
            """,
            vec_literal,
            account_id,
            min_similarity,
            fetch_limit,
        )
        candidates = [dict(r) for r in rows]
    else:
        try:
            res = await supabase_execute(
                supabase.rpc(
                    "match_qa_pairs",
                    {
                        "p_account_id": account_id,
                        "p_query_embedding": vec,
                        "p_match_count": fetch_limit,
                        "p_min_similarity": min_similarity,
                    },
                )
            )
            candidates = res.data or []
        except Exception as exc:
            logger.warning("search_similar_qa RPC failed: %s", exc)
            return []

    # Dedup: when two candidates have very similar questions (similarity > 0.92
    # between each other), keep only the most recent one.
    deduped = _dedup_by_recency(candidates)
    return deduped[:limit]


def _dedup_by_recency(candidates: List[Dict[str, Any]], threshold: float = 0.92) -> List[Dict[str, Any]]:
    """Among candidates whose questions are near-duplicates, keep the newest."""
    if len(candidates) <= 1:
        return candidates
    kept: List[Dict[str, Any]] = []
    seen_questions: List[str] = []
    for c in candidates:
        q = (c.get("question") or "").strip().lower()
        is_dup = False
        for sq in seen_questions:
            if _text_overlap(q, sq) > threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(c)
            seen_questions.append(q)
    return kept


def _text_overlap(a: str, b: str) -> float:
    """Quick token-level Jaccard similarity between two strings."""
    sa = set(a.split())
    sb = set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def format_qa_context(qa_pairs: List[Dict[str, Any]]) -> str:
    """Format matched Q&A pairs into a prompt-injectable block.

    Includes a guideline that tells the LLM to synthesize from multiple
    examples rather than copy a single one verbatim - especially important
    when examples may contradict each other (e.g. availability changes).
    """
    if not qa_pairs:
        return ""
    lines = [
        "\n\nEXEMPLES DE RÉPONSES PASSÉES DE L'ÉQUIPE :"
        "\n(Utilisez ces exemples pour vous inspirer du ton, du vocabulaire "
        "et du type d'information donnée. NE COPIEZ PAS une réponse mot pour "
        "mot : synthétisez et adaptez au contexte actuel de la conversation. "
        "Si les exemples se contredisent, préférez la réponse la plus récente.)"
    ]
    for i, qa in enumerate(qa_pairs):
        q = (qa.get("question") or "").strip()
        a = (qa.get("answer") or "").strip()
        if not q or not a:
            continue
        if len(a) > 500:
            a = a[:497] + "..."
        lines.append(f"\nQ: {q}\nR: {a}")
        if i < len(qa_pairs) - 1:
            lines.append("---")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────────

async def upsert_qa_pair(
    account_id: str,
    question: str,
    answer: str,
    category: Optional[str] = None,
    source: str = "manual",
    source_message_id: Optional[str] = None,
    qa_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Insert or update a Q&A pair, computing the embedding automatically.

    The embedding is computed on the concatenation of question + answer so that
    semantic search matches on both the intent AND the content of the response.
    """
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        return None

    embed_input = f"Q: {question}\nR: {answer}"
    vec = await embed_text(embed_input)
    rid = qa_id or str(uuid.uuid4())

    pool = get_pool()
    if pool:
        vec_literal = "[" + ",".join(str(v) for v in vec) + "]" if vec else None
        row = await fetch_one(
            """
            INSERT INTO qa_pairs (id, account_id, question, answer, category, embedding, source, source_message_id)
            VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::vector, $7, $8::uuid)
            ON CONFLICT (id) DO UPDATE SET
                question = EXCLUDED.question,
                answer = EXCLUDED.answer,
                category = EXCLUDED.category,
                embedding = EXCLUDED.embedding,
                source = EXCLUDED.source,
                source_message_id = EXCLUDED.source_message_id
            RETURNING id, account_id, question, answer, category, source, created_at, updated_at
            """,
            rid,
            account_id,
            question,
            answer,
            category,
            vec_literal,
            source,
            source_message_id,
        )
        return dict(row) if row else None

    data: Dict[str, Any] = {
        "id": rid,
        "account_id": account_id,
        "question": question,
        "answer": answer,
        "category": category,
        "source": source,
        "source_message_id": source_message_id,
    }
    if vec:
        data["embedding"] = vec
    res = await supabase_execute(
        supabase.table("qa_pairs").upsert(data, on_conflict="id")
    )
    return res.data[0] if res.data else None


async def delete_qa_pair(qa_id: str) -> bool:
    pool = get_pool()
    if pool:
        await execute("DELETE FROM qa_pairs WHERE id = $1::uuid", qa_id)
        return True
    await supabase_execute(
        supabase.table("qa_pairs").delete().eq("id", qa_id)
    )
    return True


async def list_qa_pairs(
    account_id: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    pool = get_pool()
    if pool:
        rows = await fetch_all(
            """
            SELECT id, account_id, question, answer, category, source,
                   source_message_id, created_at, updated_at
            FROM qa_pairs
            WHERE account_id = $1::uuid
            ORDER BY updated_at DESC
            LIMIT $2 OFFSET $3
            """,
            account_id,
            limit,
            offset,
        )
        return [dict(r) for r in rows]

    res = await supabase_execute(
        supabase.table("qa_pairs")
        .select("id, account_id, question, answer, category, source, source_message_id, created_at, updated_at")
        .eq("account_id", account_id)
        .order("updated_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    return res.data or []


async def count_qa_pairs(account_id: str) -> int:
    pool = get_pool()
    if pool:
        row = await fetch_one(
            "SELECT count(*)::int AS cnt FROM qa_pairs WHERE account_id = $1::uuid",
            account_id,
        )
        return row["cnt"] if row else 0
    res = await supabase_execute(
        supabase.table("qa_pairs")
        .select("id", count="exact")
        .eq("account_id", account_id)
    )
    return res.count if hasattr(res, "count") and res.count is not None else len(res.data or [])


# ──────────────────────────────────────────────────────────────────
# Extraction from conversation history
# ──────────────────────────────────────────────────────────────────

_LOW_QUALITY_STARTS = {
    "ok", "oui", "non", "d'accord", "entendu", "merci", "bien reçu",
    "bonjour", "bonsoir", "bonne journée", "bonne soirée", "à bientôt",
    "je me renseigne", "aucune idée", "je ne sais pas", "je sais pas",
}

def _is_low_quality_answer(answer: str) -> bool:
    """Filter out answers that are too vague, short, or purely acknowledgments."""
    a = answer.strip().lower().rstrip("!.,;: ")
    if len(a) < 25:
        return True
    first_sentence = a.split("\n")[0].split(".")[0].strip()
    if first_sentence in _LOW_QUALITY_STARTS:
        if len(a) < 60:
            return True
    return False


async def extract_qa_from_conversations(
    account_id: str,
    since_days: int = 365,
    min_question_len: int = 10,
    min_answer_len: int = 25,
) -> int:
    """
    Scan the last N days of conversations for this account, find
    human-operator outbound replies that follow an inbound message,
    and create Q&A pairs from them.

    Pairs are ordered newest-first so that when two questions are
    near-identical the most recent answer wins (inserted last = upsert
    overwrites the older one).

    Returns the number of new Q&A pairs created.
    """
    pool = get_pool()
    if not pool:
        logger.warning("extract_qa_from_conversations requires direct PostgreSQL pool")
        return 0

    # Pairs ordered by reply_ts ASC so that the most recent answer for a
    # given question is processed last and overwrites older ones via upsert.
    #
    # Pairing rules to avoid mismatched Q/A:
    #  1. The inbound question must be within 2 hours before the outbound reply.
    #  2. There must be no OTHER human-operator outbound message between the
    #     question and this reply (meaning the question was already answered).
    #  3. The question must be the most recent inbound before the reply.
    rows = await fetch_all(
        """
        WITH human_replies AS (
            SELECT
                m.id AS reply_id,
                m.conversation_id,
                m.content_text AS answer,
                m.timestamp AS reply_ts
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.account_id = $1::uuid
              AND m.direction = 'outbound'
              AND m.timestamp >= now() - make_interval(days => $2)
              AND (m.sent_via = 'ui' OR m.sent_by_user_id IS NOT NULL)
              AND m.content_text IS NOT NULL
              AND length(trim(m.content_text)) >= $4
              AND m.is_system IS NOT TRUE
        ),
        paired AS (
            SELECT
                hr.reply_id,
                hr.reply_ts,
                hr.answer,
                q.content_text AS question,
                q.timestamp    AS question_ts
            FROM human_replies hr
            CROSS JOIN LATERAL (
                SELECT qi.content_text, qi.timestamp
                FROM messages qi
                WHERE qi.conversation_id = hr.conversation_id
                  AND qi.direction = 'inbound'
                  AND qi.timestamp < hr.reply_ts
                  AND qi.timestamp > hr.reply_ts - interval '2 hours'
                  AND qi.content_text IS NOT NULL
                  AND length(trim(qi.content_text)) >= $3
                ORDER BY qi.timestamp DESC
                LIMIT 1
            ) q
            WHERE NOT EXISTS (
                SELECT 1 FROM messages mid
                WHERE mid.conversation_id = hr.conversation_id
                  AND mid.direction = 'outbound'
                  AND mid.timestamp > q.timestamp
                  AND mid.timestamp < hr.reply_ts
                  AND (mid.sent_via = 'ui' OR mid.sent_by_user_id IS NOT NULL)
                  AND mid.is_system IS NOT TRUE
            )
        )
        SELECT reply_id, question, answer, reply_ts
        FROM paired
        WHERE question IS NOT NULL
        ORDER BY reply_ts ASC
        LIMIT 5000
        """,
        account_id,
        since_days,
        min_question_len,
        min_answer_len,
    )

    if not rows:
        logger.info("extract_qa: no Q&A pairs found for account %s", account_id)
        return 0

    logger.info("extract_qa: found %d candidate pairs for account %s", len(rows), account_id)

    # Filter out pairs that already exist (by source_message_id)
    existing_ids = set()
    existing_rows = await fetch_all(
        "SELECT source_message_id FROM qa_pairs WHERE account_id = $1::uuid AND source = 'auto' AND source_message_id IS NOT NULL",
        account_id,
    )
    for er in existing_rows:
        mid = er.get("source_message_id")
        if mid:
            existing_ids.add(str(mid))

    new_pairs = [
        r for r in rows
        if str(r["reply_id"]) not in existing_ids
    ]

    if not new_pairs:
        logger.info("extract_qa: all pairs already exist for account %s", account_id)
        return 0

    logger.info("extract_qa: %d new pairs to embed for account %s", len(new_pairs), account_id)

    # Dedup by question text: keep only the newest answer per unique question.
    # Since rows are ordered ASC by reply_ts, later entries overwrite earlier.
    deduped: Dict[str, Dict[str, Any]] = {}
    for pair in new_pairs:
        q = (pair["question"] or "").strip().lower()
        if not q:
            continue
        key = q
        # Also collapse near-duplicates (same words)
        for existing_key in list(deduped.keys()):
            if _text_overlap(q, existing_key) > 0.85:
                key = existing_key
                break
        deduped[key] = pair  # newest wins (list is ASC)

    unique_pairs = list(deduped.values())
    logger.info(
        "extract_qa: %d unique pairs after dedup (from %d) for account %s",
        len(unique_pairs), len(new_pairs), account_id,
    )

    # Embed and insert (skip low-quality answers)
    created = 0
    skipped_quality = 0
    for pair in unique_pairs:
        q = (pair["question"] or "").strip()
        a = (pair["answer"] or "").strip()
        if not q or not a:
            continue
        if _is_low_quality_answer(a):
            skipped_quality += 1
            continue
        try:
            result = await upsert_qa_pair(
                account_id=account_id,
                question=q,
                answer=a,
                source="auto",
                source_message_id=str(pair["reply_id"]),
            )
            if result:
                created += 1
        except Exception as exc:
            logger.warning("extract_qa: failed to insert pair: %s", exc)

    logger.info(
        "extract_qa: created %d Q&A pairs for account %s (%d skipped low-quality)",
        created, account_id, skipped_quality,
    )
    return created


async def reembed_all(account_id: Optional[str] = None) -> int:
    """Re-compute embeddings for all existing Q&A pairs (or one account).

    Useful after changing the embedding strategy (e.g. Q-only → Q+A combined).
    Also removes low-quality pairs during the sweep.
    """
    pool = get_pool()
    if not pool:
        logger.warning("reembed_all requires direct PostgreSQL pool")
        return 0

    where = "WHERE account_id = $1::uuid" if account_id else ""
    args = [account_id] if account_id else []
    rows = await fetch_all(
        f"SELECT id, account_id, question, answer FROM qa_pairs {where} ORDER BY created_at",
        *args,
    )
    if not rows:
        return 0

    logger.info("reembed_all: %d pairs to process", len(rows))
    updated = 0
    deleted = 0

    for r in rows:
        q = (r.get("question") or "").strip()
        a = (r.get("answer") or "").strip()
        rid = str(r["id"])

        if not q or not a or _is_low_quality_answer(a):
            await execute("DELETE FROM qa_pairs WHERE id = $1::uuid", rid)
            deleted += 1
            continue

        embed_input = f"Q: {q}\nR: {a}"
        vec = await embed_text(embed_input)
        if not vec:
            continue

        vec_literal = "[" + ",".join(str(v) for v in vec) + "]"
        await execute(
            "UPDATE qa_pairs SET embedding = $1::vector WHERE id = $2::uuid",
            vec_literal,
            rid,
        )
        updated += 1

    logger.info(
        "reembed_all: %d updated, %d deleted (low quality), %d total processed",
        updated, deleted, len(rows),
    )
    return updated
