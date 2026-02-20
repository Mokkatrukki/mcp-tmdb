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
server.py        ← MCP-palvelimen pääpiste (FastMCP)
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
- Projektirakenne: `pyproject.toml`, `.env`, `.mcp.json`, GitHub-repo
- Startup-muisti: genret (FI), sertifikaatit (FI), watch providers (FI)
- 11 työkalua käytössä (ks. alla)

**Työkalut:**
- `search_by_title` — nimihaku (elokuva/sarja)
- `search_multi` — nimihaku kaikki tyypit kerralla
- `search_person` — henkilöhaku
- `get_details` — elokuvan/sarjan tiedot
- `get_person` — henkilön tiedot + roolit (append_to_response)
- `discover` — suodatushaku: genre (FI-nimet), keywords, vuosi, arvosana, kesto, kieli, watch_provider
- `get_recommendations` — suositukset id:n perusteella
- `trending` — trendaavat (movie/tv/all, day/week)
- `list_genres` — genret (FI)
- `list_certifications` — ikärajat (FI)
- `list_watch_providers` — suoratoistopalvelut (FI)

**Seuraavaksi (Taso 3):**
- `smart_search` — luonnollinen kieli → discover-parametrit (LLM-tulkinta)

Dokumentaatio: `FLOWS.md`, `TMDB_API.md`

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
