"""PSP voorinstellingen (.PspScript) lezen zonder code uit te voeren, en koppelen aan PixelPickle.

Een PSP voorinstelling heet  Preset_<Opdracht>_<Naam>.PspScript  en bevat een functie die een
dictionary teruggeeft. Die lezen we met 'ast'; App.Constants.X.Y wordt de tekst "Y"."""
import ast
import glob
import os
import re

PSP_DIRS = [
    os.path.expanduser("~/.var/app/com.usebottles.bottles/data/bottles/bottles/pspxi/drive_c/Program Files/"
                       "Corel/Corel Paint Shop Pro Photo XI/Voorinstellingen"),
    os.path.expanduser("~/.var/app/com.usebottles.bottles/data/bottles/bottles/pspxi/drive_c/users/deck/"
                       "Documents/Mijn PSP-bestanden/Voorinstellingen"),
]

# PSP opdrachtnaam -> PixelPickle ID (menu-opdracht of gereedschap)
KIND_TO_CID = {
    "AddNoise": 0x8089, "AgedNewspaper": 0x80c4, "Airbrush": 0xd092, "AutoSmallScratchRemoval": 0x806f,
    "BackgroundEraser": 0xd0c0, "Backlighting": 0x82b3, "BallsAndBubbles": 0x81f1, "BarrelCorrection": 0x818d,
    "BlackAndWhiteFilm": 0x82e6, "BlackPencil": 0x80a4, "Blinds": 0x80a5, "Blur": 0x8083, "BlurAverage": 0x8065,
    "BlurMore": 0x8084, "BrushStrokes": 0x80bc, "Burn": 0xd0a3, "Buttonize": 0x80a0, "Charcoal": 0x80aa,
    "ChangeToTarget": 0xd0ab, "Chisel": 0x80a2, "ChromaticAberrationRemoval": 0x82c4, "Chrome": 0x80ab,
    "Circle": 0x8098, "Clarify": 0x806a, "CloneBrush": 0xd081, "ColorAdjustBrightnessContrast": 0x8052,
    "ColorAdjustChannelMixer": 0x8062, "ColorAdjustCurves": 0x8075, "ColorAdjustHSL": 0x8076,
    "ColorAdjustHueMap": 0x805f, "ColorAdjustLevels": 0x8060, "ColorAdjustRGB": 0x8054,
    "ColorAdjustThreshold": 0x8063, "ColorBalance": 0x82dc, "ColoredChalk": 0x80a6, "ColoredEdges": 0x80c7,
    "ColoredFoil": 0x80cc, "ColoredPencil": 0x80a9, "Colorize": 0x804a, "ColorReplacer": 0xd0ac,
    "Contours": 0x80c9, "Crop": 0xd040, "Curlicues": 0x80ae, "Cutout": 0x809f, "Deinterlace": 0x806d,
    "Despeckle": 0x808a, "DigitalCameraNoiseRemoval": 0x82c1, "Dilate": 0x808b, "DisplacementMap": 0x8287,
    "Dodge": 0xd0a2, "DropShadow": 0x809e, "EdgePreservingSmooth": 0x8068, "Emboss": 0x808c,
    "EmbossTool": 0xd0a8, "Enamel": 0x80bf, "EnhanceEdges": 0x807d, "EnhanceEdgesMore": 0x807e,
    "Eraser": 0xd0b0, "Erode": 0x808d, "FadeCorrection": 0x8064, "Feedback": 0x80ac, "FillFlash": 0x82b1,
    "FindEdges": 0x807f, "FindHorizontalEdges": 0x8080, "FindVerticalEdges": 0x8081, "FineLeather": 0x80ce,
    "FisheyeCorrection": 0x818e, "Fur": 0x80ca, "GaussianBlur": 0x80b5, "GlowingEdges": 0x80a7,
    "Halftone": 0x818b, "HighPass": 0x82da, "HighPassSharpen": 0x82db, "HistogramAdjustment": 0x8070,
    "HistogramEqualize": 0x8056, "HistogramStretch": 0x8057, "HorizontalCylinder": 0x8096,
    "HorizontalPerspective": 0x809c, "HotWax": 0x80a1, "Hue": 0xd0aa, "InfraredFilm": 0x82e7,
    "InnerBevel": 0x80b2, "JPEGArtifactRemoval": 0x806b, "Kaleidoscope": 0x80ad, "LensDistortion": 0x818f,
    "LightenDarken": 0xd0a1, "Lights": 0x80c6, "MagnifyingLens": 0x81e5, "Median": 0x8066,
    "MoirePatternRemoval": 0x806c, "MosaicAntique": 0x80b9, "MosaicGlass": 0x80ba, "MotionBlur": 0x808f,
    "NegativeImage": 0x804b, "NeonGlow": 0x80a8, "Offset": 0x80bb, "OneStepNoiseRemoval": 0x82f1,
    "OneStepPhotoFix": 0x8240, "OneStepPurpleFringeFix": 0x82d9, "OuterBevel": 0x80b3, "PageCurl": 0x80c2,
    "PaintBrush": 0xd091, "Pattern": 0x80af, "Pencil": 0x80c8, "Pentagon": 0x8099, "PhotoLooks": 0x8319,
    "Pinch": 0x8094, "PincushionCorrection": 0x818c, "Pixelate": 0x808e, "PolarCoordinates": 0x818a,
    "PolishedStone": 0x80c1, "Posterize": 0x804c, "Punch": 0x8095, "PushBrush": 0xd0a5, "RadialBlur": 0x8288,
    "RedEyeRemoval": 0x806e, "Ripple": 0x8092, "RotatingMirror": 0x80b7, "RoughLeather": 0x80cd,
    "SaltAndPepper": 0x8074, "Sandstone": 0x80be, "Saturation": 0xd0a9, "Sculpture": 0x80b0,
    "SeamlessTiling": 0x8188, "Sepia": 0x80c3, "Sharpen": 0x8085, "SharpenBrush": 0xd0a7, "SharpenMore": 0x8086,
    "Skew": 0x809a, "SmartPhotoFix": 0x82d8, "SmoothSkin": 0x8307, "SmudgeBrush": 0xd0a4, "Soften": 0x8087,
    "SoftenBrush": 0xd0a6, "SoftenMore": 0x8088, "SoftFocus": 0x8192, "SoftPlastic": 0x80c0, "Solarize": 0x804d,
    "Spherize": 0x8189, "SpikyHalo": 0x80b8, "Straighten": 0xd051, "StrawWall": 0x80cb, "Sunburst": 0x80c5,
    "Texture": 0x80b1, "TexturePreservingSmooth": 0x8067, "Tiles": 0x80b4, "TimeMachine": 0x82fe,
    "Topography": 0x80bd, "TraceContour": 0x8082, "Twirl": 0x8091, "UnsharpMask": 0x809b,
    "UserDefinedFilter": 0x807c, "VerticalCylinder": 0x8097, "VerticalPerspective": 0x809d, "Warp": 0x80b6,
    "Wave": 0x8093, "Weave": 0x80a3, "Wind": 0x8090,
}

PSP_BLEND = ["Normal", "Darken", "Lighten", "Hue", "HueLegacy", "Saturation", "SaturationLegacy", "Color",
             "ColorLegacy", "Luminance", "LuminanceLegacy", "Multiply", "Screen", "Dissolve", "Overlay",
             "HardLight", "SoftLight", "Difference", "Dodge", "Burn", "Exclusion", "PaintBehind"]
PSP_MATCH = ["None", "RGBValue", "Color", "Brightness", "Perceptual", "Traditional", "AllOpaque", "Opacity"]

# PSP naam -> PixelPickle optie voor gereedschappen (penselen e.d.)
TOOL_KEYS = {"size": "size", "hardness": "hardness", "step": "step", "density": "density",
             "thickness": "thickness", "rotation": "rotation", "opacity": "opacity", "tolerance": "tolerance",
             "feather": "feather", "antialias": "antialias", "samplemerged": "sample_merged",
             "contiguous": "contiguous", "rate": "rate", "aligned": "clone_aligned"}


def _norm(k):
    return re.sub(r"[^a-z0-9]", "", k.lower())


class _Eval(ast.NodeVisitor):
    def value(self, n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Dict):
            return {self.value(k): self.value(v) for k, v in zip(n.keys, n.values)}
        if isinstance(n, (ast.Tuple, ast.List)):
            return [self.value(e) for e in n.elts]
        if isinstance(n, ast.Attribute):  # App.Constants.BlendMode.Normal -> "Normal"
            return n.attr
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            v = self.value(n.operand)
            return -v if isinstance(v, (int, float)) else v
        return None


def parse(path):
    """Geeft (soort, naam, platte dict met genormaliseerde sleutels) of None."""
    m = re.match(r"Preset_([^_]+)_(.*)\.PspScript$", os.path.basename(path), re.I)
    if not m:
        return None
    kind, name = m.group(1), m.group(2).strip()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, OSError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("Preset_"):
            for st in node.body:
                if isinstance(st, ast.Return):
                    d = _Eval().value(st.value)
                    if isinstance(d, dict):
                        flat = {}

                        def walk(x):
                            for k, v in x.items():
                                if isinstance(v, dict):
                                    walk(v)
                                elif isinstance(k, str):
                                    flat[_norm(k)] = v
                        walk(d)
                        return kind, name, flat
    return None


def scan(dirs=None):
    """{cid: [(naam, platte dict), ...]} voor alle PSP voorinstellingen die bij PixelPickle horen."""
    out = {}
    for d in dirs or PSP_DIRS:
        for path in sorted(glob.glob(os.path.join(glob.escape(d), "Preset_*.PspScript"))):
            r = parse(path)
            if r and r[0] in KIND_TO_CID:
                kind, name, flat = r
                if name.lower().startswith("last applied") or name.lower() == "standaardwaarden":
                    continue
                out.setdefault(KIND_TO_CID[kind], []).append((name, flat))
    return out


def to_tool_opts(flat):
    o = {}
    for k, ours in TOOL_KEYS.items():
        v = flat.get(k)
        if isinstance(v, bool):
            o[ours] = v
        elif isinstance(v, (int, float)):
            o[ours] = int(round(v))
    if flat.get("shape") in ("Round", "Square"):
        o["brush_shape"] = 0 if flat["shape"] == "Round" else 1
    if flat.get("blendmode") in PSP_BLEND:
        o["blend"] = PSP_BLEND.index(flat["blendmode"])
    if flat.get("matchmode") in PSP_MATCH:
        o["match_mode"] = PSP_MATCH.index(flat["matchmode"])
    return o


META = {"autoactionmode", "executionmode", "randomseed", "autoproof", "previewvisible", "revertwhenfinished",
        "dialogplacement", "version"}


def _numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def to_effect_params(eff, flat):
    """Koppel PSP waarden aan effectparameters op naam. Geeft (params, aantal gekoppeld, aantal te koppelen)."""
    flat = {k: v for k, v in flat.items() if k not in META}
    used, out, hits = set(), {}, 0
    params = [p for p in eff.params if p["type"] in ("int", "bool", "color", "choice")]

    def find(p):
        keys = [_norm(p["key"]), _norm(p["label"])]
        for k in keys:
            if k in flat and k not in used:
                return k
        cands = [fk for fk in flat if fk not in used and len(keys[0]) >= 3 and (keys[0] in fk or fk in keys[0])]
        return cands[0] if len(cands) == 1 else None

    for p in params:
        k = find(p)
        if k is None:
            continue
        v = flat[k]
        t = p["type"]
        if t == "int" and _numeric(v):
            out[p["key"]] = int(min(p["hi"], max(p["lo"], round(v))))
        elif t == "bool" and isinstance(v, bool):
            out[p["key"]] = v
        elif t == "choice" and isinstance(v, bool) and len(p["options"]) == 2:
            out[p["key"]] = int(v)
        elif t == "choice" and _numeric(v) and 0 <= v < len(_all_options(p)):
            out[p["key"]] = int(v)
        elif t == "color" and isinstance(v, (list, tuple)) and len(v) >= 3 and all(_numeric(c) for c in v[:3]):
            out[p["key"]] = tuple(int(c) for c in v[:3])
        else:
            continue
        used.add(k)
        hits += 1
    # één getal aan beide kanten: dan horen ze bij elkaar
    ints = [p for p in params if p["type"] == "int"]
    nums = [k for k, v in flat.items() if _numeric(v) and k not in used]
    if len(ints) == 1 and ints[0]["key"] not in out and len(nums) == 1:
        p = ints[0]
        out[p["key"]] = int(min(p["hi"], max(p["lo"], round(flat[nums[0]]))))
        hits += 1
    return out, hits, len(params)


def usable(eff, flat):
    prm, hits, n = to_effect_params(eff, flat)
    return prm if n and hits / n >= 0.5 else None


def _all_options(p):
    from .effects import all_options
    return all_options(p)
