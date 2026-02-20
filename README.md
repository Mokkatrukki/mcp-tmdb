# mcp-tmdb

MCP-palvelin, joka yhdistää Claude Code -agenttiin TMDB:n elokuva- ja sarjadatan. Luonnollisella kielellä voi hakea elokuvia ja sarjoja, tarkastella tietoja ja vertailla vaihtoehtoja.

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

| Työkalu | Kuvaus |
|---|---|
| `search_by_title` | Hae elokuvia tai sarjoja nimellä |
| `get_details` | Tarkemmat tiedot TMDB-id:llä |
| `list_genres` | Genret suomeksi |
| `list_certifications` | Suomen ikärajat |

## Stack

Python, [FastMCP](https://github.com/jlowin/fastmcp), httpx, TMDB v3 API
