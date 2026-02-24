import asyncio
import datetime
import httpx

from .memory import memory, TMDB_API_KEY, TMDB_BASE, _log
from .prompts import rerank_candidates, rerank_by_criteria, SmartSearchIntent
from .classifier import classify_query
from .tools import discover, trending, search_by_title, search_person


async def _similar_to(intent: SmartSearchIntent) -> str:
    """Hae teoksia jotka ovat samankaltaisia kuin referenssiteokset (1–n kpl)."""
    ref_type = intent.media_type

    _SKIP_KW = {
        "anime", "based on light novel", "based on manga", "based on novel",
        "based on web novel", "based on a video game", "magic", "adventure",
        "romance", "based on comic book", "superhero",
        "shounen", "shoujo", "josei", "seinen",
    }

    async def _fetch_keyword_discover(client, ref_id, ref_lang, primary_genre_id, user_kw_ids, extra_params=None):
        """Hae referenssin keywordit → yhdistä user-keywordeihin → discover.
        Strategia: strict (AND top-2) ensin, OR-fallback täydentää jos tuloksia < 10.
        Palauttaa (disc_results, ref_kw_names)."""
        kw_field = "results" if ref_type == "tv" else "keywords"
        kw_r = await client.get(
            f"{TMDB_BASE}/{ref_type}/{ref_id}/keywords",
            params={"api_key": TMDB_API_KEY},
        )
        ref_kws = kw_r.json().get(kw_field, [])

        filtered = [kw for kw in ref_kws if kw.get("name", "").lower() not in _SKIP_KW][:8]
        ref_kw_ids = [str(kw["id"]) for kw in filtered]
        ref_kw_names = [kw["name"] for kw in filtered]

        for kw in ref_kws:
            name = kw.get("name", "").lower()
            kw_id = str(kw.get("id", ""))
            if name and kw_id:
                memory["keyword_cache"][name] = kw_id

        all_kw_ids = list(dict.fromkeys(user_kw_ids + ref_kw_ids))
        if not all_kw_ids:
            return [], ref_kw_names

        base_params = {
            "api_key": TMDB_API_KEY,
            "language": "en",
            "with_original_language": ref_lang or "",
            "with_genres": str(primary_genre_id) if primary_genre_id else "",
            "sort_by": "vote_average.desc",
            "vote_count.gte": 100,
            "include_adult": True,
        }
        if extra_params:
            base_params.update(extra_params)

        seen: set[int] = set()
        results: list[dict] = []

        if len(all_kw_ids) >= 2:
            r = await client.get(
                f"{TMDB_BASE}/discover/{ref_type}",
                params={**base_params, "with_keywords": ",".join(all_kw_ids[:2])},
            )
            for item in r.json().get("results", []):
                if item["id"] not in seen:
                    seen.add(item["id"])
                    results.append(item)

        if len(results) < 10:
            r = await client.get(
                f"{TMDB_BASE}/discover/{ref_type}",
                params={**base_params, "with_keywords": "|".join(all_kw_ids)},
            )
            for item in r.json().get("results", []):
                if item["id"] not in seen:
                    seen.add(item["id"])
                    results.append(item)

        return results, ref_kw_names

    async with httpx.AsyncClient() as client:
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
            return max(results[:5], key=lambda x: x.get("vote_count", 0))

        ref_results = await asyncio.gather(*[_search_one(t) for t in ref_titles])
        refs = [r for r in ref_results if r is not None]
        not_found = [t for t, r in zip(ref_titles, ref_results) if r is None]
        if not_found:
            _log("SIMILAR_TO", f"Referenssejä ei löydy: {not_found}")
        if not refs:
            return f"Ei löydy referenssiteoksia: {', '.join(repr(t) for t in ref_titles)}"

        primary_ref = refs[0]
        ref_lang = primary_ref.get("original_language")
        primary_genre_id = (primary_ref.get("genre_ids") or [None])[0]

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

        provider_list = memory["movie_providers"] if ref_type == "movie" else memory["tv_providers"]
        provider_extras = []
        for wp in (intent.watch_providers or []):
            prov_match = next(
                (p for p in provider_list if p["provider_name"].lower() == wp.lower()),
                None,
            )
            if prov_match:
                provider_extras.append({"with_watch_providers": prov_match["provider_id"], "watch_region": "FI"})

        if provider_extras:
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
                    if item["id"] not in seen_recs and item.get("original_language") == ref_lang:
                        seen_recs.add(item["id"])
                        recs.append(item)

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
        candidates=candidates[:30],
    )

    id_to_item = {item["id"]: item for item in candidates}
    top = [id_to_item[rid] for rid in ranked_ids if rid in id_to_item]

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

    search_params = {"api_key": TMDB_API_KEY, "query": franchise, "include_adult": True}
    async with httpx.AsyncClient() as client:
        p1, p2 = await asyncio.gather(
            client.get(f"{TMDB_BASE}/search/{ref_type}", params={**search_params, "page": 1}),
            client.get(f"{TMDB_BASE}/search/{ref_type}", params={**search_params, "page": 2}),
        )
    results = p1.json().get("results", []) + p2.json().get("results", [])

    if not results:
        return f"Ei löydy franchisea: '{franchise}'"

    franchise_lower = franchise.lower()
    filtered = [
        item for item in results
        if franchise_lower in (item.get("name") or item.get("title", "")).lower()
        or franchise_lower in (item.get("original_name") or item.get("original_title", "")).lower()
    ]
    if not filtered:
        filtered = results

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


async def route(query: str) -> str:
    """Tulkitsee kyselyn ja reitittää oikeaan hakuun."""
    try:
        intent = await classify_query(query, memory)
    except Exception as e:
        return f"Virhe kyselyn tulkinnassa: {e}"

    _log(
        "SMART_SEARCH REITITYS",
        f"intent={intent.intent} | media_type={intent.media_type} | "
        f"reference_titles={intent.reference_titles} | actor_name={intent.actor_name} | "
        f"genres={intent.genres} | keywords={intent.keywords} | "
        f"year_from={intent.year_from} | year_to={intent.year_to} | "
        f"watch_providers={intent.watch_providers}",
    )

    match intent.intent:
        case "franchise":
            return await _franchise_search(intent, query)
        case "trending":
            return await trending(type=intent.media_type, time_window=intent.time_window)
        case "person":
            return await search_person(intent.person_name or query)
        case "lookup":
            return await search_by_title(intent.title or query, intent.media_type)
        case "similar_to":
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
