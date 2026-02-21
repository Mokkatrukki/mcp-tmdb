import datetime
import os
from pydantic import BaseModel
from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv

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
    watch_provider: str | None = None
    person_name: str | None = None
    title: str | None = None
    name: str | None = None
    reference_title: str | None = None
    sort_by: str = "popularity.desc"
    min_votes: int = 100
    airing_now: bool = False
    both_types: bool = False


def _build_prompt(query: str, memory: dict) -> str:
    today = datetime.date.today().isoformat()
    movie_genres = ", ".join(g["name"] for g in memory.get("movie_genres", []))
    tv_genres = ", ".join(g["name"] for g in memory.get("tv_genres", []))
    providers = ", ".join(p["provider_name"] for p in memory.get("movie_providers", [])[:20])

    return f"""Olet elokuva- ja sarjahakujärjestelmä. Analysoi hakukysely ja palauta JSON.
Tänään on {today}.

## Käytettävissä olevat genret:
Elokuvagenret: {movie_genres}
Sarjagenret: {tv_genres}

## Suoratoistopalvelut (Suomi):
{providers}

## Intent — valitse MITÄ käyttäjä haluaa, ei sanamuodosta:

discover:    Lista teoksia annetuin kriteerein. Käyttäjä ei etsi yhtä tiettyä
             teosta vaan vaihtoehtoja. Merkkejä: tyylin/tunnelman kuvailu,
             genreviittaus, aikaväli, kieliviittaus ilman nimeä.

lookup:      Tiedot yhdestä nimetystä teoksesta. Merkkejä: "kerro", "mikä on",
             teoksen nimi ilman vertailuasetelmaa.

similar_to:  Teos mainitaan VERTAILUKOHTANA, ei kohteena.
             Merkkejä: "kuten", "samanlainen kuin", "X tyylinen", "X oli hyvä
             anna lisää", "enemmän kuin X", teos + pyyntö lisää samaa.
             → aseta reference_title

person:      Tietoa henkilöstä. Merkkejä: "kuka on", henkilönimi yksin.

trending:    Suosio juuri nyt. Merkkejä: "trendaa", "mitä katsotaan nyt".

## media_type — käytä AINOASTAAN näitä arvoja:
- "movie" = elokuva, filmi, leffaa, elokuvia
- "tv" = sarja, sarjoja, sarjaa, sarjat, k-drama, anime-sarja, animesarjoja,
         show, shows, series. Käytä aina kun maininta sarjamuodosta.
Älä koskaan käytä "tv_show", "series" tai muuta arvoa.

## Kieli — päättele kontekstista, eksplisiittinen maininta EI tarvita:

- sana "anime" missä tahansa taivutusmuodossa (anime, animea, animeita, animen,
  animeja, animesarja, animesarjoja, animelokuva jne.) tai anime-tyylilaji
  → language="ja" + genres=["Animaatio"] + media_type="tv"
  Anime-tyylilajit: isekai, seinen, shonen/shounen, shojo, mecha, slice of life, ecchi
- isekai AINA → language="ja" + genres=["Animaatio"] + keywords=["isekai", "parallel world"] + media_type="tv"
- "k-drama", "korealainen" → language="ko"
- "bollywood", "intialainen elokuva" → language="hi"
- "ranskalainen", "ranskalaisella" → language="fr"
- Tuntematon japanilainen teos referenssinä → language="ja"

## Aikavälit:

- "X-luvulla" tai "X:stä lähtien" → year_from=X (year_to jää tyhjäksi = tähän päivään)
- "X-luvulta Y-luvulle" tai "X–Y" → year_from=X, year_to=Y
- "2000-luvulla" = year_from=2000
- "2010-luvulta tähän päivään" = year_from=2010
- Yksittäinen vuosi → year=XXXX (ei year_from/year_to)

## Erityistilanteet:

- "tässä seasonissa", "tällä hetkellä menossa", "juuri nyt airing", "menossa olevia",
  "nyt pyörivät", "käynnissä olevat", "ei loppu"
  → airing_now=true + media_type="tv". Palvelin laskee ajankohtaisen season-alueen automaattisesti.
  (Sarjat airoavat, elokuvat eivät — airing_now AINA → media_type="tv")

- "elokuvat ja sarjat", "sekä elokuvat että sarjat", "kaikki formaatit"
  → both_types=true. Palvelin tekee kaksi hakua.

## Tyylit ja tunnelma → keywords (TMDB-englanniksi):

Tunnelma/tyylisana → keywords-listaan:
- "synkkä", "tumma", "dark" → "dark fantasy"
- "kosto", "kostotarina" → "revenge"
- "psykologinen" → "psychological"
- "väkivaltainen", "gore", "brutaali" → "gore"
- "kypsä", "aikuisille", "mature" → "seinen" tai "adult animation"
- "isekai" → "isekai", "parallel world" (+ language="ja", genres=["Animaatio"])
- "seinen" → "seinen"
- "shonen", "shounen" → käytä aina TMDB:n canonical-muoto "shounen" (ei "shonen")
- "twist", "yllätys" → "twist ending"
- "tosi tarina", "tositapahtumiin" → "based on true story"
- "noir" → "neo-noir"
- "aikamatka" → "time travel"
- "cyberpunk", "kybermatka" → "cyberpunk"
- "dystopia" → "dystopia"
- "vibet", "wibe", "vibe", "tunnelma" → ÄLÄ aseta erikseen, käytä muita merkkejä

## Laatu ja järjestys:

- "paras", "parhaat", "top", "klassikko", "pakko katsoa", "must see"
  → sort_by="vote_average.desc", min_votes=500
- "suosituin", "trending" (ilman "nyt") → sort_by="popularity.desc"
- "uusin", "juuri julkaistu" → sort_by="release_date.desc"

## Hakukysely:
{query}"""


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

    return SmartSearchIntent(**data)


class _RerankedIds(BaseModel):
    ids: list[int]


async def rerank_candidates(
    ref_name: str,
    ref_overview: str,
    ref_kw_names: list[str],
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

    prompt = f"""Olet elokuvasuositin. Referenssiteos:
Nimi: {ref_name}
Kuvaus: {ref_overview[:400]}
Teemat: {', '.join(ref_kw_names) or '-'}{user_kw_str}

Valitse alla olevista kandidaateista enintään 12 temaattisesti parhaiten sopivaa.
Suosi teoksia jotka jakavat saman tunnelman, teemat tai tarinaelementit referenssin kanssa.
Palauta lista ID-numeroista parhaimmasta huonoimpaan.

Kandidaatit:
{cand_lines}"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RerankedIds,
        ),
    )
    result = _RerankedIds.model_validate_json(response.text)
    return result.ids


async def classify_query(query: str, memory: dict) -> SmartSearchIntent:
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = _build_prompt(query, memory)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SmartSearchIntent,
        ),
    )
    intent = SmartSearchIntent.model_validate_json(response.text)
    return _postprocess(intent, query)
