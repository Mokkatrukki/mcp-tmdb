# test_integration.py — oikeat API-kutsut LLM:lle ja TMDB:lle
#
# NÄITÄ TESTEJÄ EI AJETA OLETUKSENA.
# Ne tekevät oikeita verkkoyhteyksiä ja maksavat API-kutsuja.
#
# Aja kaikki integration-testit:
#   uv run pytest -m integration -v
#
# Aja yksittäinen:
#   uv run pytest tests/test_integration.py::test_classify_discover -v
#
# @pytest.mark.integration merkitsee testin — pytest jättää sen välistä
# ellei erikseen pyydä -m integration -lipulla.

import pytest
from search.memory import memory, load_memory
from search.classifier import classify_query
from search.prompts import SmartSearchIntent


# ─────────────────────────────────────────────────────────────
# Fixture: lataa muisti kerran koko moduulille
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
async def loaded_memory():
    """
    Fixture ajaa load_memory() kerran ennen kaikkia testejä tässä tiedostossa.
    scope="module" tarkoittaa: kerran per tiedosto (ei per testi).
    autouse=True tarkoittaa: käytetään automaattisesti ilman että jokainen
    testi pyytää sitä erikseen.
    """
    await load_memory()


# ─────────────────────────────────────────────────────────────
# Luokittelutestit — oikeat LLM-kutsut
# ─────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_classify_discover():
    """Perusdiscover-kysely tunnistetaan oikein."""
    intent = await classify_query("hyviä toimintaelokuvia 90-luvulta", memory)
    assert intent.intent == "discover"
    assert intent.media_type == "movie"

@pytest.mark.integration
async def test_classify_similar_to():
    """Vertailukysely tunnistetaan similar_to:ksi."""
    intent = await classify_query("samanlaisia sarjoja kuin Breaking Bad", memory)
    assert intent.intent == "similar_to"
    assert intent.media_type == "tv"
    assert intent.reference_titles is not None
    assert any("Breaking Bad" in t for t in intent.reference_titles)

@pytest.mark.integration
async def test_classify_trending():
    intent = await classify_query("mitä elokuvia trendaa tällä viikolla", memory)
    assert intent.intent == "trending"

@pytest.mark.integration
async def test_classify_person():
    intent = await classify_query("kuka on Tom Hanks", memory)
    assert intent.intent == "person"

@pytest.mark.integration
async def test_classify_lookup():
    intent = await classify_query("kerro elokuvasta Inception", memory)
    assert intent.intent == "lookup"
    assert intent.title is not None

@pytest.mark.integration
async def test_classify_franchise():
    intent = await classify_query("parhaat Gundam-sarjat", memory)
    assert intent.intent == "franchise"
    assert intent.media_type == "tv"

@pytest.mark.integration
async def test_classify_watch_provider():
    """Watch provider poimitaan kyselystä."""
    intent = await classify_query("Netflix-sarjoja 2020-luvulta", memory)
    assert intent.intent == "discover"
    assert intent.watch_providers is not None
    assert any("Netflix" in p for p in intent.watch_providers)

@pytest.mark.integration
async def test_classify_anime_asettaa_japanin():
    """
    Yhdistää LLM:n luokittelun + _postprocess-säännön:
    animekysely → language="ja" joko LLM:ltä tai postprocessista.
    """
    intent = await classify_query("hyviä shounen-animeita", memory)
    assert intent.language == "ja"

@pytest.mark.integration
async def test_classify_actor_discover():
    """Näyttelijä + genre → discover + actor_name."""
    intent = await classify_query("Tom Hanksin draamaelokuvat", memory)
    assert intent.intent == "discover"
    assert intent.actor_name is not None
    assert "Hanks" in intent.actor_name
