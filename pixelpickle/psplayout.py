"""Indeling van de gereedschapsbalk, overgenomen uit de PSP XI installatie van de gebruiker
(register: UI Customization\\BCGToolBar-7013). Elke lijst is één knop; meerdere items vormen
een uitklapgroep. Getallen zijn de originele opdracht ID's, zodat sneltoetsen één op één kloppen."""
import json
import os

TOOL_NAMES = {
    0xd001: "Pannen", 0xd002: "Zoomen",
    0xd011: "Selecteren", 0xd012: "Verplaatsen",
    0xd021: "Selectie", 0xd022: "Selectie uit vrije hand", 0xd023: "Toverstaf",
    0xd030: "Pipet",
    0xd040: "Bijsnijden",
    0xd051: "Rechttrekken", 0xd052: "Perspectiefcorrectie",
    0xd060: "Rode ogen",
    0xd070: "Makeover",
    0xd081: "Klonen", 0xd082: "Krasjes verwijderen", 0xd083: "Object verwijderen",
    0xd091: "Penseel", 0xd092: "Airbrush",
    0xd0a1: "Lichter/donkerder", 0xd0a2: "Tegenhouden", 0xd0a3: "Doordrukken", 0xd0a4: "Uitsmeren",
    0xd0a5: "Verspreiden", 0xd0a6: "Verzachten", 0xd0a7: "Verscherpen", 0xd0a8: "Bosseleren",
    0xd0a9: "Verzadiging Omhoog/Omlaag", 0xd0aa: "Kleurtoon omhoog/omlaag",
    0xd0ab: "Naar doel overgaan", 0xd0ac: "Kleur vervangen",
    0xd0b0: "Wisser",
    0xd0c0: "Achtergrondwisser",
    0xd0d1: "Vlakvulling", 0xd0d2: "Kleurwisselaar",
    0xd0e0: "Plaatjespenseel",
    0xd0f0: "Tekst",
    0xd101: "Basisvorm", 0xd102: "Rechthoek", 0xd103: "Ovaal", 0xd104: "Symmetrische vorm",
    0xd110: "Pen",
    0xd121: "Penseel Verwringen", 0xd122: "Maasvormig verwringen",
    0xd131: "Olieverfpenseel", 0xd132: "Krijt", 0xd133: "Pastel", 0xd134: "Kleurkrijt",
    0xd135: "Kleurpotlood", 0xd136: "Markering", 0xd137: "Paletmes", 0xd138: "Uitsmeren (kunstmedia)",
    0xd139: "Tekeningwisser",
}

TOOLBAR = [
    [0xd001, 0xd002],
    [0xd011, 0xd012],
    [0xd021, 0xd022, 0xd023],
    [0xd030],
    [0xd040],
    [0xd051, 0xd052],
    [0xd060],
    [0xd070],
    [0xd081, 0xd082, 0xd083],
    [0xd091, 0xd092],
    list(range(0xd0a1, 0xd0ad)),
    [0xd0b0],
    [0xd0c0],
    [0xd0d1, 0xd0d2],
    [0xd0e0],
    [0xd0f0],
    [0xd101, 0xd102, 0xd103, 0xd104],
    [0xd110],
    [0xd121, 0xd122],
    list(range(0xd131, 0xd13a)),
]

STANDARD_TOOLBAR = [0xe100, None, 0xe101, None, 0xe103, 0xe104, None, 0x82ec, None, 0xe12b, 0xe12c,
                    None, 0x80d1, None, 0x8242, 0x8243, None, "Foto verbeteren", "Paletten", 0x8136, 0x8132]
PHOTO_MENU = [0x8240, 0x82d8, None, 0x82f1, 0x82dc, 0x806a, 0x82db]
PALETTES_MENU = [0x822d, 0x8022, 0x8002, 0x81ae, 0x8029, 0x8185, 0x82cc, 0x8159, 0x3aca, 0x3acc, 0x800a, 0x81ba]

_DATA = os.path.join(os.path.dirname(__file__), "data", "pp_menus.json")


def load_layout():
    with open(_DATA, encoding="utf-8") as f:
        data = json.load(f)
    tool_keys = {int(k, 16): v for k, v in data["tool_keys"].items()}
    return data["menus"], tool_keys
