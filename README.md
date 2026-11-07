# PixelPickle

Fotobewerker voor Linux met een begrijpelijke en vertrouwde indeling van de gereedschappen. Menu's,
gereedschappen en sneltoetsen staan op vaste, logische plekken, zodat je direct aan de slag kunt en
niet hoeft te zoeken.

## Wat het kan

**Werkruimte**
- Menubalk, standaardwerkbalk en een gereedschapsbalk met uitklapgroepen.
- Optiebalk met de instellingen van het gekozen gereedschap, netjes uitgelijnd, met eigen
  voorinstellingen per gereedschap.
- Paletten Materialen, Lagen en Geschiedenis, los te maken en vrij te plaatsen.
- Meerdere afbeeldingen tegelijk, als tabbladen of als losse vensters.
- Snelmenu's met de rechtermuisknop op de afbeelding, de tabbladen en de lagen.
- Strakke lijniconen in de accentkleur van je eigen thema; ziet er goed uit op licht en donker.
- Nederlands en Engels.

**Gereedschappen**
- Pannen en zoomen, selecteren en verplaatsen.
- Selecties: rechthoek, ovaal en andere vormen, uit de vrije hand (ook punt tot punt en Slimme rand)
  en de toverstaf met overeenkomstmodi en tolerantie. Bij puntsgewijs selecteren schuift het beeld
  vanzelf mee als je bij de rand van het venster komt.
- Bijsnijden met een aanpasbaar kader: grepen op hoeken en zijden, vaste verhoudingen, maten in te
  typen en uitlijnen op laag of afbeelding. Dubbelklik in het kader om bij te snijden.
- Rechtzetten, perspectiefcorrectie, rode ogen verwijderen, klonen en krasjes verwijderen.
- Penseel, airbrush, wisser, vlakvulling en kleurwisselaar.
- Retoucheerpenselen: lichter/donkerder, tegenhouden, doordrukken, vegen, duwen, verzachten,
  verscherpen, reliëf, verzadiging, tint en meer.
- Kunstmedia: olieverfpenseel, krijt, pastel, kleurkrijt en kleurpotlood, elk met een eigen streek.
- Verwringen met een penseel (duwen, uitzetten, samentrekken, draaien, gladstrijken) en met een raster.
- Pen met rechte lijnen, Bézier-krommen en vrije lijnen; knooppunten blijven bewerkbaar tot Toepassen.
- Vormen (rechthoek, ovaal, symmetrische vormen, basisvormen) en bewerkbare tekst.

**Materialen**
- Kleur, verloop (lineair, rechthoekig, zonnestraal, radiaal; met hoek, herhalingen en middelpunt) en
  patroon (met hoek en schaal; ook een geopende afbeelding of een eigen bestand).
- Werkt met de vulemmer, de penselen en de vormen.
- 45 verlopen en 43 patronen meegeleverd: van metaal, neon en landschappen tot hout, marmer,
  stoffen en dierenprints.

**Lagen**
- 21 mengmodi, dekking, lagengroepen, maskerlagen, aanpassingslagen en vectorlagen.
- Vectorlagen: lijnen en vormen blijven bewerkbaar zolang je met de afbeelding bezig bent (en in .ora).
- Mengbereiken: bepaal per kanaal waar een laag zichtbaar is, op basis van de laag zelf en van wat
  eronder ligt.
- Koppelingssets, transparantie vergrendelen en lagen markeren met een kleur.

**Aanpassen en effecten**
- 142 aanpassingen en effecten met een Vóór/Na voorbeeld waarin je kunt zoomen en schuiven, een
  voorbeeld op de afbeelding zelf en voorinstellingen.
- Effecten zoeken met voorbeelden naast elkaar, en snelle fotocorrecties via Foto verbeteren.

**Bestanden en veiligheid**
- Openen en opslaan: PNG, JPEG, TIFF, BMP, WebP, GIF (ook transparant, via GIF-optimalisatie),
  OpenRaster (.ora, met lagen) en PspImage (.pspimage, met lagen).
- Ongedaan maken en opnieuw, met alle stappen in het palet Geschiedenis.
- Automatisch opslaan naar een herstelmap, op een instelbaar interval.

**Hulp**
- Beknopte gebruikershandleiding en een overzicht van alle sneltoetsen in het menu Help.

## Installeren

Download het pakket voor jouw distributie bij de nieuwste
[release](https://github.com/rene-timmermans/pixelpickle/releases/latest). Alles wat PixelPickle nodig
heeft, installeert je pakketbeheerder automatisch mee. Daarna staat PixelPickle in het menu (Grafisch)
of start je het met `pixelpickle`.

| Distributie | Installeren | Verwijderen |
|---|---|---|
| Arch, SteamOS, Manjaro, EndeavourOS | `sudo pacman -U pixelpickle-<versie>-1-any.pkg.tar.zst` | `sudo pacman -R pixelpickle` |
| Debian 13 of nieuwer, recente Ubuntu | `sudo apt install ./pixelpickle_<versie>-1_all.deb` | `sudo apt remove pixelpickle` |
| Fedora | `sudo dnf install ./pixelpickle-<versie>-1.*.noarch.rpm` | `sudo dnf remove pixelpickle` |

Elk pakket wordt bij een release automatisch gebouwd, geïnstalleerd en getest op die distributie.
Ubuntu 24.04 en Debian 12 worden niet ondersteund.

## Taal

Bij de eerste start is de taal Engels. Kies Nederlands via
**File > Preferences > General Program Preferences** (*Bestand > Voorkeuren > Algemene
programmavoorkeuren*).

## Wat er nieuw is

**0.7.0** Vectorlagen: lijnen van de pen en vormen blijven bewerkbaar zolang je met de afbeelding bezig
bent. Pak ze later weer op met de pen in de modus Bewerken om knooppunten, kleur en lijn aan te passen.

**0.6.1** De pen is vernieuwd: lijnen en polylijnen, punt tot punt met Bézier-krommen, uit de vrije hand
en bewerken van knooppunten, met lijnstijl, verbinding en verstek. De lijn blijft bewerkbaar tot Toepassen.

**0.6.0** Negen nieuwe gereedschappen: perspectiefcorrectie, krasjes verwijderen, penseel verwringen,
maasvormig verwringen en de kunstmedia olieverfpenseel, krijt, pastel, kleurkrijt en kleurpotlood.
Retoucheerpenselen zoals verscherpen en bosseleren werken nu één keer per streek, met de optie Doorlopend
om het effect op te bouwen.

**0.5.5** Het beeld schuift alleen nog mee bij de rand tijdens puntsgewijs selecteren, niet meer bij
penselen en andere gereedschappen. Opgeloste glitch in het kleurenpalet en een vinkje bij Opties voor
gereedschap.

**0.5.4** Een stuk uit een selectie halen of eraan toevoegen met de modus Verwijderen of Toevoegen werkt nu
ook als je binnen de bestaande selectie klikt.

**0.5.3** 45 verlopen en 43 patronen, direct in het programma.

**0.5.2** Nieuwe omschrijving van het programma in de pakketten en het menu.

**0.5.1** Het effectvenster meldt het wanneer er een selectie actief is, zodat duidelijk is waarom het
voorbeeld alleen dat gebied toont.

**0.5.0** Vooral cosmetisch: eigen lijniconen in de accentkleur van het thema voor alle werkbalken,
paletten en muisaanwijzers, en een strak uitgelijnde optiebalk. Nieuw: mengbereiken in
Laageigenschappen.

**0.4.0** Bijsnijden met een aanpasbaar kader, verloop en patroon als materiaal, automatisch opslaan,
gebruikershandleiding en een nieuw venster Info. Zonder geopende afbeelding is geen gereedschap actief;
daarna komt het laatst gebruikte gereedschap terug.

**0.3** Engels als tweede taal, pakketten voor Debian, Ubuntu en Fedora, een eigen programma-icoon,
zoomen en schuiven in het effectvoorbeeld en automatisch meeschuiven bij de rand tijdens het selecteren.

**0.2** Eigen muisaanwijzer per gereedschap; vrije software onder de GPL.

**0.1** Eerste versie: menu's, gereedschappen, lagen en effecten.

## Ontwikkelen

```
./pixelpickle.sh                                           # starten vanuit de broncode
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/smoke.py   # tests
```

Functies die nog niet gebouwd zijn, staan in [TODO.md](TODO.md).

## Licentie

PixelPickle is vrije software onder de [GNU General Public License v3.0 of later](LICENSE).
