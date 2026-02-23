import os
from pydantic import BaseModel
from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv


_LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "debug.log")


def _log(section: str, text: str) -> None:
    border = "─" * 60
    entry = f"\n{border}\n[LOG] {section}\n{border}\n{text}\n"
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"


class SmartSearchIntent(BaseModel):
    intent: str           # discover|lookup|person|similar_to|trending
    confidence: str       # high|low
    media_type: str = "movie"   # MUST be exactly "movie" or "tv" — nothing else
    time_window: str = "week"
    genres: list[str] | None = None
    keywords: list[str] | None = None
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    min_rating: float | None = None
    language: str | None = None
    watch_providers: list[str] | None = None
    person_name: str | None = None
    title: str | None = None
    name: str | None = None
    reference_titles: list[str] | None = None
    sort_by: str = "popularity.desc"
    min_votes: int = 100
    airing_now: bool = False
    both_types: bool = False
    actor_name: str | None = None
    franchise_query: str | None = None



import re as _re


def _postprocess(intent: SmartSearchIntent, query: str = "") -> SmartSearchIntent:
    """Deterministiset korjaussäännöt Geminin paluuarvoon."""
    data = intent.model_dump()

    # airing_now → aina tv (sarjat airoavat, elokuvat eivät)
    if data.get("airing_now"):
        data["media_type"] = "tv"

    # Animaatio-genre ilman kieltä → oletuksena japani
    genres = data.get("genres") or []
    if any("animaatio" in g.lower() for g in genres) and not data.get("language"):
        data["language"] = "ja"

    # Suora tekstipohjainen anime-tunnistus kyselystä
    if query and not data.get("language"):
        if _re.search(r'\banim[a-zäöå]+\b|\bisekai\b|\bseinen\b|\bshonen\b|\bshounen\b', query, _re.IGNORECASE):
            data["language"] = "ja"
            if not genres:
                data["genres"] = ["Animaatio"]

    # Sarjaviittaus kyselyssä → aina tv, riippumatta intentistä
    if query and data.get("media_type") != "tv":
        if _re.search(r'\bsarj[a-zäöå]*\b|\bshow[s]?\b|\bseries\b', query, _re.IGNORECASE):
            data["media_type"] = "tv"

    return SmartSearchIntent(**data)


class _RerankedIds(BaseModel):
    ids: list[int]


async def rerank_candidates(
    ref_items: list[dict],        # [{name, overview, kw_names}] — yksi per referenssi
    user_keywords: list[str] | None,
    candidates: list[dict],
) -> list[int]:
    """Käytä Geminiä valitsemaan temaattisesti parhaiten sopivat kandidaatit."""
    if not candidates:
        return []

    cand_lines = "\n".join(
        f"[{c['id']}] {c.get('name') or c.get('title', '?')} "
        f"({(c.get('first_air_date') or c.get('release_date', ''))[:4]}) "
        f"- {c.get('overview', '')[:150]}"
        for c in candidates
    )
    user_kw_str = f"\nKäyttäjä painottaa erityisesti: {', '.join(user_keywords)}" if user_keywords else ""

    ref_lines = "\n".join(
        f"{i + 1}. {item['name']} — {item['overview'][:300]} — teemat: {', '.join(item['kw_names']) or '-'}"
        for i, item in enumerate(ref_items)
    )

    prompt = f"""Olet elokuvasuositin.
Referenssiteokset:
{ref_lines}{user_kw_str}

Valitse alla olevista kandidaateista enintään 12 temaattisesti parhaiten sopivaa.
Suosi teoksia jotka jakavat saman tunnelman, teemat tai tarinaelementit kaikkien referenssiteosten kanssa.
Palauta lista ID-numeroista parhaimmasta huonoimpaan.

Kandidaatit:
{cand_lines}"""

    _log("GEMINI #2 PROMPT (rerank_candidates)", prompt)
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RerankedIds,
        ),
    )
    _log("GEMINI #2 VASTAUS (rerank_candidates)", response.text)
    result = _RerankedIds.model_validate_json(response.text)
    return result.ids


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

    prompt = f"""Käyttäjä etsii: "{user_query}"

Järjestä alla olevat teokset niin että parhaiten käyttäjän hakua vastaavat ovat ensin.
Palauta lista ID-numeroista parhaimmasta huonoimpaan. Sisällytä vain relevantit teokset.

Kandidaatit:
{cand_lines}"""

    _log("GEMINI #2 PROMPT (rerank_by_criteria)", prompt)
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RerankedIds,
        ),
    )
    _log("GEMINI #2 VASTAUS (rerank_by_criteria)", response.text)
    result = _RerankedIds.model_validate_json(response.text)
    return result.ids


