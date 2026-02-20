# TMDB API — Kartta

Tässä tiedostossa merkitään mitkä endpointit ovat käytössä, mitkä ehkä myöhemmin,
ja mitkä jätetään kokonaan pois. Päivitetään sitä mukaa kun rakennetaan.

Merkinnät:
- ✅ käytössä
- 🔜 ehkä myöhemmin
- ❌ ei tarvita tässä projektissa

---

## Startup-muisti (Taso 0)

Haetaan kerran käynnistyksen yhteydessä.

| Endpoint | Käyttö |
|----------|--------|
| ✅ GET /genre/movie/list | elokuvagenret LLM:n sanastoksi |
| ✅ GET /genre/tv/list | sarjagenret LLM:n sanastoksi |
| ✅ GET /certification/movie/list | ikärajat (FI) |
| ✅ GET /certification/tv/list | ikärajat sarjoille |
| ✅ GET /configuration/countries | maiden lista, regiooni-asetuksia varten |

---

## Search (Taso 1 — suorat työkalut)

| Endpoint | Käyttö |
|----------|--------|
| ✅ GET /search/movie | hae elokuvia nimellä |
| ✅ GET /search/tv | hae sarjoja nimellä |
| ✅ GET /search/multi | hae kaikkea kerralla (elokuva + sarja + henkilö) |
| ✅ GET /search/person | hae henkilöä nimellä |
| ❌ GET /search/collection | ei tarvita |
| ❌ GET /search/company | ei tarvita |
| ❌ GET /search/keyword | ei tarvita suoraan |

---

## Movies (Taso 1 — get_details ja muut)

| Endpoint | Käyttö |
|----------|--------|
| ✅ GET /movie/{id} | elokuvan perustiedot |
| ✅ GET /movie/{id}/credits | ohjaaja, näyttelijät |
| ✅ GET /movie/{id}/keywords | avainsanat (käytetään myös Discoverissa) |
| ✅ GET /movie/{id}/recommendations | samankaltaiset suositukset |
| 🔜 GET /movie/{id}/watch/providers | mistä voi katsoa (Suomi) |
| 🔜 GET /movie/{id}/similar | samankaltaiset (vs. recommendations) |
| 🔜 GET /movie/{id}/videos | traileri ym. |
| ❌ GET /movie/{id}/reviews | ei tarvita |
| ❌ GET /movie/{id}/lists | ei tarvita |
| ❌ GET /movie/{id}/release_dates | ei tarvita toistaiseksi |
| ❌ GET /movie/{id}/images | ei tarvita (tekstitulokset) |

---

## TV Series (Taso 1 — sama logiikka kuin Movies)

| Endpoint | Käyttö |
|----------|--------|
| ✅ GET /tv/{id} | sarjan perustiedot |
| ✅ GET /tv/{id}/credits | tekijät, näyttelijät |
| ✅ GET /tv/{id}/keywords | avainsanat |
| ✅ GET /tv/{id}/recommendations | suositukset |
| 🔜 GET /tv/{id}/watch/providers | mistä voi katsoa |
| 🔜 GET /tv/{id}/content_ratings | ikärajat sarjalle |
| ❌ GET /tv/{id}/similar | ehkä myöhemmin |
| ❌ GET /tv/{id}/videos | ei tarvita |
| ❌ GET /tv/{id}/reviews | ei tarvita |
| ❌ GET /tv/seasons, /tv/episodes | ei tarvita toistaiseksi |

---

## People (Taso 1 — henkilöhaut)

| Endpoint | Käyttö |
|----------|--------|
| ✅ GET /person/{id} | henkilön perustiedot |
| ✅ GET /person/{id}/combined_credits | kaikki roolit (elokuvat + sarjat) |
| ✅ GET /person/{id}/movie_credits | vain elokuvaroolit |
| ✅ GET /person/{id}/tv_credits | vain sarjaroolit |
| ❌ GET /person/{id}/images | ei tarvita |
| ❌ GET /person/{id}/tagged_images | ei tarvita |

---

## Discover (Taso 2 — smart_search)

LLM muuntaa luonnollisen kielen näiksi parametreiksi.

| Endpoint | Käyttö |
|----------|--------|
| ✅ GET /discover/movie | filtteröity elokuvahaku |
| ✅ GET /discover/tv | filtteröity sarjahaku |

Tärkeimmät Discover-parametrit:
- `with_genres` — genre id:t (startup-muistista)
- `with_keywords` — avainsanat (startup-muistista)
- `vote_average.gte/lte` — arvosana-asteikko
- `with_cast` — näyttelijä id:llä
- `with_crew` — ohjaaja id:llä
- `sort_by` — järjestys (popularity, vote_average, release_date...)
- `certification` + `certification_country` — ikäraja
- `primary_release_year` / `first_air_date_year` — vuosi
- `with_runtime.gte/lte` — kesto minuutteina

---

## Movie Lists & TV Series Lists (Taso 1/2)

Valmiit listat ilman filtteröintiä.

| Endpoint | Käyttö |
|----------|--------|
| 🔜 GET /movie/popular | suositut elokuvat nyt |
| 🔜 GET /movie/top_rated | parhaiten arvostellut |
| 🔜 GET /movie/now_playing | nyt teattereissa |
| 🔜 GET /tv/popular | suositut sarjat |
| 🔜 GET /tv/top_rated | parhaiten arvostellut sarjat |
| 🔜 GET /tv/airing_today | tänään esitettävät |

---

## Trending

| Endpoint | Käyttö |
|----------|--------|
| 🔜 GET /trending/all/{time_window} | trendaavat (day/week) |
| 🔜 GET /trending/movie/{time_window} | trendaavat elokuvat |
| 🔜 GET /trending/tv/{time_window} | trendaavat sarjat |

---

## Find

| Endpoint | Käyttö |
|----------|--------|
| 🔜 GET /find/{external_id} | hae IMDB-id:llä tai muulla |

Hyödyllinen agenttihaun monivaihehaussa.

---

## Ei tarvita ollenkaan

- **ACCOUNT** — ei käyttäjäkohtaista toimintaa
- **Authentication** — käytetään vain API key -autentikaatiota
- **CHANGES** — muutoshistoria, ei tarvita
- **COLLECTIONS** — elokuvasarjat, ehkä paljon myöhemmin
- **COMPANIES** — tuotantoyhtiöt, ei tarvita
- **GUEST SESSIONS** — ei tarvita
- **LISTS** — käyttäjän omat listat, ei tarvita
- **NETWORKS** — TV-verkot, ei tarvita
- **KEYWORDS /keywords/{id}** — haetaan elokuvan/sarjan kautta, ei suoraan
- **REVIEWS** — ei tarvita
- **WATCH PROVIDERS** — ehkä myöhemmin (mistä voi katsoa Suomessa)
