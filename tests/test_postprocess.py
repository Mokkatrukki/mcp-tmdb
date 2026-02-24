# test_postprocess.py — puhtaat yksikkötestit _postprocess-säännöille
#
# Nämä testit eivät tee API-kutsuja eivätkä käytä LLM:ää.
# Jokainen testi luo SmartSearchIntentin, kutsuu _postprocess(),
# ja tarkistaa että deterministiset säännöt toimivat oikein.
#
# Aja: uv run pytest tests/test_postprocess.py -v

import pytest
from search.prompts import SmartSearchIntent, _postprocess


def make_intent(**kwargs) -> SmartSearchIntent:
    """Apufunktio: luo intentin oletusarvoilla + ylikirjoituksilla."""
    defaults = {"intent": "discover", "media_type": "movie"}
    return SmartSearchIntent(**{**defaults, **kwargs})


# ─────────────────────────────────────────────────────────────
# airing_now-säännöt
# ─────────────────────────────────────────────────────────────

def test_airing_now_pakottaa_tv():
    """airing_now=True → media_type aina tv, vaikka intent sanoo movie."""
    intent = make_intent(media_type="movie", airing_now=True)
    result = _postprocess(intent)
    assert result.media_type == "tv"

def test_airing_now_false_ei_muuta():
    intent = make_intent(media_type="movie", airing_now=False)
    result = _postprocess(intent)
    assert result.media_type == "movie"


# ─────────────────────────────────────────────────────────────
# Anime/animaatio-tunnistus
# ─────────────────────────────────────────────────────────────

def test_animaatio_genre_asettaa_japanin():
    """Jos genre on Animaatio eikä kieltä ole, oletetaan japani."""
    intent = make_intent(genres=["Animaatio"])
    result = _postprocess(intent)
    assert result.language == "ja"

def test_animaatio_genre_ei_ylikirjoita_olemassa_olevaa_kielta():
    """Jos kieli on jo asetettu, animaatio-genre ei muuta sitä."""
    intent = make_intent(genres=["Animaatio"], language="ko")
    result = _postprocess(intent)
    assert result.language == "ko"  # ei muutu

def test_anime_sanasta_tulee_japani_ja_genre():
    intent = make_intent(media_type="tv")
    result = _postprocess(intent, query="hyviä anime-sarjoja")
    assert result.language == "ja"
    assert "Animaatio" in result.genres

def test_isekai_tunnistetaan():
    intent = make_intent(media_type="tv")
    result = _postprocess(intent, query="isekai-sarjoja")
    assert result.language == "ja"

def test_seinen_tunnistetaan():
    intent = make_intent(media_type="tv")
    result = _postprocess(intent, query="seinen-animeita")
    assert result.language == "ja"


# ─────────────────────────────────────────────────────────────
# Sarjaviittaus → tv
# ─────────────────────────────────────────────────────────────

def test_sarjat_kyselyssa_pakottaa_tv():
    intent = make_intent(media_type="movie")
    result = _postprocess(intent, query="hyviä sarjoja 90-luvulta")
    assert result.media_type == "tv"

def test_show_pakottaa_tv():
    intent = make_intent(media_type="movie")
    result = _postprocess(intent, query="good crime shows")
    assert result.media_type == "tv"

def test_series_pakottaa_tv():
    intent = make_intent(media_type="movie")
    result = _postprocess(intent, query="best drama series")
    assert result.media_type == "tv"

def test_ei_sarjaviittausta_ei_muuta():
    intent = make_intent(media_type="movie")
    result = _postprocess(intent, query="hyviä toimintaelokuvia")
    assert result.media_type == "movie"


# ─────────────────────────────────────────────────────────────
# Kielitunnistus
# ─────────────────────────────────────────────────────────────

def test_k_drama_asettaa_korean():
    intent = make_intent()
    result = _postprocess(intent, query="hyviä k-drama sarjoja")
    assert result.language == "ko"

def test_korealainen_asettaa_korean():
    intent = make_intent()
    result = _postprocess(intent, query="korealaisia romanssielokuvia")
    assert result.language == "ko"

def test_bollywood_asettaa_hindin():
    intent = make_intent()
    result = _postprocess(intent, query="bollywood-elokuvia")
    assert result.language == "hi"

def test_kieli_ei_ylikirjoitu_jos_jo_asetettu():
    """Jos LLM on jo asettanut kielen, _LANGUAGE_HINTS ei ylikirjoita."""
    intent = make_intent(language="fr")
    result = _postprocess(intent, query="k-drama sarjoja")
    assert result.language == "fr"  # ei muutu


# ─────────────────────────────────────────────────────────────
# Tyylisanat → TMDB-keywordit
# ─────────────────────────────────────────────────────────────

def test_synkka_lisaa_dark_fantasy_keywordin():
    intent = make_intent()
    result = _postprocess(intent, query="synkkiä fantasiaelokuvia")
    assert "dark fantasy" in result.keywords

def test_romantti_lisaa_romance_keywordin():
    intent = make_intent()
    result = _postprocess(intent, query="romanttisia komedioita")
    assert "romance" in result.keywords

def test_aikuismais_lisaa_josei_ja_romance():
    intent = make_intent()
    result = _postprocess(intent, query="aikuismaisia anime-sarjoja")
    assert "josei" in result.keywords
    assert "romance" in result.keywords

def test_tyylisanat_yhdistetaan_llm_keywordeihin():
    """LLM:n tuottamat keywordit säilyvät, tyylisanat lisätään perään."""
    intent = make_intent(keywords=["psychological"])
    result = _postprocess(intent, query="synkkiä trillereitä")
    assert "psychological" in result.keywords
    assert "dark fantasy" in result.keywords

def test_ei_tyylisanaa_ei_muuta_keywordeja():
    intent = make_intent(keywords=["action"])
    result = _postprocess(intent, query="hyviä toimintaelokuvia")
    assert result.keywords == ["action"]


# ─────────────────────────────────────────────────────────────
# Järjestys/laatu-sanat
# ─────────────────────────────────────────────────────────────

def test_paras_asettaa_vote_average_sortin():
    intent = make_intent()  # sort_by="popularity.desc" oletuksena
    result = _postprocess(intent, query="parasta draamaa")
    assert result.sort_by == "vote_average.desc"
    assert result.min_votes == 500

def test_klassikko_asettaa_vote_average_sortin():
    intent = make_intent()
    result = _postprocess(intent, query="klassikoita 80-luvulta")
    assert result.sort_by == "vote_average.desc"

def test_uusin_asettaa_release_date_sortin():
    intent = make_intent()
    result = _postprocess(intent, query="uusimpia toimintaelokuvia")
    assert result.sort_by == "release_date.desc"

def test_sort_ei_ylikirjoitu_jos_llm_asetti():
    """Jos LLM on jo valinnut muun sortin, sort hints ei ylikirjoita."""
    intent = make_intent(sort_by="vote_average.desc")
    result = _postprocess(intent, query="parasta toimintaa")
    # sort_by oli jo eri kuin popularity.desc, joten ei muutu uusin-vihjeen kautta
    # mutta "paras" on sort hint joka osuu → tässä se pysyy vote_average.desc
    assert result.sort_by == "vote_average.desc"
