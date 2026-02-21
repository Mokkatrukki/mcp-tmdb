# MCP-TMDB — Kutsuketjut

Tässä tiedostossa kuvataan miten eri kyselyt kulkevat järjestelmän läpi.
Tasot kasvavat ylhäältä alas — yksinkertaisesta monimutkaiseen.

---

## Taso 0 — Käynnistys (startup-muisti)

Palvelin hakee kerran käynnistyksen yhteydessä datan jota kaikki muut kutsut tarvitsevat.

```
MCP Server                         TMDB API
    |                                  |
    |-- GET /genre/movie/list -------->|
    |<-- elokuvagenret (id + nimi) ----|
    |                                  |
    |-- GET /genre/tv/list ----------->|
    |<-- sarjagenret (id + nimi) ------|
    |                                  |
    |-- GET /configuration/countries ->|
    |<-- ikärajat (FI oletuksena) -----|
    |                                  |
  [muisti ladattu, palvelin valmis]
```

---

## Taso 1 — Suorat työkalut (v1)

Yksinkertaiset haut ilman LLM-tulkintaa. Yksi kysymys, yksi TMDB-kutsu, yksi vastaus.

### search_by_title

```
Käyttäjä / LLM       MCP Server              TMDB API
      |                   |                      |
      |-- search_by_title("Blade Runner") ------->|
      |                   |-- GET /search/movie ->|
      |                   |<-- lista osumista ----|
      |<-- muotoiltu lista tuloksista ------------|
      |                   |                      |
```

### get_details

```
Käyttäjä / LLM       MCP Server              TMDB API
      |                   |                      |
      |-- get_details(id=78, type="movie") ------>|
      |                   |-- GET /movie/78 ----->|
      |                   |<-- täydet tiedot -----|
      |<-- muotoiltu tietolevy -------------------|
      |                   |                      |
```

### list_genres

```
Käyttäjä / LLM       MCP Server
      |                   |
      |-- list_genres(type="movie") -->|
      |      [ei TMDB-kutsua,          |
      |       data on jo muistissa]    |
      |<-- genrelista (id + nimi) -----|
      |                   |
```

---

## Taso 2 — smart_search

Luonnollinen kieli → Gemini tulkitsee intent → route → TMDB.
Lähes kaikki "lista"-haut päätyvät **discover**-terminaaliin.

---

### Päärakenne

```
┌─────────────────────────────────┐
│      smart_search(query)        │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│         Gemini Flash            │
│  intent + parametrit (JSON)     │
└──────┬──────────────────┬───────┘
       │ confidence=high  │ confidence=low
       ▼                  ▼
┌─────────────┐    ┌──────────────────────┐
│   Router    │    │  low_confidence      │
│  (ks. alla) │    │  + suggested_prompts │
└─────────────┘    └──────────────────────┘
```

---

### Reitti 1: Discover (tavoite ~80% kyselyistä)

Terminaali: `discover()`

```
┌────────────────────────────────┐
│  "Löydä 90-luvun noir-         │
│   trillereita"                 │
└──────────────┬─────────────────┘
               │
               ▼
┌────────────────────────────────┐
│  Gemini                        │
│  genres: [trilleri]            │
│  keywords: [noir]  ← resolv.   │
│  year: 1990–1999               │
│  type: movie                   │
└──────────────┬─────────────────┘
               │ keywords tarvitsee ID:t
               ▼
┌────────────────────────────────┐   ┌─────────────────┐
│  /search/keyword?query=noir    │──▶│  keyword_id: 42 │
└────────────────────────────────┘   └────────┬────────┘
                                              │
               ┌──────────────────────────────┘
               ▼
┌────────────────────────────────┐
│  discover(                     │
│    genres=[trilleri],          │
│    with_keywords=[42],         │
│    year=1990–1999              │
│  )                             │
└──────────────┬─────────────────┘
               │
               ▼
         [tuloslista]
```

Huom: keywords ovat TMDB:ssä ID-pohjaisia, joten ne pitää resolvoida
ennen discoveria. Genret ovat jo muistissa (startup-muisti).

---

### Reitti 2: Discover + henkilö (esim. "Tom Hanksin musikaalit")

Terminaali: `discover()` — mutta vaatii ensin henkilön resolvoinnin.

```
┌────────────────────────────────┐
│  "Tom Hanksin musikaalit"      │
└──────────────┬─────────────────┘
               │
               ▼
┌────────────────────────────────┐
│  Gemini                        │
│  intent: discover              │
│  person: "Tom Hanks"  ← resolv.│
│  genres: [musiikki]            │
│  type: movie                   │
└──────┬────────────────┬────────┘
       │                │
       ▼                ▼
┌─────────────┐  ┌─────────────────┐
│ search_     │  │ /search/keyword │
│ person(     │  │ (jos tarvitaan) │
│ "Tom Hanks")│  └────────┬────────┘
└──────┬──────┘           │
       │ person_id: 31    │
       └────────┬─────────┘
                ▼
┌────────────────────────────────┐
│  discover(                     │
│    with_cast=31,               │
│    genres=[musiikki]           │
│  )                             │
└──────────────┬─────────────────┘
               │
               ▼
         [tuloslista]
```

---

### Low confidence

```
┌────────────────────────────────┐
│  "jotain ihan siistiä"         │
└──────────────┬─────────────────┘
               │
               ▼
┌────────────────────────────────┐
│  Gemini: confidence=low        │
└──────────────┬─────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────┐
│  {                                                 │
│    success: false,                                 │
│    reason: "low_confidence",                       │
│    suggested_prompts: [                            │
│      "Etsi toimintaelokuvia 90-luvulta",           │
│      "Kerro elokuvasta Inception",                 │
│      "Kuka on Christopher Nolan?",                 │
│      "Suosittele jotain kuten Interstellar",        │
│      "Mitä sarjoja trendaa nyt?"                   │
│    ]                                               │
│  }                                                 │
└────────────────────────────────────────────────────┘
```

Claude voi tarttua listaan ja ohjata keskustelun eteenpäin.

---

### Muut reitit (toteutetaan myöhemmin)

```
lookup          → search_by_title → get_details
person          → search_person → get_person
recommendations → search_by_title → get_recommendations
trending        → trending
```

---

### Huomioita

- `min_rating` vain jos käyttäjä eksplisiittisesti pyytää ("parhaiten arvosteltuja")
- `type` (movie/tv) päätellään kontekstista, default: movie
- Gemini palauttaa aina validia JSONia (response_schema)
- Loki: `{query, intent, params, result_count, confidence}` → search.log.jsonl

---

## Tulossa — Taso 3 (monivaiheinen agenttihaku)

Useita kierroksia kun yksi kutsu ei riitä.
Esim. "Harrison Fordin elokuvat joissa hän oli pahis."

*(dokumentoidaan kun toteutetaan)*
