import asyncio
from app.core.db import supabase, supabase_execute

CONV_ID = "fb0b6803-b084-452a-acbe-18ca2e87499d"

async def reset():
    await supabase_execute(
        supabase.table("conversations")
        .update({"bot_flow_state": None})
        .eq("id", CONV_ID)
    )
    print(f"Reset bot_flow_state for {CONV_ID} - done.")

asyncio.run(reset())
