# MCP-TMDB

> "Mitäs tänään katsottaisiin?"

MCP-palvelin joka yhdistää Claude-chattiälyn TMDB:n elokuva- ja sarjadataan.
Voit kirjoittaa luonnollisella kielellä — palvelin ymmärtää mitä haet ja hakee oikean datan.

---

## Mitä tämä osaa

### Luonnollinen kielenhaku (`smart_search`)

Kirjoita mitä tahansa, palvelin tulkitsee:

```
"Tom Hanksin näyttelemät sotaelokuvat"
"samanlaisia sarjoja kuin Downton Abbey, saatavilla Yle Areenassa tai Amazon Primessä"
"parhaat vakavat Gundam-sarjat"
"tummia psykologisia trillereitä 2010-luvulta"
"mitä anime-sarjoja trendaa nyt"
"Nolan-elokuvat parhaimmasta huonoimpaan"
```

Smart search tunnistaa automaattisesti:
- Haetaanko elokuvia vai sarjoja
- Onko kyseessä suositus, haku, henkilö vai franchise
- Mikä suoratoistopalvelu on kiinnostava
- Millä kielellä teokset ovat (anime → japani, k-drama → korea jne.)

### Suodatushaku (`discover`)

Filtteröi genren, vuoden, arvosanan, kielen, suoratoistopalvelun tai näyttelijän mukaan.
Useita palveluja tuettu: "Netflixistä tai Disney Plussilta".

### Samankaltaisuushaku (`similar_to`)

Anna referenssiteos, saat temaattisesti samankaltaisia tuloksia.
Hakee sekä TMDB:n suositukset että keyword-pohjaisen discover-haun rinnakkain.
Gemini rerankaa tulokset — ei pelkkää suosiojärjestystä.

### Franchise-haku

Hae kaikki sarjat tai elokuvat tietystä franchisesta:
```
"kaikki Turtles-sarjat"
"parhaat Star Wars -elokuvat"
```

### Elokuvan tiedot + jatko-osat (`get_details`)

Hae elokuvan tiedot TMDB-id:llä. Jos elokuva kuuluu kokoelmaan
(esim. Blade Runner, Star Wars), näytetään automaattisesti kaikki osat.

### Muut työkalut

| Työkalu | Kuvaus |
|---------|--------|
| `search_by_title` | Nimihaku elokuville tai sarjoille |
| `search_person` | Henkilöhaku näyttelijälle tai ohjaajalle |
| `get_person` | Henkilön tiedot ja tärkeimmät roolit |
| `get_recommendations` | TMDB:n suositukset teoksen id:llä |
| `trending` | Trendaavat elokuvat/sarjat juuri nyt |
| `list_genres` | Kaikki käytettävissä olevat genret |
| `list_watch_providers` | Suoratoistopalvelut Suomessa |

---

## Asennus

### 1. Kloonaa ja asenna riippuvuudet

```bash
git clone https://github.com/sinun-käyttäjänimi/MCP-tmdb.git
cd MCP-tmdb
uv sync
```

### 2. Luo `.env`-tiedosto

```bash
cp .env.example .env   # tai luo käsin
```

Lisää avaimet:

```
TMDB_API_KEY_V3=sinun_tmdb_api_avain
GEMINI_API_KEY=sinun_gemini_api_avain
```

- **TMDB API -avain:** [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) — rekisteröidy ja pyydä v3-avain
- **Gemini API -avain:** [aistudio.google.com](https://aistudio.google.com) — tarvitaan `smart_search`-toimintoon

### 3. Luo `.mcp.json` Claude Codea varten

```bash
cp .mcp.json.example .mcp.json
```

Muokkaa `.mcp.json`:iin oikea polku:

```json
{
  "mcpServers": {
    "tmdb": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "/absoluuttinen/polku/MCP-tmdb"
    }
  }
}
```

### 4. Testaa

```bash
uv run python server.py
```

Palvelimen pitäisi käynnistyä ja ladata genret, suoratoistopalvelut ja keyword-cache muistiin.

---

## Käyttö Claude Codessa

Kun `.mcp.json` on paikallaan, käynnistä Claude Code projektin kansiossa.
Palvelin yhdistyy automaattisesti. Voit testata:

```
/mcp
```

Jonka jälkeen voit käyttää suoraan:

```
Hae minulle Tom Hanksin parhaat elokuvat
Mitä sarjoja on trendannut tällä viikolla?
Samanlaisia kuin Breaking Bad
```

---

## Tekninen dokumentaatio

- **`FLOWS.md`** — Arkkitehtuuri, kutsuketjut ja smart_search-polut selitettynä. Hyvä luettavaksi jos haluat ymmärtää miten järjestelmä toimii sisältä.
- **`CLAUDE.md`** — Ohjeet Claude Codelle projektin kehittämiseen.
- **`VISION.md`** — Alkuperäinen visio ja suunnitteluperiaatteet.

---

## Stack

- **Python 3.12+** + `uv` pakettienhallintaan
- **FastMCP** (Anthropicin virallinen MCP SDK)
- **httpx** — async HTTP-kutsut TMDB:lle
- **Gemini 2.5 Flash Lite** — kyselyn tulkinta ja tulosten rerankaus
- **TMDB API v3** — elokuva- ja sarjadata

---

## Rajoitukset

- Suoratoistopalvelut ja ikärajat Suomen mukaan (region=FI)
- Vastaukset suomeksi (TMDB palauttaa suomenkieliset kuvaukset kun saatavilla)
- Smart search vaatii Gemini API -avaimen
- TMDB:n henkilöprofiilit ovat joskus epätäydellisiä (roolit voivat puuttua)
