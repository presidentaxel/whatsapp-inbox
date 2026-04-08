import asyncio
from app.core.db import supabase, supabase_execute

async def check():
    r = await supabase_execute(
        supabase.table("conversations")
        .select("id, bot_flow_state, playground_flow_id, bot_enabled")
        .not_.is_("bot_flow_state", "null")
        .limit(10)
    )
    for row in r.data:
        st = row.get("bot_flow_state") or {}
        cid = row["id"]
        fid = row.get("playground_flow_id")
        bot = row.get("bot_enabled")
        cur = st.get("currentNodeId")
        cont = st.get("continueFromNodeId")
        vkeys = list((st.get("variables") or {}).keys())
        print(f"conv={cid}  flow={fid}  bot={bot}  currentNode={cur}  continue={cont}  vars={vkeys}")

asyncio.run(check())
