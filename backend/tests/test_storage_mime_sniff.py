"""Tests pour le sniff MIME (méthode B) de storage_service.

On vérifie que les magic bytes des formats principaux sont reconnus, et que
`resolve_upload_mime_type` se rabat correctement sur le sniff quand le MIME
déclaré est manquant ou `application/octet-stream`.
"""

from __future__ import annotations

import struct

import pytest

from app.services import storage_service as svc


# ---------------------------------------------------------------------------
# Échantillons d'octets minimaux qui suffisent pour reconnaître un format.
# (On n'a pas besoin d'un fichier valide bout-en-bout, juste les magic bytes.)
# ---------------------------------------------------------------------------


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 12


def _gif() -> bytes:
    return b"GIF89a" + b"\x00" * 16


def _bmp() -> bytes:
    return b"BM" + b"\x00" * 32


def _webp() -> bytes:
    # RIFF + size (4 octets) + 'WEBP'
    return b"RIFF" + struct.pack("<I", 1024) + b"WEBPVP8 " + b"\x00" * 8


def _wav() -> bytes:
    return b"RIFF" + struct.pack("<I", 1024) + b"WAVEfmt " + b"\x00" * 8


def _avi() -> bytes:
    return b"RIFF" + struct.pack("<I", 1024) + b"AVI LIST" + b"\x00" * 8


def _pdf() -> bytes:
    return b"%PDF-1.7\n" + b"\x00" * 16


def _mp4(brand: bytes = b"isom") -> bytes:
    # 4 octets size + "ftyp" + brand + 4 octets minor + compat brands
    return b"\x00\x00\x00\x20" + b"ftyp" + brand + b"\x00\x00\x00\x00" + b"isom" * 2


def _quicktime() -> bytes:
    return _mp4(brand=b"qt  ")


def _audio_m4a() -> bytes:
    return _mp4(brand=b"M4A ")


def _3gp() -> bytes:
    return _mp4(brand=b"3gp4")


def _webm() -> bytes:
    # EBML header (Matroska / WebM)
    return b"\x1a\x45\xdf\xa3" + b"\x00" * 28


def _ogg() -> bytes:
    return b"OggS" + b"\x00" * 28


def _mp3_with_id3() -> bytes:
    return b"ID3\x04\x00\x00" + b"\x00" * 26


def _mp3_frame() -> bytes:
    return b"\xff\xfb\x90\x00" + b"\x00" * 28


def _zip() -> bytes:
    return b"PK\x03\x04" + b"\x00" * 28


def _rar() -> bytes:
    return b"Rar!\x1a\x07\x00" + b"\x00" * 28


# ---------------------------------------------------------------------------
# sniff_mime_from_bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data,expected",
    [
        (_png(), "image/png"),
        (_jpeg(), "image/jpeg"),
        (_gif(), "image/gif"),
        (_bmp(), "image/bmp"),
        (_webp(), "image/webp"),
        (_wav(), "audio/wav"),
        (_avi(), "video/x-msvideo"),
        (_pdf(), "application/pdf"),
        (_mp4(), "video/mp4"),
        (_quicktime(), "video/quicktime"),
        (_audio_m4a(), "audio/mp4"),
        (_3gp(), "video/3gpp"),
        (_webm(), "video/webm"),
        (_ogg(), "audio/ogg"),
        (_mp3_with_id3(), "audio/mpeg"),
        (_mp3_frame(), "audio/mpeg"),
        (_zip(), "application/zip"),
        (_rar(), "application/vnd.rar"),
    ],
)
def test_sniff_recognises_known_formats(data, expected):
    assert svc.sniff_mime_from_bytes(data) == expected


def test_sniff_returns_none_for_garbage():
    assert svc.sniff_mime_from_bytes(b"") is None
    assert svc.sniff_mime_from_bytes(b"abc") is None  # trop court
    assert svc.sniff_mime_from_bytes(b"\x00" * 64) is None  # pas de signature


def test_sniff_unknown_ftyp_brand_falls_back_to_mp4():
    # ftyp avec brand inconnu → on retombe sur video/mp4 (cas le plus courant)
    blob = b"\x00\x00\x00\x20" + b"ftyp" + b"XXXX" + b"\x00\x00\x00\x00" + b"\x00" * 16
    assert svc.sniff_mime_from_bytes(blob) == "video/mp4"


# ---------------------------------------------------------------------------
# normalize_mime_type
# ---------------------------------------------------------------------------


def test_normalize_strips_params_and_lowercases():
    assert svc.normalize_mime_type("Image/JPEG; charset=binary") == "image/jpeg"


def test_normalize_returns_none_for_octet_stream():
    assert svc.normalize_mime_type("application/octet-stream") is None
    assert svc.normalize_mime_type("APPLICATION/OCTET-STREAM") is None


def test_normalize_returns_none_for_empty():
    assert svc.normalize_mime_type("") is None
    assert svc.normalize_mime_type(None) is None
    assert svc.normalize_mime_type("   ") is None


# ---------------------------------------------------------------------------
# resolve_upload_mime_type : flux complet (méthode B en action)
# ---------------------------------------------------------------------------


def test_resolve_keeps_declared_when_valid():
    mime, source = svc.resolve_upload_mime_type(
        declared="image/png", media_data=b"any", log_label="t1"
    )
    assert mime == "image/png"
    assert source == "declared"


def test_resolve_falls_back_to_sniff_when_octet_stream():
    mime, source = svc.resolve_upload_mime_type(
        declared="application/octet-stream",
        media_data=_png(),
        log_label="t2",
    )
    assert mime == "image/png"
    assert source == "sniff"


def test_resolve_falls_back_to_sniff_when_declared_empty():
    mime, source = svc.resolve_upload_mime_type(
        declared="", media_data=_pdf(), log_label="t3"
    )
    assert mime == "application/pdf"
    assert source == "sniff"


def test_resolve_keeps_octet_stream_when_sniff_fails():
    """
    Si le contenu n'est ni reconnu ni déclaré, on retourne `application/octet-stream`
    en `fallback` - Supabase rejettera l'upload (415), mais le log permettra de
    diagnostiquer.
    """
    mime, source = svc.resolve_upload_mime_type(
        declared="application/octet-stream",
        media_data=b"\x00" * 64,
        log_label="t4",
    )
    assert mime == "application/octet-stream"
    assert source == "fallback"


def test_resolve_strips_charset_param():
    mime, source = svc.resolve_upload_mime_type(
        declared="audio/mpeg; charset=binary",
        media_data=b"",
        log_label="t5",
    )
    assert mime == "audio/mpeg"
    assert source == "declared"


def test_resolve_logs_warning_when_sniff_returns_unallowed_mime(caplog):
    """
    Un type comme `video/3gpp` n'est pas dans la whitelist du bucket Supabase :
    on doit journaliser un warning explicite (sans casser).
    """
    with caplog.at_level("WARNING"):
        mime, source = svc.resolve_upload_mime_type(
            declared=None,
            media_data=_3gp(),
            log_label="3gp-case",
        )
    assert mime == "video/3gpp"
    assert source == "sniff"
    assert any("hors liste bucket" in r.message for r in caplog.records)
