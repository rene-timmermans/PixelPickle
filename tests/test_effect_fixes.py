"""Effecten die voorheen hetzelfde deden of een instelling negeerden:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_effect_fixes.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pixelpickle.effects import Ctx, load_all

E = load_all()
rng = np.random.default_rng(1)
img = np.zeros((64, 64, 4), np.uint8); img[..., 3] = 255
img[:, 32:, :3] = 255                                          # harde rand
img[10:12, 5:20, :3] = 255                                     # fijn detail
img[40:50, 40:50, :3] = rng.integers(0, 255, (10, 10, 3))      # textuur
ctx = Ctx()


def run(cid, **p):
    return E[cid].fn(img, ctx, **p).astype(float)


blur, blurm, soft, softm = run(0x8083), run(0x8084), run(0x8087), run(0x8088)
d = lambda x, y: float(np.abs(x - y).mean())  # noqa: E731
print("verschil vervagen/verzachten:", round(d(blur, soft), 2), "| meer vervagen/nog zachter:", round(d(blurm, softm), 2))
assert d(blur, soft) > 0.3 and d(blurm, softm) > 0.3
# verzachten behoudt het fijne detail beter dan vervagen; 'meer' is sterker dan de gewone versie
detail = lambda r: r[11, 10, 0]  # noqa: E731
assert detail(soft) > detail(blur) and detail(blurm) < detail(blur) and detail(softm) < detail(soft)
avg, gau = run(0x8065, radius=6), run(0x80b5, radius=6)
print("verschil gemiddeld/gaussiaans (straal 6):", round(d(avg, gau), 2))
assert d(avg, gau) > 0.3
# filmkorrel: uniform heeft geen uitschieters, willekeurig (normaal) wel
flat = np.full((200, 200, 4), 128, np.uint8); flat[..., 3] = 255
n0 = E[0x8089].fn(flat, ctx, amount=20, kind=0, mono=1)[..., 0].astype(float) - 128
n1 = E[0x8089].fn(flat, ctx, amount=20, kind=1, mono=1)[..., 0].astype(float) - 128
k = lambda x: float(((x - x.mean()) ** 4).mean() / x.var() ** 2)  # noqa: E731
print("kurtosis willekeurig:", round(k(n0), 2), "| uniform:", round(k(n1), 2), "(normaal ~3, uniform ~1.8)")
assert k(n0) > 2.5 and k(n1) < 2.1 and abs(n0.std() - n1.std()) < 6
print("ALLES OK")
