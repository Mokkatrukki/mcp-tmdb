from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import httpx
import os

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY_V3")
TMDB_BASE = "https://api.themoviedb.org/3"

# Startup-muisti — ladataan kerran käynnistyksen yhteydessä
memory: dict = {
    "movie_genres": [],   # [{id, name}]
    "tv_genres": [],      # [{id, name}]
    "movie_certifications": [],  # FI-sertifikaatit [{certification, meaning, order}]
    "tv_certifications": [],     # FI-sertifikaatit
}


async def load_memory():
    params = {"api_key": TMDB_API_KEY}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}/genre/movie/list", params={**params, "language": "fi"})
        memory["movie_genres"] = r.json()["genres"]

        r = await client.get(f"{TMDB_BASE}/genre/tv/list", params={**params, "language": "fi"})
        memory["tv_genres"] = r.json()["genres"]

        r = await client.get(f"{TMDB_BASE}/certification/movie/list", params=params)
        memory["movie_certifications"] = r.json()["certifications"].get("FI", [])

        r = await client.get(f"{TMDB_BASE}/certification/tv/list", params=params)
        memory["tv_certifications"] = r.json()["certifications"].get("FI", [])

    print(f"Muisti ladattu: {len(memory['movie_genres'])} elokuvagenreä, "
          f"{len(memory['tv_genres'])} sarjagenreä, "
          f"{len(memory['movie_certifications'])} elokuvasertifikaattia (FI), "
          f"{len(memory['tv_certifications'])} sarjasertifikaattia (FI)")


@asynccontextmanager
async def lifespan(app):
    await load_memory()
    yield


mcp = FastMCP("tmdb", lifespan=lifespan)


@mcp.tool()
async def list_genres(type: str = "movie") -> str:
    """
    Listaa käytettävissä olevat genret.
    type: 'movie' tai 'tv'
    """
    genres = memory["movie_genres"] if type == "movie" else memory["tv_genres"]
    if not genres:
        return "Genrejä ei ladattu — onko palvelin käynnistetty oikein?"
    return "\n".join(f"{g['id']}: {g['name']}" for g in genres)


@mcp.tool()
async def list_certifications(type: str = "movie") -> str:
    """
    Listaa Suomen ikärajat.
    type: 'movie' tai 'tv'
    """
    certs = memory["movie_certifications"] if type == "movie" else memory["tv_certifications"]
    if not certs:
        return "Sertifikaatteja ei ladattu."
    sorted_certs = sorted(certs, key=lambda c: c["order"])
    return "\n".join(f"{c['certification']}: {c['meaning']}" for c in sorted_certs)


@mcp.tool()
async def search_by_title(query: str, type: str = "movie") -> str:
    """
    Hae elokuvia tai sarjoja nimellä.
    query: hakusana
    type: 'movie' tai 'tv'
    """
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "fi",
        "include_adult": False,
        "page": 1,
    }
    endpoint = "/search/movie" if type == "movie" else "/search/tv"
    genre_map = {g["id"]: g["name"] for g in memory["movie_genres" if type == "movie" else "tv_genres"]}

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    total = data.get("total_results", 0)

    if not results:
        return f"Ei tuloksia haulle '{query}'."

    lines = [f"Hakutulos: {total} osumaa (näytetään {len(results)})\n"]
    for item in results:
        if type == "movie":
            title = item.get("title", "?")
            original = item.get("original_title", "")
            date = item.get("release_date", "")[:4]
        else:
            title = item.get("name", "?")
            original = item.get("original_name", "")
            date = item.get("first_air_date", "")[:4]

        item_id = item.get("id")
        overview = item.get("overview", "")[:200]
        genre_names = [genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
        vote = item.get("vote_average", 0)
        votes = item.get("vote_count", 0)

        name_str = title if title == original or not original else f"{title} ({original})"
        lines.append(
            f"[{item_id}] {name_str} ({date})\n"
            f"  Genret: {', '.join(genre_names) or '-'}\n"
            f"  Arvosana: {vote:.1f}/10 ({votes} ääntä)\n"
            f"  {overview}"
        )

    return "\n\n".join(lines)


@mcp.tool()
async def get_details(id: int, type: str = "movie") -> str:
    """
    Hae elokuvan tai sarjan tarkemmat tiedot TMDB-id:llä.
    id: TMDB-id (saadaan search_by_title-hausta)
    type: 'movie' tai 'tv'
    """
    params = {"api_key": TMDB_API_KEY, "language": "fi"}
    endpoint = f"/movie/{id}" if type == "movie" else f"/tv/{id}"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        d = r.json()

    genres = ", ".join(g["name"] for g in d.get("genres", []))

    if type == "movie":
        title = d.get("title", "?")
        original = d.get("original_title", "")
        name_str = title if title == original or not original else f"{title} ({original})"
        runtime = d.get("runtime")
        budget = d.get("budget", 0)
        revenue = d.get("revenue", 0)
        countries = ", ".join(c["name"] for c in d.get("production_countries", []))

        lines = [
            f"{name_str} ({d.get('release_date', '')[:4]})",
            f"Tagline: {d.get('tagline', '')}" if d.get("tagline") else None,
            f"Genret: {genres or '-'}",
            f"Kesto: {runtime} min" if runtime else None,
            f"Status: {d.get('status', '-')}",
            f"Maat: {countries or '-'}",
            f"Arvosana: {d.get('vote_average', 0):.1f}/10 ({d.get('vote_count', 0)} ääntä)",
            f"Budjetti: ${budget:,}" if budget else None,
            f"Tuotto: ${revenue:,}" if revenue else None,
            f"IMDb: {d.get('imdb_id', '')}" if d.get("imdb_id") else None,
            "",
            d.get("overview", ""),
        ]
    else:
        name = d.get("name", "?")
        original = d.get("original_name", "")
        name_str = name if name == original or not original else f"{name} ({original})"
        creators = ", ".join(c["name"] for c in d.get("created_by", []))
        networks = ", ".join(n["name"] for n in d.get("networks", []))
        seasons = [s for s in d.get("seasons", []) if s.get("season_number", 0) > 0]
        season_lines = [
            f"  Kausi {s['season_number']}: {s['episode_count']} jaksoa"
            + (f" ({s['air_date'][:4]})" if s.get("air_date") else "")
            + (f" — {s['vote_average']:.1f}/10" if s.get("vote_average") else "")
            for s in seasons
        ]

        lines = [
            f"{name_str} ({d.get('first_air_date', '')[:4]}–{d.get('last_air_date', '')[:4]})",
            f"Tagline: {d.get('tagline', '')}" if d.get("tagline") else None,
            f"Genret: {genres or '-'}",
            f"Luojat: {creators}" if creators else None,
            f"Verkosto: {networks}" if networks else None,
            f"Status: {d.get('status', '-')}" + (" (tuotannossa)" if d.get("in_production") else ""),
            f"Kaudet: {d.get('number_of_seasons', 0)}, jaksoja yhteensä: {d.get('number_of_episodes', 0)}",
            f"Arvosana: {d.get('vote_average', 0):.1f}/10 ({d.get('vote_count', 0)} ääntä)",
            "",
            d.get("overview", ""),
        ]
        if season_lines:
            lines += ["", "Kaudet:"] + season_lines

    return "\n".join(line for line in lines if line is not None)


if __name__ == "__main__":
    mcp.run()
