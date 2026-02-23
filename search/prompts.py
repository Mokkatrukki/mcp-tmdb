import datetime
import os
import sys
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


def _build_prompt(query: str, memory: dict) -> str:
    today = datetime.date.today().isoformat()
    movie_genres = ", ".join(g["name"] for g in memory.get("movie_genres", []))
    tv_genres = ", ".join(g["name"] for g in memory.get("tv_genres", []))
    providers = ", ".join(p["provider_name"] for p in memory.get("movie_providers", []))

    return f"""Olet elokuva- ja sarjahakujärjestelmä. Analysoi hakukysely ja palauta JSON.
Tänään on {today}.

## Käytettävissä olevat genret:
Elokuvagenret: {movie_genres}
Sarjagenret: {tv_genres}

## Suoratoistopalvelut (Suomi):
{providers}

watch_providers on lista palveluja. Yksi palvelu → ["Netflix"]. Useita ("tai"/"tai jommalla kummalla") → ["Yle Areena", "Amazon Prime Video"]. Käytä aina tarkkaa nimeä yllä olevasta listasta.

## Intent — valitse MITÄ käyttäjä haluaa, ei sanamuodosta:

franchise:   Käyttäjä haluaa teoksia tietystä franchisesta/sarjasta nimellä +
             valintakriteerin (paras, tummin, suosituin jne.).
             Merkkejä: franchise-nimi + adjektiivi/kriteeri ilman yhtä tiettyä teosta.
             Esimerkkejä: "parhaat Gundam-sarjat", "tummimmat Star Wars -elokuvat",
             "suosituimmat Marvel-sarjat". → aseta franchise_query=<franchise-nimi>

discover:    Lista teoksia annetuin kriteerein. Käyttäjä ei etsi yhtä tiettyä
             teosta vaan vaihtoehtoja. Merkkejä: tyylin/tunnelman kuvailu,
             genreviittaus, aikaväli, kieliviittaus ilman nimeä.
             Jos kyselyssä on näyttelijän tai ohjaajan nimi + muita kriteerejä
             (genre, vuosi, tyyli jne.) → discover + actor_name=<nimi>.
             Esimerkkejä: "Tom Hanksin sotaelokuvat", "Nolan-elokuvat",
             "Cate Blanchettin draamat 2010-luvulta".

lookup:      Tiedot yhdestä nimetystä teoksesta. Merkkejä: "kerro", "mikä on",
             teoksen nimi ilman vertailuasetelmaa.

similar_to:  Teos mainitaan VERTAILUKOHTANA, ei kohteena.
             Merkkejä: "kuten", "samanlainen kuin", "X tyylinen", "X oli hyvä
             anna lisää", "enemmän kuin X", teos + pyyntö lisää samaa.
             → aseta reference_titles listana
             Yksi teos → ["The Lobster"]
             Useita → ["The Lobster", "Parasite"]
             TÄRKEÄÄ: Jos kyselyssä mainitaan suoratoistopalvelu, aseta watch_providers.
             Esimerkki: "sarjoja kuten Downton Abbey Yle Areenasta"
               → intent=similar_to, reference_titles=["Downton Abbey"], watch_providers=["Yle Areena"]

person:      Tietoa henkilöstä — EI teoslistaa filtterein. Merkkejä: "kuka on",
             henkilönimi YKSIN ilman muita kriteereitä, "kerro X:stä".
             Jos henkilönimen lisäksi on genre/vuosi/muu kriteeri → discover.

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


async def classify_query(query: str, memory: dict) -> SmartSearchIntent:
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = _build_prompt(query, memory)
    _log("GEMINI #1 PROMPT (classify_query)", prompt)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SmartSearchIntent,
        ),
    )
    _log("GEMINI #1 VASTAUS (raaka JSON)", response.text)
    intent = SmartSearchIntent.model_validate_json(response.text)
    postprocessed = _postprocess(intent, query)
    _log("INTENT (postprocess jälkeen)", postprocessed.model_dump_json(indent=2))
    return postprocessed
