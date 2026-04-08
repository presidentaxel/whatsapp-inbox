import pathlib

p = pathlib.Path(r'd:\Code\whatsapp-inbox\backend\app\services\flow_runtime_service.py')
c = p.read_text(encoding='utf-8')

# Fix 1: Add fallback when gemini text reply is empty/None
old1 = '''                    reply = await generate_flow_gemini_text_reply(
                        conversation_id,
                        account_id,
                        inbound_text,
                        sys_prompt,
                        hint if hint else None,
                    )
                    if vk:
                        variables[vk] = reply or ""'''

new1 = '''                    reply = await generate_flow_gemini_text_reply(
                        conversation_id,
                        account_id,
                        inbound_text,
                        sys_prompt,
                        hint if hint else None,
                    )
                    if not reply:
                        logger.warning(
                            "playground flow: gemini text reply empty/None for node %s, using fallback",
                            cursor,
                        )
                        reply = (
                            "Je suis disponible pour r\\u00e9pondre \\u00e0 vos questions. "
                            "Pouvez-vous reformuler votre demande ?"
                        )
                    if vk:
                        variables[vk] = reply'''

# Need to handle encoding carefully
old1_bytes = old1.encode('utf-8')
if old1 in c:
    c = c.replace(old1, new1, 1)
    print("Fix 1 applied")
else:
    print("Fix 1: looking for pattern...")
    # Try to find it
    marker = "reply = await generate_flow_gemini_text_reply("
    idx = c.find(marker)
    if idx >= 0:
        # Find the next "if vk:" after this
        end_marker = "variables[vk] = reply or \"\""
        end_idx = c.find(end_marker, idx)
        if end_idx >= 0:
            end_idx += len(end_marker)
            old_section = c[idx:end_idx]
            new_section = '''reply = await generate_flow_gemini_text_reply(
                        conversation_id,
                        account_id,
                        inbound_text,
                        sys_prompt,
                        hint if hint else None,
                    )
                    if not reply:
                        logger.warning(
                            "playground flow: gemini text reply empty/None for node %s, using fallback",
                            cursor,
                        )
                        reply = (
                            "Je suis disponible pour r\u00e9pondre \u00e0 vos questions. "
                            "Pouvez-vous reformuler votre demande ?"
                        )
                    if vk:
                        variables[vk] = reply'''
            c = c[:idx] + new_section + c[end_idx:]
            print("Fix 1 applied via marker search")
        else:
            print("Fix 1: could not find end marker")
    else:
        print("Fix 1: could not find start marker")

# Fix 2: Add unresolved template safety net in interactiveNode
old2 = "if ntype == \"interactiveNode\":"
# Find the body = _subst_vars line after interactiveNode
marker2 = "body = _subst_vars(data.get(\"body\") or \"\", variables)"
idx2 = c.find(marker2)
if idx2 >= 0:
    # Find "if not body:" after this
    check_marker = "if not body:"
    check_idx = c.find(check_marker, idx2)
    if check_idx >= 0:
        # Replace "if not body:" with a check that also handles unresolved templates
        nl = '\r\n' if '\r\n' in c[:100] else '\n'
        old_check = "            if not body:"
        new_check = f"            body = _strip_unresolved_vars(body){nl}            if not body:"
        # Only replace the first occurrence after idx2
        first_occurrence = c.find(old_check, idx2)
        if first_occurrence >= 0 and first_occurrence < idx2 + 500:
            c = c[:first_occurrence] + new_check + c[first_occurrence + len(old_check):]
            print("Fix 2 applied")
        else:
            print("Fix 2: could not find exact check location")
    else:
        print("Fix 2: could not find 'if not body' marker")
else:
    print("Fix 2: could not find body marker")

# Fix 3: Add _strip_unresolved_vars function before _subst_vars
func_marker = "def _subst_vars(text: str, variables: Dict[str, Any]) -> str:"
func_idx = c.find(func_marker)
if func_idx >= 0:
    nl = '\r\n' if '\r\n' in c[:100] else '\n'
    new_func = f'''_UNRESOLVED_VAR_RE = re.compile(r"\\{{\\{{[^{{}}]+\\}}\\}}"){nl}{nl}{nl}def _strip_unresolved_vars(text: str) -> str:{nl}    """{nl}    Si le texte ne contient QUE des {{{{...}}}} non r\u00e9solus (pas de texte r\u00e9el autour),{nl}    le remplacer par un fallback. Sinon, retirer les marqueurs restants.{nl}    """{nl}    if not text:{nl}        return text{nl}    stripped = _UNRESOLVED_VAR_RE.sub("", text).strip(){nl}    if not stripped:{nl}        return ""{nl}    return _UNRESOLVED_VAR_RE.sub("", text).strip() if _UNRESOLVED_VAR_RE.search(text) else text{nl}{nl}{nl}'''
    c = c[:func_idx] + new_func + c[func_idx:]
    print("Fix 3 applied")
else:
    print("Fix 3: could not find _subst_vars function")

p.write_text(c, encoding='utf-8')
print("Done")
