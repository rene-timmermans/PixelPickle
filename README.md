# PixelPickle

Fotobewerker voor Linux met de vertrouwde indeling en sneltoetsen van Paint Shop Pro XI:
dezelfde menu's, gereedschapsbalk met uitklapgroepen, optiebalk, paletten (Materialen, Lagen) en
documenten met tabs.

## Installeren (Arch, SteamOS, Manjaro, EndeavourOS)

```
sudo pacman -U pixelpickle-0.2.0-1-any.pkg.tar.zst
```

pacman installeert automatisch de benodigde pakketten: `python`, `pyside6`, `python-numpy` en
`python-pillow`. Daarna staat PixelPickle in het menu (Grafisch) of start je het met `pixelpickle`.

Verwijderen: `sudo pacman -R pixelpickle`

### Overstappen van de oude naam "Pigment" (versie 0.1.x)

Er bestaat al een ander Arch pakket met de naam `pigment`; daarom heet dit programma nu PixelPickle.
Verwijder eerst de oude versie, anders kan `pacman -Syu` hem vervangen door dat andere pakket:

```
sudo pacman -R pigment
sudo pacman -U pixelpickle-0.2.0-1-any.pkg.tar.zst
```

Instellingen en voorinstellingen worden bij de eerste start automatisch overgenomen, en .ora bestanden
van de oude versie openen gewoon.

## Wat het kan

- Gereedschappen zoals in PSP XI, met dezelfde posities en sneltoetsen (A, Z, K, M, S, E, R, C, B, L, J,
  X, F, I, T, P, G, Q, H, V), waaronder selecties met Slimme rand, toverstaf met overeenkomstmodi en
  tolerantie, alle retoucheerpenselen, klonen, vormen en bewerkbare tekst.
- Lagen met 21 mengmodi, groepen, maskerlagen en aanpassingslagen.
- 142 effecten en aanpassingen met Vóór/Na voorbeeld en voorinstellingen.
- Openen en opslaan: PNG, JPEG, TIFF, BMP, WebP, GIF (ook transparant via GIF-optimalisatie),
  OpenRaster (.ora, met lagen) en Paint Shop Pro (.pspimage).

## Ontwikkelen

```
python3 -m venv .venv && .venv/bin/pip install PySide6 numpy Pillow
./pixelpickle.sh                                           # starten vanuit de broncode
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/smoke.py   # tests
tools/build_package.sh                                 # pacman pakket in dist/
```

## Licentie

PixelPickle is vrije software onder de [GNU General Public License v3.0 of later](LICENSE).
