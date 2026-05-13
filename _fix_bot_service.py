"""Patch bot_service.py: catch BaseException in generate_flow_gemini_text_reply."""
import pathlib

fp = pathlib.Path(r"d:\Code\whatsapp-inbox\backend\app\services\bot_service.py")
src = fp.read_text(encoding="utf-8")

old = '    except Exception as exc:\n        logger.error("Flow Gemini text reply failed for %s: %s", conversation_id, exc)\n        return None'

new = '    except BaseException as exc:\n        logger.error("Flow Gemini text reply failed for %s: %s (%s)", conversation_id, exc, type(exc).__name__)\n        return None'

for le in ['\r\n', '\n']:
    o = old.replace('\n', le)
    if o in src:
        src = src.replace(o, new.replace('\n', le), 1)
        print("bot_service BaseException fix: OK")
        break
else:
    print("NOT FOUND")

fp.write_text(src, encoding="utf-8")
print("Done.")
