"""
Promptin yleistymistestit — kutsuu oikeaa Gemini-APIa.

Nämä kyselyt EIVÄT saa olla samoja kuin promptin esimerkit.
Epäonnistunut testi → promptia pitää parantaa, ei koodia.

Ajo: uv run pytest tests/ -v
"""
import asyncio
import time
import pytest
from search.prompts import classify_query, SmartSearchIntent

# Käytetään tyhjää memory-dictia testeissä (genret eivät vaikuta luokitteluun)
_MOCK_MEMORY = {
    "movie_genres": [
        {"id": 28, "name": "Toiminta"},
        {"id": 12, "name": "Seikkailu"},
        {"id": 16, "name": "Animaatio"},
        {"id": 35, "name": "Komedia"},
        {"id": 18, "name": "Draama"},
        {"id": 10751, "name": "Perhe"},
        {"id": 14, "name": "Fantasia"},
        {"id": 36, "name": "Historia"},
        {"id": 27, "name": "Kauhu"},
        {"id": 10402, "name": "Musiikki"},
        {"id": 9648, "name": "Mysteeri"},
        {"id": 10749, "name": "Romanssi"},
        {"id": 878, "name": "Tieteisseikkailu"},
        {"id": 53, "name": "Trilleri"},
        {"id": 10752, "name": "Sota"},
        {"id": 37, "name": "Lännenelokuva"},
    ],
    "tv_genres": [
        {"id": 10759, "name": "Toiminta ja seikkailu"},
        {"id": 16, "name": "Animaatio"},
        {"id": 35, "name": "Komedia"},
        {"id": 80, "name": "Rikos"},
        {"id": 99, "name": "Dokumentti"},
        {"id": 18, "name": "Draama"},
        {"id": 10751, "name": "Perhe"},
        {"id": 10762, "name": "Lapset"},
        {"id": 9648, "name": "Mysteeri"},
        {"id": 10763, "name": "Uutiset"},
        {"id": 10764, "name": "Reality"},
        {"id": 10765, "name": "Sci-Fi ja fantasia"},
        {"id": 10766, "name": "Saippuaooppera"},
        {"id": 10767, "name": "Puheohjelma"},
        {"id": 10768, "name": "Sota ja politiikka"},
        {"id": 37, "name": "Lännenelokuva"},
    ],
    "movie_providers": [
        {"provider_id": 8, "provider_name": "Netflix"},
        {"provider_id": 337, "provider_name": "Disney Plus"},
        {"provider_id": 323, "provider_name": "HBO Max"},
        {"provider_id": 119, "provider_name": "Amazon Prime Video"},
    ],
    "tv_providers": [
        {"provider_id": 8, "provider_name": "Netflix"},
        {"provider_id": 337, "provider_name": "Disney Plus"},
    ],
    "keyword_cache": {},
}


def run(coro):
    # Throttle API calls to stay within free tier (10 RPM)
    time.sleep(7)
    return asyncio.run(coro)


def assert_checks(intent: SmartSearchIntent, checks: dict, query: str):
    for key, expected in checks.items():
        if key == "genres_has":
            genres = intent.genres or []
            assert any(expected.lower() in g.lower() for g in genres), (
                f"[{query!r}] genres should contain '{expected}', got {genres}"
            )
        elif key == "keywords_has":
            keywords = intent.keywords or []
            assert any(expected.lower() in kw.lower() for kw in keywords), (
                f"[{query!r}] keywords should contain '{expected}', got {keywords}"
            )
        elif key == "reference_title_nonempty":
            assert intent.reference_title, (
                f"[{query!r}] reference_title should not be empty"
            )
        else:
            actual = getattr(intent, key, None)
            assert actual == expected, (
                f"[{query!r}] {key}: expected {expected!r}, got {actual!r}"
            )


# ── Anime-tunnistus ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,checks", [
    (
        "Japanilainen kauhusarja",
        {"language": "ja", "media_type": "tv"},
    ),
    (
        "Suosittele hyvää shonen-animea",
        {"language": "ja", "keywords_has": "shounen"},
    ),
    (
        "Parhaat isekai-sarjat",
        {"language": "ja", "keywords_has": "isekai"},
    ),
    (
        "Kypsää tummanpuhuvaa animea aikuisille",
        {"language": "ja"},
    ),
    (
        "Romanttinen slice of life -anime",
        {"language": "ja", "genres_has": "Animaatio", "keywords_has": "slice of life"},
    ),
])
def test_anime_detection(query, checks):
    intent = run(classify_query(query, _MOCK_MEMORY))
    assert_checks(intent, checks, query)


# ── Similar_to ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,checks", [
    (
        "Etsi samanlainen kuin Kaifuku Jutsushi no Yarinaoshi",
        {"intent": "similar_to", "reference_title_nonempty": True},
    ),
    (
        "Attack on Titan oli mahtava, anna lisää",
        {"intent": "similar_to"},
    ),
    (
        "Made in Abyss tyylinen sarja",
        {"intent": "similar_to"},
    ),
    (
        "Katoin Dark-sarjan, mitä muuta samankaltaista?",
        {"intent": "similar_to"},
    ),
])
def test_similar_to(query, checks):
    intent = run(classify_query(query, _MOCK_MEMORY))
    assert_checks(intent, checks, query)


# ── Aikavälit ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,checks", [
    (
        "Parhaat scifi-elokuvat 2000-luvulla",
        {"year_from": 2000, "sort_by": "vote_average.desc"},
    ),
    (
        "Sotaelokuva 2010-luvulta tähän päivään",
        {"year_from": 2010},
    ),
    (
        "90-luvun kauhuelokuvat",
        {"year_from": 1990, "year_to": 1999},
    ),
])
def test_year_range(query, checks):
    intent = run(classify_query(query, _MOCK_MEMORY))
    assert_checks(intent, checks, query)


# ── Airing now ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,checks", [
    (
        "Mitkä on tässä seasonissa hyviä romanttisia animeita",
        {"airing_now": True, "language": "ja", "media_type": "tv"},
    ),
    (
        "Tällä hetkellä menossa olevia sarjoja",
        {"airing_now": True, "media_type": "tv"},
    ),
])
def test_airing_now(query, checks):
    intent = run(classify_query(query, _MOCK_MEMORY))
    assert_checks(intent, checks, query)


# ── Both types ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,checks", [
    (
        "Cyberpunk-elokuvat ja -sarjat",
        {"both_types": True, "keywords_has": "cyberpunk"},
    ),
    (
        "Scifi sekä elokuvina että sarjoina",
        {"both_types": True},
    ),
])
def test_both_types(query, checks):
    intent = run(classify_query(query, _MOCK_MEMORY))
    assert_checks(intent, checks, query)


# ── Kieli muista kulttuureista ───────────────────────────────────────────────

@pytest.mark.parametrize("query,checks", [
    ("Korealaista romantiikkaa",    {"language": "ko"}),
    ("Ranskalaisella tehty draama", {"language": "fr"}),
    ("Bollywood-musikaali",         {"language": "hi"}),
])
def test_language_inference(query, checks):
    intent = run(classify_query(query, _MOCK_MEMORY))
    assert_checks(intent, checks, query)


# ── Suomalainen slangi ───────────────────────────────────────────────────────

@pytest.mark.parametrize("query,checks", [
    (
        "Cyberpunk wibaiset elokuvat",
        {"keywords_has": "cyberpunk"},
    ),
    (
        "Tummat noir wibaiset trillerit",
        {"keywords_has": "neo-noir"},
    ),
])
def test_slang_keywords(query, checks):
    intent = run(classify_query(query, _MOCK_MEMORY))
    assert_checks(intent, checks, query)
