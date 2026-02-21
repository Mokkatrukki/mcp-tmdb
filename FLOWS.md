# MCP-TMDB — Arkkitehtuuri ja kutsuketjut

---

## Projektirakenne

```
server.py           ← MCP-kuori: @mcp.tool()-rekisteröinnit
search/
  memory.py         ← startup-muisti (genret, palvelut, keyword-cache)
  state.py          ← SearchState TypedDict (LangGraph-tila)
  prompts.py        ← SmartSearchIntent + _build_prompt() + classify_query()
  nodes.py          ← solmufunktiot (classify, resolve, fetch, execute, merge)
  graph.py          ← build_graph() → CompiledGraph
data/
  keywords.json     ← verifioitu TMDB-keyword-kartta (ID:t tarkistettu)
tests/
  test_prompt.py    ← Gemini-kutsut eri kyselyillä, assert parametrit oikein
```

---

## Taso 0 — Käynnistys (startup-muisti)

```
MCP Server                         TMDB API
    |                                  |
    |-- GET /genre/movie/list -------->|
    |<-- elokuvagenret (id + nimi) ----|
    |-- GET /genre/tv/list ----------->|
    |<-- sarjagenret (id + nimi) ------|
    |-- GET /certification/movie/list ->|
    |<-- ikärajat FI -----------------|
    |-- GET /watch/providers/movie ---->|
    |<-- suoratoistopalvelut FI -------|
    |                                  |
  [muisti ladattu → build_graph() → palvelin valmis]
```

---

## Taso 1 — Suorat työkalut

Yksi kutsu → yksi TMDB-API-pyyntö → yksi vastaus. Ei LLM-tulkintaa.

| Työkalu | Kuvaus |
|---|---|
| `search_by_title` | nimihaku (movie/tv) |
| `search_multi` | nimihaku kaikki tyypit kerralla |
| `search_person` | henkilöhaku |
| `get_details` | elokuvan/sarjan tiedot id:llä |
| `get_person` | henkilön tiedot + roolit (append_to_response) |
| `get_keywords` | teoksen keywordit (tallentuu cacheen) |
| `get_recommendations` | suositukset id:n perusteella |
| `trending` | trendaavat (movie/tv/all, day/week) |
| `discover` | suodatushaku (genre, keyword, vuosi, kieli, palvelu, cast) |
| `list_genres` | muistista, FI-nimet |
| `list_certifications` | muistista, FI |
| `list_watch_providers` | muistista, FI |

**discover()-parametrit:**
```
type, genres (FI-nimet), keywords (EN), year, year_from, year_to,
min_rating, min_votes, sort_by, max_runtime, language,
watch_provider, with_cast, date_gte, date_lte
```

---

## Taso 2 — smart_search + LangGraph

Luonnollinen kieli → Gemini tulkitsee → LangGraph reititys → TMDB-kutsut → vastaus.

### Pääpolku

```
smart_search(query)
      │
      ▼
 classify_intent
 (Gemini-kutsu)
      │
      ├─ confidence=low ──────────────► handle_low_confidence → [ehdotukset]
      │
      ├─ trending ────────────────────► execute_trending → END
      │
      ├─ person ──────────────────────► execute_person → END
      │
      ├─ lookup ──────────────────────► execute_lookup → END
      │
      ├─ similar_to ──────────────────► resolve_reference
      │                                      │
      │                                 fetch_keywords
      │                                      │
      │                        ┌─── fetch_recommendations
      │                        │         │
      │                        │    execute_discover
      │                        │         │
      │                        └────► merge_similar → END
      │
      ├─ discover + person ───────────► resolve_person
      │                                      │
      │                                 execute_discover → END
      │
      ├─ discover + both_types ───────► execute_both_types → END
      │
      └─ discover ────────────────────► execute_discover → END
```

### Solmufunktiot (nodes.py)

| Solmu | Tehtävä |
|---|---|
| `classify_intent` | Gemini-kutsu → täyttää SearchState-kentät |
| `resolve_reference` | search_by_title(reference_title) → reference_id |
| `resolve_person` | search_person(person_name) → cast_id |
| `fetch_keywords` | get_keywords(reference_id) → reference_keywords (top 5) |
| `fetch_recommendations` | get_recommendations(reference_id) → recommendations_result |
| `execute_discover` | discover() käyttäen kaikkia state-kenttiä → discover_result |
| `execute_both_types` | discover() kahdesti (movie + tv) → discover_result |
| `execute_lookup` | search_by_title + get_details → final_result |
| `execute_person` | search_person + get_person → final_result |
| `execute_trending` | trending(type, time_window) → final_result |
| `merge_similar` | yhdistä rec + discover, dedup id:llä → final_result |
| `handle_low_confidence` | → ehdotusviesti |

### similar_to -polku yksityiskohtaisesti

```
Kysely: "jotain kuten Redo of Healer"

classify_intent:
  intent=similar_to, reference_title="Kaifuku Jutsushi...",
  language="ja", genres=["Animaatio"], media_type="tv"
        │
        ▼
resolve_reference:
  search_by_title("Kaifuku Jutsushi...") → reference_id=131894
        │
        ▼
fetch_keywords:
  /tv/131894/keywords → ["revenge", "ecchi", "dark fantasy", ...]
  top 5 → reference_keywords
        │
        ▼
fetch_recommendations:
  /tv/131894/recommendations → recommendations_result (teksti)
        │
        ▼
execute_discover:
  keywords = [Geminiltä saadut] + [reference_keywords]
  discover(language="ja", genres=["Animaatio"],
           keywords=yhdistetyt, ...) → discover_result
        │
        ▼
merge_similar:
  recommendations ensin (TMDB:n oma järjestys)
  + discover-tulokset joita ei ole jo suosituksissa (dedup id:llä)
  → final_result
```

### airing_now -logiikka

```python
# execute_discover laskee automaattisesti kun airing_now=True:
today = date.today()
if   month <= 3:  gte="YYYY-01-01", lte="YYYY-03-31"
elif month <= 6:  gte="YYYY-04-01", lte="YYYY-06-30"
elif month <= 9:  gte="YYYY-07-01", lte="YYYY-09-30"
else:             gte="YYYY-10-01", lte="YYYY-12-31"
# → first_air_date.gte / first_air_date.lte
```

---

## Gemini-prompti (prompts.py)

Prompti opettaa **säännöt ja merkit**, ei tekstuaalisia esimerkkejä.
Esimerkit ovat testisarjassa (tests/test_prompt.py), ei promptissa.

### Mitä prompti sisältää

**1. Konteksti (injektoitu muistista)**
- Tänään on {today}
- Elokuvagenret suomeksi (muistista)
- Sarjagenret suomeksi (muistista)
- Suoratoistopalvelut Suomessa (muistista)

**2. Intent-säännöt — mikä käyttäjä haluaa, ei sanamuodon perusteella**

| Intent | Merkit |
|---|---|
| `discover` | tyylin/tunnelman kuvailu, genreviittaus, aikaväli ilman nimeä |
| `lookup` | yksi nimetty teos + "kerro", "mikä on" |
| `similar_to` | teos VERTAILUKOHTANA: "kuten X", "X tyylinen", "X oli hyvä anna lisää" |
| `person` | henkilönimi yksin, "kuka on" |
| `trending` | "trendaa", "mitä katsotaan nyt" |

**3. media_type — tiukat arvot**
- Vain `"movie"` tai `"tv"` — ei muuta

**4. Kielipäättely — eksplisiittistä mainintaa ei tarvita**

| Merkki | Tulos |
|---|---|
| "anime", "manga-pohjainen", isekai, seinen, shonen jne. | `language="ja"` + `genres=["Animaatio"]` + `media_type="tv"` |
| isekai (aina) | + `media_type="tv"` |
| "k-drama", "korealainen" | `language="ko"` |
| "bollywood", "intialainen elokuva" | `language="hi"` |
| "ranskalainen", "ranskalaisella" | `language="fr"` |

**5. Aikavälit**

| Ilmaisu | Tulos |
|---|---|
| "X-luvulla" | `year_from=X` |
| "X-luvulta tähän päivään" | `year_from=X` (year_to tyhjä) |
| "X-luvulta Y-luvulle" | `year_from=X, year_to=Y` |
| yksittäinen vuosi | `year=XXXX` |

**6. Erityistilanteet**

| Ilmaisu | Tulos |
|---|---|
| "tässä seasonissa", "tällä hetkellä menossa" | `airing_now=true` |
| "elokuvat ja sarjat", "kaikki formaatit" | `both_types=true` |

**7. Tunnelma/tyyli → keywords (TMDB-englanniksi, ID-kartta data/keywords.json:ssa)**

| Suomi | TMDB keyword |
|---|---|
| synkkä, tumma | dark fantasy |
| kosto, kostotarina | revenge |
| psykologinen | psychological |
| väkivaltainen, gore, brutaali | gore |
| kypsä, aikuisille | seinen / adult animation |
| isekai | isekai, parallel world |
| noir | neo-noir |
| aikamatka | time travel |
| cyberpunk, kybermatka | cyberpunk |
| dystopia | dystopia |
| shonen/shounen | shounen (TMDB canonical) |
| "vibet", "wibe", "tunnelma" | ÄLÄ aseta — käytä muita merkkejä |

**8. Laatu ja järjestys**

| Ilmaisu | sort_by | min_votes |
|---|---|---|
| "paras", "parhaat", "klassikko", "must see" | vote_average.desc | 500 |
| "suosituin", "trending" | popularity.desc | 100 |
| "uusin", "juuri julkaistu" | release_date.desc | 100 |

---

## data/keywords.json

Ainoa autoritatiivinen lähde TMDB-keyword-ID:ille.
**Jokainen ID on verifioitu oikeasta TMDB-datasta** — ei arvailua.

```
concept_to_tmdb:  käsite → [{id, name}]  (TMDB ID:t)
fi_to_concept:    suomi → käsite         (kielitulkinta)
_unverified:      käsitteet jotka EI ole TMDB-keywordeja
```

Päivitys: `get_keywords(id)` uusilla teoksilla → lisää tähän.

---

## Keyword-resoluutio (nodes.py: _resolve_keywords)

```
keyword-nimi
    │
    ├─ data/keywords.json:ssa? → käytä verifioitua ID:tä
    │
    ├─ keyword_cache:ssa (muistissa)? → käytä cachea
    │
    └─ hae TMDB:n /search/keyword → tallenna cacheen → käytä
```

---

## Testisarja (tests/test_prompt.py)

Testataan oikeilla käyttötapauksilla — nämä eivät saa olla promptissa esimerkkeinä.
Kutsutaan oikeaa Gemini-APIa (ei mockia).
Epäonnistunut testi = promptia pitää parantaa, ei koodia.

| Kategoria | Testattavat kyselyt |
|---|---|
| Anime-tunnistus | "Japanilainen kauhusarja", "shonen-anime", "isekai-sarjat", "mangaan pohjaava" |
| similar_to | "kuten Kaifuku Jutsushi", "Attack on Titan oli hyvä", "Made in Abyss tyylinen" |
| Aikavälit | "2000-luvulla", "2010-luvulta tähän päivään", "90-luvun kauhu" |
| airing_now | "tässä seasonissa romanttisia animeita", "tällä hetkellä menossa" |
| both_types | "Cyberpunk-elokuvat ja -sarjat", "scifi elokuvina ja sarjoina" |
| Kieli | "Korealaista romantiikkaa", "Ranskalaisella tehty draama", "Bollywood-musikaali" |
| Suomislangi | "cyberpunk wibaiset elokuvat", "tummat noir wibaiset trillerit" |

Ajo: `uv run pytest tests/ -v`
Vapaa-tason rajoitus: 20 pyyntöä/päivä → aja testeissä pieni erä kerrallaan.
