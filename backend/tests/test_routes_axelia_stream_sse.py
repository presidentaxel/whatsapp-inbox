import codecs

from app.api.routes_axelia import _consume_sse_done_from_buffer


def test_utf8_incremental_decode_split_multibyte_char():
    """Même scénario que le handler SSE : chunks bytes arbitraires ne doivent pas casser le JSON."""
    dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buf = ""
    inner = 'event: done\ndata: {"text": "Prise en charge café", "model": "m"}\n\n'
    raw = inner.encode("utf-8")
    # Coupure volontaire au milieu de « é » (U+00E9 = 0xC3 0xA9)
    cut = raw.index(b"caf") + 3
    c1, c2 = raw[:cut], raw[cut:]
    buf += dec.decode(c1)
    buf += dec.decode(c2)
    buf += dec.decode(b"", final=True)
    _rest, payload = _consume_sse_done_from_buffer(buf)
    assert payload is not None
    assert payload["text"] == "Prise en charge café"
    assert payload["model"] == "m"


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
