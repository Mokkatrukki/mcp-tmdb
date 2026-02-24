# test_intent.py — Pydantic-validointitestit SmartSearchIntentille
#
# Nämä testit varmistavat että Literal-tyypit toimivat:
# - virheelliset arvot hylätään heti
# - oletusarvot ovat oikein
#
# Aja: uv run pytest tests/test_intent.py -v

import pytest
from pydantic import ValidationError
from search.prompts import SmartSearchIntent


# ─────────────────────────────────────────────────────────────
# Literal-validointi: intent
# ─────────────────────────────────────────────────────────────

def test_validi_intent_toimii():
    for intent in ["discover", "similar_to", "franchise", "lookup", "person", "trending"]:
        obj = SmartSearchIntent(intent=intent, media_type="movie")
        assert obj.intent == intent

def test_tuntematon_intent_hylkäytyy():
    """LLM ei pysty palauttamaan hallusinoitua intenttia hiljaa."""
    with pytest.raises(ValidationError) as exc_info:
        SmartSearchIntent(intent="suosittele_elokuvia", media_type="movie")
    # Pydantic kertoo mitkä arvot olisivat oikeita
    assert "discover" in str(exc_info.value)

def test_tyhja_intent_hylkaytyy():
    with pytest.raises(ValidationError):
        SmartSearchIntent(intent="", media_type="movie")


# ─────────────────────────────────────────────────────────────
# Literal-validointi: media_type
# ─────────────────────────────────────────────────────────────

def test_validi_media_type_toimii():
    for mt in ["movie", "tv"]:
        obj = SmartSearchIntent(intent="discover", media_type=mt)
        assert obj.media_type == mt

def test_tuntematon_media_type_hylkaytyy():
    with pytest.raises(ValidationError) as exc_info:
        SmartSearchIntent(intent="discover", media_type="anime")
    assert "movie" in str(exc_info.value)

def test_both_media_type_hylkaytyy():
    """'both' ei ole validi arvo — both_types-kenttä hoitaa sen."""
    with pytest.raises(ValidationError):
        SmartSearchIntent(intent="discover", media_type="both")


# ─────────────────────────────────────────────────────────────
# Oletusarvot
# ─────────────────────────────────────────────────────────────

def test_oletusarvot_ovat_oikein():
    intent = SmartSearchIntent(intent="discover", media_type="movie")
    assert intent.sort_by == "popularity.desc"
    assert intent.min_votes == 100
    assert intent.airing_now == False
    assert intent.both_types == False
    assert intent.genres is None
    assert intent.keywords is None
    assert intent.title is None
    assert intent.person_name is None
    assert intent.reference_titles is None
    assert intent.franchise_query is None


# ─────────────────────────────────────────────────────────────
# JSON round-trip (tärkeä add_training_example-toiminnolle)
# ─────────────────────────────────────────────────────────────

def test_json_roundtrip():
    """SmartSearchIntent pitää selvitä JSON:sta takaisin objektiksi."""
    original = SmartSearchIntent(
        intent="similar_to",
        media_type="tv",
        reference_titles=["Breaking Bad"],
        watch_providers=["Netflix"],
    )
    json_str = original.model_dump_json()
    restored = SmartSearchIntent.model_validate_json(json_str)

    assert restored.intent == original.intent
    assert restored.media_type == original.media_type
    assert restored.reference_titles == original.reference_titles
    assert restored.watch_providers == original.watch_providers
