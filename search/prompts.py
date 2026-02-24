import asyncio
from typing import Literal
from pydantic import BaseModel
import dspy

from .memory import _log


class SmartSearchIntent(BaseModel):
    # --- Kaikille intenteille ---
    intent: Literal["discover", "similar_to", "franchise", "lookup", "person", "trending"]
    media_type: Literal["movie", "tv"] = "movie"

    # --- trending ---
    time_window: str = "week"

    # --- discover ---
    genres: list[str] | None = None
    keywords: list[str] | None = None
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    min_rating: float | None = None
    language: str | None = None
    sort_by: str = "popularity.desc"
    min_votes: int = 100
    airing_now: bool = False
    both_types: bool = False
    actor_name: str | None = None

    # --- discover + similar_to ---
    watch_providers: list[str] | None = None

    # --- similar_to ---
    reference_titles: list[str] | None = None

    # --- lookup ---
    title: str | None = None

    # --- person ---
    person_name: str | None = None

    # --- franchise ---
    franchise_query: str | None = None



import re as _re

# Suomenkielinen tyylisana → TMDB-keywordit englanniksi
_STYLE_KEYWORDS: dict[str, list[str]] = {
    "synkkä":       ["dark fantasy"],
    "tumma":        ["dark fantasy"],
    "kosto":        ["revenge"],
    "psykologinen": ["psychological"],
    "isekai":       ["isekai", "parallel world"],
    "aikamatka":    ["time travel"],
    "cyberpunk":    ["cyberpunk"],
    "dystopia":     ["dystopia"],
    "noir":         ["neo-noir"],
    "twist":        ["twist ending"],
    "tosi tarina":  ["based on true story"],
    "shonen":       ["shounen"],
    "shounen":      ["shounen"],
    "seinen":       ["seinen"],
    "mecha":        ["mecha"],
    "aikuismais":   ["josei", "romance"],   # aikuismainen, aikuismaisia, aikuismaisempi...
    "kypsä":        ["josei", "seinen"],
    "romantti":     ["romance"],            # romanttinen, romanttisia, romanttisempi...
    "romanssi":     ["romance"],
}

# Kielimerkki kyselyssä → ISO 639-1
_LANGUAGE_HINTS: dict[str, str] = {
    "k-drama":      "ko",
    "korealainen":  "ko",
    "bollywood":    "hi",
    "intialainen":  "hi",
    "ranskalainen": "fr",
    "espanjalainen":"es",
    "italialainen": "it",
}

# Laatu/järjestys-sanat kyselyssä → sort_by + min_votes
_SORT_HINTS: list[tuple[str, str, int]] = [
    ("paras",       "vote_average.desc", 500),
    ("klassikko",   "vote_average.desc", 500),
    ("must see",    "vote_average.desc", 500),
    ("suosituin",   "popularity.desc",   100),
    ("uusin",       "release_date.desc", 100),
    ("tuorein",     "release_date.desc", 100),
    # "ei tarvitse olla parhaita" / "vähemmän tunnettu" → laajempi pool, laatu-sort
    ("parhaita",    "vote_average.desc",  50),
    ("tunnettu",    "vote_average.desc",  50),
    ("piilo",       "vote_average.desc",  30),
]


def _postprocess(intent: SmartSearchIntent, query: str = "") -> SmartSearchIntent:
    """Deterministiset korjaussäännöt LLM:n paluuarvoon."""
    data = intent.model_dump()
    q = query.lower() if query else ""

    # airing_now → aina tv
    if data.get("airing_now"):
        data["media_type"] = "tv"

    # Animaatio-genre ilman kieltä → oletuksena japani
    genres = data.get("genres") or []
    if any("animaatio" in g.lower() for g in genres) and not data.get("language"):
        data["language"] = "ja"

    # Anime-tunnistus tekstistä
    if q and not data.get("language"):
        if _re.search(r'\banim[a-zäöå]+\b|\bisekai\b|\bseinen\b|\bshonen\b|\bshounen\b', q, _re.IGNORECASE):
            data["language"] = "ja"
            if not genres:
                data["genres"] = ["Animaatio"]

    # Sarjaviittaus → aina tv
    if q and data.get("media_type") != "tv":
        if _re.search(r'\bsarj[a-zäöå]*\b|\bshow[s]?\b|\bseries\b', q, _re.IGNORECASE):
            data["media_type"] = "tv"

    # Kielitunnistus hakutaulukosta
    if q and not data.get("language"):
        for hint, lang in _LANGUAGE_HINTS.items():
            if hint in q:
                data["language"] = lang
                break

    # Tyylisanat → TMDB-keywordit (lisätään LLM:n tuottamien perään)
    if q:
        extra: list[str] = []
        for fi_word, en_kws in _STYLE_KEYWORDS.items():
            if fi_word in q:
                extra.extend(kw for kw in en_kws if kw not in extra)
        if extra:
            existing = data.get("keywords") or []
            data["keywords"] = list(dict.fromkeys(existing + extra))

    # Järjestys/laatu-sanat (vain jos LLM jätti oletuksen)
    if q and data.get("sort_by") == "popularity.desc":
        for hint, sort_by, min_votes in _SORT_HINTS:
            if hint in q:
                data["sort_by"] = sort_by
                data["min_votes"] = min_votes
                break

    return SmartSearchIntent(**data)


class _RerankedIds(BaseModel):
    ids: list[int]


class _RerankByReference(dspy.Signature):
    """Olet elokuvasuositin. Valitse kandidaateista temaattisesti parhaiten
    sopivat referenssiteosten perusteella. Palauta enintään 12 ID:tä
    parhaimmasta huonoimpaan."""

    references: str = dspy.InputField(desc="Referenssiteokset: nimi, kuvaus ja teemat")
    user_emphasis: str = dspy.InputField(desc="Käyttäjän painottamat teemat, tai tyhjä")
    candidates: str = dspy.InputField(desc="Kandidaatit muodossa [ID] Nimi (vuosi) - kuvaus")
    result: _RerankedIds = dspy.OutputField(desc="ID-lista parhaimmasta huonoimpaan, max 12")


class _RerankByCriteria(dspy.Signature):
    """Olet elokuva- ja sarjasuositin. Järjestä kandidaatit niin että parhaiten
    käyttäjän hakua vastaavat ovat ensin. Palauta enintään 12 ID:tä
    parhaimmasta huonoimpaan. Sisällytä vain relevantit teokset."""

    user_query: str = dspy.InputField(desc="Käyttäjän hakukysely")
    candidates: str = dspy.InputField(desc="Kandidaatit muodossa [ID] Nimi (vuosi) - kuvaus")
    result: _RerankedIds = dspy.OutputField(desc="ID-lista parhaimmasta huonoimpaan, max 12")


_reranker = dspy.ChainOfThought(_RerankByReference)
_criteria_reranker = dspy.ChainOfThought(_RerankByCriteria)


async def rerank_candidates(
    ref_items: list[dict],        # [{name, overview, kw_names}] — yksi per referenssi
    user_keywords: list[str] | None,
    candidates: list[dict],
) -> list[int]:
    """Valitse temaattisesti parhaiten sopivat kandidaatit DSPy:n avulla."""
    if not candidates:
        return []

    ref_lines = "\n".join(
        f"{i+1}. {item['name']} — {item['overview'][:300]} — teemat: {', '.join(item['kw_names']) or '-'}"
        for i, item in enumerate(ref_items)
    )
    user_kw_str = ", ".join(user_keywords) if user_keywords else ""
    cand_lines = "\n".join(
        f"[{c['id']}] {c.get('name') or c.get('title','?')} "
        f"({(c.get('first_air_date') or c.get('release_date',''))[:4]}) "
        f"- {c.get('overview','')[:150]}"
        for c in candidates
    )

    _log("DSPY RERANK INPUT", f"refs={ref_lines[:300]}\nkw={user_kw_str}\ncands={cand_lines[:300]}")

    prediction = await asyncio.to_thread(
        _reranker,
        references=ref_lines,
        user_emphasis=user_kw_str,
        candidates=cand_lines,
    )

    _log("DSPY RERANK TULOS", str(prediction.result.ids))
    return prediction.result.ids


async def rerank_by_criteria(user_query: str, candidates: list[dict]) -> list[int]:
    """Järjestä kandidaatit käyttäjän kriteerien mukaan (ei referenssiteosta)."""
    if not candidates:
        return []

    cand_lines = "\n".join(
        f"[{c['id']}] {c.get('name') or c.get('title', '?')} "
        f"({(c.get('first_air_date') or c.get('release_date', ''))[:4]}) "
        f"- {c.get('overview', '')[:150]}"
        for c in candidates
    )

    _log("DSPY CRITERIA RERANK INPUT", f"query={user_query}\ncands={cand_lines[:300]}")

    prediction = await asyncio.to_thread(
        _criteria_reranker,
        user_query=user_query,
        candidates=cand_lines,
    )

    _log("DSPY CRITERIA RERANK TULOS", str(prediction.result.ids))
    return prediction.result.ids


