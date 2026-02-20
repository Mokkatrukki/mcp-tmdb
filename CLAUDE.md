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

**Tehty (Taso 1 valmis):**
- Projektirakenne pystytetty (`pyproject.toml`, `.env`, `.mcp.json`)
- `server.py` — FastMCP + lifespan-käynnistys
- Startup-muisti: genret (FI) ja sertifikaatit (FI) ladataan käynnistyksessä
- Työkalut: `list_genres`, `list_certifications`, `search_by_title`, `get_details`
- Git-repo pystytetty, remote GitHubissa (mokkatrukki/mcp-tmdb)

**Seuraavaksi (Taso 2):**
- Suodatushaut: genre, vuosi, arvosana (discover-endpoint)
- Henkilöhaku: ohjaaja, näyttelijä
- Suositukset: "samanlaisia kuin X"

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
