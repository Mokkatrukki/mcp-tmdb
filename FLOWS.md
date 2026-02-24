# MCP-TMDB — Miten tämä toimii

> Iso idea: käyttäjä kirjoittaa luonnollista kieltä.
> Järjestelmä ajattelee. TMDB hakee. Vastaus tulee takaisin.

---

## Tiedostorakenne

```
server.py            ← MCP-rekisteröinti + 2 omaa työkalua (63 riviä)
search/
  memory.py          ← käynnistysmuisti, _log, TMDB-vakiot
  tools.py           ← 12 TMDB-työkalua plain async-funktioina
  smart.py           ← _similar_to, _franchise_search, route()
  prompts.py         ← SmartSearchIntent, _postprocess, DSPy-rerankerit
  classifier.py      ← DSPy-luokittelija, save_example
data/
  keywords.json      ← TMDB keyword-id:t, verifioitu manuaalisesti
  examples.json      ← luokitteluesimerkit BootstrapFewShot-optimointia varten
```

Jako on tarkoituksellinen:
- `tools.py` ei tiedä älykkäästä hausta mitään — se on pelkkä TMDB-kuori
- `smart.py` käyttää `tools.py`:n funktioita, ei toisinpäin
- `server.py` on pelkkä rekisteröintikerros — ei logiikkaa

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
  │  DSPy ChainOfThought lukee:      │
  │  · kyselyn                       │
  │  · genret (FI)                   │
  │  · suoratoistopalvelut (FI)      │
  │  · tämän päivän päivämäärä       │
  │                                  │
  │  Malli: Gemini 2.5 Flash Lite    │
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

Intent-kentät ovat Pydantic `Literal`-tyyppiä — jos Gemini palauttaa
tuntemattoman intentin, Pydantic hylkää sen välittömästi ennen kuin
koodi ehtii käyttää arvoa.

---

## SmartSearchIntent — rakenne

Yksi Pydantic-malli joka kuvaa mitä käyttäjä haluaa. Kentät on ryhmitelty
sen mukaan mihin intenttiin ne kuuluvat:

```python
class SmartSearchIntent(BaseModel):
    # Kaikille intenteille
    intent:     Literal["discover", "similar_to", "franchise",
                        "lookup", "person", "trending"]
    media_type: Literal["movie", "tv"] = "movie"

    # trending
    time_window: str = "week"

    # discover
    genres, keywords, year, year_from, year_to,
    min_rating, language, sort_by, min_votes,
    airing_now, both_types, actor_name

    # discover + similar_to
    watch_providers: list[str] | None

    # similar_to
    reference_titles: list[str] | None

    # lookup
    title: str | None

    # person
    person_name: str | None

    # franchise
    franchise_query: str | None
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

"sarj*" / "show" / "series" kyselyssä → media_type="tv"

kielisana kyselyssä ("k-drama" jne.)  → language="ko" (tai muu ISO 639-1)

tyylisana kyselyssä ("synkkä" jne.)   → lisätään TMDB-keyword
```

Periaate: LLM hoitaa tulkinnan, deterministinen koodi hoitaa
varmuusverkon. Kumpikin tekee sen mihin se on paras.

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
  DSPy ChainOfThought (_RerankByCriteria)
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
   │                      │    │  3. user-kw + ref-kw          │
   │                      │    │     AND top-2 ensin (tarkat)  │
   │                      │    │     OR-fallback jos < 10      │
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


VAIHE 3 — DSPy rerankaus (_RerankByReference)
───────────────────────────────────────────────

  DSPy saa referenssiteoksen kuvauksen + teemat + kandidaatit.
  Gemini valitsee parhaiten sopivat ja järjestää ne.
  Palautetaan top 12.
```

**Jos watch_providers on asetettu:**
Recommendations-vaihe ohitetaan kokonaan (TMDB ei tue platformifilttereitä
recommendations-endpointissa). Sen sijaan ajetaan yksi discover per palvelu
rinnakkain ja yhdistetään tulokset.

---

## DSPy kaikkialla — yksi LLM-kirjasto

Kaikki LLM-kutsut kulkevat DSPy:n kautta. Mallina Gemini 2.5 Flash Lite.

```
search/classifier.py
  _classifier = dspy.ChainOfThought(QueryClassification)
      → kyselyn luokittelu → SmartSearchIntent

search/prompts.py
  _reranker          = dspy.ChainOfThought(_RerankByReference)
      → similar_to rerankaus referenssiteoksen perusteella

  _criteria_reranker = dspy.ChainOfThought(_RerankByCriteria)
      → franchise rerankaus käyttäjän kriteerien perusteella
```

Kaikki kolme käyttävät samaa `dspy.configure(lm=...)` -konfiguraatiota.
Mallin vaihtaminen tapahtuu yhdestä paikasta (`classifier.py`).

---

## Miksi LLM-rerankaus on turvallinen ratkaisu

```
✓ TURVALLINEN:  DSPy valitsee TMDB:stä haettujen joukosta
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

**Nykyinen ongelma:** cache katoaa kun palvelin käynnistyy uudelleen.
→ Seuraava askel: tallenna cache `data/keyword_cache.json`:iin ja lataa se käynnistyksessä.

---

## DSPy-luokittelija — miten toimii ja miten parannetaan

### Luokitteluketju

```
classify_query(query, memory)
        │
        ▼
DSPy ChainOfThought
  · rakentaa promptin: ohjeteksti + syötteet
  · Gemini tuottaa reasoning-ketjun (CoT)
  · parsii tuloksen SmartSearchIntent-objektiksi
  · Pydantic validoi: tuntematon intent → ValidationError
        │
        ▼
_postprocess(result, query)   ← deterministiset korjaussäännöt
        │
        ▼
SmartSearchIntent valmis → reititys
```

Lokit näyttävät jokaisen vaiheen:
```
[DSPY REASONING]  ... Geminin ajatusketju ...
[DSPY RESULT (raaka)]  { intent: "...", ... }
[INTENT (postprocess jälkeen)]  { intent: "...", ... }
```

### Kun luokittelu menee väärin — miten korjataan

**1. Havaitse virhe** — smart_search palauttaa väärän tuloksen

**2. Käytä `add_training_example`-työkalua:**
```
add_training_example(
  query="sarjoja kuten Downton Abbey Yle Areenasta",
  correct_intent_json='{"intent":"similar_to","media_type":"tv",
    "reference_titles":["Downton Abbey"],"watch_providers":["Yle Areena"]}'
)
```
Tallentuu → `data/examples.json`

**3. Tarkista `QueryClassification`-signatuuri** (`search/classifier.py`):
- Puuttuuko intent-tyyppi ohjetekstistä?
- Onko edge case katettu esimerkeillä?
- Lisää sääntö tarvittaessa suoraan docstringiin

### Optimointi BootstrapFewShot:lla (kun esimerkkejä ~20 kpl)

```python
# Tällä hetkellä: nolla-shot ChainOfThought
_classifier = dspy.ChainOfThought(QueryClassification)

# Tulevaisuudessa: few-shot optimoitu versio
from dspy.teleprompt import BootstrapFewShot

examples = json.loads(Path("data/examples.json").read_text())
trainset = [
    dspy.Example(query=e["query"], result=SmartSearchIntent(**e["correct"]))
    .with_inputs("query", "available_movie_genres", "available_tv_genres",
                 "available_providers", "today")
    for e in examples
]

teleprompter = BootstrapFewShot(metric=your_metric)
optimized = teleprompter.compile(_classifier, trainset=trainset)
```

**Milloin optimoida:**
- Esimerkkejä ≥ 20 kpl `data/examples.json`:ssä
- Sama virhe toistuu eri kyselyissä
- Signatuuri-muutos ei riitä korjaamaan

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

similar_to + watch_provider   TMDB recommendations-     discover per
→ recommendations ohitetaan   endpoint ei tue           palvelu, ei
                               platform-filttereitä     recommendations
```

---

## Seuraavat kehitysideat

Tässä asioita joita voisi tehdä seuraavaksi, helpoimmasta monimutkaisimpaan:

### Nopeat voitot

**Testit `_postprocess`-säännöille**
Deterministiset säännöt ovat täydellinen testikohde — ei LLM-kutsuja,
nopeat, kertovat heti jos jokin hajoaa. Esim. `pytest tests/test_postprocess.py`.

**Persistent keyword-cache**
Nyt cache katoaa käynnistyksen yhteydessä. Tallennus `data/keyword_cache.json`:iin
ja lataus käynnistyksessä — muutama rivi koodia, iso hyöty API-kutsuissa.

### Classifier-parannukset

**BootstrapFewShot-optimointi**
Kun `data/examples.json`:ssä on ~20 esimerkkiä, voidaan optimoida
DSPy:n promptit automaattisesti. Todennäköisesti parantaa luokittelutarkkuutta
merkittävästi erityisesti edge caseissa.

**Epävarma kysely → tarkennus**
Jos DSPy:n reasoning-ketjusta näkyy epävarmuus, voisi pyytää käyttäjältä
tarkennusta ennen hakua. "Tarkoitatko elokuvaa vai sarjaa?"

### Isommat ominaisuudet

**Käyttäjän preferenssimuisti**
"En tykkää kauhusta", "suosin 2010-luvun elokuvia", "olen jo nähnyt Breaking Badin"
→ tallennetaan sessiokohtaisesti tai pysyvästi, vaikuttaa hakuihin.

**similar_to + watch_providers yhdistettynä**
Nyt recommendations ohitetaan kokonaan jos palvelu asetettu.
Voisi hakea recommendations ensin, sitten filtteröidä palvelun mukaan
erillisellä watch_providers-kyselyllä.

**Monireferenssinen similar_to**
Toimii jo teknisesti (`reference_titles: list[str]`), mutta rerankausta
voisi parantaa: nyt ensimmäinen referenssi dominoi kielen ja genren valinnan.
