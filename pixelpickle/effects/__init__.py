"""Register van effecten en aanpassingen.

Elk effect is een functie  fn(a, ctx, **params) -> np.ndarray
  a      : np.ndarray uint8 (H, W, 4), RGBA, NIET voorvermenigvuldigd. Niet in-place wijzigen.
  ctx    : Ctx met fg/bg (RGB tuples), scale (voorbeeldschaal: vermenigvuldig pixelmaten hiermee), seed
  params : waarden van de parameters (zie Int/Choice/Bool/Color/Curve hieronder)
  return : np.ndarray uint8 (H, W, 4) met dezelfde vorm.

Registreren met de decorator @effect(cid, "Naam", [parameters]); cid is het originele PSP opdracht ID
uit pixelpickle/data/pp_menus.json, zodat het menu-item automatisch werkt.
"""
from dataclasses import dataclass, field

REGISTRY = {}


@dataclass
class Effect:
    cid: int
    name: str
    fn: object
    params: list = field(default_factory=list)


def effect(cid, name, params=()):
    def deco(fn):
        REGISTRY[cid] = Effect(cid, name, fn, list(params))
        return fn
    return deco


def Int(key, label, lo, hi, default):
    return dict(type="int", key=key, label=label, lo=lo, hi=hi, default=default)


def Choice(key, label, options, default=0, extra=None):
    """extra: functie die bij het openen van het venster nog keuzes achter de vaste toevoegt (bijvoorbeeld
    patronen uit een eigen installatie); die staan niet in de vaste lijst, de handleiding of de vertalingen."""
    d = dict(type="choice", key=key, label=label, options=list(options), default=default)
    if extra is not None:
        d["extra"] = extra
    return d


def all_options(p):
    """Vaste keuzes plus de keuzes die er bij het openen bij komen."""
    try:
        return p["options"] + (list(p["extra"]()) if p.get("extra") else [])
    except Exception:  # noqa: BLE001 - een onleesbare extra map mag het venster niet breken
        return list(p["options"])


def Bool(key, label, default=False):
    return dict(type="bool", key=key, label=label, default=default)


def Color(key, label, default=(255, 255, 255)):
    """default mag ook "fg" of "bg" zijn (voor- of achtergrondkleur)."""
    return dict(type="color", key=key, label=label, default=default)


def Curve(key, label, default=((0, 0), (255, 255))):
    return dict(type="curve", key=key, label=label, default=[list(p) for p in default])


@dataclass
class Ctx:
    fg: tuple = (0, 0, 0)
    bg: tuple = (255, 255, 255)
    scale: float = 1.0
    seed: int = 1


def defaults(eff, ctx=None):
    out = {}
    for p in eff.params:
        d = p["default"]
        if p["type"] == "color" and ctx is not None and d in ("fg", "bg"):
            d = ctx.fg if d == "fg" else ctx.bg
        out[p["key"]] = d
    return out


def load_all():
    import importlib
    import pkgutil
    for m in pkgutil.iter_modules(__path__):
        if not m.name.startswith("_") and m.name != "common":
            try:
                importlib.import_module(f"{__name__}.{m.name}")
            except Exception as e:  # een kapot effectbestand mag het programma niet blokkeren
                print(f"Effecten in {m.name} niet geladen: {e!r}")
    return REGISTRY
