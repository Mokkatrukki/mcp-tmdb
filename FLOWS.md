# MCP-TMDB — Miten tämä toimii

> Iso idea: käyttäjä kirjoittaa luonnollista kieltä.
> Järjestelmä ajattelee. TMDB hakee. Vastaus tulee takaisin.
> Yksinkertainen. Mutta alla on kerroksia.

---

## Tiedostorakenne

```
server.py          ← MCP-palvelin + kaikki työkalut + smart_search-reititys
search/
  memory.py        ← käynnistysmuisti (genret, palvelut, keyword-cache)
  prompts.py       ← classify_query() + rerank_candidates() + Pydantic-mallit
data/
  keywords.json    ← TMDB keyword-id:t, verifioitu manuaalisesti
```

---

## Kaksi maailmaa: suorat työkalut ja älykäs haku

```
┌─────────────────────────────────────────────────────────┐
│                    MCP-työkalut                         │
│                                                         │
│  SUORAT — ohut kuori TMDB:n päälle, ei ajattelua       │
│  ┌──────────────────┬──────────────────────────────┐   │
│  │ search_by_title  │ nimihaku (elokuva / sarja)   │   │
│  │ search_multi     │ nimihaku kaikki tyypit        │   │
│  │ search_person    │ henkilöhaku                  │   │
│  │ get_details      │ tiedot TMDB-id:llä           │   │
│  │ get_person       │ henkilö + roolit             │   │
│  │ get_keywords     │ teoksen keywordit            │   │
│  │ get_recommendations │ TMDB:n suositukset       │   │
│  │ trending         │ trendaavat nyt               │   │
│  │ discover         │ suodatushaku                 │   │
│  │ list_genres      │ genret muistista (FI)        │   │
│  │ list_certifications │ ikärajat (FI)            │   │
│  │ list_watch_providers │ suoratoistopalvelut     │   │
│  └──────────────────┴──────────────────────────────┘   │
│                                                         │
│  ÄLYKÄS — ainoa työkalu joka ajattelee                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │              smart_search(query)                 │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## smart_search — kokonaiskuva

```
käyttäjä kirjoittaa kyselyn
         │
         ▼
  ┌─────────────────────────────────────┐
  │         classify_query()            │
  │                                     │
  │  Gemini lukee:                      │
  │  · kyselyn                          │
  │  · kaikki käytettävissä olevat      │
  │    genret (FI)                      │
  │  · suoratoistopalvelut (FI)         │
  │  · tämän päivän päivämäärä          │
  │                                     │
  │  Palauttaa: SmartSearchIntent       │
  └──────────────┬──────────────────────┘
                 │
         intent? │
         ┌───────┴────────┐
         │                │
    ─────┼─────────────────┼──────────────────────
    trending  person  lookup  discover  similar_to
         │        │       │        │         │
      trending() │  search_ discover()  _similar_to()
                 │  by_title()         (ks. alla)
            search_
            person()
```

---

## classify_query() — mitä promptissa lukee

Gemini saa noin 130 riviä ohjeita. Tässä tiivistelmä:

### Intent — mistä Gemini tunnistaa tarkoituksen

```
INTENT          TUNNISTAA TÄSTÄ
─────────────────────────────────────────────────────
discover      · tyylin/tunnelman kuvailu ilman nimeä
              · genreviittaus ("suomalainen draama")
              · aikaväli, kieliviittaus

similar_to    · teos mainitaan VERTAILUNA, ei kohteena
              · "kuten X", "X tyylinen", "enemmän kuin X"
              · → asettaa reference_title

lookup        · yksi nimetty teos, "kerro", "mikä on"

person        · henkilönimi, "kuka on"

trending      · "trendaa", "mitä katsotaan nyt"
```

### Kieli — automaattinen päättely

```
"anime" missä tahansa muodossa  →  language="ja" + genres=["Animaatio"]
"isekai"                        →  language="ja" + keywords=["isekai", "parallel world"]
"k-drama", "korealainen"        →  language="ko"
"bollywood", "intialainen"      →  language="hi"
```

### Tyylit → keywords (TMDB-englanniksi)

```
"synkkä", "dark"       →  "dark fantasy"
"kosto"                →  "revenge"
"gore", "brutaali"     →  "gore"
"psykologinen"         →  "psychological"
"aikamatka"            →  "time travel"
"cyberpunk"            →  "cyberpunk"
"dystopia"             →  "dystopia"
```

### Laatu ja järjestys

```
"paras", "klassikko"   →  sort_by=vote_average.desc, min_votes=500
"uusin"                →  sort_by=release_date.desc
"trendaa"              →  sort_by=popularity.desc
```

---

## _similar_to() — kolmivaiheinen prosessi

Tässä tapahtuu eniten. Referenssiteos toimii ankkurina.

```
VAIHE 1 — Hae referenssiteos
─────────────────────────────
käyttäjä: "samanlaisia kuin Redo of Healer, gore, synkkä"
                │
                ▼
     search/tv?query="Redo of Healer"
                │
                ▼
     ref_id=99071, ref_lang="ja", ref_genre_ids=[16,...]
     ref_overview="Parantajan poika..."


VAIHE 2 — Rinnakkain (asyncio.gather)
──────────────────────────────────────

   ┌──────────────────────┐    ┌──────────────────────────────────┐
   │  /tv/99071/          │    │  _fetch_keyword_discover()       │
   │  recommendations     │    │                                  │
   │                      │    │  1. /tv/99071/keywords           │
   │  TMDB:n oma lista    │    │     → [rape, revenge, gore,      │
   │  "muut käyttäjät     │    │        mutilation, dark fantasy, │
   │   katsoi myös..."    │    │        seinen, ...]              │
   │                      │    │                                  │
   │  ~20 tulosta         │    │  2. Suodatetaan generiset pois   │
   │                      │    │     (anime, based on manga,      │
   │                      │    │      magic, romance, adventure)  │
   │                      │    │                                  │
   │                      │    │  3. User-keywordit ensin +       │
   │                      │    │     ref-keywordit → OR-lista     │
   │                      │    │                                  │
   │                      │    │  4. /discover/tv                 │
   │                      │    │     ?with_keywords=570|9748|...  │
   │                      │    │     &with_original_language=ja   │
   │                      │    │     &include_adult=true          │
   │                      │    │                                  │
   │                      │    │  ~20 tulosta                     │
   └──────────────────────┘    └──────────────────────────────────┘
            │                               │
            └───────────────┬───────────────┘
                            │
                   disc + recs yhdistetään
                   duplikaatit poistetaan
                   ~30 kandidaattia


VAIHE 3 — LLM rerankaus (Gemini kutsu #2)
───────────────────────────────────────────

  Geminille annetaan:

  ┌──────────────────────────────────────────────────────┐
  │  Referenssiteos: "回復術士のやり直し"                │
  │  Kuvaus: "Parantaja joka käytetään hyväksi..."       │
  │  Teemat: revenge, gore, mutilation, dark fantasy...  │
  │  Käyttäjä painottaa: gore, dark fantasy              │
  │                                                      │
  │  Kandidaatit:                                        │
  │  [35935] Berserk (1997) - 8.5/10 - Dark warrior...  │
  │  [82591] Goblin Slayer (2018) - 8.0/10 - ...        │
  │  [37854] One Piece (1999) - 8.7/10 - Merirosvot...  │
  │  [97923] Sleepy Princess (2020) - 8.4/10 - ...      │
  │  ... (max 30)                                        │
  └──────────────────────────────────────────────────────┘
                         │
                         ▼
              Gemini palauttaa: [35935, 82591, ...]
              (ID:t parhaimmasta huonoimpaan)
                         │
                         ▼
              Järjestetään kandidaatit → top 12
              Palautetaan käyttäjälle
```

### Miksi rerankaus on turvallista (eikä hallusinoi)

```
✓ TURVALLINEN:  Gemini valitsee TMDB:stä haettujen joukosta
                → ei voi keksiä sarjoja joita ei ole
                → vain järjestää ja suodattaa olemassaolevaa

✗ VAARALLINEN:  "Keksi 10 moottoripyöräanimen nimeä"
                → LLM voisi keksiä sarjoja joita ei ole
                → tai sekoittaa nimiä / vuosilukuja
                → tätä EI käytetä
```

---

## Discover-polku

Yksinkertaisempi kuin similar_to — yksi API-kutsu:

```
intent.keywords  →  keyword-ID:t cachesta / TMDB-hausta
intent.genres    →  genre-ID:t muistista (FI-nimet → ID:t)
intent.language  →  with_original_language
intent.min_votes →  vote_count.gte
                         │
                         ▼
              /discover/movie   tai   /discover/tv
                         │
                         ▼
                    tulokset suoraan
```

Erityistapaukset:
- `both_types=true` → kaksi discover-kutsua rinnakkain (movie + tv), yhdistetään
- `airing_now=true` → lasketaan automaattisesti season-aikaväli → `first_air_date.gte/lte`

---

## Startup-muisti (memory.py)

Kerätään kerran kun palvelin käynnistyy. Pysyy muistissa.

```
käynnistys
    │
    ├── /genre/movie/list?language=fi   →  movie_genres  (19 genreä)
    ├── /genre/tv/list?language=fi      →  tv_genres     (16 genreä)
    ├── /certification/movie/list       →  movie_certs   (FI ikärajat)
    ├── /certification/tv/list          →  tv_certs      (FI ikärajat)
    └── /watch/providers/movie?region=FI →  providers    (62 palvelua)

    + keyword_cache = {}   ← täyttyy ajonaikaisesti
```

keyword_cache toimii näin:
```
1. käyttäjä pyytää "gore"-keywordiä
2. cache tyhjä → haetaan /search/keyword?query=gore → id=10292
3. tallennetaan: cache["gore"] = "10292"
4. seuraava pyyntö: cache["gore"] löytyy → ei API-kutsua
```

get_keywords täyttää cachen sivutuotteena — kun haet teoksen keywordit,
ne kaikki lisätään cacheen automaattisesti.

---

## Tunnetut rajoitukset

```
ONGELMA                          SYY                    RATKAISU
───────────────────────────────────────────────────────────────────
"anime jossa moottoripyöriä"   TMDB tägää harvoin      ei ratkaisua
→ 4 tulosta, Akira puuttuu     ajoneuvoja keywords-     tällä hetkellä
                                kentässä

Discover palauttaa suosittuja  keyword OR-logiikka      rerank auttaa
animeita geneeristen tagia     osuu laajasti            osittain
kanssa (AoT on "gore")

Recommendations = ei sisältö-  TMDB käyttää metadata-  rerank korjaa
pohjainen vaan metadata         ei katsojakokemusta
```

---

## Tänään rakennettu (2025-02-22)

```
ENNEN                          JÄLKEEN
──────────────────────────────────────────────────────────
include_adult=False            include_adult=True
                               → adult-anime löytyy

discover: kaikki genre-id:t   discover: vain primary genre
OR-listana                     → vähemmän kohinaa

keywords: ei käytetty          keywords: user_kw + ref_kw
similar_to-haussa              OR-logiikalla → parempi

recs ensin → sort vote_avg     disc ensin (temaattinen) →
→ One Piece #1                 recs täydentää → ei re-sort

ei rerankkausta                Gemini kutsu #2 rerankaa
→ suosituimmat voittaa         30 kandidaatista → top 12
                               → temaattisesti osuvat ensin
```

---

*Luettu ennen nukkumaanmenoa. Huomenna lisää.*
