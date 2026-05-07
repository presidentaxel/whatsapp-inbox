from app.api.routes_axelia import _consume_sse_done_from_buffer


def test_consume_sse_done_from_fragmented_frames():
    buf = ""
    payload = None
    chunks = [
        "event: progress\ndata: {\"phase\":\"thinking\"}\n\n",
        "event: done\ndata: {\"text\": \"Bon",
        "jour\", \"model\": \"gemini-2.5-flash\"}\n\n",
    ]
    for chunk in chunks:
        buf += chunk
        buf, maybe = _consume_sse_done_from_buffer(buf)
        if maybe is not None:
            payload = maybe
    assert payload is not None
    assert payload["text"] == "Bonjour"
    assert payload["model"] == "gemini-2.5-flash"
    assert buf == ""


def test_consume_sse_done_keeps_incomplete_frame_in_buffer():
    buf, payload = _consume_sse_done_from_buffer(
        "event: done\ndata: {\"text\":\"partiel\"}"
    )
    assert payload is None
    assert "event: done" in buf
