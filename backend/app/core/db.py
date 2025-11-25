from supabase import create_client
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


async def supabase_execute(query_builder):
    """
    Run a Supabase query in a worker thread so FastAPI's event loop stays free.
    """
    return await run_in_threadpool(query_builder.execute)