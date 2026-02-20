# TMDB MCP Server — Visio

> "Mitäs tänään katsottaisiin?"

Tämä projekti on MCP-palvelin joka yhdistää chattiälyn elokuvien ja sarjojen maailmaan. Tavoite ei ole rakentaa hakukonetta vaan **älykäs kaveri joka tuntee elokuvat** — sellainen jolle voi sanoa "haluaisin jotain raskasta ja surullista, mutta ei liian pitkää" ja saada oikeasti hyödyllinen vastaus.

---

## Henki

Pidämme asiat yksinkertaisina mutta teemme ne kunnolla. Jokainen palikka hierotaan toimivaksi ennen seuraavaa. Ei ylisuunnitella, ei rakenneta tulevaisuutta varten — rakennetaan tämä hyvin.

Tämä on myös oppimisprojekti: MCP:n toimintalogiikka, LLM-kutsujen rakentaminen, TMDB:n API:n syvempi ymmärtäminen. Kaikki nämä ovat tavoitteita itsessään.

---

## Arkkitehtuuri

```
Käyttäjä / Chattiäly
       │
       ▼
   MCP Server  (yksi palvelin, kaksi työkalukerrosta)
   ┌──────────────────────────────────────────┐
   │                                          │
   │  [Suorat työkalut]   [Älykäs haku]       │
   │  - hae nimellä       - smart_search      │
   │  - hae id:llä        - suositukset       │
   │  - lista genreistä                       │
   │                                          │
   │  Startup-muisti:                         │
   │  genret, sertifikaatit, top-keywords     │
   └──────────────────────────────────────────┘
          │                    │
          ▼                    ▼
      TMDB API            LLM-tulkinta
      (httpx)             (query → parametrit)
          │
          ▼
      Web UI (FastAPI + HTMX)
```

### Älykäs haku — ydin

Monimutkainen kysely kulkee näin:

```
"raaka noitaelokuva"
       │
       ▼
  LLM saa kontekstina:
  - käytettävissä olevat genret
  - käytettävissä olevat top-keywords
  - discover-endpointin parametrit
       │
       ▼
  LLM tuottaa strukturoidun haun:
  { genres: [27, 14], keywords: ["witch", "witchcraft"],
    vote_average_gte: 6.0, sort_by: "vote_average.desc" }
       │
       ▼
  Yksi TMDB Discover -kutsu
       │
       ▼
  LLM karsii ja muotoilee tulokset
  → tekstityyppinen vastaus chatille
```

Ei iteratiivisia silmukoita. Yksi tulkintakutsu, yksi hakukutsu, yksi vastaus.

---

## Tekniset valinnat

| Asia | Valinta | Miksi |
|------|---------|-------|
| TMDB-kutsu | `httpx` (async) | Täysi kontrolli, nähdään mitä tapahtuu |
| MCP SDK | `mcp` (Anthropic Python) | Virallinen, hyvin dokumentoitu |
| Web framework | FastAPI | Async-valmis, sopii samaan prosessiin |
| UI | HTMX + server-rendered | Yksinkertainen, kasvaa tarpeen mukaan |
| LLM-kutsu | Suora API-kutsu | Pidetään ketju näkyvänä, ei mustia laatikoita |

---

## Startup-muisti

Kun palvelin käynnistyy, se hakee kerran TMDB:ltä:

- **Elokuvagenret** — virallinen lista id+nimi
- **Sarjagenret** — oma lista, eri kuin elokuvat
- **Ikärajat** — Suomi oletuksena, configista vaihdettavissa
- **Top-keywords** — yleisimmät käytössä olevat, ei kaikkia tuhansia

Tämä data toimii LLM:n "sanastona" — se tietää mitä on tarjolla ennen kuin yrittää muuntaa kyselyn parametreiksi.

---

## MCP-työkalut (alustava lista)

### Suorat (v1)
- `search_by_title(query, type)` — nopea tekstihaku
- `get_details(id, type)` — yksityiskohdat id:llä
- `list_genres(type)` — mitä genrejä on käytössä

### Älykäs (v2)
- `smart_search(query)` — luonnollinen kieli → tulokset
- `get_recommendations(id, type)` — "lisää samaa"

---

## Web UI — muistivihko

UI ei ole päätuote vaan **ikkuna palvelimen sisälle**. Aloitetaan pienestä:

- Palvelimen tila (käynnissä, metadata ladattu)
- Lokivirta — mitä kutsuja on tehty
- Viimeisin haku ja sen parametrit
- TMDB-vastaus raakamuodossa

Myöhemmin voi lisätä: hakutulosten kortit, "kuolleet polut" (miksi tulos hylättiin), tokenikulutus, timeline.

---

## Konfiguraatio

```toml
# config.toml
[tmdb]
api_key = "..."
region = "FI"          # ikärajat ja suoratoistopalvelut
language = "fi-FI"     # vastaustekstit

[llm]
provider = "anthropic"
model = "claude-haiku-4-5-20251001"   # nopea ja halpa tulkintaan
```

---

## Rakennusjärjestys

1. **TMDB-yhteys** — httpx-client, startup-muisti, perusparametrit
2. **Suorat MCP-työkalut** — search, details, genres (testattavissa heti)
3. **Discover-endpoint** — parametrit haltuun, testataan käsin
4. **LLM-tulkinta** — prompt joka muuntaa kyselyn discover-parametreiksi
5. **Smart search -työkalu** — yhdistää 3+4
6. **Web UI** — FastAPI + HTMX, aloitetaan statuksesta ja lokeista
7. **Hiominen** — vastausten muotoilu, reunatapaukset, config

---

## Vastauslogiikka — kolme tilaa

MCP ei yritä vastata kaikkeen. Jokaisella kyselyllä on kolme mahdollista ulostuloa:

```
Kysely
  │
  ├─ VASTAUS    → löydettiin tuloksia, muotoiltu teksti chatille
  │
  ├─ TARKENNA   → kysely liian lavea tai epäselvä
  │               "Tarkoitatko elokuvaa vai sarjaa?"
  │               "Haluatko suosituksia vai etsitkö jotain tiettyä?"
  │               → kirjataan logiin: mitä kysyttiin
  │
  └─ EI TUETA   → pyyntö ei kuulu toimialaan
                  "Vertailu ei kuulu toimintoihini."
                  "Tähän minulla ei ole tukea."
                  → kirjataan logiin: mitä pyydettiin
```

### Missä tarkentamispäätös tehdään?

Hybridi: ensin nopea sääntötarkistus, sitten LLM.

```
Kysely
  │
  ├─ Sääntötarkistus (ei LLM-kutsua)
  │   - liian lyhyt tai pelkkää melua?
  │   → TARKENNA heti
  │
  └─ LLM-tulkinta
      - palauttaa discover-parametrit
      - tai { action: "clarify", reason: "..." }
      - tai { action: "unsupported", reason: "..." }
```

Luotetaan LLM:ään järkevissä tapauksissa — sen ei tarvitse olla täydellinen, sen täytyy olla rehellinen.

### Miksi näin?

**Hallusinoinnin välttäminen** on keskeinen arvo. LLM:lle annetaan hyvät lähtötiedot (oikeat genret, oikeat parametrit, oikeaa TMDB-dataa) — ei anneta sen keksiä. Jos data ei riitä, sanotaan se ääneen.

**Lokit ovat kultaa.** Tallentamalla mitä ei tueta ja missä tarvittaisiin tarkennusta, nähdään mihin suuntaan kannattaa kehittää. Käyttäjien oikeat kysymykset kertovat enemmän kuin spekulaatio.

**Token-tehokkuus** on designtavoite, ei jälkiajatus. LLM-kutsuihin mennään vain kun tarvitaan, ja silloinkin prompt on tiivis ja konteksti rajattu — annetaan LLM:lle juuri se tieto mitä se tarvitsee, ei enempää.

---

## Mitä tämä ei ole (vielä)

- Ei käyttäjäkohtaisia suosituksia tai historiaa
- Ei suoratoistopalvelujen saatavuustarkistusta
- Ei iteratiivista agenttia joka etsii useita kertoja
- Ei tukea usealle käyttäjälle samanaikaisesti
