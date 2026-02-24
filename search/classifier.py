import asyncio
import datetime
import json
import os
from pathlib import Path

import dspy
from dotenv import load_dotenv

from .memory import _log
from .prompts import SmartSearchIntent, _postprocess

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

## Intent — valitse yksi:

franchise:   Franchise-nimi + valintakriteeri (paras/tummin/suosituin).
             → franchise_query=<nimi>
             Esimerkit: "parhaat Gundam-sarjat", "tummimmat Star Wars -elokuvat"

discover:    Lista teoksia kriteereillä — ei yhtä nimettyä teosta.
             Näyttelijä/ohjaaja + kriteeri → discover + actor_name=<nimi>
             Esimerkit: "Tom Hanksin sotaelokuvat", "Nolan-elokuvat"

lookup:      Tiedot yhdestä nimetystä teoksesta.
             Merkkejä: "kerro", "mikä on", teoksen nimi yksin.

similar_to:  Teos mainitaan vertailukohtana, ei kohteena.
             Merkkejä: "kuten", "samanlainen kuin", "X tyylinen", "lisää kuin X".
             → reference_titles=["Nimi"]  tai useita ["A", "B"]
             Jos suoratoistopalvelu mainittu → watch_providers=["Palvelu"]

person:      Henkilönimi yksin, ilman muita kriteerejä.
             Henkilö + genre/vuosi/muu → discover.

trending:    "trendaa", "mitä katsotaan nyt".

## media_type — AINOASTAAN "movie" tai "tv":
- "movie" = elokuva, filmi, leffa
- "tv" = sarja, sarjat, show, series, anime

## Kentät intenteittäin:

### lookup
- title: teoksen nimi

### person
- person_name: henkilön nimi

### franchise
- franchise_query: franchisen nimi

### similar_to
- reference_titles: lista referenssiteosten nimistä, esim. ["Inception", "Interstellar"]
- watch_providers: tarkka palvelun nimi annetusta listasta (valinnainen)

### discover (+ similar_to)
- watch_providers: tarkka palvelun nimi annetusta listasta
- genres: käytettävissä olevista genrenimistä (suomeksi)
- keywords: englanniksi — tunnelma, tyyli, teemat
  Anime-demografiat: josei=aikuisnaiset (kypsä romantiikka), seinen=aikuismiehet,
  shounen=nuoret pojat — lisää hakuun kun anime + kohderyhmä mainitaan
  Esimerkki: "aikuismainen romanttinen anime" → keywords: ["josei", "romance"]
- year / year_from / year_to: päättele aikaväli kyselystä ("90-luvulta" → year_from=1990)
- sort_by: popularity.desc / vote_average.desc / release_date.desc
- min_votes: jos "ei parhaita" / "vähemmän tunnettu" / "en ole nähnyt" → 50
  (pienempi kynnys = laajempi pool, vähemmän mainstream-tuloksia)
- language: ISO 639-1 alkuperäiskielelle
- actor_name: näyttelijän/ohjaajan nimi, kun haetaan henkilön teoksia
- airing_now: true jos "nyt airing" / "menossa olevat" / "tässä seasonissa"
- both_types: true jos halutaan sekä elokuvia että sarjoja

### trending
- time_window: "day" tai "week"
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
