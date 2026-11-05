"""Openen en opslaan: gewone formaten via Pillow, lagen via OpenRaster (.ora)."""
import io
import os
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageOps
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from . import imageops as ops
from .document import BLEND_MODES, Document, Layer, new_image

OPEN_FILTER = ("Alle afbeeldingen (*.ora *.png *.jpg *.jpeg *.jpe *.bmp *.gif *.tif *.tiff *.webp "
               "*.tga *.pcx *.ico *.psd *.ppm *.pgm *.pbm *.xpm *.jp2 *.dds *.pspimage *.psp *.pspframe "
               "*.psptube *.pspmask *.tub *.msk);;"
               "OpenRaster met lagen (*.ora);;Alle bestanden (*)")
SAVE_FILTER = ("Paint Shop Pro (*.pspimage);;OpenRaster met lagen (*.ora);;PNG (*.png);;JPEG (*.jpg *.jpeg);;"
               "TIFF (*.tif *.tiff);;BMP (*.bmp);;WebP (*.webp);;GIF (*.gif);;Targa (*.tga)")
LAYERED = {".ora", ".pspimage", ".psp"}
PSP_EXT = {".pspimage", ".psp", ".pspframe", ".psptube", ".pspmask", ".tub", ".msk"}


class FileError(Exception):
    pass


def _png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _pil_to_qimage(im: Image.Image) -> QImage:
    return ops.rgba_to_qimage(np.asarray(im.convert("RGBA")))


def load(path: str) -> Document:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ora":
        return load_ora(path)
    if ext in PSP_EXT:
        from . import psp
        try:
            return psp.load(path)
        except psp.PspError as e:
            raise FileError(str(e))
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            img = _pil_to_qimage(im)
    except Exception:
        img = QImage(path)
        if img.isNull():
            raise FileError(f"Kan {os.path.basename(path)} niet openen.")
        img = img.convertToFormat(ops.FMT)
    doc = Document(img.width(), img.height())
    doc.layers[0].image = img
    if img.hasAlphaChannel() and ops.qimage_to_rgba(img)[..., 3].min() < 255:
        doc.layers[0].name = "Raster 1"
    doc.path = path
    return doc


def save(doc: Document, path: str, quality=90):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ora":
        save_ora(doc, path)
        return []
    if ext in (".pspimage", ".psp"):
        from . import psp
        return psp.save(doc, path)
    flat = doc.flattened()
    arr = ops.qimage_to_rgba(flat)
    if ext == ".gif":
        save_gif(path, gif_image(arr))
        return
    im = Image.fromarray(arr, "RGBA")
    if ext in (".jpg", ".jpeg", ".jpe", ".bmp"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    kwargs = {}
    if ext in (".jpg", ".jpeg", ".jpe", ".webp"):
        kwargs["quality"] = quality
    if ext in (".tif", ".tiff"):
        kwargs["compression"] = "tiff_lzw"
    tmp = path + ".tmp"
    try:
        im.save(tmp, format=Image.registered_extensions().get(ext, "PNG"), **kwargs)
        os.replace(tmp, path)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise FileError(str(e))


def save_ora(doc: Document, path: str):
    import json
    root = ET.Element("image", w=str(doc.w), h=str(doc.h), version="0.0.3")
    tmp = path + ".tmp"
    counter = [0]
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "image/openraster", compress_type=zipfile.ZIP_STORED)

        def common(el, l):
            el.set("name", l.name)
            el.set("opacity", f"{l.opacity:.3f}")
            el.set("visibility", "visible" if l.visible else "hidden")
            el.set("composite-op", BLEND_MODES[l.mode][2])
            if l.lock_alpha:
                el.set("brushwork-lock-alpha", "1")
            if l.link_set:
                el.set("brushwork-link-set", str(l.link_set))

        def emit(parent, group):
            for l in reversed(doc.children(group)):  # OpenRaster: bovenste eerst
                if l.kind == "group":
                    st = ET.SubElement(parent, "stack")
                    common(st, l)
                    if l.collapsed:
                        st.set("brushwork-collapsed", "1")
                    emit(st, l)
                    continue
                src = f"data/layer{counter[0]}.png"
                counter[0] += 1
                el = ET.SubElement(parent, "layer", src=src, x="0", y="0")
                common(el, l)
                if l.kind == "mask":
                    el.set("brushwork-mask", "1")
                if l.adjust is not None:
                    el.set("brushwork-adjust", json.dumps([l.adjust[0], l.adjust[1]]))
                z.writestr(src, _png_bytes(l.image), compress_type=zipfile.ZIP_STORED)
        emit(ET.SubElement(root, "stack"), None)
        z.writestr("stack.xml", ET.tostring(root, encoding="utf-8", xml_declaration=True),
                   compress_type=zipfile.ZIP_DEFLATED)
        flat = doc.flattened()
        z.writestr("mergedimage.png", _png_bytes(flat), compress_type=zipfile.ZIP_STORED)
        thumb = flat.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio)
        z.writestr("Thumbnails/thumbnail.png", _png_bytes(thumb), compress_type=zipfile.ZIP_STORED)
    os.replace(tmp, path)


def load_ora(path: str) -> Document:
    import json
    ops_by_name = {m[2]: i for i, m in enumerate(BLEND_MODES)}
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("stack.xml"))
        # Bestanden uit versie 0.1.x gebruikten de oude naam (Pigment) in eigen attributen en mengmodi
        for el in root.iter():
            for k in [k for k in el.attrib if k.startswith("pigment-")]:
                el.attrib["brushwork-" + k[len("pigment-"):]] = el.attrib.pop(k)
            op = el.get("composite-op", "")
            if op.startswith("pigment:"):
                el.set("composite-op", "brushwork:" + op[len("pigment:"):])
        w, h = int(root.get("w")), int(root.get("h"))
        doc = Document(w, h, None)
        layers = []  # van boven naar onder, zoals in het bestand

        def props(el, lay):
            lay.opacity = float(el.get("opacity", 1))
            lay.visible = el.get("visibility", "visible") != "hidden"
            lay.mode = ops_by_name.get(el.get("composite-op", "svg:src-over"), 0)
            lay.lock_alpha = el.get("brushwork-lock-alpha") == "1"
            lay.link_set = int(el.get("brushwork-link-set", 0))

        def walk(stack, group, dx=0, dy=0):
            for el in stack:
                if el.tag == "stack":
                    g = Layer(el.get("name", "Groep"), new_image(w, h))
                    g.kind = "group"
                    g.group = group
                    g.collapsed = el.get("brushwork-collapsed") == "1"
                    props(el, g)
                    layers.append(g)
                    walk(el, g, dx + int(float(el.get("x", 0))), dy + int(float(el.get("y", 0))))
                elif el.tag == "layer":
                    with Image.open(io.BytesIO(z.read(el.get("src")))) as im:
                        part = _pil_to_qimage(im)
                    img = new_image(w, h)
                    p = QPainter(img)
                    p.drawImage(dx + int(float(el.get("x", 0))), dy + int(float(el.get("y", 0))), part)
                    p.end()
                    lay = Layer(el.get("name", "Laag"), img)
                    props(el, lay)
                    lay.group = group
                    if el.get("brushwork-mask") == "1":
                        lay.kind = "mask"
                    if el.get("brushwork-adjust"):
                        cid, prm = json.loads(el.get("brushwork-adjust"))
                        lay.adjust = (cid, {k: (tuple(v) if isinstance(v, list) and len(v) == 3 and not isinstance(v[0], list) else v)
                                            for k, v in prm.items()})
                    layers.append(lay)
        walk(root.find("stack"), None)
    if not any(l.kind != "group" for l in layers):
        raise FileError("Leeg OpenRaster bestand.")
    doc.layers = list(reversed(layers))
    doc.active = len(doc.layers) - 1
    doc.normalize()
    doc.active = len(doc.layers) - 1
    doc.raster_counter = len(doc.layers)
    doc.path = path
    return doc


# ---------------------------------------------------------------- GIF met transparantie
def gif_image(rgba: np.ndarray, sel: np.ndarray | None = None, transparency=1, match_color=(255, 255, 255),
              match_tol=0, partial=0, threshold=128, blend_color=(255, 255, 255), colors=256, dither=True):
    """Maak een P-modus Pillow afbeelding voor GIF.
    transparency: 0 geen, 1 bestaande transparantie, 2 binnen selectie, 3 buiten selectie, 4 kleur.
    partial: 0 drempel, 1 overvloeien met kleur (voor half doorzichtige pixels)."""
    a = rgba.astype(np.float32)
    alpha = a[..., 3]
    if partial == 1:
        k = alpha[..., None] / 255
        rgb = a[..., :3] * k + np.array(blend_color, np.float32) * (1 - k)
        if transparency == 1:
            transparent = alpha == 0
        else:
            transparent = np.zeros(alpha.shape, bool)
    else:
        rgb = a[..., :3]
        transparent = alpha < threshold if transparency == 1 else np.zeros(alpha.shape, bool)
        if transparency != 1:  # geen transparantie gekozen: vlak maken op de overvloeikleur
            k = alpha[..., None] / 255
            rgb = rgb * k + np.array(blend_color, np.float32) * (1 - k)
    if transparency == 2 and sel is not None:
        transparent = sel > 127
    elif transparency == 3 and sel is not None:
        transparent = sel <= 127
    elif transparency == 4:
        transparent = np.abs(rgb - np.array(match_color, np.float32)).max(axis=-1) <= match_tol * 1.275
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    want = max(2, min(256, colors)) - (1 if transparent.any() else 0)
    q = im.quantize(colors=want, method=Image.Quantize.MEDIANCUT,
                    dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE)
    if transparent.any():
        idx = np.array(q)
        idx[transparent] = want
        pal = q.getpalette()[: want * 3] + [0, 0, 0]
        q = Image.fromarray(idx.astype(np.uint8), "P")
        q.putpalette(pal)
        q.info["transparency"] = want
    return q


def save_gif(path, q: Image.Image, interlace=False):
    tmp = path + ".tmp"
    kw = {"interlace": interlace}
    if "transparency" in q.info:
        kw["transparency"] = q.info["transparency"]
    q.save(tmp, format="GIF", **kw)
    os.replace(tmp, path)
