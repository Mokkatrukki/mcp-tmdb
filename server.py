from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

from search.memory import load_memory
from search.prompts import SmartSearchIntent
from search.classifier import save_example
from search import tools
from search.smart import route


@asynccontextmanager
async def lifespan(app):
    await load_memory()
    yield


mcp = FastMCP("tmdb", lifespan=lifespan)

for _fn in [
    tools.list_genres,
    tools.list_certifications,
    tools.search_by_title,
    tools.get_details,
    tools.list_watch_providers,
    tools.discover,
    tools.search_multi,
    tools.search_person,
    tools.get_person,
    tools.trending,
    tools.get_recommendations,
    tools.get_keywords,
]:
    mcp.tool()(_fn)


@mcp.tool()
async def smart_search(query: str) -> str:
    """
    Hae elokuvia, sarjoja tai henkilöitä luonnollisella kielellä.
    Tulkitsee kyselyn automaattisesti ja reitittää oikeaan hakuun.
    query: hakukysely suomeksi tai englanniksi
    """
    return await route(query)


@mcp.tool()
async def add_training_example(query: str, correct_intent_json: str) -> str:
    """
    Tallenna oikea luokitteluvastaus harjoitusesimerkkeihin DSPy-optimointia varten.
    query: alkuperäinen hakukysely joka meni väärin
    correct_intent_json: oikea SmartSearchIntent JSON-muodossa
    Esimerkki: {"intent":"similar_to","media_type":"tv","reference_titles":["Downton Abbey"],"watch_providers":["Yle Areena"]}
    """
    try:
        intent = SmartSearchIntent.model_validate_json(correct_intent_json)
        save_example(query, intent)
        return f"Esimerkki tallennettu: {query!r}"
    except Exception as e:
        return f"Virhe: {e}"


if __name__ == "__main__":
    mcp.run()
