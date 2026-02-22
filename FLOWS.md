# MCP-TMDB — Miten tämä toimii

> Iso idea: käyttäjä kirjoittaa luonnollista kieltä.
> Järjestelmä ajattelee. TMDB hakee. Vastaus tulee takaisin.

---

## Tiedostorakenne

```
server.py          ← MCP-palvelin + kaikki työkalut + smart_search-reititys
search/
  memory.py        ← käynnistysmuisti (genret, palvelut, keyword-cache)
  prompts.py       ← classify_query() + rerank_candidates() + rerank_by_criteria()
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
│  ┌──────────────────────┬────────────────────────────┐  │
│  │ search_by_title      │ nimihaku (elokuva / sarja) │  │
│  │ search_multi         │ nimihaku kaikki tyypit     │  │
│  │ search_person        │ henkilöhaku                │  │
│  │ get_details          │ tiedot + kokoelma-osat     │  │
│  │ get_person           │ henkilö + roolit           │  │
│  │ get_keywords         │ teoksen keywordit          │  │
│  │ get_recommendations  │ TMDB:n suositukset         │  │
│  │ trending             │ trendaavat nyt             │  │
│  │ discover             │ suodatushaku               │  │
│  │ list_genres          │ genret muistista (FI)      │  │
│  │ list_certifications  │ ikärajat (FI)              │  │
│  │ list_watch_providers │ suoratoistopalvelut        │  │
│  └──────────────────────┴────────────────────────────┘  │
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
  ┌──────────────────────────────────┐
  │        classify_query()          │
  │                                  │
  │  Gemini lukee:                   │
  │  · kyselyn                       │
  │  · genret (FI)                   │
  │  · suoratoistopalvelut (FI)      │
  │  · tämän päivän päivämäärä       │
  │                                  │
  │  Palauttaa: SmartSearchIntent    │
  └──────────────┬───────────────────┘
                 │
         _postprocess()   ← deterministiset korjaussäännöt
                 │
         intent? │
                 ▼
   ┌─────────────────────────────────────────────────┐
   │ franchise  → _franchise_search()               │
   │ discover   → discover() [+ actor_name-resolvaus│
   │              + watch_providers-looppi]         │
   │ similar_to → _similar_to()                     │
   │ lookup     → search_by_title()                 │
   │ person     → search_person()                   │
   │ trending   → trending()                        │
   └─────────────────────────────────────────────────┘
```

---

## Intentin tunnistaminen — mistä Gemini tietää mitä käyttäjä haluaa

```
INTENT       MILLOIN                          ESIMERKKI
──────────────────────────────────────────────────────────────
franchise  · franchise-nimi + kriteeri        "parhaat Gundam-sarjat"
           · ei yhtä tiettyä teosta           "tummimmat Star Wars -elokuvat"

discover   · genre/tunnelma ilman nimeä       "suomalaisia draamoja 90-luvulta"
           · näyttelijä + kriteeri            "Tom Hanksin sotaelokuvat"
           · watch_provider mainittu          "Netflix-sarjoja 2020-luvulta"

similar_to · teos mainitaan VERTAILUNA        "samanlaisia kuin Inception"
           · "kuten X", "X tyylinen"          "enemmän Sopranos-henkistä"

lookup     · yksi nimetty teos               "kerro Blade Runnerista"
           · "kerro", "mikä on"              "mikä on Breaking Bad"

person     · henkilönimi YKSIN               "kuka on Tom Hanks"
           · ei genre/vuosi-filttereitä      "kerro Meryl Streepistä"
           (jos filttereitä → discover!)

trending   · "trendaa", "mitä katsotaan nyt" "mitä elokuvia trendaa"
```

---

## _postprocess() — Geminin jälkeen tehtävät automaattiset korjaukset

Gemini voi tehdä virheitä. Tämä funktio korjaa deterministisesti:

```
Sääntö                                   Korjaus
─────────────────────────────────────────────────────────────
airing_now=true                        → media_type="tv"
                                         (sarjat airoavat, elokuvat eivät)

genres=["Animaatio"] ilman kieltä      → language="ja"
                                         (animaatio on japani oletuksena)

"anime/isekai/seinen" kyselyssä        → language="ja" + genres=["Animaatio"]

franchise_query asetettu + "sarj*"     → media_type="tv"
kyselyssä                                (Gemini voi sekoittaa elokuva/sarja)
```

---

## discover-polku

Yksinkertaisin polku — yksi tai useampi API-kutsu:

```
intent.genres        →  genre-ID:t muistista (FI-nimet → ID:t)
intent.keywords      →  keyword-ID:t cachesta tai TMDB-hausta
intent.language      →  with_original_language
intent.actor_name    →  /search/person → with_cast ID
intent.watch_providers → with_watch_providers + watch_region=FI
                              │
                              ▼
                 /discover/movie  tai  /discover/tv
                              │
                              ▼
                         tulokset
```

**Erityistapaukset:**

`both_types=true` → kaksi discover-kutsua rinnakkain (movie + tv)

`watch_providers` sisältää useita palveluja → yksi haku per palvelu,
tulokset eri osioina:
```
## Yle Areena
...
## Amazon Prime Video
...
```

`actor_name` → haetaan ensin henkilön TMDB-id → lisätään with_cast-filtteriksi:
```
"Tom Hanksin sotaelokuvat"
  → actor_name="Tom Hanks"
  → /search/person?query=Tom+Hanks → id=31
  → /discover/movie?with_cast=31&with_genres=10752
```

---

## franchise-polku

Käytetään kun haetaan kaikki tietyn franchisen teokset + käyttäjän kriteeri
(paras, tummin, suosituin jne.):

```
franchise_query="Gundam", media_type="tv"
         │
         ▼
  Haetaan 2 sivua ilman kielirajoitusta (40 tulosta)
  /search/tv?query=Gundam&page=1
  /search/tv?query=Gundam&page=2   (rinnakkain)
         │
         ▼
  Suodatetaan: poistetaan tulokset joiden nimessä ei ole "gundam"
  (vältää täysin epäolennaiset)
         │
         ▼
  rerank_by_criteria(query, kandidaatit[:30])
  "parhaat vakavat tummat Gundam sarjat"
         │
         ▼
  Gemini järjestää temaattisesti → top tulokset
```

**Miksi 2 sivua ilman kielirajoitusta?**
TMDB:n hakutulokset vaihtelevat kielen mukaan. Japanilaiset sarjat
(Gundam, Dragon Ball jne.) löytyvät paremmin ilman `language=fi`-rajoitusta.

---

## similar_to-polku — kolmivaiheinen

Referenssiteos toimii ankkurina. Kolme vaihetta:

```
VAIHE 1 — Hae referenssiteos
─────────────────────────────
"samanlaisia kuin Redo of Healer, gore, synkkä"
                │
                ▼
     /search/tv?query="Redo of Healer"
                │
                ▼
     ref_id=99071, ref_lang="ja", ref_genre_ids=[16,...]


VAIHE 2 — Rinnakkain (asyncio.gather)
──────────────────────────────────────

   ┌──────────────────────┐    ┌───────────────────────────────┐
   │  /tv/99071/          │    │  _fetch_keyword_discover()    │
   │  recommendations     │    │                               │
   │                      │    │  1. /tv/99071/keywords        │
   │  TMDB:n oma lista:   │    │     → [revenge, gore,         │
   │  "muut katsoi myös"  │    │        dark fantasy, seinen]  │
   │                      │    │                               │
   │  ~20 tulosta         │    │  2. Poistetaan generiset:     │
   │                      │    │     anime, based on manga,    │
   │                      │    │     magic, romance, adventure │
   │                      │    │                               │
   │                      │    │  3. user-kw + ref-kw → OR    │
   │                      │    │                               │
   │                      │    │  4. /discover/tv              │
   │                      │    │     ?with_keywords=X|Y|Z      │
   │                      │    │     &with_original_language=ja│
   │                      │    │     &include_adult=true       │
   └──────────────────────┘    └───────────────────────────────┘
            │                               │
            └───────────────┬───────────────┘
                            │
                 disc + recs yhdistetään
                 duplikaatit poistetaan
                 ~30 kandidaattia


VAIHE 3 — LLM rerankaus (Gemini kutsu #2)
───────────────────────────────────────────

  Geminille annetaan referenssiteoksen kuvaus + teemat + kandidaatit.
  Gemini valitsee parhaiten sopivat ja järjestää ne.
  Palautetaan top 12.
```

**Jos watch_providers on asetettu:**
Recommendations-vaihe ohitetaan kokonaan (TMDB ei tue platformifilttereitä
recommendations-endpointissa). Sen sijaan ajetaan yksi discover per palvelu
rinnakkain ja yhdistetään tulokset.

---

## get_details — kokoelmatuki elokuville

Kun haet elokuvan tiedot, palvelin tarkistaa automaattisesti kuuluuko
se kokoelmaan (esim. Blade Runner Collection, Star Wars Collection):

```
/movie/{id}
    │
    ├── belongs_to_collection.id löytyy?
    │       │
    │       ▼
    │   /collection/{collection_id}
    │       │
    │       ▼
    │   Kaikki kokoelman osat aikajärjestyksessä
    │   "tämä" merkitään ◄
    │
    └── ei → ei lisätietoja
```

Esimerkki:
```
Blade Runner: The Final Cut (1982)
...
Osa kokoelmaa: Blade Runner Collection
  Blade Runner: The Final Cut (1982) — 7.9/10 ◄ tämä
  Blade Runner 2049 (2017) — 7.6/10
```

---

## Miksi LLM-rerankaus on turvallinen ratkaisu

```
✓ TURVALLINEN:  Gemini valitsee TMDB:stä haettujen joukosta
                → ei voi keksiä teoksia joita ei ole
                → vain järjestää ja suodattaa olemassaolevaa

✗ VAARALLINEN:  "Keksi 10 moottoripyöräanimen nimeä"
                → LLM voisi hallusinoida teoksia
                → tätä EI käytetä
```

---

## Startup-muisti (memory.py)

Kerätään kerran palvelimen käynnistyksessä, pysyy muistissa:

```
käynnistys
    ├── /genre/movie/list?language=fi    →  movie_genres  (19 genreä)
    ├── /genre/tv/list?language=fi       →  tv_genres     (16 genreä)
    ├── /certification/movie/list        →  movie_certs   (FI ikärajat)
    ├── /certification/tv/list           →  tv_certs      (FI ikärajat)
    ├── /watch/providers/movie?region=FI →  movie_providers
    ├── /watch/providers/tv?region=FI    →  tv_providers
    └── keyword_cache = {}               ← täyttyy ajonaikaisesti
```

Keyword-cache toimii näin:
```
1. käyttäjä pyytää "gore"-keywordiä
2. cache tyhjä → /search/keyword?query=gore → id=10292
3. tallennetaan: cache["gore"] = "10292"
4. seuraava pyyntö → löytyy cachesta, ei API-kutsua
```

`get_keywords` täyttää cachen sivutuotteena — teoksen keywordit
lisätään automaattisesti.

---

## Tunnetut rajoitukset

```
ONGELMA                        SYY                      TILANNE
──────────────────────────────────────────────────────────────────
"anime jossa moottoripyöriä"  TMDB tägää harvoin        ei ratkaisua
→ Akira ei löydy              ajoneuvoja keywords-
                               kentässä

Näyttelijän TV-roolit         TMDB:n henkilöprofiilit   ei ratkaisua
puuttuvat discover-hausta     ovat epätäydellisiä       tällä hetkellä
(esim. Pamela Anderson /       (Baywatch TV puuttuu)
Baywatch TV)

Franchise-haku ei löydä       TMDB-haku ei indeksoi     osittainen:
kaikkia osia jos franchise-   japanilaisia nimiä        2-sivu-haku
nimi on vain japanissa        hyvin englanniksi          auttaa
```
