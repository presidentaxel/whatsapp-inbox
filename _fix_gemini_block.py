"""Patch flow_runtime_service.py: wrap gemini gen in try/except BaseException,
add safety net for unresolved {{…}} in interactiveNode and sendText."""

import re, pathlib

fp = pathlib.Path(r"d:\Code\whatsapp-inbox\backend\app\services\flow_runtime_service.py")
src = fp.read_text(encoding="utf-8")

# ── FIX 1: wrap gemini gen text block in try/except BaseException ──
old_gemini = (
    '                if sys_raw:\n'
    '                    # Prompt de sc\u00e9nario : remplit {{varKey}} pour le n\u0153ud suivant (interactive / texte).\n'
    '                    # Pas d\u2019envoi WhatsApp ici pour \u00e9viter le doublon avec ce n\u0153ud suivant.\n'
    '                    sys_prompt = _subst_vars(sys_raw, variables)\n'
    '                    hint = data.get("hint") or ""\n'
    '                    reply = await generate_flow_gemini_text_reply(\n'
    '                        conversation_id,\n'
    '                        account_id,\n'
    '                        inbound_text,\n'
    '                        sys_prompt,\n'
    '                        hint if hint else None,\n'
    '                    )\n'
    '                    if not reply:\n'
    '                        logger.warning(\n'
    '                            "playground flow: gemini text reply returned None for node %s, "\n'
    '                            "using fallback. inbound=%r",\n'
    '                            cursor, (inbound_text or "")[:80],\n'
    '                        )\n'
    '                    if vk:\n'
    '                        variables[vk] = reply if reply else (\n'
    '                            "Je suis l\u00e0 pour vous aider. Pouvez-vous pr\u00e9ciser votre r\u00e9ponse ?"\n'
    '                        )\n'
    '                    cursor = _successor(edges, cursor) or _successor(\n'
    '                        edges, cursor, "intent-unknown"\n'
    '                    )\n'
    '                    continue\n'
    '                cname = contact.get("display_name") or contact.get("whatsapp_number")\n'
    '                reply = await generate_bot_reply(\n'
    '                    conversation_id,\n'
    '                    account_id,\n'
    '                    inbound_text,\n'
    '                    cname,\n'
    '                )\n'
    '                if vk:\n'
    '                    variables[vk] = reply or ""\n'
    '                if reply:\n'
    '                    await send_message(\n'
    '                        {"conversation_id": conversation_id, "content": reply},\n'
    '                        skip_bot_trigger=True,\n'
    '                    )\n'
    '                cursor = _successor(edges, cursor) or _successor(\n'
    '                    edges, cursor, "intent-unknown"\n'
    '                )\n'
    '                continue'
)

new_gemini = (
    '                if sys_raw:\n'
    '                    reply = None\n'
    '                    try:\n'
    '                        sys_prompt = _subst_vars(sys_raw, variables)\n'
    '                        hint = data.get("hint") or ""\n'
    '                        reply = await generate_flow_gemini_text_reply(\n'
    '                            conversation_id,\n'
    '                            account_id,\n'
    '                            inbound_text,\n'
    '                            sys_prompt,\n'
    '                            hint if hint else None,\n'
    '                        )\n'
    '                    except BaseException as _gemini_exc:\n'
    '                        logger.error(\n'
    '                            "playground flow: gemini gen CRASHED for node %s: %s",\n'
    '                            cursor, _gemini_exc,\n'
    '                        )\n'
    '                    if not reply:\n'
    '                        logger.warning(\n'
    '                            "playground flow: gemini text reply empty/None for node %s, "\n'
    '                            "using fallback. inbound=%r  vars=%s",\n'
    '                            cursor, (inbound_text or "")[:80],\n'
    '                            list(variables.keys()),\n'
    '                        )\n'
    '                    if vk:\n'
    '                        variables[vk] = reply if reply else (\n'
    '                            "Je suis l\u00e0 pour vous aider. Pouvez-vous pr\u00e9ciser votre r\u00e9ponse ?"\n'
    '                        )\n'
    '                        logger.info(\n'
    '                            "playground flow: set var %r = %r (node %s)",\n'
    '                            vk, (variables[vk] or "")[:60], cursor,\n'
    '                        )\n'
    '                    cursor = _successor(edges, cursor) or _successor(\n'
    '                        edges, cursor, "intent-unknown"\n'
    '                    )\n'
    '                    continue\n'
    '                reply = None\n'
    '                try:\n'
    '                    cname = contact.get("display_name") or contact.get("whatsapp_number")\n'
    '                    reply = await generate_bot_reply(\n'
    '                        conversation_id,\n'
    '                        account_id,\n'
    '                        inbound_text,\n'
    '                        cname,\n'
    '                    )\n'
    '                except BaseException as _bot_exc:\n'
    '                    logger.error(\n'
    '                        "playground flow: bot reply CRASHED for node %s: %s",\n'
    '                        cursor, _bot_exc,\n'
    '                    )\n'
    '                if vk:\n'
    '                    variables[vk] = reply if reply else (\n'
    '                        "Je suis l\u00e0 pour vous aider. Pouvez-vous pr\u00e9ciser votre r\u00e9ponse ?"\n'
    '                    )\n'
    '                if reply:\n'
    '                    await send_message(\n'
    '                        {"conversation_id": conversation_id, "content": reply},\n'
    '                        skip_bot_trigger=True,\n'
    '                    )\n'
    '                cursor = _successor(edges, cursor) or _successor(\n'
    '                    edges, cursor, "intent-unknown"\n'
    '                )\n'
    '                continue'
)

# Normalize line endings for matching
for le in ['\r\n', '\n']:
    old_norm = old_gemini.replace('\n', le)
    if old_norm in src:
        src = src.replace(old_norm, new_gemini.replace('\n', le), 1)
        print("FIX 1 (gemini gen block): OK")
        break
else:
    print("FIX 1: NOT FOUND - dumping context around 'if sys_raw:'")
    idx = src.find("if sys_raw:")
    if idx >= 0:
        print(repr(src[idx-20:idx+200]))
    else:
        print("'if sys_raw:' not found at all!")

# ── FIX 2: safety net in interactiveNode - strip unresolved {{…}} ──
old_interactive = '            body = _subst_vars(data.get("body") or "", variables)\n            _warn_unresolved_vars(body, cursor)'
new_interactive = (
    '            body = _subst_vars(data.get("body") or "", variables)\n'
    '            _warn_unresolved_vars(body, cursor)\n'
    '            body = re.sub(r"\\{\\{[^}]+\\}\\}", "", body).strip()\n'
    '            if not body:\n'
    '                body = "Pouvez-vous pr\u00e9ciser votre r\u00e9ponse ?"'
)

for le in ['\r\n', '\n']:
    old_i = old_interactive.replace('\n', le)
    if old_i in src:
        src = src.replace(old_i, new_interactive.replace('\n', le), 1)
        print("FIX 2 (interactiveNode safety net): OK")
        break
else:
    print("FIX 2: NOT FOUND")

# ── FIX 3: safety net in sendText - strip unresolved {{…}} ──
old_sendtext = '            body = _subst_vars(data.get("body") or "", variables)\n            _warn_unresolved_vars(body, cursor)\n            if body:'
new_sendtext = (
    '            body = _subst_vars(data.get("body") or "", variables)\n'
    '            _warn_unresolved_vars(body, cursor)\n'
    '            body = re.sub(r"\\{\\{[^}]+\\}\\}", "", body).strip()\n'
    '            if body:'
)

for le in ['\r\n', '\n']:
    old_s = old_sendtext.replace('\n', le)
    if old_s in src:
        src = src.replace(old_s, new_sendtext.replace('\n', le), 1)
        print("FIX 3 (sendText safety net): OK")
        break
else:
    print("FIX 3: NOT FOUND")

# ── FIX 4: also wrap gemini keyword (intent) call in try/except BaseException ──
old_keyword = (
    '            sys_prompt = _subst_vars(data.get("systemPrompt") or "", variables)\n'
    '            hint = data.get("hint") or ""\n'
    '            keyword = await generate_flow_gemini_keyword(\n'
    '                conversation_id,\n'
    '                account_id,\n'
    '                inbound_text,\n'
    '                sys_prompt,\n'
    '                hint if hint else None,\n'
    '            )\n'
    '            if not keyword:'
)
new_keyword = (
    '            sys_prompt = _subst_vars(data.get("systemPrompt") or "", variables)\n'
    '            hint = data.get("hint") or ""\n'
    '            keyword = None\n'
    '            try:\n'
    '                keyword = await generate_flow_gemini_keyword(\n'
    '                    conversation_id,\n'
    '                    account_id,\n'
    '                    inbound_text,\n'
    '                    sys_prompt,\n'
    '                    hint if hint else None,\n'
    '                )\n'
    '            except BaseException as _kw_exc:\n'
    '                logger.error(\n'
    '                    "playground flow: gemini keyword CRASHED for node %s: %s",\n'
    '                    cursor, _kw_exc,\n'
    '                )\n'
    '            if not keyword:'
)

for le in ['\r\n', '\n']:
    old_k = old_keyword.replace('\n', le)
    if old_k in src:
        src = src.replace(old_k, new_keyword.replace('\n', le), 1)
        print("FIX 4 (gemini keyword try/except): OK")
        break
else:
    print("FIX 4: NOT FOUND")

fp.write_text(src, encoding="utf-8")
print("Done - file saved.")
