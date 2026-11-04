"""Controleert elk geregistreerd effect: .venv/bin/python -I tests/test_effects.py [module ...]
Test vorm/type, randgevallen van parameters, transparantie en snelheid (2 MP)."""
import os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pigment import effects
from pigment.effects import Ctx, defaults

only = sys.argv[1:]
reg = effects.load_all()
rng = np.random.default_rng(0)
h, w = 90, 120
yy, xx = np.mgrid[0:h, 0:w]
photo = np.dstack([xx * 2 % 256, yy * 2.8 % 256, (xx + yy) % 256, np.full((h, w), 255)]).astype(np.uint8)
photo[30:60, 40:80, :3] = [220, 120, 40]
trans = photo.copy(); trans[..., 3] = (xx * 255 // w).astype(np.uint8); trans[:10] = 0
tiny = rng.integers(0, 256, (3, 2, 4), dtype=np.uint8)
big = np.dstack([rng.integers(0, 256, (1200, 1700, 3)), np.full((1200, 1700), 255)]).astype(np.uint8)
fails, slow = [], []
ctx = Ctx(fg=(0, 0, 0), bg=(255, 255, 255))
for cid, eff in sorted(reg.items()):
    if only and eff.fn.__module__.split(".")[-1] not in only:
        continue
    variants = [defaults(eff, ctx)]
    for p in eff.params:
        if p["type"] == "int":
            for v in (p["lo"], p["hi"]):
                d = defaults(eff, ctx); d[p["key"]] = v; variants.append(d)
        elif p["type"] == "choice":
            for v in range(len(p["options"])):
                d = defaults(eff, ctx); d[p["key"]] = v; variants.append(d)
        elif p["type"] == "bool":
            d = defaults(eff, ctx); d[p["key"]] = not p["default"]; variants.append(d)
    try:
        for img in (photo, trans, tiny):
            for prm in variants:
                for sc in (1.0, 0.25):
                    src = img.copy()
                    out = eff.fn(img, Ctx(fg=(0, 0, 0), bg=(255, 255, 255), scale=sc), **prm)
                    assert np.array_equal(src, img), "invoer is gewijzigd"
                    assert isinstance(out, np.ndarray) and out.dtype == np.uint8 and out.shape == img.shape, \
                        f"uitvoer {getattr(out, 'dtype', None)} {getattr(out, 'shape', None)}"
        t = time.time()
        eff.fn(big, ctx, **defaults(eff, ctx))
        dt = time.time() - t
        if dt > 4:
            slow.append((eff.name, round(dt, 1)))
    except Exception as e:
        fails.append((hex(cid), eff.name, repr(e)))
        traceback.print_exc()
print(f"getest: {len(reg) if not only else 'selectie'}; fouten: {len(fails)}; traag (>4 s op 2 MP): {slow}")
for f in fails:
    print("FOUT", *f)
sys.exit(1 if fails else 0)
