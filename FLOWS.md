# Miten MCP-TMDB toimii

Iso kuva: käyttäjä kirjoittaa luonnollista kieltä → LLM tulkitsee → TMDB hakee → teksti takaisin.

---

## Tiedostot

```
server.py         ← kaikki MCP-työkalut + smart_search-logiikka
search/
  memory.py       ← startup-muisti (genret, palvelut, keyword-cache)
  prompts.py      ← classify_query() + SmartSearchIntent
data/
  keywords.json   ← TMDB keyword-id:t, verifioitu manuaalisesti
```

---

## Suorat työkalut

Nämä eivät ajattele — ne ovat ohut kuori TMDB:n REST API:n päälle.
Yksi kutsu sisään, yksi vastaus ulos.

| Työkalu | Tekee |
|---|---|
| `search_by_title` | nimihaku |
| `search_multi` | nimihaku kaikki tyypit kerralla |
| `search_person` | henkilöhaku |
| `get_details` | tiedot TMDB-id:llä |
| `get_person` | henkilön tiedot + roolit |
| `get_recommendations` | TMDB:n suositukset id:llä |
| `get_keywords` | teoksen keywordit id:llä |
| `trending` | trendaavat (movie/tv/all, day/week) |
| `discover` | suodatushaku (genre, vuosi, kieli, arvosana, palvelu) |
| `list_genres` | genret muistista (FI) |
| `list_certifications` | ikärajat muistista (FI) |
| `list_watch_providers` | suoratoistopalvelut muistista (FI) |

---

## smart_search

Ainoa työkalu joka "ajattelee". Yksi Gemini-kutsu tulkitsee kyselyn, sitten reititys.

```
käyttäjä kirjoittaa
       ↓
 classify_query()   ←── Gemini lukee kyselyn + genret + palvelut
       ↓
  intent?
   ├─ trending    →  trending()
   ├─ person      →  search_person()
   ├─ lookup      →  search_by_title()
   ├─ similar_to  →  _similar_to()
   └─ discover    →  discover()
```

### similar_to — miten toimii nyt

```
1. Hae referenssiteos nimellä → saa id, kielen, genre-id:t

2. Hae rinnakkain:
   ├─ /tv/{id}/recommendations   (TMDB:n oma lista)
   └─ /discover/tv               (sama kieli + genret, paras arvosana)

3. Yhdistä listat, poista duplikaatit
   Lajittele vote_average mukaan → top 15
```

### similar_to — missä on tilaa parantaa

TMDB:n recommendations on **metadata-pohjainen**, ei sisältöpohjainen.
"Kuten Redo of Healer, gore, K18" → palauttaa geneerisiä animeita,
koska TMDB ei tiedä mikä on gore ja mikä ei.

💡 **Idea: LLM valitsee kandidaateista**
Anna LLM:lle lista 30+ kandidaatista + käyttäjän teemat.
LLM tietää mitä "gore" tai "ahdistava" tarkoittaa, TMDB ei.
```python
candidates = recs + disc  # ~40 teosta datoineen
return await llm_pick(query, themes, candidates)  # Gemini call #2
```

💡 **Idea: hae enemmän dataa per kandidaatti**
Nyt palautetaan vain discover-data (genre, arvosana, kuvaus).
get_details antaisi myös keywordit, tuotantomaat, kaudet — LLM voisi
valita paremmin. Pitäisi tehdä rinnakkain (asyncio.gather).

---

## Startup-muisti

Haetaan kerran palvelimen käynnistyessä, pidetään muistissa koko ajan:

- **Genret** (FI) — elokuvat + sarjat → discover voi ottaa suomenkielisiä nimiä
- **Ikärajat** (FI) — list_certifications-työkalu
- **Suoratoistopalvelut** (FI) — discover-filtteri
- **keyword_cache** — täyttyy ajonaikaisesti discover-kutsujen myötä
