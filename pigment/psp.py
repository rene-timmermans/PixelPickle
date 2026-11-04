"""Paint Shop Pro bestanden lezen (.pspimage, .psp, .pspframe, .psptube, .pspmask, .tub, .msk).

Opbouw (openbare PSP bestandsspecificatie): 32 bytes handtekening, versie (major, minor), daarna blokken
'~BK\\0' + blok ID (WORD) + lengte (DWORD). Vanaf versie 6 beginnen blokken met een 'chunk' waarvan het
eerste DWORD de eigen lengte is; onbekende velden aan het eind slaan we daarmee veilig over."""
import struct
import zlib

import numpy as np
from PySide6.QtGui import QColor

from . import imageops as ops
from .document import Document, Layer, new_image

SIG = b"Paint Shop Pro Image File\n\x1a\0\0\0\0\0"
B_IMAGE, B_CREATOR, B_COLOR, B_LAYER_START, B_LAYER, B_CHANNEL = 0, 1, 2, 3, 4, 5
B_COMPOSITE_IMAGE, B_COMPOSITE_BANK, B_COMPOSITE_ATTR, B_JPEG = 9, 16, 17, 18
B_GROUP_EXT, B_MASK_EXT, B_ADJUST_EXT = 25, 26, 12
B_VECTOR_EXT, B_SHAPE, B_PAINTSTYLE, B_LINESTYLE = 13, 14, 15, 19



# PSP mengmodus -> index in pigment.document.BLEND_MODES
PSP_BLEND = {0: 0, 1: 1, 2: 2, 3: 4, 4: 6, 5: 8, 6: 10, 7: 11, 8: 12, 9: 13, 10: 14, 11: 15, 12: 16,
             13: 17, 14: 18, 15: 19, 16: 20, 17: 3, 18: 5, 19: 7, 20: 9}
LT_RASTER, LT_FLOATING, LT_VECTOR, LT_ADJUST, LT_GROUP, LT_MASK, LT_ARTMEDIA = 1, 2, 3, 4, 5, 6, 7


class PspError(Exception):
    pass


class Reader:
    def __init__(self, data: bytes):
        if not data.startswith(SIG[:27]):
            raise PspError("Geen Paint Shop Pro bestand.")
        self.d = data
        self.major, self.minor = struct.unpack_from("<HH", data, 32)
        self.hdr = 14 if self.major <= 3 else 10  # versie 3 heeft een extra lengteveld
        self.chunked = self.major >= 4               # vanaf PSP 6 (versie 4) beginnen blokken met hun lengte

    def blocks(self, start, end):
        pos = start
        d = self.d
        while pos + self.hdr <= end:
            if d[pos:pos + 4] != b"~BK\0":
                nxt = d.find(b"~BK\0", pos + 1, end)
                if nxt < 0:
                    return
                pos = nxt
                continue
            bid = struct.unpack_from("<H", d, pos + 4)[0]
            ln = struct.unpack_from("<I", d, pos + self.hdr - 4)[0]
            body = pos + self.hdr
            yield bid, body, min(body + ln, end)
            pos = body + ln

    # ---------------------------------------------------------------- algemene info
    def image_info(self, body):
        d = self.d
        p = body + (4 if self.chunked else 0)
        w, h = struct.unpack_from("<ii", d, p)
        res = struct.unpack_from("<d", d, p + 8)[0]
        unit = d[p + 16]
        p += 8 + 8 + 1  # resolutie (double) + eenheid
        comp, depth, planes = struct.unpack_from("<HHH", d, p)
        return dict(w=w, h=h, compression=comp, depth=depth, res=res, res_unit=unit)

    @staticmethod
    def px_per_point(info):
        """Omrekening tekstgrootte in punten naar pixels. Gemeten aan PSP XI bestanden met eenheid cm (2):
        pixels = punten * resolutie / 2,54 / 72 (klopt op 4 teksten in 2 bestanden). Voor inch (1) aangenomen
        pixels = punten * resolutie / 72 (nog niet met een voorbeeld gecontroleerd)."""
        res = info.get("res") or 72.0
        if not 1 <= res <= 10000:
            res = 72.0
        return res / 2.54 / 72 if info.get("res_unit") == 2 else res / 72

    def palette(self, body):
        d = self.d
        p = body + (4 if self.chunked else 0)
        n = struct.unpack_from("<I", d, p)[0]
        pal = np.frombuffer(d, np.uint8, count=n * 4, offset=p + 4).reshape(n, 4)
        return pal[:, [2, 1, 0]].copy()  # BGRx -> RGB

    # ---------------------------------------------------------------- kanalen
    def decompress(self, raw, comp, size):
        if comp == 0:
            return raw
        if comp == 2:
            return zlib.decompress(raw)
        if comp == 1:  # RLE
            out = bytearray()
            i = 0
            n = len(raw)
            while i < n and len(out) < size:
                c = raw[i]
                i += 1
                if c > 128:
                    out += bytes([raw[i]]) * (c - 128)
                    i += 1
                else:
                    out += raw[i:i + c]
                    i += c
            return bytes(out)
        raise PspError("JPEG gecomprimeerde lagen worden (nog) niet ondersteund.")

    def channel(self, body, end, comp, w, h, depth=8):
        d = self.d
        if self.chunked:
            cl = struct.unpack_from("<I", d, body)[0]
            clen, ulen, btype, ctype = struct.unpack_from("<IIHH", d, body + 4)
            p = body + cl
        else:
            clen, ulen, btype, ctype = struct.unpack_from("<IIHH", d, body)
            p = body + 12
        raw = self.decompress(d[p:p + clen], comp, ulen)
        bpp = 2 if depth == 48 else 1
        row = w * bpp
        padded = (row + 3) & ~3
        if len(raw) >= padded * h and padded != row and len(raw) < row * h + h * 4 + 1 and len(raw) != row * h:
            a = np.frombuffer(raw, np.uint8, count=padded * h).reshape(h, padded)[:, :row]
        else:
            a = np.frombuffer(raw, np.uint8, count=min(len(raw), row * h))
            if a.size < row * h:
                a = np.pad(a, (0, row * h - a.size))
            a = a.reshape(h, row)
        if bpp == 2:
            a = a.view("<u2")[:, :w] >> 8
            a = a.astype(np.uint8)
        return btype, ctype, a

    def bitmap(self, info, chans, w, h, pal=None):
        """Kanalen samenvoegen tot RGBA (h, w, 4) en eventueel een gebruikersmasker."""
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[..., 3] = 255
        mask = None
        have_alpha = False
        for btype, ctype, a in chans:
            if a.shape != (h, w):
                continue
            if btype in (0, 8):  # 0 = laagbeeld, 8 = samengesteld beeld
                if ctype in (1, 2, 3):
                    rgba[..., ctype - 1] = a
                elif pal is not None and info["depth"] <= 8:
                    rgba[..., :3] = pal[np.minimum(a, len(pal) - 1)]
                else:
                    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = a
            elif btype in (1, 9):  # transparantiemasker van laag of samengesteld beeld
                rgba[..., 3] = a
                have_alpha = True
            elif btype == 2:
                mask = a
        return rgba, mask, have_alpha

    # ---------------------------------------------------------------- lagen
    def layer(self, body, end, info, pal):
        d = self.d
        L = {}
        if self.chunked:
            cl = struct.unpack_from("<I", d, body)[0]
            nl = struct.unpack_from("<H", d, body + 4)[0]
            L["name"] = d[body + 6:body + 6 + nl].decode("utf-8", "replace") if self.major >= 10 \
                else d[body + 6:body + 6 + nl].decode("cp1252", "replace")
            p = body + 6 + nl
            L["type"] = d[p]
            L["rect"] = struct.unpack_from("<4i", d, p + 1)
            L["saved"] = struct.unpack_from("<4i", d, p + 17)
            L["opacity"], L["blend"], L["flags"], L["protect"], L["link"] = struct.unpack_from("<5B", d, p + 33)
            L["mask_rect"] = struct.unpack_from("<4i", d, p + 38)
            L["mask_saved"] = struct.unpack_from("<4i", d, p + 54)
            L["mask_disabled"] = d[p + 71] if p + 71 < body + cl else 0
            tail_end = body + cl
            if tail_end - p >= 120 and d[tail_end - 5] == 1:  # markeren in lagenpalet + COLORREF
                r_, g_, b_ = d[tail_end - 4], d[tail_end - 3], d[tail_end - 2]
                L["highlight"] = (r_, g_, b_)
            q = body + cl
            if d[q:q + 4] != b"~BK\0" and q + 8 <= end:  # bitmap info chunk
                q += struct.unpack_from("<I", d, q)[0]
            sub_start = q
        else:
            L["name"] = d[body:body + 256].split(b"\0")[0].decode("cp1252", "replace")
            p = body + 256
            L["type"] = LT_RASTER
            L["rect"] = struct.unpack_from("<4i", d, p + 1)
            L["saved"] = struct.unpack_from("<4i", d, p + 17)
            L["opacity"], L["blend"], vis, L["protect"], L["link"] = struct.unpack_from("<5B", d, p + 33)
            L["flags"] = vis
            L["mask_rect"] = struct.unpack_from("<4i", d, p + 38)
            L["mask_saved"] = struct.unpack_from("<4i", d, p + 54)
            L["mask_disabled"] = d[p + 71]
            # vaste lengte: + mengbereiken (5x2x4) + bitmap/kanaal aantallen
            sub_start = p + 75 + 2 + 40 + 4
            nxt = d.find(b"~BK\0", p, end)
            sub_start = nxt if nxt >= 0 else end
        sx0, sy0, sx1, sy1 = L["saved"]
        sw, sh = max(0, sx1 - sx0), max(0, sy1 - sy0)
        # de opgeslagen rechthoek ligt binnen de laagrechthoek (gecontroleerd met PSP XI bestanden)
        L["pos"] = (L["rect"][0] + sx0, L["rect"][1] + sy0)
        mx0, my0, mx1, my1 = L["mask_saved"]
        mw, mh = max(0, mx1 - mx0), max(0, my1 - my0)
        chans = []
        L["children"] = 0
        L["mask_fill"] = None
        L["adjust"] = None
        for bid, b, e in self.blocks(sub_start, end):
            if bid == B_CHANNEL:
                if self.chunked:
                    btype = struct.unpack_from("<H", d, b + 12)[0]
                else:
                    btype = struct.unpack_from("<H", d, b + 8)[0]
                if btype in (2, 7):  # 2 = (laag)masker, 7 = masker van een aanpassingslaag
                    chans.append(self.channel(b, e, info["compression"], mw, mh))
                else:
                    chans.append(self.channel(b, e, info["compression"], sw, sh, info["depth"] if info["depth"] == 48 else 8))
            elif bid == B_GROUP_EXT and self.chunked:
                cl = struct.unpack_from("<I", d, b)[0]
                if cl >= 8:
                    L["children"] = struct.unpack_from("<I", d, b + 4)[0]
            elif bid == B_MASK_EXT and self.chunked:  # masker zonder pixels: één vulwaarde
                L["mask_fill"] = struct.unpack_from("<I", d, b + 4)[0] & 0xff
            elif bid == B_ADJUST_EXT and self.chunked:
                L["adjust"] = self.adjustment(b, e)
            elif bid == B_VECTOR_EXT and self.chunked:
                L["shapes"] = self.vector(b, e)
        img = [c for c in chans if c[0] not in (2, 7)]
        rgba, _, have_alpha = self.bitmap(info, img, sw, sh, pal) if sw and sh else (None, None, False)
        um = [c for c in chans if c[0] in (2, 7)]
        L["mask_pos"] = (L["mask_rect"][0] + mx0, L["mask_rect"][1] + my0) if "mask_rect" in L else (mx0, my0)
        L["mask"] = um[0][2] if um and um[0][2].shape == (mh, mw) and mw and mh else None
        L["rgba"] = rgba
        return L

    # ---------------------------------------------------------------- vectoren (tekst)
    def vector(self, b, e):
        """Lees tekstobjecten uit een vectorlaag. Andere vormen worden (nog) overgeslagen."""
        d = self.d
        shapes = []
        q = b + struct.unpack_from("<I", d, b)[0]
        for bid, sb, se in self.blocks(q, e):
            if bid != B_SHAPE:
                continue
            try:
                t = self.text_shape(sb, se)
            except (struct.error, IndexError, UnicodeDecodeError):
                t = None
            if t:
                shapes.append(t)
        return shapes

    def text_shape(self, sb, se):
        d = self.d
        cl = struct.unpack_from("<I", d, sb)[0]
        nl = struct.unpack_from("<H", d, sb + 4)[0]
        name = d[sb + 6:sb + 6 + nl].decode("cp1252", "replace")
        visible = bool(struct.unpack_from("<I", d, sb + 8 + nl)[0] & 4) if cl >= 12 + nl else True
        p = sb + cl
        tcl = struct.unpack_from("<I", d, p)[0]
        _, ax, ay = struct.unpack_from("<BII", d, p + 4)
        m = struct.unpack_from("<9d", d, p + 13)
        p += tcl
        n_el = struct.unpack_from("<II", d, p)[1]
        p += struct.unpack_from("<I", d, p)[0]
        font = dict(family="Arial", size=24.0, points=True, weight=400, italic=False)
        stroke = fill = None
        runs = []  # [(lettertype, rand, vulling, tekst)]
        for _ in range(n_el):
            ecl = struct.unpack_from("<I", d, p)[0]
            etype = struct.unpack_from("<H", d, p + 4)[0]
            p += ecl
            if etype == 1:  # teken
                ccl = struct.unpack_from("<I", d, p)[0]
                ch = chr(struct.unpack_from("<I", d, p + 4)[0])
                p += ccl
                if not runs or runs[-1][0] is not font or runs[-1][1] != stroke or runs[-1][2] != fill:
                    runs.append((font, stroke, fill, ""))
                f_, s_, fi_, t_ = runs[-1]
                runs[-1] = (f_, s_, fi_, t_ + ch)
            elif etype == 2:  # lettertype en stijl, gevolgd door verf- en lijnstijlblokken
                fcl = struct.unpack_from("<I", d, p)[0]
                fl = struct.unpack_from("<H", d, p + 4)[0]
                fam = d[p + 6:p + 6 + fl].decode("cp1252", "replace")
                r = p + 6 + fl
                weight = struct.unpack_from("<I", d, r + 4)[0]
                size = struct.unpack_from("<d", d, r + 12)[0]
                if not 0.5 <= size < 5000:
                    size = float(struct.unpack_from("<I", d, r)[0])
                font = dict(family=fam, size=size, points=d[r + 20] == 1, weight=weight, italic=False)
                p += fcl
                colors = []
                while d[p:p + 4] == b"~BK\0":
                    bid, ln = struct.unpack_from("<HI", d, p + 4)
                    if bid == B_PAINTSTYLE:
                        kind = struct.unpack_from("<H", d, p + 14)[0]
                        colors.append((d[p + 20], d[p + 21], d[p + 22]) if kind == 1 else None)
                    p += 10 + ln
                if colors:
                    stroke = colors[0]
                    fill = colors[1] if len(colors) > 1 else None
            else:
                break
        text = "".join(r[3] for r in runs)
        return dict(name=name, visible=visible, anchor=(ax, ay), matrix=m, runs=runs,
                    text=text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n"))

    def adjustment(self, b, e):
        """Aanpassingslaag. Type 2 = curven: vier opzoektabellen (hoofd, R, G, B) van 256 bytes."""
        d = self.d
        cl = struct.unpack_from("<I", d, b)[0]
        kind = struct.unpack_from("<H", d, b + 4)[0]
        out = {"kind": kind}
        if kind == 2:
            luts = []
            # tabellen staan op vaste afstand (299 bytes per kanaal, waarvan 256 de tabel)
            start = b + 49
            for k in range(4):
                t = d[start + k * 299: start + k * 299 + 256]
                if len(t) == 256:
                    luts.append(np.frombuffer(t, np.uint8).copy())
            out["luts"] = luts
        return out

    # ---------------------------------------------------------------- hele bestand
    def read(self) -> Document:
        d = self.d
        info, pal, layers, composite = None, None, [], None
        for bid, body, end in self.blocks(36, len(d)):
            if bid == B_IMAGE:
                info = self.image_info(body)
            elif bid == B_COLOR:
                pal = self.palette(body)
            elif bid == B_LAYER_START:
                first = body
                for lb, b, e in self.blocks(first, end):
                    if lb == B_LAYER:
                        layers.append(self.layer(b, e, info, pal))
            elif bid == B_COMPOSITE_BANK and composite is None:
                composite = (body, end)
        if info is None:
            raise PspError("Geen afbeeldingsgegevens gevonden.")
        return self.to_document(info, layers, composite, pal)

    def composite_image(self, info, composite, pal):
        body, end = composite
        d = self.d
        q = body + (struct.unpack_from("<I", d, body)[0] if self.chunked else 0)
        for bid, b, e in self.blocks(q, end):
            if bid == B_COMPOSITE_IMAGE:
                p = b + struct.unpack_from("<I", d, b)[0]
                if d[p:p + 4] != b"~BK\0":
                    p += struct.unpack_from("<I", d, p)[0]
                chans = []
                cpal = pal
                for cb, bb, ee in self.blocks(p, e):
                    if cb == B_CHANNEL:
                        chans.append(self.channel(bb, ee, info["compression"], info["w"], info["h"]))
                    elif cb == B_COLOR:
                        cpal = self.palette(bb)
                if chans:
                    rgba, _, _ = self.bitmap(info, chans, info["w"], info["h"], cpal)
                    return rgba
        return None

    @staticmethod
    def _mask_image(W, H, fill, L):
        """Grijswaardenmasker: vulwaarde buiten de maskerrechthoek, opgeslagen pixels erbinnen."""
        from PySide6.QtGui import QPainter
        img = new_image(W, H, QColor(fill, fill, fill))
        m = L.get("mask")
        if m is not None:
            g = np.dstack([m, m, m, np.full_like(m, 255)])
            p = QPainter(img)
            p.drawImage(*L["mask_pos"], ops.rgba_to_qimage(g))
            p.end()
        return img

    def to_document(self, info, layers, composite, pal) -> Document:
        from PySide6.QtGui import QPainter
        W, H = info["w"], info["h"]
        doc = Document(W, H, None)
        out = []
        open_groups = []  # [groepslaag, nog te verwachten lagen]
        notes = []
        for L in layers:
            t = L["type"]
            lay = Layer(L["name"] or "Laag", new_image(W, H), L["opacity"] / 255,
                        bool(L["flags"] & 1), PSP_BLEND.get(L["blend"], 0), bool(L["protect"]))
            lay.link_set = L["link"]
            if L.get("highlight"):
                lay.highlight = QColor(*L["highlight"])
            if L["rgba"] is not None:
                part = ops.rgba_to_qimage(L["rgba"])
                p = QPainter(lay.image)
                p.drawImage(*L.get("pos", L["saved"][:2]), part)
                p.end()
            if t == LT_GROUP:
                lay.kind = "group"
            elif t == LT_MASK:
                lay.kind = "mask"
                v = 255 if L["mask_fill"] is None else L["mask_fill"]
                lay.image = self._mask_image(W, H, v, L)
            elif t == LT_ADJUST:
                adj = L["adjust"] or {}
                lay.image = self._mask_image(W, H, 255, L)
                if adj.get("kind") == 2 and adj.get("luts"):
                    master = adj["luts"][0]
                    xs = [0, 32, 64, 96, 128, 160, 192, 224, 255]
                    lay.adjust = (0x8075, {"points": [[x, int(master[x])] for x in xs], "channel": 0})
                    if any(not np.array_equal(t_, np.arange(256)) for t_ in adj["luts"][1:]):
                        notes.append(f"{lay.name}: alleen de hoofdcurve is overgenomen (geen aparte R/G/B curven)")
                else:
                    lay.name += " (aanpassing nog niet ondersteund)"
                    lay.visible = False
                    lay.image = new_image(W, H)
                    notes.append(f"{L['name']}: dit type aanpassingslaag wordt nog niet ondersteund")
            elif t == LT_VECTOR and L.get("shapes"):
                lay.image = render_text_shapes(L["shapes"], W, H, self.px_per_point(info))
                notes.append(f"{L['name']}: tekst is omgezet naar een rasterlaag (nog niet bewerkbaar als tekst)")
            elif t in (LT_VECTOR, LT_ARTMEDIA) and L["rgba"] is None:
                lay.name += " (vectorlaag, nog niet ondersteund)"
                lay.visible = False
                notes.append(f"{L['name']}: deze vectorvormen worden nog niet ondersteund (verborgen)")
            # groepslidmaatschap: de groepskop staat in het bestand vóór zijn lagen
            if open_groups:
                lay.group = open_groups[-1][0]
                for g in open_groups:
                    g[1] -= 1
                while open_groups and open_groups[-1][1] <= 0:
                    open_groups.pop()
            out.append(lay)
            if t == LT_GROUP and L["children"] > 0:
                open_groups.append([lay, L["children"]])
            # oud laagmasker (PSP 7/8): omzetten naar groep + maskerlaag zoals PSP XI dat doet
            if L["mask"] is not None and not L["mask_disabled"] and t not in (LT_MASK, LT_ADJUST):
                mimg = new_image(W, H, QColor(255, 255, 255))
                m = L["mask"]
                g = np.dstack([m, m, m, np.full_like(m, 255)])
                p = QPainter(mimg)
                p.drawImage(L["rect"][0] + L["mask_saved"][0], L["rect"][1] + L["mask_saved"][1], ops.rgba_to_qimage(g))
                p.end()
                grp = Layer(f"Groep - {lay.name}", new_image(W, H))
                grp.kind = "group"
                grp.group = lay.group
                msk = Layer(f"Masker - {lay.name}", mimg)
                msk.kind = "mask"
                msk.group = grp
                lay.group = grp
                out += [msk, grp]
        if not any(l.kind == "raster" and l.adjust is None for l in out):
            rgba = self.composite_image(info, composite, pal) if composite else None
            if rgba is None:
                raise PspError("Dit PSP bestand bevat geen leesbare lagen.")
            out = [Layer("Achtergrond", ops.rgba_to_qimage(rgba))]
        doc.layers = out
        doc.normalize()
        doc.active = len(doc.layers) - 1
        doc.raster_counter = len(doc.layers)
        doc.import_notes = notes
        return doc


def render_text_shapes(shapes, W, H, px_per_pt=1.0):
    """Teken PSP tekstobjecten: begin van de basislijn op het ankerpunt, daarna de vormmatrix."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QTransform
    img = new_image(W, H)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for sh in shapes:
        if not sh["visible"] or not sh["text"]:
            continue
        m = sh["matrix"]
        p.save()
        p.setTransform(QTransform(m[0], m[3], m[1], m[4], m[2], m[5]))
        p.translate(*sh["anchor"])
        x = y = 0.0
        line_h = 0.0
        for f, stroke, fill, chunk in sh["runs"]:
            font = QFont(f["family"])
            font.setPixelSize(max(1, round(f["size"] * (px_per_pt if f["points"] else 1.0))))
            font.setWeight(QFont.Weight(min(1000, max(1, int(f["weight"])))))
            fm = QFontMetricsF(font)
            line_h = max(line_h, fm.lineSpacing())
            parts = chunk.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            for i, part in enumerate(parts):
                if i > 0:
                    x = 0.0
                    y += line_h
                    line_h = fm.lineSpacing()
                if not part:
                    continue
                path = QPainterPath()
                path.addText(QPointF(x, y), font, part)
                if fill is not None:
                    p.fillPath(path, QColor(*fill))
                if stroke is not None:
                    pen = QPen(QColor(*stroke), 1.0)
                    pen.setCosmetic(True)
                    p.strokePath(path, pen)
                x += fm.horizontalAdvance(part)
        p.restore()
    p.end()
    return img


def load(path) -> Document:
    with open(path, "rb") as f:
        data = f.read()
    doc = Reader(data).read()
    doc.path = path
    return doc


def inspect(path):
    """Overzicht voor diagnose: versie, afmetingen en lagen."""
    r = Reader(open(path, "rb").read())
    out = [f"versie {r.major}.{r.minor}"]
    info = None
    for bid, body, end in r.blocks(36, len(r.d)):
        if bid == B_IMAGE:
            info = r.image_info(body)
            out.append(f"{info}")
        elif bid == B_LAYER_START:
            for lb, b, e in r.blocks(body, end):
                if lb == B_LAYER:
                    L = r.layer(b, e, info, None)
                    out.append(f"laag '{L['name']}' type={L['type']} rect={L['saved']} dekking={L['opacity']} "
                               f"meng={L['blend']} vlag={L['flags']} kinderen={L['children']} "
                               f"masker={'ja' if L['mask'] is not None else 'nee'}")
    return "\n".join(out)


# ================================================================ schrijven (PSP 8 formaat, versie 6.0)
# 120 bytes laaginformatie na de naam, overgenomen uit een PSP bestand; we vullen alleen bekende velden in.
_LAYER_TAIL = bytes.fromhex(
    "01000000000000000020030000e8030000000000000000000020030000e8030000ff00010000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000ffff0000ffff0000ffff0000ffff0000ffff0000ffff00"
    "00ffff0000ffff0000ffff0000ffff00ffff4000")
PIGMENT_TO_PSP_BLEND = {v: k for k, v in PSP_BLEND.items()}


def _block(bid, body: bytes) -> bytes:
    return b"~BK\0" + struct.pack("<HI", bid, len(body)) + body


def _channel(plane: np.ndarray, btype, ctype, full_size) -> bytes:
    raw = np.ascontiguousarray(plane, np.uint8).tobytes()
    comp = zlib.compress(raw, 6)
    return _block(B_CHANNEL, struct.pack("<IIIHH", 16, len(comp), full_size, btype, ctype) + comp)


def _layer_block(name, rgba, rect, opacity, blend, visible, protect, link, full_size, background=False):
    nm = name.encode("cp1252", "replace")[:255]
    tail = bytearray(_LAYER_TAIL)
    tail[0] = LT_RASTER
    tail[1:17] = struct.pack("<4i", *rect)
    tail[17:33] = struct.pack("<4i", *rect)
    tail[33] = max(0, min(255, round(opacity * 255)))
    tail[34] = blend
    tail[35] = 1 if visible else 0
    tail[36] = 1 if protect else 0
    tail[37] = link & 0xff
    info = struct.pack("<IH", 6 + len(nm) + len(tail), len(nm)) + nm + bytes(tail)
    nch = 3 if background else 4
    bitmap = struct.pack("<IHH", 8, 1 if background else 2, nch)
    chans = b"".join(_channel(rgba[..., i], 0, i + 1, full_size) for i in range(3))
    if not background:
        chans += _channel(rgba[..., 3], 1, 0, full_size)
    return _block(B_LAYER, info + bitmap + chans)


_CURVE_SEP = bytes.fromhex("2b0100000002000000ffff0000000000000000000000000000000000000000000000000000000000000000")


def _info_chunk(name, ltype, rect, opacity, blend, visible, protect, link, highlight=None, mask_rect=None):
    nm = name.encode("cp1252", "replace")[:255]
    tail = bytearray(_LAYER_TAIL)
    tail[0] = ltype
    tail[1:17] = struct.pack("<4i", *rect)
    tail[17:33] = struct.pack("<4i", 0, 0, rect[2] - rect[0], rect[3] - rect[1])  # relatief t.o.v. rect
    tail[33] = max(0, min(255, round(opacity * 255)))
    tail[34] = blend
    tail[35] = 1 if visible else 0
    tail[36] = 1 if protect else 0
    tail[37] = link & 0xff
    if highlight is not None:
        tail[-5:] = bytes([1, highlight.red(), highlight.green(), highlight.blue(), 0])
    if ltype in (LT_MASK, LT_ADJUST):
        tail[72] = 1  # zo schrijft PSP XI het bij masker- en aanpassingslagen
        if mask_rect is not None:
            tail[38:54] = struct.pack("<4i", *mask_rect)
            tail[54:70] = struct.pack("<4i", 0, 0, mask_rect[2] - mask_rect[0], mask_rect[3] - mask_rect[1])
    return struct.pack("<IH", 6 + len(nm) + len(tail), len(nm)) + nm + bytes(tail)


def _no_bitmap():
    return struct.pack("<IHH", 8, 0, 0)


def _curves_ext(points):
    """Aanpassingslaag curven: zelfde opbouw als PSP XI (hoofdcurve + identieke R/G/B)."""
    from .effects.adjust import _monotone_lut
    master = np.clip(np.rint(_monotone_lut(points)), 0, 255).astype(np.uint8).tobytes()
    ident = bytes(range(256))
    body = struct.pack("<IH", 6, 2)
    for t in (master, ident, ident, ident):
        body += _CURVE_SEP + t
    return _block(B_ADJUST_EXT, body)


def _cropped(rgba):
    """Bijsnijden tot de niet-transparante pixels (zoals PSP opslaat). Geeft (rect, deelbeeld)."""
    ys, xs = np.nonzero(rgba[..., 3])
    if len(xs) == 0:
        return None, None
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return (int(x0), int(y0), int(x1), int(y1)), rgba[y0:y1, x0:x1]


def save(doc, path):
    """Schrijf een .pspimage in het formaat van PSP XI (versie 9.0) met lagen, groepen, maskers en
    curven-aanpassingslagen. Geeft een lijst met waarschuwingen terug."""
    W, H = doc.w, doc.h
    full = W * H * 3
    warn = []
    out = []

    def emit(group):
        for l in doc.children(group):
            blend = PIGMENT_TO_PSP_BLEND.get(l.mode, 0)
            common = (l.opacity, blend, l.visible, l.lock_alpha, l.link_set, l.highlight)
            if l.kind == "group":
                n = len(doc.subtree(l)) - 1
                info = _info_chunk(l.name, LT_GROUP, (0, 0, 0, 0), *common)
                ext = _block(B_GROUP_EXT, struct.pack("<IIB", 9, n, 1))
                out.append(_block(B_LAYER, info + ext + _no_bitmap()))
                emit(l)
            elif l.kind == "mask":
                a = ops.qimage_to_rgba(l.image)
                g = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114).astype(np.uint8)
                if g.min() == g.max():
                    info = _info_chunk(l.name, LT_MASK, (0, 0, 0, 0), *common)
                    ext = _block(B_MASK_EXT, struct.pack("<IIB", 9, int(g[0, 0]), 0x32))
                    out.append(_block(B_LAYER, info + ext + _no_bitmap()))
                else:
                    info = _info_chunk(l.name, LT_MASK, (0, 0, 0, 0), *common, mask_rect=(0, 0, W, H))
                    ext = _block(B_MASK_EXT, struct.pack("<IIB", 9, 255, 0x32))
                    bm = struct.pack("<IHH", 8, 1, 1) + _channel(g, 2, 0, W * H)
                    out.append(_block(B_LAYER, info + ext + bm))
            elif l.adjust is not None:
                if l.adjust[0] == 0x8075 and l.adjust[1].get("channel", 0) == 0:
                    a = ops.qimage_to_rgba(l.image)
                    g = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) * (a[..., 3] / 255)
                    g = np.clip(np.rint(g), 0, 255).astype(np.uint8)
                    if g.min() == 255:
                        info = _info_chunk(l.name, LT_ADJUST, (0, 0, 0, 0), *common)
                        bm = _no_bitmap()
                    else:
                        info = _info_chunk(l.name, LT_ADJUST, (0, 0, 0, 0), *common, mask_rect=(0, 0, W, H))
                        bm = struct.pack("<IHH", 8, 1, 1) + _channel(g, 7, 0, W * H)
                    out.append(_block(B_LAYER, info + _curves_ext(l.adjust[1]["points"]) + bm))
                else:
                    warn.append(f"aanpassingslaag '{l.name}' kan nog niet als PSP aanpassingslaag worden "
                                "bewaard en is weggelaten (in .ora blijft hij bewaard)")
            else:
                rgba = ops.qimage_to_rgba(l.image)
                rect, part = _cropped(rgba)
                if rect is None:
                    info = _info_chunk(l.name, LT_RASTER, (0, 0, 0, 0), *common)
                    out.append(_block(B_LAYER, info + _no_bitmap()))
                    continue
                info = _info_chunk(l.name, LT_RASTER, rect, *common)
                chans = b"".join(_channel(part[..., i], 0, i + 1, full) for i in range(3))
                chans += _channel(part[..., 3], 1, 0, full)
                out.append(_block(B_LAYER, info + struct.pack("<IHH", 8, 2, 4) + chans))
    emit(None)
    nlayers = len(out)
    img = struct.pack("<IiidBHHHIBIiHI", 46, W, H, 72.0, 1, 2, 24, 1, 1 << 24, 0, full,
                      max(0, nlayers - 1), nlayers, 0x05000001)
    body = bytearray(SIG + struct.pack("<HH", 9, 0))
    body += _block(B_IMAGE, img)
    comp = ops.qimage_to_rgba(doc.flattened())
    attr = struct.pack("<IiiHHHIH", 24, W, H, 24, 2, 1, 1 << 24, 0)
    cimg = struct.pack("<IHH", 8, 2, 4) + b"".join(_channel(comp[..., i], 8, i + 1, full) for i in range(3)) \
        + _channel(comp[..., 3], 9, 0, full)
    body += _block(B_COMPOSITE_BANK, struct.pack("<II", 8, 1) + _block(B_COMPOSITE_ATTR, attr)
                   + _block(B_COMPOSITE_IMAGE, cimg))
    body += _block(B_LAYER_START, b"".join(out))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(body)
    import os
    os.replace(tmp, path)
    return warn
