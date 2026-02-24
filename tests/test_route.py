# test_route.py — route()-funktion testit mockaamalla classify_query
#
# Mocking tarkoittaa: korvataan oikea funktio väliaikaisesti
# "tekaistulla" versiolla joka palauttaa sen mitä haluamme testata.
#
# Miksi mockata? classify_query tekee oikean LLM-kutsun (hidas, maksaa).
# Haluamme vain testata REITITTÄMISTÄ — onko oikea haara valittu.
#
# unittest.mock.patch toimii näin:
#   with patch("moduuli.funktio") as mock_fn:
#       mock_fn.return_value = haluamamme_arvo
#       # tästä eteenpäin kutsut moduuli.funktio() palauttavat haluamamme_arvo
#
# Aja: uv run pytest tests/test_route.py -v

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from search.prompts import SmartSearchIntent
from search.smart import route


def make_intent(**kwargs) -> SmartSearchIntent:
    defaults = {"intent": "discover", "media_type": "movie"}
    return SmartSearchIntent(**{**defaults, **kwargs})


# ─────────────────────────────────────────────────────────────
# Miten patch toimii — yksinkertaisin esimerkki
# ─────────────────────────────────────────────────────────────

async def test_trending_reititys():
    """
    Testataan: kun intent on 'trending', route() kutsuu trending()-funktiota.

    patch("search.smart.trending") korvaa trending-funktion smart.py:ssä
    AsyncMock-oliolla. AsyncMock tallentaa kaikki kutsut ja niiden argumentit.
    """
    trending_intent = make_intent(intent="trending", media_type="tv", time_window="day")

    # patch kohdistuu SIIHEN MODUULIIN jossa funktio on importoitu
    # (smart.py tekee: from .tools import trending)
    with patch("search.smart.classify_query", new=AsyncMock(return_value=trending_intent)):
        with patch("search.smart.trending", new=AsyncMock(return_value="trendaavat sarjat")) as mock_trending:
            result = await route("mitä trendaa nyt")

    # Varmistetaan että trending() kutsuttiin oikeilla argumenteilla
    mock_trending.assert_called_once_with(type="tv", time_window="day")
    assert result == "trendaavat sarjat"


async def test_person_reititys():
    """Kun intent on 'person', route() kutsuu search_person() henkilön nimellä."""
    person_intent = make_intent(intent="person", person_name="Tom Hanks")

    with patch("search.smart.classify_query", new=AsyncMock(return_value=person_intent)):
        with patch("search.smart.search_person", new=AsyncMock(return_value="Tom Hanks info")) as mock_person:
            result = await route("kuka on Tom Hanks")

    mock_person.assert_called_once_with("Tom Hanks")
    assert result == "Tom Hanks info"


async def test_person_fallback_kyselyyn():
    """Jos person_name on None, käytetään alkuperäistä kyselyä."""
    person_intent = make_intent(intent="person", person_name=None)

    with patch("search.smart.classify_query", new=AsyncMock(return_value=person_intent)):
        with patch("search.smart.search_person", new=AsyncMock(return_value="...")) as mock_person:
            await route("Meryl Streep")

    # person_name=None → fallback kyselyyn "Meryl Streep"
    mock_person.assert_called_once_with("Meryl Streep")


async def test_lookup_reititys():
    """Kun intent on 'lookup', route() kutsuu search_by_title()."""
    lookup_intent = make_intent(intent="lookup", media_type="movie", title="Inception")

    with patch("search.smart.classify_query", new=AsyncMock(return_value=lookup_intent)):
        with patch("search.smart.search_by_title", new=AsyncMock(return_value="Inception tiedot")) as mock_search:
            result = await route("kerro Inceptionista")

    mock_search.assert_called_once_with("Inception", "movie")
    assert result == "Inception tiedot"


async def test_similar_to_reititys():
    """Kun intent on 'similar_to', route() kutsuu _similar_to()."""
    similar_intent = make_intent(
        intent="similar_to",
        media_type="movie",
        reference_titles=["Inception"],
    )

    with patch("search.smart.classify_query", new=AsyncMock(return_value=similar_intent)):
        with patch("search.smart._similar_to", new=AsyncMock(return_value="samankaltaisia")) as mock_similar:
            result = await route("samanlaisia kuin Inception")

    # Varmistetaan että _similar_to sai koko intent-objektin
    mock_similar.assert_called_once()
    called_intent = mock_similar.call_args[0][0]
    assert called_intent.reference_titles == ["Inception"]


async def test_luokitteluvirhe_palauttaa_virheviestin():
    """
    Jos classify_query heittää poikkeuksen, route() palauttaa
    virheviestin eikä kaadu.
    """
    with patch("search.smart.classify_query", new=AsyncMock(side_effect=Exception("API-virhe"))):
        result = await route("jotain")

    assert "Virhe" in result
    assert "API-virhe" in result


# ─────────────────────────────────────────────────────────────
# Lisäesimerkki: tarkista MITÄ argumentteja mock sai
# ─────────────────────────────────────────────────────────────

async def test_discover_both_types_kutsuu_kahdesti():
    """
    both_types=True → discover() kutsutaan kaksi kertaa rinnakkain
    (kerran movie, kerran tv).

    Tässä näkyy miten mock_calls-lista toimii.
    """
    both_intent = make_intent(
        intent="discover",
        both_types=True,
        genres=["Toiminta"],
    )

    with patch("search.smart.classify_query", new=AsyncMock(return_value=both_intent)):
        with patch("search.smart.discover", new=AsyncMock(return_value="tulokset")) as mock_discover:
            await route("toimintaelokuvia ja -sarjoja")

    # discover() pitäisi olla kutsuttu kahdesti: movie + tv
    assert mock_discover.call_count == 2

    # Kerätään molemmat kutsut ja tarkistetaan type-argumentit
    call_types = [call.kwargs["type"] for call in mock_discover.call_args_list]
    assert "movie" in call_types
    assert "tv" in call_types
