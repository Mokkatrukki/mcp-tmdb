import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY_V3")
TMDB_BASE = "https://api.themoviedb.org/3"

memory: dict = {
    "movie_genres": [],
    "tv_genres": [],
    "movie_certifications": [],
    "tv_certifications": [],
    "movie_providers": [],
    "tv_providers": [],
    "keyword_cache": {},
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

        r = await client.get(f"{TMDB_BASE}/watch/providers/movie", params={**params, "watch_region": "FI"})
        memory["movie_providers"] = [
            {"provider_id": p["provider_id"], "provider_name": p["provider_name"]}
            for p in r.json().get("results", [])
        ]

        r = await client.get(f"{TMDB_BASE}/watch/providers/tv", params={**params, "watch_region": "FI"})
        memory["tv_providers"] = [
            {"provider_id": p["provider_id"], "provider_name": p["provider_name"]}
            for p in r.json().get("results", [])
        ]

    print(
        f"Muisti ladattu: {len(memory['movie_genres'])} elokuvagenreä, "
        f"{len(memory['tv_genres'])} sarjagenreä, "
        f"{len(memory['movie_certifications'])} elokuvasertifikaattia (FI), "
        f"{len(memory['tv_certifications'])} sarjasertifikaattia (FI), "
        f"{len(memory['movie_providers'])} elokuvapalvelua (FI), "
        f"{len(memory['tv_providers'])} sarjapalvelua (FI)"
    )
