# MCP-TMDB — Claude Code ohjeet

## Projekti lyhyesti

MCP-palvelin joka yhdistää chattiälyn TMDB:n elokuva- ja sarjadataan.
Tavoite: "älykäs kaveri joka tuntee elokuvat" — luonnollisella kielellä haettavissa.

Lue tarkempi visio: `VISION.md`
API-kartta: `TMDB_API.md`
Kutsuketjut: `FLOWS.md`

## Tekninen stack

- **Python** + `uv` pakettienhallintaan
- **mcp[cli]** — Anthropicin virallinen MCP SDK (FastMCP)
- **httpx** — async HTTP-kutsut TMDB:lle
- **python-dotenv** — ympäristömuuttujat

## Projektirakenne

```
server.py        ← MCP-palvelimen pääpiste (FastMCP) + kaikki työkalut
search/
  memory.py      ← startup-muisti (genret, palvelut, keyword-cache)
  prompts.py     ← classify_query() + SmartSearchIntent (Gemini)
data/
  keywords.json  ← TMDB keyword-id:t, verifioitu manuaalisesti
pyproject.toml   ← riippuvuudet
.env             ← TMDB_API_KEY (ei versionhallintaan)
.mcp.json        ← Claude Code MCP -yhteys
```

## TMDB-autentikaatio

`.env`:ssä on molemmat avaimet. Käytetään **v3 API:a** koska dokumentaatio on sen puolella.

```
TMDB_API_KEY_V3=lyhyt_avain    ← käytetään tähän
TMDB_API_KEY=jwt_token         ← varaksi tallessa
```

V3-kutsuissa avain menee query-parametrina:
```python
params = {"api_key": TMDB_API_KEY_V3, ...}
```

## Missä ollaan nyt

**Tehty:**
- 12 MCP-työkalua (`server.py`)
- `smart_search` — Gemini tulkitsee kyselyn → if/elif-reititys oikeaan funktioon
- `_similar_to` — rinnakkain recommendations + discover → yhdistä + lajittele

**Työkalut:**
- `search_by_title` — nimihaku (elokuva/sarja)
- `search_multi` — nimihaku kaikki tyypit kerralla
- `search_person` — henkilöhaku
- `get_details` — elokuvan/sarjan tiedot
- `get_person` — henkilön tiedot + roolit (append_to_response)
- `discover` — suodatushaku: genre (FI-nimet), keywords, vuosi, arvosana, kesto, kieli, watch_provider
- `get_recommendations` — suositukset id:n perusteella
- `get_keywords` — teoksen keywordit id:llä (lisää cacheen samalla)
- `trending` — trendaavat (movie/tv/all, day/week)
- `list_genres` — genret (FI)
- `list_certifications` — ikärajat (FI)
- `list_watch_providers` — suoratoistopalvelut (FI)
- `smart_search` — Gemini-pohjainen älykäs haku (ei LangGraph)

**smart_search -polut:**
- `discover` / `both_types` — suodatushaku (myös movie+tv rinnakkain)
- `similar_to` — 3-vaiheinen: (1) hae referenssiteos, (2) rinnakkain recommendations + ref-keywordit → discover, (3) Gemini rerankaa top 12
- `lookup` / `person` / `trending` — delegointi suoraan MCP-funktiolle
- `airing_now` — season-rajat lasketaan automaattisesti

**similar_to — keskeiset yksityiskohdat:**
- `include_adult=True` — adult-sisältö mukaan (tärkeä esim. seinen-anime)
- ref-keywordit haetaan TMDB:stä, generiset suodatetaan (_SKIP_KW)
- user-keywordit + ref-keywordit yhdistetään OR-discover-kutsuun
- Gemini (kutsu #2) valitsee 30 kandidaatista temaattisesti sopivimmat
- Hallusinointiriski minimoitu: Gemini valitsee vain TMDB-haettujen joukosta

Dokumentaatio: `FLOWS.md`

## Komennot

```bash
uv sync              # asenna riippuvuudet
uv run python server.py   # käynnistä palvelin
```

## Periaatteet

- Yksinkertainen ensin — ei ylisuunnitella
- Jokainen taso testataan ennen seuraavaa
- LLM:lle annetaan vain se tieto mitä se tarvitsee
- Hallusinoinnin välttäminen on keskeinen arvo

## Git

- Commit-viesteissä ei mainita Claudea, Claude Codea tai Anthropicia
- Ei `Co-Authored-By: Claude` -rivejä
