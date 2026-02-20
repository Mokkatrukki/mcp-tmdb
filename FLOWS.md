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

## Tulossa — Taso 2 (smart_search)

LLM tulkitsee luonnollisen kielen → Discover API -parametrit → tulokset.

*(dokumentoidaan kun toteutetaan)*

---

## Tulossa — Taso 3 (monivaiheinen agenttihaku)

Useita kierroksia kun yksi kutsu ei riitä.
Esim. "Harrison Fordin elokuvat joissa hän oli pahis."

*(dokumentoidaan kun toteutetaan)*
