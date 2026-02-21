import datetime
import json
import pathlib
import re
import httpx

from .memory import memory, TMDB_API_KEY, TMDB_BASE
from .prompts import classify_query, SmartSearchIntent
from .state import SearchState

LOG_FILE = pathlib.Path(__file__).parent.parent / "search.log.jsonl"
KEYWORDS_FILE = pathlib.Path(__file__).parent.parent / "data" / "keywords.json"

SUGGESTED_PROMPTS = [
    "Etsi toimintaelokuvia 90-luvulta",
    "Löydä korealaisella tehtyjä romanttisia sarjoja",
    "Kerro elokuvasta Inception",
    "Kuka on Christopher Nolan?",
    "Suosittele jotain samankaltaista kuin Interstellar",
    "Mitä sarjoja trendaa tällä viikolla?",
    "Animesarjoja Netflixistä",
]

_keyword_data: dict = {}


def _load_keyword_data() -> None:
    global _keyword_data
    if KEYWORDS_FILE.exists():
        with KEYWORDS_FILE.open(encoding="utf-8") as f:
            _keyword_data = json.load(f)


def _extract_first_id(text: str) -> int | None:
    m = re.search(r'\[(\d+)\]', text)
    return int(m.group(1)) if m else None


def _count_results(text: str) -> int:
    m = re.search(r'Hakutulos: (\d+) osumaa', text)
    return int(m.group(1)) if m else (1 if text and "Ei " not in text[:20] else 0)


def _log_search(query: str, intent: str, confidence: str, params: dict, result_count: int) -> None:
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "query": query,
        "intent": intent,
        "confidence": confidence,
        "params": params,
        "result_count": result_count,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _format_results(results: list, type: str, genre_map: dict, prefix: str = "") -> list[str]:
    lines = []
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
        overview = item.get("overview", "")[:150]
        genre_names = [genre_map.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
        vote = item.get("vote_average", 0)
        votes = item.get("vote_count", 0)

        name_str = title if title == original or not original else f"{title} ({original})"
        id_str = f"[{prefix}{item_id}]" if prefix else f"[{item_id}]"
        lines.append(
            f"{id_str} {name_str} ({date})\n"
            f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
            f"  {overview}"
        )
    return lines


async def _resolve_keywords(kw_list: list[str]) -> list[str]:
    """Resolve keyword names to TMDB IDs, using cache and keyword data."""
    kw_ids = []
    concept_map = _keyword_data.get("concept_to_tmdb", {})

    async with httpx.AsyncClient() as client:
        for kw in kw_list:
            kw_lower = kw.lower()

            # Check keyword data file first (verified IDs)
            if kw_lower in concept_map:
                entries = concept_map[kw_lower]
                if entries:
                    for entry in entries:
                        kw_id = str(entry["id"])
                        memory["keyword_cache"][entry["name"].lower()] = kw_id
                        kw_ids.append(kw_id)
                    continue

            # Check runtime cache
            if kw_lower in memory["keyword_cache"]:
                kw_ids.append(memory["keyword_cache"][kw_lower])
                continue

            # Search TMDB
            r = await client.get(
                f"{TMDB_BASE}/search/keyword",
                params={"api_key": TMDB_API_KEY, "query": kw},
            )
            results_kw = r.json().get("results", [])
            if results_kw:
                kw_id = str(results_kw[0]["id"])
                memory["keyword_cache"][kw_lower] = kw_id
                kw_ids.append(kw_id)

    return kw_ids


async def _discover_request(
    type: str,
    genres: list[str] | None,
    keywords: list[str] | None,
    language: str | None,
    watch_provider: str | None,
    with_cast: int | None,
    sort_by: str,
    min_votes: int,
    min_rating: float | None,
    year: int | None,
    year_from: int | None,
    year_to: int | None,
    date_gte: str | None,
    date_lte: str | None,
) -> tuple[list, int]:
    """Execute a discover API call. Returns (results, total)."""
    genre_list = memory["movie_genres"] if type == "movie" else memory["tv_genres"]
    genre_map = {g["name"].lower(): g["id"] for g in genre_list}

    params: dict = {
        "api_key": TMDB_API_KEY,
        "language": "fi",
        "sort_by": sort_by,
        "vote_count.gte": min_votes,
        "include_adult": False,
        "page": 1,
    }

    if genres:
        ids = []
        for name in genres:
            gid = genre_map.get(name.lower())
            if gid:
                ids.append(str(gid))
        if ids:
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
        params["first_air_date.gte"] = date_gte
    if date_lte:
        params["first_air_date.lte"] = date_lte

    if min_rating is not None:
        params["vote_average.gte"] = min_rating

    if language:
        params["with_original_language"] = language

    if keywords:
        kw_ids = await _resolve_keywords(keywords)
        if kw_ids:
            params["with_keywords"] = "|".join(kw_ids)

    if watch_provider:
        provider_list = memory["movie_providers"] if type == "movie" else memory["tv_providers"]
        match = next(
            (p for p in provider_list if p["provider_name"].lower() == watch_provider.lower()),
            None,
        )
        if match:
            params["with_watch_providers"] = match["provider_id"]
            params["watch_region"] = "FI"

    if with_cast is not None:
        params["with_cast"] = with_cast

    endpoint = "/discover/movie" if type == "movie" else "/discover/tv"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    return data.get("results", []), data.get("total_results", 0)


def _get_season_dates() -> tuple[str, str]:
    """Calculate current season date range for airing_now."""
    today = datetime.date.today()
    year = today.year
    month = today.month

    if month <= 3:
        season_start = f"{year}-01-01"
        season_end = f"{year}-03-31"
    elif month <= 6:
        season_start = f"{year}-04-01"
        season_end = f"{year}-06-30"
    elif month <= 9:
        season_start = f"{year}-07-01"
        season_end = f"{year}-09-30"
    else:
        season_start = f"{year}-10-01"
        season_end = f"{year}-12-31"

    return season_start, season_end


# ── Solmufunktiot ──────────────────────────────────────────────────────────────

async def classify_intent(state: SearchState) -> dict:
    query = state["query"]
    intent_obj: SmartSearchIntent = await classify_query(query, memory)

    result = {
        "intent": intent_obj.intent,
        "confidence": intent_obj.confidence,
        "media_type": intent_obj.media_type,
        "time_window": intent_obj.time_window,
        "sort_by": intent_obj.sort_by,
        "min_votes": intent_obj.min_votes,
        "airing_now": intent_obj.airing_now,
        "both_types": intent_obj.both_types,
    }

    if intent_obj.genres is not None:
        result["genres"] = intent_obj.genres
    if intent_obj.keywords is not None:
        result["keywords"] = intent_obj.keywords
    if intent_obj.year is not None:
        result["year"] = intent_obj.year
    if intent_obj.year_from is not None:
        result["year_from"] = intent_obj.year_from
    if intent_obj.year_to is not None:
        result["year_to"] = intent_obj.year_to
    if intent_obj.min_rating is not None:
        result["min_rating"] = intent_obj.min_rating
    if intent_obj.language is not None:
        result["language"] = intent_obj.language
    if intent_obj.watch_provider is not None:
        result["watch_provider"] = intent_obj.watch_provider
    if intent_obj.person_name is not None:
        result["person_name"] = intent_obj.person_name
    if intent_obj.title is not None:
        result["title"] = intent_obj.title
    if intent_obj.name is not None:
        result["name"] = intent_obj.name
    if intent_obj.reference_title is not None:
        result["reference_title"] = intent_obj.reference_title

    _log_search(
        query,
        intent_obj.intent,
        intent_obj.confidence,
        intent_obj.model_dump(exclude_none=True),
        0,
    )

    return result


async def resolve_reference(state: SearchState) -> dict:
    title = state.get("reference_title", "")
    media_type = state.get("media_type", "movie")

    if not title:
        return {"final_result": "Virhe: referenssiteosta ei löydy kyselystä."}

    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "fi",
        "include_adult": False,
        "page": 1,
    }
    endpoint = "/search/movie" if media_type == "movie" else "/search/tv"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return {"final_result": f"Ei löydy referenssiteosta: '{title}'"}

    return {"reference_id": results[0]["id"]}


async def resolve_person(state: SearchState) -> dict:
    person_name = state.get("person_name", "")
    if not person_name:
        return {}

    params = {
        "api_key": TMDB_API_KEY,
        "query": person_name,
        "language": "fi",
        "include_adult": False,
        "page": 1,
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}/search/person", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if results:
        return {"cast_id": results[0]["id"]}
    return {}


async def fetch_keywords(state: SearchState) -> dict:
    reference_id = state.get("reference_id")
    media_type = state.get("media_type", "movie")

    if not reference_id:
        return {"reference_keywords": []}

    if media_type == "movie":
        endpoint = f"/movie/{reference_id}/keywords"
        field = "keywords"
    else:
        endpoint = f"/tv/{reference_id}/keywords"
        field = "results"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params={"api_key": TMDB_API_KEY})
        r.raise_for_status()
        data = r.json()

    keywords = data.get(field, [])

    # Lisätään cacheen
    for kw in keywords:
        name = kw.get("name", "").lower()
        kw_id = str(kw.get("id", ""))
        if name and kw_id:
            memory["keyword_cache"][name] = kw_id

    # Palautetaan top 5 keyword-nimeä
    top_keywords = [kw["name"] for kw in keywords[:5]]
    return {"reference_keywords": top_keywords}


async def fetch_recommendations(state: SearchState) -> dict:
    reference_id = state.get("reference_id")
    media_type = state.get("media_type", "movie")

    if not reference_id:
        return {"recommendations_result": ""}

    endpoint = (
        f"/movie/{reference_id}/recommendations"
        if media_type == "movie"
        else f"/tv/{reference_id}/recommendations"
    )
    params = {"api_key": TMDB_API_KEY, "language": "fi", "page": 1}

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return {"recommendations_result": ""}

    genre_list = memory["movie_genres"] if media_type == "movie" else memory["tv_genres"]
    genre_map = {g["id"]: g["name"] for g in genre_list}

    lines = [f"Suosituksia ({len(results)} kpl)\n"]
    lines += _format_results(results, media_type, genre_map)
    return {"recommendations_result": "\n\n".join(lines)}


async def execute_discover(state: SearchState) -> dict:
    media_type = state.get("media_type", "movie")
    genres = state.get("genres")
    language = state.get("language")
    watch_provider = state.get("watch_provider")
    cast_id = state.get("cast_id")
    sort_by = state.get("sort_by", "popularity.desc")
    min_votes = state.get("min_votes", 100)
    min_rating = state.get("min_rating")
    year = state.get("year")
    year_from = state.get("year_from")
    year_to = state.get("year_to")
    airing_now = state.get("airing_now", False)

    # Yhdistetään Geminiltä saadut keywordit + referenssiteoksen keywordit
    gemini_keywords = state.get("keywords") or []
    ref_keywords = state.get("reference_keywords") or []
    all_keywords = gemini_keywords + [kw for kw in ref_keywords if kw not in gemini_keywords]

    date_gte = None
    date_lte = None
    if airing_now:
        date_gte, date_lte = _get_season_dates()

    results, total = await _discover_request(
        type=media_type,
        genres=genres,
        keywords=all_keywords if all_keywords else None,
        language=language,
        watch_provider=watch_provider,
        with_cast=cast_id,
        sort_by=sort_by,
        min_votes=min_votes,
        min_rating=min_rating,
        year=year,
        year_from=year_from,
        year_to=year_to,
        date_gte=date_gte,
        date_lte=date_lte,
    )

    if not results:
        return {"discover_result": "Ei tuloksia annetuilla hakuehdoilla."}

    genre_list = memory["movie_genres"] if media_type == "movie" else memory["tv_genres"]
    genre_map = {g["id"]: g["name"] for g in genre_list}

    lines = [f"Hakutulos: {total} osumaa (näytetään {len(results)})\n"]
    lines += _format_results(results, media_type, genre_map)
    return {"discover_result": "\n\n".join(lines)}


async def execute_both_types(state: SearchState) -> dict:
    """Execute discover for both movie and tv, merge results."""
    genres = state.get("genres")
    language = state.get("language")
    watch_provider = state.get("watch_provider")
    sort_by = state.get("sort_by", "popularity.desc")
    min_votes = state.get("min_votes", 100)
    min_rating = state.get("min_rating")
    year = state.get("year")
    year_from = state.get("year_from")
    year_to = state.get("year_to")
    gemini_keywords = state.get("keywords") or []
    ref_keywords = state.get("reference_keywords") or []
    all_keywords = gemini_keywords + [kw for kw in ref_keywords if kw not in gemini_keywords]

    movie_results, movie_total = await _discover_request(
        type="movie",
        genres=genres,
        keywords=all_keywords if all_keywords else None,
        language=language,
        watch_provider=watch_provider,
        with_cast=None,
        sort_by=sort_by,
        min_votes=min_votes,
        min_rating=min_rating,
        year=year,
        year_from=year_from,
        year_to=year_to,
        date_gte=None,
        date_lte=None,
    )

    tv_results, tv_total = await _discover_request(
        type="tv",
        genres=genres,
        keywords=all_keywords if all_keywords else None,
        language=language,
        watch_provider=watch_provider,
        with_cast=None,
        sort_by=sort_by,
        min_votes=min_votes,
        min_rating=min_rating,
        year=year,
        year_from=year_from,
        year_to=year_to,
        date_gte=None,
        date_lte=None,
    )

    movie_genre_map = {g["id"]: g["name"] for g in memory["movie_genres"]}
    tv_genre_map = {g["id"]: g["name"] for g in memory["tv_genres"]}

    lines = [f"Hakutulos: {movie_total} elokuvaa, {tv_total} sarjaa\n"]

    if movie_results:
        lines.append("## Elokuvat\n")
        lines += _format_results(movie_results[:10], "movie", movie_genre_map, prefix="movie/")

    if tv_results:
        lines.append("\n## Sarjat\n")
        lines += _format_results(tv_results[:10], "tv", tv_genre_map, prefix="tv/")

    if not movie_results and not tv_results:
        return {"discover_result": "Ei tuloksia annetuilla hakuehdoilla."}

    return {"discover_result": "\n\n".join(lines)}


async def execute_lookup(state: SearchState) -> dict:
    title = state.get("title") or state.get("query", "")
    media_type = state.get("media_type", "movie")

    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "fi",
        "include_adult": False,
        "page": 1,
    }
    endpoint = "/search/movie" if media_type == "movie" else "/search/tv"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return {"final_result": f"Ei tuloksia haulle '{title}'."}

    item_id = results[0]["id"]

    # Haetaan tarkemmat tiedot
    detail_params = {"api_key": TMDB_API_KEY, "language": "fi"}
    detail_endpoint = f"/movie/{item_id}" if media_type == "movie" else f"/tv/{item_id}"

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{detail_endpoint}", params=detail_params)
        r.raise_for_status()
        d = r.json()

    genres = ", ".join(g["name"] for g in d.get("genres", []))

    if media_type == "movie":
        title_str = d.get("title", "?")
        original = d.get("original_title", "")
        name_str = title_str if title_str == original or not original else f"{title_str} ({original})"
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

        lines = [
            f"{name_str} ({d.get('first_air_date', '')[:4]}–{d.get('last_air_date', '')[:4]})",
            f"Tagline: {d.get('tagline', '')}" if d.get("tagline") else None,
            f"Genret: {genres or '-'}",
            f"Luojat: {creators}" if creators else None,
            f"Verkosto: {networks}" if networks else None,
            f"Status: {d.get('status', '-')}",
            f"Kaudet: {d.get('number_of_seasons', 0)}, jaksoja yhteensä: {d.get('number_of_episodes', 0)}",
            f"Arvosana: {d.get('vote_average', 0):.1f}/10 ({d.get('vote_count', 0)} ääntä)",
            "",
            d.get("overview", ""),
        ]

    return {"final_result": "\n".join(line for line in lines if line is not None)}


async def execute_person(state: SearchState) -> dict:
    name = state.get("name") or state.get("person_name") or state.get("query", "")

    params = {
        "api_key": TMDB_API_KEY,
        "query": name,
        "language": "fi",
        "include_adult": False,
        "page": 1,
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}/search/person", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return {"final_result": f"Ei löydy henkilöä: '{name}'"}

    person_id = results[0]["id"]

    detail_params = {
        "api_key": TMDB_API_KEY,
        "language": "fi",
        "append_to_response": "combined_credits",
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}/person/{person_id}", params=detail_params)
        r.raise_for_status()
        d = r.json()

    credits = d.get("combined_credits", {})
    dept = d.get("known_for_department", "")
    birthday = d.get("birthday") or ""
    deathday = d.get("deathday") or ""
    place = d.get("place_of_birth") or ""
    bio = (d.get("biography") or "")[:400]

    date_str = birthday[:4] if birthday else "?"
    if deathday:
        date_str += f"–{deathday[:4]}"

    lines = [
        f"{d.get('name', '?')} ({date_str})",
        f"Ammatti: {dept}" if dept else None,
        f"Syntymäpaikka: {place}" if place else None,
        "",
        bio if bio else None,
    ]

    cast = credits.get("cast", [])
    seen_ids: set = set()
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

    return {"final_result": "\n".join(line for line in lines if line is not None)}


async def execute_trending(state: SearchState) -> dict:
    media_type = state.get("media_type", "all")
    time_window = state.get("time_window", "week")

    endpoint = f"/trending/{media_type}/{time_window}"
    params = {"api_key": TMDB_API_KEY, "language": "fi"}

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{TMDB_BASE}{endpoint}", params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return {"final_result": "Ei trendaavia tuloksia."}

    movie_genre_map = {g["id"]: g["name"] for g in memory["movie_genres"]}
    tv_genre_map = {g["id"]: g["name"] for g in memory["tv_genres"]}
    window_str = "tänään" if time_window == "day" else "tällä viikolla"

    lines = [f"Trendaavat ({window_str})\n"]
    for item in results:
        item_media = item.get("media_type", media_type)

        if item_media == "person":
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

        if item_media == "movie":
            title = item.get("title", "?")
            original = item.get("original_title", "")
            date = item.get("release_date", "")[:4]
            gmap = movie_genre_map
        else:
            title = item.get("name", "?")
            original = item.get("original_name", "")
            date = item.get("first_air_date", "")[:4]
            gmap = tv_genre_map

        name_str = title if title == original or not original else f"{title} ({original})"
        genre_names = [gmap.get(gid, str(gid)) for gid in item.get("genre_ids", [])]
        vote = item.get("vote_average", 0)
        votes = item.get("vote_count", 0)
        overview = item.get("overview", "")[:150]

        lines.append(
            f"[{item_media}/{item.get('id')}] {name_str} ({date})\n"
            f"  Genret: {', '.join(genre_names) or '-'} | {vote:.1f}/10 ({votes} ääntä)\n"
            f"  {overview}"
        )

    return {"final_result": "\n\n".join(lines)}


async def merge_similar(state: SearchState) -> dict:
    """Merge recommendations and discover results, deduplicating by ID."""
    rec_text = state.get("recommendations_result", "")
    disc_text = state.get("discover_result", "")

    if not rec_text and not disc_text:
        return {"final_result": "Ei tuloksia."}
    if not rec_text:
        return {"final_result": disc_text}
    if not disc_text:
        return {"final_result": rec_text}

    # Pura ID:t molemmista
    rec_ids = set(re.findall(r'\[(\d+)\]', rec_text))
    disc_items = re.findall(r'(\[(\d+)\][^\[]*(?:\n  [^\[]*)*)', disc_text)

    # Lisää discover-tulokset jotka eivät ole jo suosituksissa
    unique_disc_parts = []
    for full_match, item_id in disc_items:
        if item_id not in rec_ids:
            unique_disc_parts.append(full_match.strip())

    reference_title = state.get("reference_title", "")
    header = f"Samankaltaisia kuin '{reference_title}':\n" if reference_title else ""

    combined_parts = [rec_text]
    if unique_disc_parts:
        combined_parts.append("\n## Lisää samankaltaisia:\n")
        combined_parts.extend(unique_disc_parts)

    return {"final_result": header + "\n\n".join(combined_parts)}


async def handle_low_confidence(state: SearchState) -> dict:
    suggestions = "\n".join(f"  • {p}" for p in SUGGESTED_PROMPTS)
    return {
        "final_result": f"En ymmärtänyt hakuasi täysin. Kokeile esimerkiksi:\n{suggestions}"
    }
