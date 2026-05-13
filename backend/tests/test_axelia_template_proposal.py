"""Tests pour le mode « propose-puis-corrige » de create_template côté Axelia.

L'objectif est de vérifier que le catalogue + le prompt section communiquent au
modèle :

1. qu'il doit proposer un spec complet d'emblée (texte + nom + catégorie + langue),
2. qu'il ne doit pas demander le nom et la catégorie en tours séparés,
3. qu'il doit ré-émettre l'appel avec les corrections sans relancer une question,
4. les défauts attendus (snake_case, MARKETING vs UTILITY, fr).

Ces tests sont volontairement « contractuels » sur le contenu du prompt :
ils protègent la consigne de régressions silencieuses.
"""

from __future__ import annotations

from app.services import playground_skills as skills


def _create_template_entry() -> dict:
    entry = next(
        (s for s in skills.SKILLS_CATALOG if s["name"] == "create_template"),
        None,
    )
    assert entry is not None, "create_template doit rester dans SKILLS_CATALOG"
    return entry


def test_create_template_use_when_enforces_propose_then_correct():
    use_when = _create_template_entry()["use_when"].lower()
    # Le mode propose-puis-corrige est explicite
    assert "propose-puis-corrige" in use_when
    # Interdit explicite des questions séparées
    assert "jamais" in use_when
    assert "questions séparées" in use_when


def test_create_template_use_when_states_defaults():
    use_when = _create_template_entry()["use_when"]
    # Défauts encodés : nom snake_case, catégorie heuristique, langue fr
    assert "snake_case" in use_when
    assert "MARKETING" in use_when and "UTILITY" in use_when
    assert "language = 'fr'" in use_when or "language='fr'" in use_when


def test_create_template_use_when_handles_corrections():
    use_when = _create_template_entry()["use_when"]
    # La consigne sur la correction doit être présente
    assert "corrige" in use_when.lower()
    assert "ré-émets" in use_when.lower() or "re-emets" in use_when.lower()


def test_axelia_skills_prompt_section_documents_propose_then_correct():
    text = skills.get_axelia_skills_prompt_section()
    # Mode propose-puis-corrige, rappel d'absence de questions séparées
    assert "PROPOSE-PUIS-CORRIGE" in text
    # Les 3 axes du spec complet
    assert "nom suggéré" in text and "catégorie suggérée" in text
    # Carte UI = validation finale (pas de tour intermédiaire)
    assert "n'enchaîne PAS un tour intermédiaire" in text
    # Comportement face à une correction
    assert "RÉ-ÉMETS create_template" in text


def test_axelia_skills_prompt_section_lists_defaults():
    text = skills.get_axelia_skills_prompt_section()
    assert "MARKETING" in text and "UTILITY" in text
    assert "snake_case" in text
    assert "language = 'fr'" in text
