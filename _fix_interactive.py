"""Patch: add safety net to interactiveNode handler."""
import pathlib

fp = pathlib.Path(r"d:\Code\whatsapp-inbox\backend\app\services\flow_runtime_service.py")
src = fp.read_text(encoding="utf-8")

# Target: interactiveNode handler specifically
old = (
    'if ntype == "interactiveNode":\n'
    '            body = _subst_vars(data.get("body") or "", variables)\n'
    '            _warn_unresolved_vars(body, cursor)\n'
    '            kind = data.get("uiKind")'
)

new = (
    'if ntype == "interactiveNode":\n'
    '            body = _subst_vars(data.get("body") or "", variables)\n'
    '            _warn_unresolved_vars(body, cursor)\n'
    '            body = re.sub(r"\\{\\{[^}]+\\}\\}", "", body).strip()\n'
    '            if not body:\n'
    '                body = "Pouvez-vous pr\u00e9ciser votre r\u00e9ponse ?"\n'
    '            kind = data.get("uiKind")'
)

for le in ['\r\n', '\n']:
    o = old.replace('\n', le)
    if o in src:
        src = src.replace(o, new.replace('\n', le), 1)
        print("interactiveNode safety net: OK")
        break
else:
    print("NOT FOUND")

fp.write_text(src, encoding="utf-8")
print("Done.")
