# mcp-tmdb

MCP-palvelin, joka yhdistää chattiälyn TMDB:n elokuva- ja sarjadataan. Luonnollisella kielellä voi hakea elokuvia ja sarjoja, suodattaa genren, kielen tai suoratoistopalvelun mukaan ja tarkastella tekijätietoja.

> "Mitäs tänään katsottaisiin?"

## Asennus

Tarvitset [uv](https://docs.astral.sh/uv/):n ja TMDB API -avaimen (v3).

```bash
git clone https://github.com/mokkatrukki/mcp-tmdb
cd mcp-tmdb
uv sync
```

Luo `.env`:

```
TMDB_API_KEY_V3=avaimesi_tähän
```

## Käyttö

Claude Code tunnistaa palvelimen automaattisesti `.mcp.json`:n kautta. Käynnistys tapahtuu taustalla — ei tarvitse tehdä mitään erikoista.

## Työkalut

### Haku

| Työkalu | Kuvaus |
|---|---|
| `search_by_title(query, type)` | Hae elokuvia tai sarjoja nimellä |
| `search_multi(query)` | Hae elokuvia, sarjoja ja henkilöitä yhdellä haulla |
| `search_person(query)` | Hae henkilöä nimellä (näyttelijä, ohjaaja...) |

### Tiedot

| Työkalu | Kuvaus |
|---|---|
| `get_details(id, type)` | Elokuvan tai sarjan tarkemmat tiedot |
| `get_person(id)` | Henkilön tiedot ja tärkeimmät roolit |

### Suodatushaku

| Työkalu | Kuvaus |
|---|---|
| `discover(...)` | Hae filtterien avulla: genre, avainsanat, vuosi, arvosana, kesto, kieli, suoratoistopalvelu |

### Trendit ja suositukset

| Työkalu | Kuvaus |
|---|---|
| `trending(type, time_window)` | Trendaavat elokuvat, sarjat tai kaikki (day/week) |
| `get_recommendations(id, type)` | Suosituksia elokuvan tai sarjan perusteella |

### Apulistat

| Työkalu | Kuvaus |
|---|---|
| `list_genres(type)` | Käytettävissä olevat genret suomeksi |
| `list_certifications(type)` | Suomen ikärajat |
| `list_watch_providers(type)` | Suomessa saatavilla olevat suoratoistopalvelut |

## Rakennusjärjestys

- [x] Taso 1 — Perushaku: `search_by_title`, `get_details`, `list_genres`
- [x] Taso 2 — Suodatushaku: `discover` (genre, keyword, watch provider...)
- [x] Taso 2 — Henkilöhaku: `search_person`, `get_person`
- [x] Taso 2 — Monihaku: `search_multi`
- [x] Taso 2 — Trendit ja suositukset: `trending`, `get_recommendations`
- [ ] Taso 3 — Älykäs haku: luonnollinen kieli → discover-parametrit (LLM-tulkinta)
- [ ] Taso 4 — Web UI: hakuloki, palvelimen tila

## Stack

Python, [FastMCP](https://github.com/jlowin/fastmcp), httpx, TMDB v3 API
