"""CRUD + extraction + search endpoints for RAG Q&A pairs."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.permissions import CurrentUser, PermissionCodes
from app.services.account_service import get_account_by_id
from app.services.qa_service import (
    count_qa_pairs,
    delete_qa_pair,
    extract_qa_from_conversations,
    list_qa_pairs,
    search_similar_qa,
    upsert_qa_pair,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class QaPairCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None


class QaPairUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None


class ExtractRequest(BaseModel):
    since_days: int = 365


# ── Helpers ──────────────────────────────────────────────────────

async def _require_account(account_id: str, current_user: CurrentUser):
    account = await get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account_not_found")
    has_access = (
        current_user.permissions.has(PermissionCodes.SETTINGS_MANAGE, account_id)
        or current_user.permissions.has(PermissionCodes.CONVERSATIONS_VIEW, account_id)
        or current_user.permissions.has(PermissionCodes.PERMISSIONS_VIEW, account_id)
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="permission_denied")
    return account


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/{account_id}")
async def get_qa_list(
    account_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    await _require_account(account_id, current_user)
    items = await list_qa_pairs(account_id, limit=limit, offset=offset)
    total = await count_qa_pairs(account_id)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/{account_id}")
async def create_qa(
    account_id: str,
    body: QaPairCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    await _require_account(account_id, current_user)
    if not body.question.strip() or not body.answer.strip():
        raise HTTPException(status_code=400, detail="question and answer required")
    result = await upsert_qa_pair(
        account_id=account_id,
        question=body.question,
        answer=body.answer,
        category=body.category,
        source="manual",
    )
    if not result:
        raise HTTPException(status_code=500, detail="failed to create Q&A pair")
    return result


@router.put("/{account_id}/{qa_id}")
async def update_qa(
    account_id: str,
    qa_id: str,
    body: QaPairUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    await _require_account(account_id, current_user)

    from app.core.pg import get_pool, fetch_one
    from app.core.db import supabase, supabase_execute

    pool = get_pool()
    if pool:
        found = await fetch_one(
            "SELECT id, question, answer, category, source FROM qa_pairs WHERE id = $1::uuid AND account_id = $2::uuid",
            qa_id, account_id,
        )
        found = dict(found) if found else None
    else:
        res = await supabase_execute(
            supabase.table("qa_pairs")
            .select("id, question, answer, category, source")
            .eq("id", qa_id)
            .eq("account_id", account_id)
            .limit(1)
        )
        found = res.data[0] if res.data else None

    if not found:
        raise HTTPException(status_code=404, detail="qa_pair_not_found")
    result = await upsert_qa_pair(
        account_id=account_id,
        question=body.question or found["question"],
        answer=body.answer or found["answer"],
        category=body.category if body.category is not None else found.get("category"),
        source=found.get("source", "manual"),
        qa_id=qa_id,
    )
    return result


@router.delete("/{account_id}/{qa_id}")
async def remove_qa(
    account_id: str,
    qa_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    await _require_account(account_id, current_user)
    await delete_qa_pair(qa_id)
    return {"ok": True}


@router.post("/{account_id}/extract")
async def extract_qa(
    account_id: str,
    body: ExtractRequest = ExtractRequest(),
    current_user: CurrentUser = Depends(get_current_user),
):
    await _require_account(account_id, current_user)
    created = await extract_qa_from_conversations(
        account_id, since_days=body.since_days
    )
    total = await count_qa_pairs(account_id)
    return {"created": created, "total": total}


@router.get("/{account_id}/search")
async def search_qa(
    account_id: str,
    q: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=20),
    current_user: CurrentUser = Depends(get_current_user),
):
    await _require_account(account_id, current_user)
    results = await search_similar_qa(account_id, q, limit=limit)
    return {"results": results, "query": q}
