# PixelPickle

Fotobewerker voor Linux met de vertrouwde indeling en sneltoetsen van Paint Shop Pro XI:
dezelfde menu's, gereedschapsbalk met uitklapgroepen, optiebalk, paletten (Materialen, Lagen) en
documenten met tabs.

## Installeren

Download het pakket voor jouw distributie bij de nieuwste
[release](https://github.com/rene-timmermans/pixelpickle/releases/latest). De benodigde onderdelen
(Python, PySide6, NumPy, Pillow) installeert je pakketbeheerder automatisch mee. Daarna staat
PixelPickle in het menu (Grafisch) of start je het met `pixelpickle`.

| Distributie | Installeren | Verwijderen |
|---|---|---|
| Arch, SteamOS, Manjaro, EndeavourOS | `sudo pacman -U pixelpickle-<versie>-1-any.pkg.tar.zst` | `sudo pacman -R pixelpickle` |
| Debian 13 of nieuwer, recente Ubuntu (getest op de nieuwste LTS en de nieuwste versie) | `sudo apt install ./pixelpickle_<versie>-1_all.deb` | `sudo apt remove pixelpickle` |
| Fedora | `sudo dnf install ./pixelpickle-<versie>-1.*.noarch.rpm` | `sudo dnf remove pixelpickle` |

Elk pakket wordt bij een release automatisch gebouwd, in een echte omgeving van die distributie
geïnstalleerd en getest (zie `.github/workflows/release.yml`). Ubuntu 24.04 en Debian 12 hebben geen
PySide6 pakket en worden daarom niet ondersteund.

### Overstappen van de oude naam "Pigment" (versie 0.1.x)

Er bestaat al een ander Arch pakket met de naam `pigment`; daarom heet dit programma nu PixelPickle.
Verwijder eerst de oude versie, anders kan `pacman -Syu` hem vervangen door dat andere pakket:

```
sudo pacman -R pigment
sudo pacman -U pixelpickle-<versie>-1-any.pkg.tar.zst
```

Instellingen en voorinstellingen worden bij de eerste start automatisch overgenomen, en .ora bestanden
van de oude versie openen gewoon.

## Taal

PixelPickle is er in het Nederlands en het Engels. Kies de taal via
**Bestand > Voorkeuren > Algemene programmavoorkeuren** (*File > Preferences > General Program
Preferences*). Bij de eerste start is de taal Engels.

## Wat het kan

- Gereedschappen zoals in PSP XI, met dezelfde posities en sneltoetsen (A, Z, K, M, S, E, R, C, B, L, J,
  X, F, I, T, P, G, Q, H, V), waaronder selecties met Slimme rand, toverstaf met overeenkomstmodi en
  tolerantie, alle retoucheerpenselen, klonen, vormen en bewerkbare tekst.
- Bijsnijden met aanpasbaar kader, vaste verhoudingen en uitlijnen op laag of afbeelding.
- Materialen: kleur, verloop (lineair, rechthoekig, zonnestraal, radiaal) en patroon, voor vulemmer,
  penselen en vormen. Verlopen en patronen van een bestaande installatie worden automatisch ingelezen.
- Lagen met 21 mengmodi, groepen, maskerlagen en aanpassingslagen.
- 142 effecten en aanpassingen met Vóór/Na voorbeeld en voorinstellingen.
- Automatisch opslaan naar een herstelmap, met herstel na een onverwachte afsluiting.
- Beknopte gebruikershandleiding in het programma (Help).
- Openen en opslaan: PNG, JPEG, TIFF, BMP, WebP, GIF (ook transparant via GIF-optimalisatie),
  OpenRaster (.ora, met lagen) en Paint Shop Pro (.pspimage).

## Ontwikkelen

```
python3 -m venv .venv && .venv/bin/pip install PySide6 numpy Pillow
./pixelpickle.sh                                           # starten vanuit de broncode
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/smoke.py   # tests
tools/build_package.sh                                 # pacman pakket in dist/ (Debian/Fedora: via GitHub Actions)
```

## Licentie

PixelPickle is vrije software onder de [GNU General Public License v3.0 of later](LICENSE).
