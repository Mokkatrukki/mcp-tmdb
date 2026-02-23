import asyncio
import datetime
import os
import sys
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
import httpx

from search.memory import memory, load_memory, TMDB_API_KEY, TMDB_BASE
from search.prompts import classify_query, rerank_candidates, rerank_by_criteria, SmartSearchIntent


_LOG_FILE = os.path.join(os.path.dirname(__file__), "debug.log")


def _log(section: str, text: str) -> None:
    border = "─" * 60
    entry = f"\n{border}\n[LOG] {section}\n{border}\n{text}\n"
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


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
        "language": "en",
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
    params = {"api_key": TMDB_API_KEY, "language": "en"}
    endpoint = f"/movie/{id}" if type == "movie" else f"/tv/{id}"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        d = r.json()

        # Elokuville: hae kokoelma (jatko-osat) jos belongs_to_collection löytyy
        collection_parts = []
        if type == "movie":
            coll = d.get("belongs_to_collection")
            if coll and coll.get("id"):
                cr = await client.get(
                    f"{TMDB_BASE}/collection/{coll['id']}",
                    params={"api_key": TMDB_API_KEY, "language": "en"},
                )
                if cr.status_code == 200:
                    parts = cr.json().get("parts", [])
                    parts.sort(key=lambda p: p.get("release_date") or "")
                    collection_parts = [(coll["name"], parts)]

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

    if collection_parts:
        coll_name, parts = collection_parts[0]
        lines += ["", f"Osa kokoelmaa: {coll_name}"]
        for p in parts:
            year = (p.get("release_date") or "")[:4]
            vote = p.get("vote_average", 0)
            marker = " ◄ tämä" if p.get("id") == id else ""
            pname = p.get("title") or p.get("name", "?")
            lines.append(f"  {pname} ({year}) — {vote:.1f}/10{marker}")

    return "\n".join(line for line in lines if line is not None)


@mcp.tool()
async def list_watch_providers(type: str = "movie") -> str:
    """
    Listaa Suomessa saatavilla olevat suoratoistopalvelut.
    type: 'movie' tai 'tv'
    """
    providers = memory["movie_providers"] if type == "movie" else memory["tv_providers"]
    if not providers:
        return "Palveluja ei ladattu."
    sorted_providers = sorted(providers, key=lambda p: p["provider_name"])
    return "\n".join(f"{p['provider_id']}: {p['provider_name']}" for p in sorted_providers)


@mcp.tool()
async def discover(
    type: str = "movie",
    genres: list[str] | None = None,
    keywords: list[str] | None = None,
    year: int | None = None,
    min_rating: float | None = None,
    min_votes: int = 100,
    sort_by: str = "popularity.desc",
    max_runtime: int | None = None,
    language: str | None = None,
    watch_provider: str | None = None,
    with_cast: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    date_gte: str | None = None,
    date_lte: str | None = None,
) -> str:
    """
    Hae elokuvia tai sarjoja filtterien avulla.
    type: 'movie' tai 'tv'
    genres: lista genrenimistä suomeksi, esim. ["toiminta", "komedia"]
    keywords: lista avainsanoista englanniksi, esim. ["witch", "time travel"]
    year: julkaisuvuosi
    min_rating: vähimmäisarvosana (0–10)
    min_votes: vähimmäisäänimäärä (oletus 100)
    sort_by: järjestys, esim. popularity.desc, vote_average.desc, release_date.desc
    max_runtime: enimmäiskesto minuutteina (vain elokuvat)
    language: alkuperäiskieli, esim. "fi", "en", "ko"
    watch_provider: suoratoistopalvelun nimi, esim. "Netflix", "Disney Plus"
    with_cast: näyttelijän/ohjaajan TMDB-id filtteriksi
    year_from: aikavälin alku (primary_release_date.gte)
    year_to: aikavälin loppu (primary_release_date.lte)
    date_gte: ilmestymispäivä alkaen "YYYY-MM-DD" (tv: air_date.gte — episodeja ilmestynyt tällä aikavälillä)
    date_lte: ilmestymispäivä päättyen "YYYY-MM-DD" (tv: air_date.lte)
    """
    genre_list = memory["movie_genres"] if type == "movie" else memory["tv_genres"]
    genre_map = {g["name"].lower(): g["id"] for g in genre_list}

    params: dict = {
        "api_key": TMDB_API_KEY,
        "language": "en",
        "sort_by": sort_by,
        "vote_count.gte": min_votes,
        "include_adult": False,
        "page": 1,
    }

    if genres:
        ids = []
        unknown = []
        for name in genres:
            gid = genre_map.get(name.lower())
            if gid:
                ids.append(str(gid))
            else:
                unknown.append(name)
        if unknown:
            return f"Tuntemattomia genrejä: {', '.join(unknown)}. Käytä list_genres-työkalua nähdäksesi saatavilla olevat genret."
        params["with_genres"] = "|".join(ids)

    if year:
        if type == "movie":
            params["primary_release_year"] = year
        else:
            params["first_air_date_year"] = year

    if year_from:
        params["primary_release_date.gte"] = f"{year_from}-01-01"
    if year_to:
        params["primary_release_date.lte"] = f"{year_to}-12-31"

    if date_gte:
        params["air_date.gte"] = date_gte
    if date_lte:
        params["air_date.lte"] = date_lte

    if min_rating is not None:
        params["vote_average.gte"] = min_rating

    if max_runtime is not None and type == "movie":
        params["with_runtime.lte"] = max_runtime

    if language:
        params["with_original_language"] = language

    if keywords:
        async with httpx.AsyncClient() as client:
            kw_ids = []
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in memory["keyword_cache"]:
                    kw_ids.append(memory["keyword_cache"][kw_lower])
                else:
                    r = await client.get(
                        f"{TMDB_BASE}/search/keyword",
                        params={"api_key": TMDB_API_KEY, "query": kw},
                    )
                    results_kw = r.json().get("results", [])
                    if results_kw:
                        kw_id = str(results_kw[0]["id"])
                        memory["keyword_cache"][kw_lower] = kw_id
                        kw_ids.append(kw_id)
            if kw_ids:
                params["with_keywords"] = "|".join(kw_ids)

    if watch_provider:
        provider_list = memory["movie_providers"] if type == "movie" else memory["tv_providers"]
        match = next(
            (p for p in provider_list if p["provider_name"].lower() == watch_provider.lower()),
            None,
        )
        if match is None:
            return f"Tuntematon suoratoistopalvelu: '{watch_provider}'. Käytä list_watch_providers-työkalua nähdäksesi saatavilla olevat palvelut."
        params["with_watch_providers"] = match["provider_id"]
        params["watch_region"] = "FI"

    if with_cast is not None:
        params["with_cast"] = with_cast

    endpoint = "/discover/movie" if type == "movie" else "/discover/tv"
    _log("TMDB DISCOVER KUTSU", f"endpoint={endpoint}\nparams={params}")

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    total = data.get("total_results", 0)

    if not results:
        return "Ei tuloksia annetuilla hakuehdoilla."

    id_to_genre = {g["id"]: g["name"] for g in genre_list}

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
        genre_names = [id_to_genre.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
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
async def search_multi(query: str) -> str:
    """
    Hae elokuvia, sarjoja ja henkilöitä yhdellä haulla.
    query: hakusana
    """
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "en",
        "include_adult": False,
        "page": 1,
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}/search/multi", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    total = data.get("total_results", 0)

    if not results:
        return f"Ei tuloksia haulle '{query}'."

    movie_genre_map = {g["id"]: g["name"] for g in memory["movie_genres"]}
    tv_genre_map = {g["id"]: g["name"] for g in memory["tv_genres"]}

    lines = [f"Hakutulos: {total} osumaa (näytetään {len(results)})\n"]
    for item in results:
        media_type = item.get("media_type")

        if media_type == "movie":
            title = item.get("title", "?")
            original = item.get("original_title", "")
            name_str = title if title == original or not original else f"{title} ({original})"
            date = item.get("release_date", "")[:4]
            genre_names = [movie_genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
            vote = item.get("vote_average", 0)
            votes = item.get("vote_count", 0)
            overview = item.get("overview", "")[:150]
            lines.append(
                f"[elokuva/{item.get('id')}] {name_str} ({date})\n"
                f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
                f"  {overview}"
            )
        elif media_type == "tv":
            name = item.get("name", "?")
            original = item.get("original_name", "")
            name_str = name if name == original or not original else f"{name} ({original})"
            date = item.get("first_air_date", "")[:4]
            genre_names = [tv_genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
            vote = item.get("vote_average", 0)
            votes = item.get("vote_count", 0)
            overview = item.get("overview", "")[:150]
            lines.append(
                f"[sarja/{item.get('id')}] {name_str} ({date})\n"
                f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
                f"  {overview}"
            )
        elif media_type == "person":
            pid = item.get("id")
            pname = item.get("name", "?")
            dept = item.get("known_for_department", "")
            known_for = item.get("known_for", [])
            known_titles = []
            for kf in known_for[:3]:
                t = kf.get("title") or kf.get("name") or "?"
                y = (kf.get("release_date") or kf.get("first_air_date") or "")[:4]
                known_titles.append(f"{t} ({y})" if y else t)
            lines.append(
                f"[henkilö/{pid}] {pname}" + (f" — {dept}" if dept else "") + "\n"
                f"  Tunnettu: {', '.join(known_titles) or '-'}"
            )

    return "\n\n".join(lines)


@mcp.tool()
async def search_person(query: str) -> str:
    """
    Hae henkilöä nimellä (näyttelijä, ohjaaja, käsikirjoittaja...).
    query: hakusana
    """
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "en",
        "include_adult": False,
        "page": 1,
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}/search/person", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    total = data.get("total_results", 0)

    if not results:
        return f"Ei tuloksia haulle '{query}'."

    lines = [f"Hakutulos: {total} osumaa (näytetään {len(results)})\n"]
    for person in results:
        pid = person.get("id")
        name = person.get("name", "?")
        dept = person.get("known_for_department", "")
        known_for = person.get("known_for", [])

        known_titles = []
        for item in known_for[:3]:
            title = item.get("title") or item.get("name") or "?"
            year = (item.get("release_date") or item.get("first_air_date") or "")[:4]
            known_titles.append(f"{title} ({year})" if year else title)

        lines.append(
            f"[{pid}] {name}" + (f" — {dept}" if dept else "") + "\n"
            f"  Tunnettu: {', '.join(known_titles) or '-'}"
        )

    return "\n\n".join(lines)


@mcp.tool()
async def get_person(id: int) -> str:
    """
    Hae henkilön tiedot ja tärkeimmät roolit TMDB-id:llä.
    id: TMDB-id (saadaan search_person-hausta)
    """
    params = {"api_key": TMDB_API_KEY, "language": "en", "append_to_response": "combined_credits"}

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}/person/{id}", params=params)
        r.raise_for_status()

    d = r.json()
    credits = d.get("combined_credits", {})

    name = d.get("name", "?")
    dept = d.get("known_for_department", "")
    birthday = d.get("birthday") or ""
    deathday = d.get("deathday") or ""
    place = d.get("place_of_birth") or ""
    bio = (d.get("biography") or "")[:400]

    date_str = birthday[:4] if birthday else "?"
    if deathday:
        date_str += f"–{deathday[:4]}"

    lines = [
        f"{name} ({date_str})",
        f"Ammatti: {dept}" if dept else None,
        f"Syntymäpaikka: {place}" if place else None,
        "",
        bio if bio else None,
    ]

    cast = credits.get("cast", [])
    seen_ids = set()
    cast_filtered = []
    for item in sorted(cast, key=lambda x: x.get("vote_count", 0), reverse=True):
        character = item.get("character") or ""
        if character.lower().startswith("self"):
            continue
        item_id = item.get("id")
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        cast_filtered.append(item)
        if len(cast_filtered) == 10:
            break

    if cast_filtered:
        lines += ["", "Tunnetuimmat roolit:"]
        for item in cast_filtered:
            title = item.get("title") or item.get("name") or "?"
            year = (item.get("release_date") or item.get("first_air_date") or "")[:4]
            character = item.get("character") or ""
            media = "elokuva" if item.get("media_type") == "movie" else "sarja"
            item_id = item.get("id")
            line = f"  [{item_id}] {title}" + (f" ({year})" if year else "") + f" — {media}"
            if character:
                line += f", rooli: {character}"
            lines.append(line)

    crew = credits.get("crew", [])
    directing = [c for c in crew if c.get("job") == "Director"]
    directing_sorted = sorted(directing, key=lambda x: x.get("vote_count", 0), reverse=True)[:5]
    if directing_sorted:
        lines += ["", "Ohjaustöitä:"]
        for item in directing_sorted:
            title = item.get("title") or item.get("name") or "?"
            year = (item.get("release_date") or item.get("first_air_date") or "")[:4]
            item_id = item.get("id")
            lines.append(f"  [{item_id}] {title}" + (f" ({year})" if year else ""))

    return "\n".join(line for line in lines if line is not None)


@mcp.tool()
async def trending(type: str = "all", time_window: str = "week") -> str:
    """
    Hae trendaavat elokuvat, sarjat tai henkilöt.
    type: 'movie', 'tv' tai 'all'
    time_window: 'day' tai 'week'
    """
    endpoint = f"/trending/{type}/{time_window}"
    params = {"api_key": TMDB_API_KEY, "language": "en"}

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return "Ei tuloksia."

    movie_genre_map = {g["id"]: g["name"] for g in memory["movie_genres"]}
    tv_genre_map = {g["id"]: g["name"] for g in memory["tv_genres"]}
    window_str = "tänään" if time_window == "day" else "tällä viikolla"

    lines = [f"Trendaavat ({window_str})\n"]
    for item in results:
        media_type = item.get("media_type", type)

        if media_type == "person":
            pid = item.get("id")
            name = item.get("name", "?")
            dept = item.get("known_for_department", "")
            known_for = item.get("known_for", [])
            known_titles = [kf.get("title") or kf.get("name") or "?" for kf in known_for[:3]]
            lines.append(
                f"[henkilö/{pid}] {name}" + (f" — {dept}" if dept else "") + "\n"
                f"  Tunnettu: {', '.join(known_titles) or '-'}"
            )
            continue

        if media_type == "movie":
            title = item.get("title", "?")
            original = item.get("original_title", "")
            date = item.get("release_date", "")[:4]
            genre_map = movie_genre_map
        else:
            title = item.get("name", "?")
            original = item.get("original_name", "")
            date = item.get("first_air_date", "")[:4]
            genre_map = tv_genre_map

        name_str = title if title == original or not original else f"{title} ({original})"
        genre_names = [genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
        vote = item.get("vote_average", 0)
        votes = item.get("vote_count", 0)
        overview = item.get("overview", "")[:150]

        lines.append(
            f"[{media_type}/{item.get('id')}] {name_str} ({date})\n"
            f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
            f"  {overview}"
        )

    return "\n\n".join(lines)


@mcp.tool()
async def get_recommendations(id: int, type: str = "movie") -> str:
    """
    Hae suosituksia elokuvan tai sarjan perusteella.
    id: TMDB-id (saadaan search_by_title- tai get_details-hausta)
    type: 'movie' tai 'tv'
    """
    endpoint = f"/movie/{id}/recommendations" if type == "movie" else f"/tv/{id}/recommendations"
    params = {"api_key": TMDB_API_KEY, "language": "en", "page": 1}

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return "Ei suosituksia."

    genre_list = memory["movie_genres"] if type == "movie" else memory["tv_genres"]
    genre_map = {g["id"]: g["name"] for g in genre_list}

    lines = [f"Suosituksia ({len(results)} kpl)\n"]
    for item in results:
        if type == "movie":
            title = item.get("title", "?")
            original = item.get("original_title", "")
            date = item.get("release_date", "")[:4]
        else:
            title = item.get("name", "?")
            original = item.get("original_name", "")
            date = item.get("first_air_date", "")[:4]

        name_str = title if title == original or not original else f"{title} ({original})"
        genre_names = [genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
        vote = item.get("vote_average", 0)
        votes = item.get("vote_count", 0)
        overview = item.get("overview", "")[:150]

        lines.append(
            f"[{item.get('id')}] {name_str} ({date})\n"
            f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
            f"  {overview}"
        )

    return "\n\n".join(lines)


@mcp.tool()
async def get_keywords(id: int, type: str = "movie") -> str:
    """
    Hae elokuvan tai sarjan keywordit TMDB-id:llä.
    id: TMDB-id (saadaan search_by_title- tai get_details-hausta)
    type: 'movie' tai 'tv'
    """
    if type == "movie":
        endpoint = f"/movie/{id}/keywords"
        field = "keywords"
    else:
        endpoint = f"/tv/{id}/keywords"
        field = "results"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params={"api_key": TMDB_API_KEY})
        r.raise_for_status()
        data = r.json()

    keywords = data.get(field, [])
    if not keywords:
        return "Ei keywordejä."

    for kw in keywords:
        name = kw.get("name", "").lower()
        kw_id = str(kw.get("id", ""))
        if name and kw_id:
            memory["keyword_cache"][name] = kw_id

    lines = [f"Keywordit ({len(keywords)} kpl):"]
    lines += [f"  [{kw['id']}] {kw['name']}" for kw in keywords]
    return "\n".join(lines)


async def _similar_to(intent: SmartSearchIntent) -> str:
    """Hae teoksia jotka ovat samankaltaisia kuin referenssiteokset (1–n kpl)."""
    ref_type = intent.media_type

    # Keywordit jotka ovat liian geneerisiä löytämään temaattisesti samankaltaisia teoksia
    _SKIP_KW = {
        "anime", "based on light novel", "based on manga", "based on novel",
        "based on web novel", "based on a video game", "magic", "adventure",
        "romance", "based on comic book", "superhero",
    }

    async def _fetch_keyword_discover(client, ref_id, ref_lang, primary_genre_id, user_kw_ids, extra_params=None):
        """Hae referenssin keywordit → yhdistä user-keywordeihin → discover (OR).
        Palauttaa (disc_results, ref_kw_names) jossa ref_kw_names on filtteröity lista keyword-nimistä."""
        kw_field = "results" if ref_type == "tv" else "keywords"
        kw_r = await client.get(
            f"{TMDB_BASE}/{ref_type}/{ref_id}/keywords",
            params={"api_key": TMDB_API_KEY},
        )
        ref_kws = kw_r.json().get(kw_field, [])

        # Suodatetaan generiset pois, otetaan enintään 8 tärkeintä
        filtered = [kw for kw in ref_kws if kw.get("name", "").lower() not in _SKIP_KW][:8]
        ref_kw_ids = [str(kw["id"]) for kw in filtered]
        ref_kw_names = [kw["name"] for kw in filtered]

        # Päivitetään keyword-cache samalla
        for kw in ref_kws:
            name = kw.get("name", "").lower()
            kw_id = str(kw.get("id", ""))
            if name and kw_id:
                memory["keyword_cache"][name] = kw_id

        # User-keywordit ensin (tärkeämmät), sitten ref-keywordit — deduplikoitu
        all_kw_ids = list(dict.fromkeys(user_kw_ids + ref_kw_ids))
        if not all_kw_ids:
            return [], ref_kw_names

        params = {
            "api_key": TMDB_API_KEY,
            "language": "en",
            "with_original_language": ref_lang or "",
            "with_genres": str(primary_genre_id) if primary_genre_id else "",
            "with_keywords": "|".join(all_kw_ids),
            "sort_by": "vote_average.desc",
            "vote_count.gte": 100,
            "include_adult": True,
        }
        if extra_params:
            params.update(extra_params)

        disc_r = await client.get(f"{TMDB_BASE}/discover/{ref_type}", params=params)
        return disc_r.json().get("results", []), ref_kw_names

    async with httpx.AsyncClient() as client:
        # 1. Hae KAIKKI referenssiteokset rinnakkain
        ref_titles = intent.reference_titles or []
        if not ref_titles:
            return "Ei referenssiteosta annettu."

        async def _search_one(title):
            r = await client.get(
                f"{TMDB_BASE}/search/{ref_type}",
                params={"api_key": TMDB_API_KEY, "query": title, "include_adult": True},
            )
            results = r.json().get("results", [])
            if not results:
                return None
            # Otetaan top 5 ja valitaan suositin — TMDB järjestää otsikkovastaavuuden
            # mukaan, joten esim. "Parasite" löytää 1982-filmin ennen 2019-versiota
            return max(results[:5], key=lambda x: x.get("vote_count", 0))

        ref_results = await asyncio.gather(*[_search_one(t) for t in ref_titles])
        refs = [r for r in ref_results if r is not None]
        not_found = [t for t, r in zip(ref_titles, ref_results) if r is None]
        if not_found:
            _log("SIMILAR_TO", f"Referenssejä ei löydy: {not_found}")
        if not refs:
            return f"Ei löydy referenssiteoksia: {', '.join(repr(t) for t in ref_titles)}"

        # Kielestä ja genrestä otetaan ensimmäisestä referenssistä
        primary_ref = refs[0]
        ref_lang = primary_ref.get("original_language")
        primary_genre_id = (primary_ref.get("genre_ids") or [None])[0]

        # 2. Resolvo intent.keywords → TMDB-ID:t
        user_kw_ids = []
        if intent.keywords:
            for kw in intent.keywords:
                kw_lower = kw.lower()
                if kw_lower in memory["keyword_cache"]:
                    user_kw_ids.append(memory["keyword_cache"][kw_lower])
                else:
                    r_kw = await client.get(
                        f"{TMDB_BASE}/search/keyword",
                        params={"api_key": TMDB_API_KEY, "query": kw},
                    )
                    results_kw = r_kw.json().get("results", [])
                    if results_kw:
                        kw_id = str(results_kw[0]["id"])
                        memory["keyword_cache"][kw_lower] = kw_id
                        user_kw_ids.append(kw_id)

        # 3. Resolvo watch_providers → TMDB-IDt (jos asetettu)
        provider_list = memory["movie_providers"] if ref_type == "movie" else memory["tv_providers"]
        provider_extras = []
        for wp in (intent.watch_providers or []):
            prov_match = next(
                (p for p in provider_list if p["provider_name"].lower() == wp.lower()),
                None,
            )
            if prov_match:
                provider_extras.append({"with_watch_providers": prov_match["provider_id"], "watch_region": "FI"})

        # 4. Rinnakkaiset TMDB-kutsut kaikille referensseille
        # Jos watch_providers asetettu: keyword-discover per ref per provider
        # Muuten: keyword-discover + recommendations per ref
        if provider_extras:
            # Järjestys: ref0/pe0, ref0/pe1, ..., ref1/pe0, ref1/pe1, ...
            gather_tasks = [
                _fetch_keyword_discover(client, ref["id"], ref_lang, primary_genre_id, user_kw_ids, extra_params=pe)
                for ref in refs
                for pe in provider_extras
            ]
            raw = await asyncio.gather(*gather_tasks)
            n_pe = len(provider_extras)
            refs_kw_names = [raw[i * n_pe][1] for i in range(len(refs))]
            seen_disc: set[int] = set()
            disc = []
            for d, _ in raw:
                for item in d:
                    if item["id"] not in seen_disc:
                        seen_disc.add(item["id"])
                        disc.append(item)
            recs = []
        else:
            # keyword-discover per ref + recommendations per ref — kaikki rinnakkain
            disc_tasks = [
                _fetch_keyword_discover(client, ref["id"], ref_lang, primary_genre_id, user_kw_ids)
                for ref in refs
            ]
            rec_tasks = [
                client.get(
                    f"{TMDB_BASE}/{ref_type}/{ref['id']}/recommendations",
                    params={"api_key": TMDB_API_KEY, "language": "en", "include_adult": True},
                )
                for ref in refs
            ]
            all_results = await asyncio.gather(*disc_tasks, *rec_tasks)
            n = len(refs)
            disc_raw = all_results[:n]
            rec_responses = all_results[n:]

            refs_kw_names = [d[1] for d in disc_raw]
            seen_disc: set[int] = set()
            disc = []
            for d, _ in disc_raw:
                for item in d:
                    if item["id"] not in seen_disc:
                        seen_disc.add(item["id"])
                        disc.append(item)

            seen_recs: set[int] = set()
            recs = []
            for resp in rec_responses:
                for item in resp.json().get("results", []):
                    if item["id"] not in seen_recs:
                        seen_recs.add(item["id"])
                        recs.append(item)

    # 5. Yhdistä laaja kandidaattijoukko (disc ensin, recs täydentää)
    excluded = {ref["id"] for ref in refs}
    order = (disc + recs) if disc else (recs + disc)
    seen = set(excluded)
    candidates = []
    for item in order:
        item_id = item.get("id")
        if item_id and item_id not in seen:
            seen.add(item_id)
            candidates.append(item)

    ref_names = [ref.get("name") or ref.get("title", "?") for ref in refs]
    if not candidates:
        return f"Ei löydy samankaltaisia teoksia: {' & '.join(repr(n) for n in ref_names)}"

    # 6. LLM rerankaa: kaikkien referenssien kuvaukset + teemat → valitaan parhaiten sopivat
    ref_items = [
        {
            "name": ref.get("name") or ref.get("title", "?"),
            "overview": ref.get("overview", ""),
            "kw_names": kw_names,
        }
        for ref, kw_names in zip(refs, refs_kw_names)
    ]
    ranked_ids = await rerank_candidates(
        ref_items=ref_items,
        user_keywords=intent.keywords,
        candidates=candidates[:30],  # max 30 kandidaattia Geminille
    )

    # Järjestetään kandidaatit Geminin suosittelemaan järjestykseen
    id_to_item = {item["id"]: item for item in candidates}
    top = [id_to_item[rid] for rid in ranked_ids if rid in id_to_item]

    # Fallback: jos rerankaus epäonnistuu, käytetään alkuperäistä järjestystä
    if not top:
        top = candidates[:12]

    genre_list = memory["tv_genres"] if ref_type == "tv" else memory["movie_genres"]
    genre_map = {g["id"]: g["name"] for g in genre_list}

    ref_label = " & ".join(f"'{n}'" for n in ref_names)
    lines = [f"Samankaltaisia kuin {ref_label}:\n"]
    for item in top:
        title = item.get("name") or item.get("title", "?")
        original = item.get("original_name") or item.get("original_title", "")
        date = (item.get("first_air_date") or item.get("release_date", ""))[:4]
        name_str = title if title == original or not original else f"{title} ({original})"
        genre_names = [genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
        vote = item.get("vote_average", 0)
        votes = item.get("vote_count", 0)
        overview = item.get("overview", "")[:150]
        lines.append(
            f"[{item.get('id')}] {name_str} ({date})\n"
            f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
            f"  {overview}"
        )

    return "\n\n".join(lines)


async def _franchise_search(intent: SmartSearchIntent, query: str) -> str:
    """Hae kaikki tietyn franchisen teokset ja järjestä käyttäjän kriteerien mukaan."""
    franchise = intent.franchise_query or query
    ref_type = intent.media_type

    # Haetaan kaksi sivua ilman kielirajoitusta — parempi kattavuus japanilaisille/muille sarjoille
    search_params = {"api_key": TMDB_API_KEY, "query": franchise, "include_adult": True}
    async with httpx.AsyncClient() as client:
        p1, p2 = await asyncio.gather(
            client.get(f"{TMDB_BASE}/search/{ref_type}", params={**search_params, "page": 1}),
            client.get(f"{TMDB_BASE}/search/{ref_type}", params={**search_params, "page": 2}),
        )
    results = p1.json().get("results", []) + p2.json().get("results", [])

    if not results:
        return f"Ei löydy franchisea: '{franchise}'"

    # Suodatetaan tulokset joiden nimessä on franchise-nimi (vältetään täysin epäolennaiset)
    franchise_lower = franchise.lower()
    filtered = [
        item for item in results
        if franchise_lower in (item.get("name") or item.get("title", "")).lower()
        or franchise_lower in (item.get("original_name") or item.get("original_title", "")).lower()
    ]
    if not filtered:
        filtered = results

    # Gemini järjestää käyttäjän kriteerien mukaan (max 30 kandidaattia)
    ranked_ids = await rerank_by_criteria(query, filtered[:30])

    genre_list = memory["tv_genres"] if ref_type == "tv" else memory["movie_genres"]
    genre_map = {g["id"]: g["name"] for g in genre_list}

    id_to_item = {item["id"]: item for item in filtered}
    top = [id_to_item[rid] for rid in ranked_ids if rid in id_to_item]
    if not top:
        top = filtered[:12]

    lines = [f"Franchise-haku '{franchise}':\n"]
    for item in top:
        title = item.get("name") or item.get("title", "?")
        original = item.get("original_name") or item.get("original_title", "")
        date = (item.get("first_air_date") or item.get("release_date", ""))[:4]
        name_str = title if title == original or not original else f"{title} ({original})"
        genre_names = [genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
        vote = item.get("vote_average", 0)
        votes = item.get("vote_count", 0)
        overview = item.get("overview", "")[:150]
        lines.append(
            f"[{item['id']}] {name_str} ({date})\n"
            f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
            f"  {overview}"
        )

    return "\n\n".join(lines)


@mcp.tool()
async def smart_search(query: str) -> str:
    """
    Hae elokuvia, sarjoja tai henkilöitä luonnollisella kielellä.
    Tulkitsee kyselyn automaattisesti ja reitittää oikeaan hakuun.
    query: hakukysely suomeksi tai englanniksi
    """
    try:
        intent = await classify_query(query, memory)
    except Exception as e:
        return f"Virhe kyselyn tulkinnassa: {e}"

    _log("SMART_SEARCH REITITYS", f"intent={intent.intent} | media_type={intent.media_type} | reference_titles={intent.reference_titles} | actor_name={intent.actor_name} | genres={intent.genres} | keywords={intent.keywords} | year_from={intent.year_from} | year_to={intent.year_to} | watch_providers={intent.watch_providers}")

    match intent.intent:
        case "low_confidence":
            return (
                "En ymmärtänyt kyselyä tarpeeksi hyvin.\n"
                "Kokeile esimerkiksi:\n"
                "  • 'toimintaelokuvia 90-luvulta'\n"
                "  • 'jotain kuten Inception'\n"
                "  • 'mitä sarjoja trendaa tällä viikolla'"
            )
        case "franchise":
            return await _franchise_search(intent, query)
        case "trending":
            return await trending(type=intent.media_type, time_window=intent.time_window)
        case "person":
            return await search_person(intent.person_name or intent.name or query)
        case "lookup":
            return await search_by_title(intent.title or intent.name or query, intent.media_type)
        case "similar_to":
            # Fallback: jos Gemini ei poiminut watch_providers, skannaa kysely itse
            if not intent.watch_providers:
                all_providers = memory["movie_providers"] + memory["tv_providers"]
                query_lower = query.lower()
                found = [
                    p["provider_name"] for p in all_providers
                    if p["provider_name"].lower() in query_lower
                ]
                if found:
                    intent.watch_providers = list(dict.fromkeys(found))
                    _log("WATCH_PROVIDERS FALLBACK", f"Poimittu kyselystä: {intent.watch_providers}")
            return await _similar_to(intent)
        case _:  # discover (+ both_types + airing_now)
            # Näyttelijä/ohjaaja-filtteri: hae TMDB-id nimellä
            with_cast_id = None
            if intent.actor_name:
                async with httpx.AsyncClient() as _pc:
                    _pr = await _pc.get(
                        f"{TMDB_BASE}/search/person",
                        params={"api_key": TMDB_API_KEY, "query": intent.actor_name},
                    )
                    _persons = _pr.json().get("results", [])
                    if _persons:
                        with_cast_id = _persons[0]["id"]
                        _log("ACTOR RESOLVAUS", f"{intent.actor_name} → id={with_cast_id} ({_persons[0].get('name')})")

            date_gte = None
            date_lte = None
            if intent.airing_now:
                today = datetime.date.today()
                y, m = today.year, today.month
                if m <= 3:
                    date_gte, date_lte = f"{y}-01-01", f"{y}-03-31"
                elif m <= 6:
                    date_gte, date_lte = f"{y}-04-01", f"{y}-06-30"
                elif m <= 9:
                    date_gte, date_lte = f"{y}-07-01", f"{y}-09-30"
                else:
                    date_gte, date_lte = f"{y}-10-01", f"{y}-12-31"
                intent.min_votes = min(intent.min_votes, 10)

            providers = intent.watch_providers or [None]

            if intent.both_types:
                movie_res, tv_res = await asyncio.gather(
                    discover(type="movie", genres=intent.genres, keywords=intent.keywords,
                             year=intent.year, min_rating=intent.min_rating, min_votes=intent.min_votes,
                             sort_by=intent.sort_by, language=intent.language,
                             watch_provider=providers[0], with_cast=with_cast_id,
                             year_from=intent.year_from, year_to=intent.year_to),
                    discover(type="tv", genres=intent.genres, keywords=intent.keywords,
                             year=intent.year, min_rating=intent.min_rating, min_votes=intent.min_votes,
                             sort_by=intent.sort_by, language=intent.language,
                             watch_provider=providers[0], with_cast=with_cast_id,
                             year_from=intent.year_from, year_to=intent.year_to),
                )
                return f"## Elokuvat\n\n{movie_res}\n\n## Sarjat\n\n{tv_res}"

            if len(providers) > 1:
                # Useita palveluja → rinnakkaiset haut, yksi osio per palvelu
                results = await asyncio.gather(*[
                    discover(
                        type=intent.media_type, genres=intent.genres, keywords=intent.keywords,
                        year=intent.year, min_rating=intent.min_rating, min_votes=intent.min_votes,
                        sort_by=intent.sort_by, language=intent.language,
                        watch_provider=wp, with_cast=with_cast_id,
                        year_from=intent.year_from, year_to=intent.year_to,
                        date_gte=date_gte, date_lte=date_lte,
                    )
                    for wp in providers
                ])
                return "\n\n".join(f"## {wp}\n\n{res}" for wp, res in zip(providers, results))

            return await discover(
                type=intent.media_type,
                genres=intent.genres,
                keywords=intent.keywords,
                year=intent.year,
                min_rating=intent.min_rating,
                min_votes=intent.min_votes,
                sort_by=intent.sort_by,
                language=intent.language,
                watch_provider=providers[0],
                with_cast=with_cast_id,
                year_from=intent.year_from,
                year_to=intent.year_to,
                date_gte=date_gte,
                date_lte=date_lte,
            )


if __name__ == "__main__":
    mcp.run()
