# Handleiding: nog bij te werken

Wijzigingen in het programma die nog in de uitgebreide handleiding (Help > Gebruikershandleiding) moeten
komen. We werken de handleiding in één keer bij, in het Engels (`pixelpickle/data/manual/prose_en.json`)
en daarna in de andere acht talen (`prose_<taal>.json`). Wat hier staat, wordt dan in één ronde vertaald.

Let op: nieuwe gereedschappen, opties, effectinstellingen of menu-opdrachten moeten meteen een Engelse
tekst krijgen, anders slaagt `tests/test_manual.py` niet. Daarvoor is dit lijstje niet nodig; het gaat hier om
aanvullingen op bestaande teksten.

## Open

(niets)

## Verwerkt

In alle negen talen verwerkt voor versie 1.0.0:

- **Lagen > Beeld** (menu-opdrachten `80ff`, `8100`, `8177`, `8176`, `8178`, `8179`): Alleen huidige laag,
  Alle lagen, Geen, Omkeren, Koppelingset weergeven en verbergen.
- **Alfakanalen** (menu-opdrachten `810e`, `810f`, `8110`, `8111`, `81e4`): selecties en maskers bewaren in
  benoemde kanalen binnen de afbeelding, laden met voorbeeld, Omkeren en Vervangen/Toevoegen/Verwijderen,
  verwijderen; bewaard in .ora en ze draaien, schalen en snijden mee.
- **Tekst met opmaak per woord en materiaal in tekst** (gereedschap `d0f0`, sectie `materials`): werkbalkje in
  het venster Tekst invoeren; vulling en rand als verloop of patroon; verloopbewerker.
- **Rode ogen verwijderen, Sculptuur, Textuur** (effecten `806e`, `80b0`, `80b1`): oogherkenning met nieuwe
  instelling Max. oogdiameter; alle patronen uit Materialen en een eigen installatie.
- **Snelmenu's en menu Objecten** (secties `vector`, `tips`, gereedschappen `d110` Pen en `d011` Kiezen, alle
  menu-opdrachten van Objecten en `8216` Vergrootglas): korter menu op de afbeelding, rechtsklik met een
  selectiegereedschap heft de selectie op, menu op de lege werkruimte, pen-snelmenu, objecten kiezen met
  Kiezen, uitlijnen/verdelen/even groot/schikken/groeperen/eigenschappen, tekst in curven, tekst op pad.
- **Laatste menu-opdrachten** (menu's Selecties, Afbeelding, Beeld, Venster, Bewerken en Bestand; zie de
  nieuwe menu-ids in `structure.json`).

In alle negen talen verwerkt voor versie 0.10.0:

- **Pijltoetsen, versnelling** (sectie `selections`, gereedschap Verplaatsen `d012`): houd je een pijltoets
  ingedrukt, dan gaan de eerste stappen per pixel en daarna steeds sneller (tot 8 pixels per stap, met
  Shift tot 80).
- **Pijltoetsen met focus op een palet** (sectie `selections`): ook na het aanklikken van een laag in het
  lagenpalet verschuiven de pijltoetsen de selectie of de laag.
- **Pijltoetsen op tekst- en vectorlagen** (gereedschap Verplaatsen `d012`): de laag blijft bewerkbaar en
  schuift gewoon mee; er wordt niets omgezet naar een rasterlaag.
- **Spiegelen en omdraaien met een selectie** (menu-opdrachten `800d` en `800c`): met een actieve selectie
  draaien alleen de geselecteerde pixels om, op hun eigen plek binnen het selectiekader, en het
  selectiekader draait mee. Zonder selectie spiegelt de hele laag.
- **Kleurwisselaar** (gereedschap `d0d2`): werkt nu op alle gelijkende kleuren in de laag, ook in losse
  delen (Aaneengesloten staat standaard uit), en vergelijkt vooral op kleurtint zodat schaduwkanten
  meegaan. Nieuwe optie Randzachtheid.
- **Menu Paletten** (sectie `workspace`): bevat nu ook Gereedschappen, om de gereedschapsbalk aan en uit te
  zetten.
- **Op updates controleren** (menu-opdracht `8125`, menu Help): opent de projectpagina op GitHub.
- **Vier nieuwe gereedschappen**: Makeover (`d070`), Object verwijderen (`d083`), Markering (`d136`) en
  Paletmes (`d137`).
- **Schuifbalk onder de invoervelden van de optiebalk** (sectie `workspace`): klikken of slepen op de dunne
  balk onderaan een veld zet de waarde direct; bij grote bereiken (zoals Grootte) loopt de balk kwadratisch.
- **Penseel Verwringen** (gereedschap `d121`): de werking loopt altijd vloeiend af naar de rand, ook bij
  Hardheid 100; Hardheid bepaalt alleen hoe groot het volle midden is.
