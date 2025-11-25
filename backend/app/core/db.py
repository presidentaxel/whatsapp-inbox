import asyncio
import logging
from supabase import create_client
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

async def supabase_execute(query_builder, timeout: float = 10.0):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(query_builder.execute),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error("Supabase query timeout after %ss", timeout)
        raise HTTPException(status_code=504, detail="database_timeout")