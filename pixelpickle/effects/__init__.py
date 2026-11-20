"""Registry of effects and adjustments.

Each effect is a function  fn(a, ctx, **params) -> np.ndarray
    a      : np.ndarray uint8 (H, W, 4), RGBA, NOT premultiplied. Do not modify in place.
    ctx    : Ctx with fg/bg (RGB tuples), scale (preview scale: multiply pixel sizes by this), seed
    params : values of the parameters (see Int/Choice/Bool/Color/Curve below)
    return : np.ndarray uint8 (H, W, 4) with the same shape.

Register with the decorator @effect(cid, "Naam", [parameters]); cid is the original PSP command ID
from pixelpickle/data/pp_menus.json, so the menu item works automatically.
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
    """extra: function that, when the window opens, adds more choices after the fixed ones (for example
    patterns from a user's own installation); these are not in the fixed list, the manual or the translations."""
    d = dict(type="choice", key=key, label=label, options=list(options), default=default)
    if extra is not None:
        d["extra"] = extra
    return d


def all_options(p):
    """Fixed choices plus the choices that are added when opening."""
    try:
        return p["options"] + (list(p["extra"]()) if p.get("extra") else [])
    except Exception:  # noqa: BLE001 - an unreadable extra folder must not break the window
        return list(p["options"])


def Bool(key, label, default=False):
    return dict(type="bool", key=key, label=label, default=default)


def Color(key, label, default=(255, 255, 255)):
    """default may also be "fg" or "bg" (foreground or background color)."""
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
            except Exception as e:  # a broken effect file must not block the program
                print(f"Effects in {m.name} not loaded: {e!r}")
    return REGISTRY
