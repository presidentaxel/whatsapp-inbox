"""Tests pour la chaîne « image jointe → en-tête template Meta ».

Couvre :
- robustesse du décodage base64 dans `_build_contents` (whitespace, data URL, padding) ;
- propagation de la PJ via `AxeliaPendingAttachment` ;
- skill `prepare_template_image_header` :
  - erreur quand pas de PJ vivante,
  - erreur sur format invalide / taille excessive,
  - chemin nominal (upload mocké → renvoie media_id) ;
- contenu du catalogue / prompt section (le LLM doit voir le nouveau skill et le workflow).
"""

from __future__ import annotations

import base64

import pytest

from app.services import axelia_chat_service as svc
from app.services import playground_skills as skills


# ---------------------------------------------------------------------------
# Décodage base64 : on tolère les data URL, les espaces / sauts de ligne, et
# le padding manquant. Une chaîne réellement invalide lève toujours.
# ---------------------------------------------------------------------------


def _png_bytes() -> bytes:
    # 1x1 pixel transparent PNG (octets fixes)
    return bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
        "890000000A49444154789C6300010000000500010D0A2DB40000000049454E44"
        "AE426082"
    )


def test_decode_attachment_b64_clean():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    assert svc._decode_attachment_b64(b64) == raw


def test_decode_attachment_b64_strips_data_url_prefix():
    raw = _png_bytes()
    b64 = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    assert svc._decode_attachment_b64(b64) == raw


def test_decode_attachment_b64_tolerates_whitespace_and_newlines():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    # On insère des CRLF tous les 12 caractères (cas vu en prod via certains clients HTTP)
    chunks = [b64[i : i + 12] for i in range(0, len(b64), 12)]
    polluted = "\r\n  ".join(chunks) + "\n"
    assert svc._decode_attachment_b64(polluted) == raw


def test_decode_attachment_b64_repairs_missing_padding():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode("ascii").rstrip("=")
    assert svc._decode_attachment_b64(b64) == raw


def test_decode_attachment_b64_rejects_empty():
    with pytest.raises(ValueError) as ex:
        svc._decode_attachment_b64("")
    assert "attachment_invalid_base64" in str(ex.value)


def test_decode_attachment_b64_rejects_non_string():
    with pytest.raises(ValueError):
        svc._decode_attachment_b64(None)  # type: ignore[arg-type]


def test_decode_attachment_b64_rejects_garbage():
    with pytest.raises(ValueError) as ex:
        svc._decode_attachment_b64("@@@@@@")
    assert "attachment_invalid_base64" in str(ex.value)


# ---------------------------------------------------------------------------
# `_build_contents` : avec PJ propre et avec PJ « polluée » (whitespace).
# ---------------------------------------------------------------------------


def test_build_contents_accepts_clean_image():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    out = svc._build_contents(
        [{"role": "user", "text": "Voici"}],
        {"mime_type": "image/png", "data_base64": b64},
    )
    assert len(out) == 1
    parts = out[0]["parts"]
    inline = next(p for p in parts if "inlineData" in p)
    assert inline["inlineData"]["mimeType"] == "image/png"
    # On reçoit du base64 propre côté Gemini, sans whitespace.
    re_b64 = inline["inlineData"]["data"]
    assert "\n" not in re_b64 and " " not in re_b64
    assert base64.b64decode(re_b64) == raw


def test_build_contents_accepts_image_with_whitespace():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    polluted = "\n".join(b64[i : i + 16] for i in range(0, len(b64), 16))
    out = svc._build_contents(
        [{"role": "user", "text": "Voici"}],
        {"mime_type": "image/png", "data_base64": polluted},
    )
    inline = next(p for p in out[0]["parts"] if "inlineData" in p)
    # Le base64 ré-injecté est nettoyé.
    assert "\n" not in inline["inlineData"]["data"]


def test_build_contents_rejects_unsupported_mime():
    with pytest.raises(ValueError) as ex:
        svc._build_contents(
            [{"role": "user", "text": "x"}],
            {"mime_type": "application/zip", "data_base64": "AAAA"},
        )
    assert "attachment_unsupported_mime" in str(ex.value)


def test_build_contents_rejects_invalid_base64():
    with pytest.raises(ValueError) as ex:
        svc._build_contents(
            [{"role": "user", "text": "x"}],
            {"mime_type": "image/png", "data_base64": ""},
        )
    assert "attachment_invalid_base64" in str(ex.value)


# ---------------------------------------------------------------------------
# Runtime étendu : `AxeliaPendingAttachment` doit être propagé via le ContextVar.
# ---------------------------------------------------------------------------


def test_axelia_runtime_has_pending_attachment_slot():
    rt = skills.AxeliaSkillsRuntime(
        acting_user=None,
        perimeter_mode="single",
        pending_attachment=skills.AxeliaPendingAttachment(
            mime_type="image/png", raw_bytes=b"\x89PNG..."
        ),
    )
    assert rt.pending_attachment is not None
    assert rt.pending_attachment.mime_type == "image/png"


def test_axelia_runtime_default_no_attachment():
    rt = skills.AxeliaSkillsRuntime(acting_user=None, perimeter_mode="all")
    assert rt.pending_attachment is None


# ---------------------------------------------------------------------------
# Skill `prepare_template_image_header`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_image_header_requires_pending_attachment(monkeypatch):
    # Aucun runtime → aucune PJ
    monkeypatch.setattr(skills, "_axelia_rt", lambda: None)
    out = await skills._skill_prepare_template_image_header({}, {"id": "acc1"})
    assert "error" in out
    assert "image jointe" in out["error"].lower()


@pytest.mark.asyncio
async def test_skill_image_header_rejects_invalid_mime(monkeypatch):
    rt = skills.AxeliaSkillsRuntime(
        acting_user=None,
        perimeter_mode="single",
        pending_attachment=skills.AxeliaPendingAttachment(
            mime_type="image/gif", raw_bytes=b"GIF89a..."
        ),
    )
    monkeypatch.setattr(skills, "_axelia_rt", lambda: rt)
    out = await skills._skill_prepare_template_image_header(
        {}, {"id": "acc", "waba_id": "w", "access_token": "t", "phone_number_id": "p"}
    )
    assert "error" in out
    assert "image/jpeg" in out["error"] or "image/png" in out["error"]


@pytest.mark.asyncio
async def test_skill_image_header_rejects_oversize(monkeypatch):
    big = b"\x89PNG" + b"\x00" * (skills._TEMPLATE_HEADER_MAX_BYTES + 10)
    rt = skills.AxeliaSkillsRuntime(
        acting_user=None,
        perimeter_mode="single",
        pending_attachment=skills.AxeliaPendingAttachment(
            mime_type="image/png", raw_bytes=big
        ),
    )
    monkeypatch.setattr(skills, "_axelia_rt", lambda: rt)
    out = await skills._skill_prepare_template_image_header(
        {}, {"id": "a", "waba_id": "w", "access_token": "t", "phone_number_id": "p"}
    )
    assert "error" in out
    assert "5 Mo" in out["error"] or "volumineuse" in out["error"]


@pytest.mark.asyncio
async def test_skill_image_header_requires_phone_number_id(monkeypatch):
    raw = _png_bytes()
    rt = skills.AxeliaSkillsRuntime(
        acting_user=None,
        perimeter_mode="single",
        pending_attachment=skills.AxeliaPendingAttachment(
            mime_type="image/png", raw_bytes=raw
        ),
    )
    monkeypatch.setattr(skills, "_axelia_rt", lambda: rt)
    out = await skills._skill_prepare_template_image_header(
        {}, {"id": "a", "waba_id": "w", "access_token": "t"}
    )
    assert "error" in out
    assert "phone_number_id" in out["error"]


@pytest.mark.asyncio
async def test_skill_image_header_happy_path(monkeypatch):
    raw = _png_bytes()
    rt = skills.AxeliaSkillsRuntime(
        acting_user=None,
        perimeter_mode="single",
        pending_attachment=skills.AxeliaPendingAttachment(
            mime_type="image/png", raw_bytes=raw
        ),
    )
    monkeypatch.setattr(skills, "_axelia_rt", lambda: rt)

    captured: dict = {}

    async def _fake_upload(
        *, phone_number_id, access_token, file_content, filename, mime_type
    ):
        captured.update(
            {
                "pid": phone_number_id,
                "tok": access_token,
                "size": len(file_content),
                "filename": filename,
                "mime": mime_type,
            }
        )
        return {"id": "upload_xyz_123"}

    # Le skill importe la fonction dynamiquement → on patche le module source.
    import app.services.whatsapp_api_service as wa_api

    monkeypatch.setattr(wa_api, "upload_media_from_bytes", _fake_upload)

    out = await skills._skill_prepare_template_image_header(
        {},
        {
            "id": "acc-1",
            "waba_id": "waba-1",
            "access_token": "tok-1",
            "phone_number_id": "pn-1",
        },
    )
    assert out.get("success") is True
    assert out.get("media_id") == "upload_xyz_123"
    assert out.get("mime_type") == "image/png"
    assert captured["pid"] == "pn-1"
    assert captured["tok"] == "tok-1"
    assert captured["mime"] == "image/png"
    assert captured["size"] == len(raw)
    assert "header_handle" in (out.get("usage_hint") or "").lower()


# ---------------------------------------------------------------------------
# Catalogue + prompt section : le modèle doit voir le nouveau skill et la séquence.
# ---------------------------------------------------------------------------


def test_catalog_lists_prepare_template_image_header():
    entry = next(
        (s for s in skills.SKILLS_CATALOG if s["name"] == "prepare_template_image_header"),
        None,
    )
    assert entry is not None
    assert entry["parameters"] == []
    assert "header_handle" in entry["description"].lower() or "media_id" in entry["description"].lower()


def test_dispatcher_knows_new_skill():
    assert "prepare_template_image_header" in skills._SKILL_HANDLERS


def test_axelia_skills_prompt_section_documents_image_header_workflow():
    text = skills.get_axelia_skills_prompt_section()
    assert "prepare_template_image_header" in text
    assert "header_handle" in text
    assert "5 Mo" in text or "5 Mo" in text  # taille limite
    # Doit nommer la séquence : prepare puis create_template
    assert text.find("prepare_template_image_header") < text.find("create_template", text.find("prepare_template_image_header"))
