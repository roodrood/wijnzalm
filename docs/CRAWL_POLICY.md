# Crawlbeleid en controleerbaarheid

De GitHub Action is een **diagnose**, geen scraper. Per forum worden uitsluitend DNS, de homepage en `/robots.txt` opgevraagd. Het rapport bevat HTTP-statuscodes, geen inhoud uit forumdiscussies.

## Volgende mijlpalen

1. Controleer de HTML-structuur van echte openbare discussiepagina's waar die toegankelijk en toegestaan zijn.
2. Bevestig toegangs- en hergebruikvoorwaarden per forum, indien nodig via de beheerders.
3. Gebruik de reeds voorbereide hervatbare crawler voor beperkte, toegestane indexeringsproeven.
4. Publiceer auditstatistiek: gevonden categorieën, topics, berichten, ontbrekende pagina's, parserfouten en dekkingspercentage.
5. Bewaar volledige berichten uitsluitend met passende toestemming; gebruik anders bronlinks en toegestane metadata.
6. Leg kennis vast per producent, cuvée, jaargang en claim, inclusief bron, proefdatum, tegenspraak en betrouwbaarheidsniveau.

**Niet gedaan:** volledige live forumcrawl, opslag van een miljoen forumberichten, of rechtenverlening door forumbeheerders.

## Uitvoeren

De workflow `.github/workflows/forum-access-probe.yml` draait op een push naar de testbranch en kan daarna handmatig worden gestart. Bekijk bij de workflow-run het artifact `wineforum-connection-report` voor JSON en Markdown-resultaten.
