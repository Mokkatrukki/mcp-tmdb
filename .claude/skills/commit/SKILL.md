---
name: commit
description: Reviewaa muutokset, päivitä CLAUDE.md:n tila ja tee git commit
disable-model-invocation: true
allowed-tools: Bash(git *), Read, Edit
argument-hint: "[commit message]"
---

# Commit-workflow

## Nykyinen tila

Muuttuneet tiedostot:
```
!`git -C /home/mokka/projektit/MCP-tmdb status --short`
```

Staged muutokset:
```
!`git -C /home/mokka/projektit/MCP-tmdb diff --cached --stat 2>/dev/null || echo "Ei stagettuja muutoksia"`
```

## Ohjeet

1. **Reviewaa muutokset** — lue diff ja arvioi lyhyesti:
   - Noudatetaanko projektin periaatteita (yksinkertaisuus, ei ylisuunnittelua)?
   - Onko selkeitä ongelmia (turhat try/except, hardkoodatut arvot, jne.)?
   - Mainitse vain konkreettiset huomiot, älä nitpickaa

2. **Päivitä CLAUDE.md** — jos muutos on merkittävä (uusi työkalu, uusi ominaisuus), päivitä "Missä ollaan nyt" -osio vastaamaan tilannetta

3. **Stage ja commit** — käytä selkeää commit-viestiä:
   - Prefiksit: `feat`, `fix`, `docs`, `refactor`, `chore`
   - Ei mainintoja Claudesta, Claude Codesta tai Anthropicista
   - Ei `Co-Authored-By` -rivejä

Jos käyttäjä antoi viestin argumenttina, käytä sitä: $ARGUMENTS
