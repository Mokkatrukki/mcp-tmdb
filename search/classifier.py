import asyncio
import datetime
import json
import os
from pathlib import Path

import dspy
from dotenv import load_dotenv

from .prompts import SmartSearchIntent, _postprocess, _log

load_dotenv()

_EXAMPLES_FILE = Path(__file__).parent.parent / "data" / "examples.json"
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

_lm = dspy.LM(
    "gemini/gemini-2.5-flash-lite-preview-09-2025",
    api_key=_GEMINI_API_KEY,
)
dspy.configure(lm=_lm)


class QueryClassification(dspy.Signature):
    """Olet elokuva- ja sarjahakujärjestelmä. Analysoi hakukysely ja palauta JSON.

## Intent — valitse MITÄ käyttäjä haluaa:

franchise:   Käyttäjä haluaa teoksia tietystä franchisesta nimellä + valintakriteerin
             (paras, tummin, suosituin jne.). Merkkejä: franchise-nimi + adjektiivi.
             Esimerkkejä: "parhaat Gundam-sarjat", "tummimmat Star Wars -elokuvat"
             → aseta franchise_query=<franchise-nimi>

discover:    Lista teoksia annetuin kriteerein. Ei etsi yhtä tiettyä teosta.
             Jos kyselyssä on näyttelijän/ohjaajan nimi + muita kriteerejä → discover + actor_name=<nimi>.
             Esimerkkejä: "Tom Hanksin sotaelokuvat", "Nolan-elokuvat", "Cate Blanchettin draamat"

lookup:      Tiedot yhdestä nimetystä teoksesta. Merkkejä: "kerro", "mikä on", teoksen nimi yksin.

similar_to:  Teos mainitaan VERTAILUKOHTANA, ei kohteena.
             Merkkejä: "kuten", "samanlainen kuin", "X tyylinen", "X oli hyvä anna lisää".
             → aseta reference_titles listana
             Yksi teos → ["The Lobster"]
             Useita → ["The Lobster", "Parasite"]
             TÄRKEÄÄ: Jos kyselyssä mainitaan suoratoistopalvelu, aseta watch_providers.
             Esimerkki: "sarjoja kuten Downton Abbey Yle Areenasta"
               → intent=similar_to, reference_titles=["Downton Abbey"], watch_providers=["Yle Areena"]

person:      Tietoa henkilöstä. Henkilönimi YKSIN ilman muita kriteerejä.
             Jos henkilönimen lisäksi on genre/vuosi/muu kriteeri → discover.

trending:    Suosio juuri nyt. "trendaa", "mitä katsotaan nyt".

## media_type — käytä AINOASTAAN "movie" tai "tv":
- "movie" = elokuva, filmi, leffaa, elokuvia
- "tv" = sarja, sarjoja, sarjaa, sarjat, k-drama, anime-sarja, show, series

## Kieli — päättele kontekstista:
- anime / animea / animeita / animesarjoja tai anime-tyylilajit (isekai, seinen, shonen, mecha,
  slice of life, ecchi) → language="ja" + genres=["Animaatio"] + media_type="tv"
- isekai → language="ja" + genres=["Animaatio"] + keywords=["isekai", "parallel world"] + media_type="tv"
- "k-drama", "korealainen" → language="ko"
- "bollywood", "intialainen elokuva" → language="hi"
- "ranskalainen" → language="fr"

## Aikavälit:
- "X-luvulla" tai "X:stä lähtien" → year_from=X
- "X-luvulta Y-luvulle" → year_from=X, year_to=Y
- Yksittäinen vuosi → year=XXXX

## Erityistilanteet:
- "tässä seasonissa", "juuri nyt airing", "menossa olevat", "nyt pyörivät"
  → airing_now=true + media_type="tv"
- "elokuvat ja sarjat", "kaikki formaatit" → both_types=true

## Tyylit → keywords (TMDB-englanniksi):
- "synkkä", "tumma" → "dark fantasy"
- "kosto" → "revenge"
- "psykologinen" → "psychological"
- "isekai" → "isekai", "parallel world"
- "aikamatka" → "time travel"
- "cyberpunk" → "cyberpunk"
- "dystopia" → "dystopia"
- "tosi tarina" → "based on true story"
- "noir" → "neo-noir"
- "twist" → "twist ending"
- shounen-muoto → käytä aina "shounen" (ei "shonen")

## Laatu ja järjestys:
- "paras", "klassikko", "must see" → sort_by="vote_average.desc", min_votes=500
- "suosituin" → sort_by="popularity.desc"
- "uusin" → sort_by="release_date.desc"
"""

    query: str = dspy.InputField(desc="Käyttäjän hakukysely")
    available_movie_genres: str = dspy.InputField(desc="Käytettävissä olevat elokuvagenret")
    available_tv_genres: str = dspy.InputField(desc="Käytettävissä olevat sarjagenret")
    available_providers: str = dspy.InputField(desc="Suoratoistopalvelut Suomessa — käytä tarkkaa nimeä")
    today: str = dspy.InputField(desc="Tämänpäiväinen päivämäärä")
    result: SmartSearchIntent = dspy.OutputField()


_classifier = dspy.ChainOfThought(QueryClassification)


def _classify_sync(query: str, memory: dict) -> SmartSearchIntent:
    movie_genres = ", ".join(g["name"] for g in memory.get("movie_genres", []))
    tv_genres = ", ".join(g["name"] for g in memory.get("tv_genres", []))
    providers = ", ".join(p["provider_name"] for p in memory.get("movie_providers", []))
    today = datetime.date.today().isoformat()

    prediction = _classifier(
        query=query,
        available_movie_genres=movie_genres,
        available_tv_genres=tv_genres,
        available_providers=providers,
        today=today,
    )

    _log("DSPY REASONING", getattr(prediction, "reasoning", "—"))
    _log("DSPY RESULT (raaka)", prediction.result.model_dump_json(indent=2))

    return _postprocess(prediction.result, query)


async def classify_query(query: str, memory: dict) -> SmartSearchIntent:
    result = await asyncio.to_thread(_classify_sync, query, memory)
    _log("INTENT (postprocess jälkeen)", result.model_dump_json(indent=2))
    return result


def save_example(query: str, correct_intent: SmartSearchIntent) -> None:
    """Tallenna oikea vastaus harjoitusesimerkkeihin."""
    examples: list[dict] = []
    if _EXAMPLES_FILE.exists():
        examples = json.loads(_EXAMPLES_FILE.read_text(encoding="utf-8"))

    # Korvaa jos sama kysely on jo listassa
    examples = [e for e in examples if e.get("query") != query]
    examples.append({
        "query": query,
        "correct": correct_intent.model_dump(),
    })

    _EXAMPLES_FILE.parent.mkdir(exist_ok=True)
    _EXAMPLES_FILE.write_text(
        json.dumps(examples, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
