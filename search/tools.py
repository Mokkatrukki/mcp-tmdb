import httpx

from .memory import memory, TMDB_API_KEY, TMDB_BASE, _log


async def list_genres(type: str = "movie") -> str:
    """
    Listaa käytettävissä olevat genret.
    type: 'movie' tai 'tv'
    """
    genres = memory["movie_genres"] if type == "movie" else memory["tv_genres"]
    if not genres:
        return "Genrejä ei ladattu — onko palvelin käynnistetty oikein?"
    return "\n".join(f"{g['id']}: {g['name']}" for g in genres)


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
        ids = [str(gid) for name in genres if (gid := genre_map.get(name.lower()))]
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
