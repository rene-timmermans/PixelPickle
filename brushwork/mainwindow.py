"""Hoofdvenster van Brushwork, met de menu-, werkbalk- en gereedschapsindeling van PSP XI."""
import os
import traceback

import numpy as np
from PySide6.QtCore import QPointF, QRect, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QInputDialog, QLabel,
                               QMainWindow, QMdiArea, QMdiSubWindow, QMenu, QMessageBox, QStyle,
                               QToolBar, QToolButton, QVBoxLayout, QWidget)

from . import dialogs, fileio
from . import imageops as ops
from .canvas import Canvas
from .document import Document, Layer, apply_region, new_image, paint_layer
from .materials import MaterialsPalette
from .palettes import HistoryPalette, LayersPalette
from .psplayout import PALETTES_MENU, PHOTO_MENU, STANDARD_TOOLBAR, TOOLBAR, load_layout
from .tools import DEFAULT_OPTS, TextTool, create_tools, recorded_keys
from . import presets as psp_presets
from .effectdialog import EffectBrowser, EffectDialog
from . import effects as effects_pkg

APP = "Brushwork"


def glyph_icon(glyph, enabled=True, size=24):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    f = QFont()
    f.setPixelSize(int(size * 0.72))
    p.setFont(f)
    if not enabled:
        p.setOpacity(0.35)
    p.setPen(QApplication.palette().windowText().color())  # volgt licht/donker thema
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return QIcon(pm)


class DocWindow(QMdiSubWindow):
    def __init__(self, main, canvas):
        super().__init__()
        self.main, self.canvas = main, canvas
        self.setWidget(canvas)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        d = canvas.doc
        d.titleChanged.connect(self.update_title)
        d.structureChanged.connect(self.update_title)
        self.update_title()

    def update_title(self):
        d = self.canvas.doc
        name = d.title().replace(" *", "*")
        self.setWindowTitle(f"{name} @ {round(self.canvas.zoom * 100)}% ({d.layer().name})")

    def closeEvent(self, e):
        others = [s for s in self.main.mdi.subWindowList() if s is not self and s.canvas.doc is self.canvas.doc]
        if others or self.main.maybe_save(self.canvas.doc):
            e.accept()
        else:
            e.ignore()


class ToolGroupButton(QToolButton):
    """Knop op de gereedschapsbalk; met een uitklappijltje als de groep meer gereedschappen heeft."""

    def __init__(self, main, tools):
        super().__init__()
        self.main, self.tools = main, tools
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setIconSize(QSize(24, 24))
        if len(tools) > 1:
            self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            menu = QMenu(self)
            for t in tools:
                a = menu.addAction(glyph_icon(t.glyph, t.available), t.name)
                key = main.tool_key(t)
                if key:
                    a.setShortcut(QKeySequence(key))
                    a.setShortcutVisibleInContextMenu(True)
                a.triggered.connect(lambda _=False, tool=t: main.select_tool(tool))
            self.setMenu(menu)
        self.clicked.connect(lambda: main.select_tool(self.current))
        self.show_tool(tools[0])

    def show_tool(self, t):
        self.current = t
        self.setIcon(glyph_icon(t.glyph, t.available))
        key = self.main.tool_key(t)
        self.setToolTip(f"{t.name}" + (f" ({key})" if key else "") + (f"\n{t.tip}" if t.tip else ""))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP)
        self.settings = QSettings("Brushwork", "Brushwork")
        self.fg = QColor(0, 0, 0)
        self.bg = QColor(255, 255, 255)
        self.fg_none = self.bg_none = False
        self.opts = dict(DEFAULT_OPTS)
        self.menu_tree, self.tool_keys = load_layout()
        self.effects = effects_pkg.load_all()
        self.last_command = None

        self.mdi = QMdiArea()
        self.mdi.setBackground(QColor(112, 112, 112))
        self.mdi.subWindowActivated.connect(self.on_active)
        self.setCentralWidget(self.mdi)
        self._active_doc = None

        self.tools = create_tools(self)
        self.tool = None
        self._build_docks()
        self._build_tools_toolbar()
        self.actions_by_id = {}
        self.doc_actions = []
        self._build_menus()
        self._build_standard_toolbar()
        self._build_status()
        for keys, fn in ((["Ctrl+Tab", "Ctrl+F6"], self.mdi.activateNextSubWindow),
                         (["Ctrl+Shift+Tab", "Ctrl+Shift+F6"], self.mdi.activatePreviousSubWindow)):
            a = QAction(self)
            a.setShortcuts([QKeySequence(k) for k in keys])
            a.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            a.triggered.connect(fn)
            self.addAction(a)
        self.set_tab_mode(self.settings.value("tabs", "true") == "true")
        self.select_tool(self.tools[0xd091])

        self.resize(1400, 900)
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        state = self.settings.value("state2")
        if state is not None:
            self.restoreState(state)
        self.update_actions()

    # ================================================================ opbouw
    def tool_key(self, tool):
        keys = self.tool_keys.get(tool.cid)
        return keys[0] if keys else ""

    def _build_tools_toolbar(self):
        tb = QToolBar("Gereedschappen")
        tb.setObjectName("tools")
        tb.setOrientation(Qt.Orientation.Vertical)
        tb.setIconSize(QSize(24, 24))
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tb)
        self.tools_toolbar = tb
        self.group_buttons = {}
        for group in TOOLBAR:
            btn = ToolGroupButton(self, [self.tools[c] for c in group])
            tb.addWidget(btn)
            for c in group:
                self.group_buttons[c] = btn
        # sneltoetsen van gereedschappen (uit de PSP instellingen van de gebruiker)
        for cid, keys in self.tool_keys.items():
            if cid in self.tools:
                a = QAction(self)
                a.setShortcuts([QKeySequence(k) for k in keys])
                a.triggered.connect(lambda _=False, t=self.tools[cid]: self.select_tool(t))
                self.addAction(a)

        self.opt_bar = QToolBar("Opties voor gereedschap")
        self.opt_bar.setObjectName("options")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.opt_bar)

    def _dock(self, title, widget, name, area=Qt.DockWidgetArea.RightDockWidgetArea):
        d = QDockWidget(title, self)
        d.setObjectName(name)
        d.setWidget(widget)
        self.addDockWidget(area, d)
        return d

    def _build_docks(self):
        self.materials = MaterialsPalette(self)
        self.layers = LayersPalette(self)
        self.history = HistoryPalette(self)
        self.dock_mat = self._dock("Materialen", self.materials, "materials")
        self.dock_layers = self._dock("Lagen", self.layers, "layers")
        self.dock_hist = self._dock("Geschiedenis", self.history, "history")
        self.dock_hist.hide()

    def handlers(self):
        D = lambda f: (lambda: f(self.doc()))  # noqa: E731
        adj = self.adjust
        return {
            # Bestand
            0xe100: self.file_new, 0xe101: self.file_open, 0xe102: self.close_active,
            0xe103: self.file_save, 0xe104: self.file_save_as, 0xe10b: lambda: self.file_save_as(copy=True),
            0xe141: self.close, 0x812d: self.export_gif, 0x814b: self.export_jpeg,
            # Bewerken
            0xe12b: D(lambda d: d.undo()), 0xe12c: D(lambda d: d.redo()), 0xe128: self.repeat_last,
            0xe123: self.edit_cut, 0xe122: self.edit_copy, 0x8105: lambda: self.edit_copy(merged=True),
            0x80e6: self.paste_new_image, 0x810d: self.paste_new_layer, 0x801e: self.paste_new_selection,
            0x801f: self.paste_into_selection, 0xe120: self.edit_clear,
            0x8020: lambda: QApplication.clipboard().clear(),
            # Beeld
            0x8007: lambda: self.canvas().actual_size(), 0x8132: lambda: self.canvas().zoom_step(True),
            0x8136: lambda: self.canvas().zoom_step(False), 0x801d: self.toggle_fullscreen,
            0x8021: self.toggle_grid,
            0x8185: lambda: self.toggle_dock(self.dock_mat), 0x81ae: lambda: self.toggle_dock(self.dock_layers),
            0x8002: lambda: self.toggle_dock(self.dock_hist), 0x81ba: lambda: self.opt_bar.setVisible(not self.opt_bar.isVisible()),
            0x81f9: lambda: self.tools_toolbar.setVisible(not self.tools_toolbar.isVisible()),
            0xe800: lambda: self.std_toolbar.setVisible(not self.std_toolbar.isVisible()),
            0xe801: lambda: self.statusBar().setVisible(not self.statusBar().isVisible()),
            # Afbeelding
            0x8242: D(lambda d: d.rotate(90)), 0x8243: D(lambda d: d.rotate(-90)), 0x800e: self.free_rotate,
            0x80d1: self.image_resize, 0x80d2: self.image_canvas, 0x807a: self.add_borders,
            0x80cf: self.crop_to_selection, 0x800d: D(lambda d: d.mirror_layer(True)),
            0x800c: D(lambda d: d.mirror_layer(False)), 0x80ed: self.image_info,
            0x8079: D(lambda d: d.apply_to_layer(ops.adj_grayscale, "Grijswaarden")),
            0x804b: D(lambda d: d.apply_to_layer(ops.adj_invert, "Negatief")),
            0x823f: lambda: self.count_colors(False),
            # Aanpassen
            0x8240: D(lambda d: d.apply_to_layer(auto_fix, "Eénstaps-fotocorrectie")),
            0x8057: D(lambda d: d.apply_to_layer(stretch, "Histogram uitbreiden")),
            0x8056: D(lambda d: d.apply_to_layer(equalize, "Histogram egaliseren")),
            0x8052: lambda: adj("Helderheid/contrast", ops.adj_brightness_contrast,
                                [("brightness", "Helderheid:", -100, 100, 0), ("contrast", "Contrast:", -100, 100, 0)]),
            0x8054: lambda: adj("Rood/groen/blauw", ops.adj_rgb, [("red", "Rood %:", -100, 100, 0),
                                ("green", "Groen %:", -100, 100, 0), ("blue", "Blauw %:", -100, 100, 0)]),
            0x8060: lambda: adj("Niveaus", ops.adj_levels, [("black", "Zwartpunt:", 0, 254, 0),
                                ("white", "Witpunt:", 1, 255, 255), ("gamma", "Gamma × 100:", 10, 500, 100)]),
            0x8063: lambda: adj("Drempel", ops.adj_threshold, [("level", "Drempel:", 1, 255, 128)]),
            0x804a: lambda: adj("Inkleuren", ops.adj_colorize, [("hue", "Kleurtoon:", 0, 359, 30),
                                ("saturation", "Verzadiging:", 0, 100, 50)]),
            0x8076: lambda: adj("Kleurtoon/verzadiging/helderheid", ops.adj_hsl,
                                [("hue", "Kleurtoon:", -180, 180, 0), ("saturation", "Verzadiging:", -100, 100, 0),
                                 ("lightness", "Helderheid:", -100, 100, 0)]),
            0x8089: lambda: adj("Grofkorreligheid toevoegen", ops.adj_noise, [("amount", "Ruis %:", 0, 100, 10),
                                ("mono", "Monochroom (0/1):", 0, 1, 0)]),
            0x8066: lambda: adj("Mediaanfilter", ops.adj_median, [("radius", "Straal:", 1, 3, 1)]),
            0x8065: lambda: adj("Gemiddeld", ops.adj_blur, [("radius", "Straal:", 1, 50, 1)]),
            0x8083: D(lambda d: d.apply_to_layer(lambda a: ops.adj_blur(a, 1), "Vervagen")),
            0x8084: D(lambda d: d.apply_to_layer(lambda a: ops.adj_blur(a, 2), "Meer vervagen")),
            0x80b5: lambda: adj("Gaussiaanse vervaging", ops.adj_blur, [("radius", "Straal:", 1, 100, 3)]),
            0x8085: D(lambda d: d.apply_to_layer(lambda a: ops.adj_sharpen(a, 1, 60), "Verscherpen")),
            0x8086: D(lambda d: d.apply_to_layer(lambda a: ops.adj_sharpen(a, 1, 140), "Nog scherper")),
            0x809b: lambda: adj("Onscherp masker", ops.adj_unsharp, [("radius", "Straal:", 1, 100, 2),
                                ("amount", "Sterkte:", 1, 500, 100), ("clip", "Clip:", 0, 100, 5)]),
            0x82db: lambda: adj("High-pass verscherpen", ops.adj_unsharp, [("radius", "Straal:", 1, 100, 10),
                                ("amount", "Sterkte:", 1, 300, 50), ("clip", "Clip:", 0, 0, 0)]),
            0x8087: D(lambda d: d.apply_to_layer(lambda a: ops.adj_blur(a, 1), "Verzachten")),
            0x8088: D(lambda d: d.apply_to_layer(lambda a: ops.adj_blur(a, 2), "Nog zachter")),
            # Effecten
            0x804c: lambda: adj("Aantal niveaus beperken", ops.adj_posterize, [("levels", "Niveaus:", 2, 255, 4)]),
            0x804d: lambda: adj("Solariseren", ops.adj_solarize, [("threshold", "Drempel:", 0, 255, 128)]),
            0x808c: D(lambda d: d.apply_to_layer(ops.adj_emboss, "Bosseleren")),
            # Lagen
            0x8140: self.new_raster_layer, 0x80f7: D(lambda d: d.duplicate_layer()),
            0x80f6: D(lambda d: d.delete_layer()), 0x80fe: self.layer_properties,
            0x8101: D(lambda d: d.arrange_layer("top")), 0x8104: D(lambda d: d.move_layer(1)),
            0x8102: D(lambda d: d.move_layer(-1)), 0x8103: D(lambda d: d.arrange_layer("bottom")),
            0x81d4: D(lambda d: d.merge_down()), 0x80f8: D(lambda d: d.flatten()),
            0x8120: D(lambda d: d.merge_visible()), 0x815d: D(lambda d: d.promote_background()),
            0x8051: lambda: self.count_colors(True),
            0x8191: D(lambda d: d.new_group()), 0x8205: D(lambda d: d.ungroup()), 0x81d5: D(lambda d: d.merge_group()),
            0x81d6: D(lambda d: d.move_into_group()), 0x81d7: D(lambda d: d.move_out_of_group()),
            0x8107: D(lambda d: d.add_mask("hide_all")), 0x8108: D(lambda d: d.add_mask("show_all")),
            0x8106: D(lambda d: d.add_mask("hide_sel")), 0x80e9: D(lambda d: d.add_mask("show_sel")),
            0x80e8: self.mask_from_image, 0x80ec: D(lambda d: d.invert_mask()), 0x821f: self.toggle_mask_overlay,
            0x80ea: self.load_mask, 0x80eb: self.save_mask, 0x80f5: D(lambda d: d.selection_from_mask()),
            # Selecties
            0x80dc: self.select_all, 0x80e2: self.select_none, 0x80dd: self.select_invert,
            0x811b: lambda: self.modify_selection("expand", "Uitbreiden", "Aantal pixels:"),
            0x811c: lambda: self.modify_selection("contract", "Inkrimpen", "Aantal pixels:"),
            0x80e3: lambda: self.modify_selection("feather", "Doezelen", "Aantal pixels:"),
            0x8109: D(lambda d: d.promote_selection()), 0x811a: self.toggle_marquee,
            0x8283: lambda: None,
            # Venster
            0xe130: self.new_window, 0x82ce: lambda: self.set_tab_mode(self.mdi.viewMode() != QMdiArea.ViewMode.TabbedView),
            0xe132: self.mdi.cascadeSubWindows, 0xe133: lambda: self.tile(False), 0xe134: lambda: self.tile(True),
            0x80d3: self.mdi.closeAllSubWindows, 0x80d4: self.duplicate_image, 0x80d5: self.fit_window_to_image,
            0x81d0: lambda: self.canvas().fit(),
            # Help
            0x8028: self.show_shortcuts, 0xe140: self.about, 0xe142: self.about,
        }

    def effect_browser(self):
        dlg = EffectBrowser(self, self.doc(), self.menu_tree)
        if dlg.exec() and dlg.chosen:
            self.run_effect(dlg.chosen)

    PIXEL_CMDS = {0xe120, 0xe123, 0x801f, 0x8079, 0x804b, 0x8240, 0x8057, 0x8056}

    def all_handlers(self):
        H = self.handlers()
        H[0x807b] = self.effect_browser
        H[0x80fa] = self.convert_to_raster
        for cid in self.PIXEL_CMDS:
            if cid in H:
                H[cid] = (lambda f: (lambda: self.ensure_raster() and f()))(H[cid])
        for cid in self.effects:
            H[cid] = lambda c=cid: self.run_effect(c)
        for cid, eff_cid in self.ADJ_LAYERS.items():
            if eff_cid in self.effects:
                H[cid] = lambda c=eff_cid: self.new_adjustment_layer(c)
        return H

    NO_DOC = {0xe100, 0xe101, 0xe141, 0x80e6, 0x8020, 0x8185, 0x81ae, 0x8002, 0x81ba, 0x81f9, 0xe800, 0xe801,
              0x801d, 0x82ce, 0xe132, 0xe133, 0xe134, 0x80d3, 0x8028, 0xe140, 0xe142}
    CHECKABLE = {0x821f: None, 0x8185: "dock_mat", 0x81ae: "dock_layers", 0x8002: "dock_hist", 0x82ce: None, 0x8021: None, 0x811a: None}

    def _build_menus(self):
        self.top_menus = {}
        H = self.all_handlers()
        mb = self.menuBar()

        def build(menu, items):
            for it in items:
                if it is None:
                    menu.addSeparator()
                    continue
                if it["items"] and not (len(it["items"]) == 1 and it["items"][0] and it["items"][0]["id"] == 0xe110):
                    sub = menu.addMenu(it["text"])
                    build(sub, it["items"])
                    continue
                if it["items"]:  # Recente bestanden
                    self.recent_menu = menu.addMenu(it["text"])
                    self.recent_menu.aboutToShow.connect(self._fill_recent)
                    continue
                a = QAction(it["text"], self)
                if it["keys"]:
                    a.setShortcuts([QKeySequence(k) for k in it["keys"]])
                cid = it["id"]
                fn = H.get(cid)
                if fn is None:
                    a.setEnabled(False)
                    a.setStatusTip("Nog niet beschikbaar in deze versie van Brushwork")
                    a.setProperty("unavailable", True)
                else:
                    a.triggered.connect(lambda _=False, f=fn, c=cid: self._run(f, c))
                    if cid not in self.NO_DOC:
                        self.doc_actions.append(a)
                if cid in self.CHECKABLE:
                    a.setCheckable(True)
                menu.addAction(a)
                self.actions_by_id.setdefault(cid, a)

        for top in self.menu_tree:
            m = mb.addMenu(top["text"])
            build(m, top["items"])
            self.top_menus[top["text"].replace("&", "")] = m
            if top["text"].replace("&", "") == "Venster":
                self.window_menu = m
                m.aboutToShow.connect(self._fill_window_menu)
        self._window_entries = []
        a = self.actions_by_id
        for cid, dock in ((0x8185, self.dock_mat), (0x81ae, self.dock_layers), (0x8002, self.dock_hist)):
            if cid in a:
                dock.visibilityChanged.connect(lambda v, act=a[cid]: act.setChecked(v))
                a[cid].setChecked(True)

    def _build_standard_toolbar(self):
        tb = QToolBar("Standaard")
        tb.setObjectName("standard")
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.removeToolBar(self.opt_bar)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.opt_bar)
        self.opt_bar.show()
        self.std_toolbar = tb
        st = self.style()
        icons = {0xe100: st.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
                 0xe101: st.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
                 0xe103: st.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
                 0xe104: glyph_icon("💾"), 0x82ec: glyph_icon("🖨", False),
                 0xe12b: glyph_icon("↶"), 0xe12c: glyph_icon("↷"), 0x80d1: glyph_icon("⤢"),
                 0x8242: glyph_icon("↻"), 0x8243: glyph_icon("↺")}
        for item in STANDARD_TOOLBAR:
            if item is None:
                tb.addSeparator()
            elif isinstance(item, str):
                btn = QToolButton()
                btn.setText(item + " ")
                btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                m = QMenu(btn)
                for cid in (PHOTO_MENU if item == "Foto verbeteren" else PALETTES_MENU):
                    if cid is None:
                        m.addSeparator()
                    elif cid in self.actions_by_id:
                        m.addAction(self.actions_by_id[cid])
                btn.setMenu(m)
                tb.addWidget(btn)
            elif item in self.actions_by_id:
                a = self.actions_by_id[item]
                if item in (0x8136, 0x8132):
                    btn = QToolButton()
                    btn.setDefaultAction(a)
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                    tb.addWidget(btn)
                    btn.setText(("🔍− 100% uitzoomen" if item == 0x8136 else "🔍+ 100% inzoomen"))
                    continue
                if item in icons:
                    a.setIcon(icons[item])
                tb.addAction(a)

    def _build_status(self):
        sb = self.statusBar()
        self.st_pos = QLabel()
        self.st_col = QLabel()
        self.st_info = QLabel()
        for w in (self.st_pos, self.st_col, self.st_info):
            w.setMinimumWidth(120)
            sb.addPermanentWidget(w)

    # ================================================================ hulpjes
    def _run(self, fn, cid=None):
        try:
            fn()
            if cid not in (0xe128, 0xe12b, 0xe12c, None):
                self.last_command = fn
        except Exception as e:
            self.report_error(e)

    def repeat_last(self):
        if self.last_command:
            self.last_command()

    def canvas(self) -> Canvas | None:
        sw = self.mdi.activeSubWindow()
        if sw is None:
            subs = self.mdi.subWindowList()
            sw = subs[-1] if subs else None
        return sw.canvas if sw is not None else None

    def doc(self) -> Document | None:
        cv = self.canvas()
        return cv.doc if cv else None

    def report_error(self, e):
        traceback.print_exc()
        QMessageBox.warning(self, APP, f"Er ging iets mis:\n{e}")

    def update_actions(self):
        has = self.canvas() is not None
        for a in self.doc_actions:
            a.setEnabled(has)

    def on_active(self, sw):
        if sw is None:
            if self.mdi.subWindowList():
                return
            doc = None
        else:
            doc = sw.canvas.doc
        if doc is not self._active_doc:
            self._active_doc = doc
            self.layers.set_doc(doc)
            self.history.set_doc(doc)
        self.update_actions()
        if sw is not None:
            self.update_status(sw.canvas)

    def update_status(self, cv, pt=None):
        if pt is not None:
            x, y = int(pt.x() // 1), int(pt.y() // 1)
            if cv.doc.rect().contains(x, y):
                c = cv.cache.pixelColor(x, y)
                self.st_pos.setText(f"x: {x}  y: {y}")
                self.st_col.setText(f"R{c.red()} G{c.green()} B{c.blue()} A{c.alpha()}")
            else:
                self.st_pos.setText("")
                self.st_col.setText("")
        self.st_info.setText(f"{cv.doc.w} × {cv.doc.h} px   lagen: {len(cv.doc.layers)}")
        w = cv.parentWidget()
        while w is not None and not isinstance(w, DocWindow):
            w = w.parentWidget()
        if w is not None:
            w.update_title()

    def toggle_dock(self, dock):
        dock.setVisible(not dock.isVisible())
        if dock.isVisible():
            dock.raise_()

    # ================================================================ gereedschap en kleur
    def select_tool(self, tool):
        if self.tool is not None:
            self.tool.deactivate()
        self.tool = tool
        for btn in set(self.group_buttons.values()):
            btn.setChecked(False)
        btn = self.group_buttons[tool.cid]
        btn.show_tool(tool)
        btn.setChecked(True)
        self.opt_bar.clear()
        widgets, self.tool_opt_keys = recorded_keys(tool)
        self.opt_bar.addWidget(self._presets_button(tool))
        lbl = QLabel(f"  {tool.name}  ")
        lbl.setStyleSheet("font-weight: bold;")
        self.opt_bar.addWidget(lbl)
        i = 0
        while i < len(widgets):  # label boven het invoerveld, zoals in PSP
            w = widgets[i]
            if isinstance(w, QLabel) and i + 1 < len(widgets):
                box = QWidget()
                v = QVBoxLayout(box)
                v.setContentsMargins(4, 0, 4, 0)
                v.setSpacing(0)
                w.setStyleSheet("font-size: 10px;")
                v.addWidget(w)
                v.addWidget(widgets[i + 1])
                self.opt_bar.addWidget(box)
                i += 2
            else:
                self.opt_bar.addWidget(w)
                i += 1
        self.statusBar().showMessage(f"{tool.name}: {tool.tip}")
        for sw in self.mdi.subWindowList():
            sw.canvas.apply_cursor()
            sw.canvas.update()

    # ---------------------------------------------------------------- voorinstellingen
    def psp_preset_list(self, cid):
        if not hasattr(self, "_psp_presets"):
            try:
                self._psp_presets = psp_presets.scan()
            except Exception:
                self._psp_presets = {}
        return self._psp_presets.get(cid, [])

    def _tool_presets(self, tool):
        import json
        try:
            return json.loads(self.settings.value(f"tool_presets/{tool.cid:04x}", "{}"))
        except (TypeError, ValueError):
            return {}

    def _presets_button(self, tool):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 0, 4, 0)
        v.setSpacing(0)
        lbl = QLabel("Voorinstellingen:")
        lbl.setStyleSheet("font-size: 10px;")
        v.addWidget(lbl)
        b = QToolButton()
        b.setIcon(glyph_icon(tool.glyph, tool.available))
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setToolTip("Voorinstellingen voor dit gereedschap")
        m = QMenu(b)
        m.aboutToShow.connect(lambda: self._fill_tool_presets(m, tool))
        b.setMenu(m)
        v.addWidget(b)
        return box

    def _fill_tool_presets(self, m, tool):
        import json
        m.clear()
        keys = self.tool_opt_keys
        m.addAction("Standaardwaarden", lambda: self._apply_tool_preset(tool, {k: DEFAULT_OPTS[k] for k in keys}))
        own = self._tool_presets(tool)
        psp = [(n, psp_presets.to_tool_opts(f)) for n, f in self.psp_preset_list(tool.cid)]
        psp = [(n, o) for n, o in psp if any(k in keys for k in o)]
        if own:
            m.addSeparator()
            for name, vals in own.items():
                m.addAction(name, lambda v=vals: self._apply_tool_preset(tool, v))
        if psp:
            sub = m.addMenu("PSP voorinstellingen")
            for name, vals in psp:
                sub.addAction(name, lambda v=vals: self._apply_tool_preset(tool, v))
        m.addSeparator()

        def save():
            name, ok = QInputDialog.getText(self, "Voorinstelling opslaan", "Naam:")
            if ok and name.strip():
                allp = self._tool_presets(tool)
                allp[name.strip()] = {k: self.opts[k] for k in keys}
                self.settings.setValue(f"tool_presets/{tool.cid:04x}", json.dumps(allp))
        m.addAction("Opslaan als voorinstelling...", save)
        if own:
            dm = m.addMenu("Verwijderen")
            for name in own:
                def rm(n=name):
                    allp = self._tool_presets(tool)
                    allp.pop(n, None)
                    self.settings.setValue(f"tool_presets/{tool.cid:04x}", json.dumps(allp))
                dm.addAction(name, rm)

    def _apply_tool_preset(self, tool, vals):
        for k, v in vals.items():
            if k in self.opts:
                self.opts[k] = v
        self.select_tool(tool)  # optiebalk opnieuw opbouwen met de nieuwe waarden

    def set_color(self, c, foreground=True):
        if foreground:
            self.fg = QColor(c)
        else:
            self.bg = QColor(c)
        self.materials.refresh()

    def set_none(self, fg, value):
        if fg:
            self.fg_none = value
        else:
            self.bg_none = value
        self.materials.refresh()
        if isinstance(self.tool, TextTool):
            self.tool.refresh()

    def swap_colors(self):
        self.fg_none, self.bg_none = self.bg_none, self.fg_none
        self.fg, self.bg = self.bg, self.fg
        self.materials.refresh()

    def reset_colors(self):
        self.fg, self.bg = QColor(0, 0, 0), QColor(255, 255, 255)
        self.materials.refresh()

    # ================================================================ documenten
    def add_document(self, doc, canvas_of=None):
        cv = Canvas(doc, self)
        sw = DocWindow(self, cv)
        self.mdi.addSubWindow(sw)
        area = self.mdi.viewport().size()
        sw.resize(QSize(min(area.width() - 40, max(400, doc.w + 40)), min(area.height() - 40, max(300, doc.h + 60))))
        sw.show()
        self._hook_tabbar()
        cv.apply_cursor()
        cv.setFocus()
        self.on_active(sw)
        return sw

    def close_active(self):
        sw = self.mdi.activeSubWindow()
        if sw:
            sw.close()

    def maybe_save(self, doc):
        if not doc.modified:
            return True
        r = QMessageBox.question(
            self, APP, f"Wilt u de wijzigingen in {doc.title().rstrip(' *')} opslaan?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save_doc(doc)
        return r == QMessageBox.StandardButton.Discard

    def file_new(self):
        dlg = dialogs.NewImageDialog(self, self.fg, self.bg)
        if dlg.exec():
            w, h, c = dlg.result_values()
            self.add_document(Document(w, h, c))

    def file_open(self):
        start = self.settings.value("lastdir", os.path.expanduser("~/Afbeeldingen"))
        paths, _ = QFileDialog.getOpenFileNames(self, "Openen", start, fileio.OPEN_FILTER)
        for p in paths:
            self.open_path(p)

    def open_path(self, path):
        for sw in self.mdi.subWindowList():
            if sw.canvas.doc.path and os.path.abspath(sw.canvas.doc.path) == os.path.abspath(path):
                self.mdi.setActiveSubWindow(sw)
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            doc = fileio.load(path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP, f"Kan het bestand niet openen:\n{path}\n\n{e}")
            return
        QApplication.restoreOverrideCursor()
        self.settings.setValue("lastdir", os.path.dirname(path))
        self._add_recent(path)
        self.add_document(doc)

    def _add_recent(self, path):
        rec = [p for p in (self.settings.value("recent") or []) if p != path]
        self.settings.setValue("recent", [path] + rec[:9])

    def _fill_recent(self):
        self.recent_menu.clear()
        for i, p in enumerate(self.settings.value("recent") or []):
            a = self.recent_menu.addAction(f"&{i + 1} {p}" if i < 9 else p)
            a.triggered.connect(lambda _=False, path=p: self.open_path(path))
        if self.recent_menu.isEmpty():
            self.recent_menu.addAction("(leeg)").setEnabled(False)

    def file_save(self):
        self.save_doc(self.doc())

    def file_save_as(self, copy=False):
        self.save_doc(self.doc(), ask=True, copy=copy)

    def save_doc(self, doc, ask=False, copy=False):
        path = doc.path
        ext = os.path.splitext(path)[1].lower() if path else ""
        writable = {".pspimage", ".psp", ".ora", ".png", ".jpg", ".jpeg", ".jpe", ".tif", ".tiff", ".bmp", ".webp", ".gif", ".tga"}
        if ask or not path or ext not in writable:
            base = os.path.splitext(path)[0] if path else os.path.join(
                self.settings.value("lastdir", os.path.expanduser("~/Afbeeldingen")), doc.untitled)
            default_ext = ".pspimage" if len(doc.layers) > 1 else ".png"
            path, flt = QFileDialog.getSaveFileName(self, "Opslaan als", base + default_ext, fileio.SAVE_FILTER,
                                                    "Paint Shop Pro (*.pspimage)" if default_ext == ".pspimage" else "PNG (*.png)")
            if not path:
                return False
            if not os.path.splitext(path)[1]:
                path += "." + flt.split("*.")[1].split(" ")[0].rstrip(")")
            ext = os.path.splitext(path)[1].lower()
        if ext not in fileio.LAYERED and len(doc.layers) > 1:
            r = QMessageBox.question(self, APP, "Dit formaat kan geen lagen bewaren. De afbeelding wordt "
                                     "samengevoegd opgeslagen; uw lagen blijven in Brushwork behouden.\n\n"
                                     "Tip: gebruik .ora om de lagen te bewaren.\n\nDoorgaan?")
            if r != QMessageBox.StandardButton.Yes:
                return False
        quality = 90
        if ext in (".jpg", ".jpeg", ".jpe", ".webp"):
            quality, ok = QInputDialog.getInt(self, "Kwaliteit", "Kwaliteit (1 tot 100):",
                                              int(self.settings.value("quality", 90)), 1, 100)
            if not ok:
                return False
            self.settings.setValue("quality", quality)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            warnings = fileio.save(doc, path, quality) or []
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP, f"Opslaan mislukt:\n{e}")
            return False
        QApplication.restoreOverrideCursor()
        if warnings:
            QMessageBox.information(self, APP, "Opgeslagen, met deze aanpassingen voor het PSP formaat:\n\n• "
                                    + "\n• ".join(warnings) + "\n\nTip: bewaar ook een .ora om alles bewerkbaar te houden.")
        self.settings.setValue("lastdir", os.path.dirname(path))
        self._add_recent(path)
        if not copy:
            doc.path = path
            doc.set_modified(False)
            doc.titleChanged.emit()
        self.statusBar().showMessage(f"Opgeslagen: {path}", 4000)
        return True

    def _export_path(self, doc, ext, title):
        base = os.path.splitext(doc.path)[0] if doc.path else os.path.join(
            self.settings.value("lastdir", os.path.expanduser("~/Afbeeldingen")), doc.untitled)
        path, _ = QFileDialog.getSaveFileName(self, title, base + ext, f"{ext[1:].upper()} (*{ext})")
        if path and not path.lower().endswith(ext):
            path += ext
        return path

    def export_gif(self):
        d = self.doc()
        dlg = dialogs.GifExportDialog(self, d)
        if not dlg.exec():
            return
        path = self._export_path(d, ".gif", "GIF exporteren")
        if path:
            fileio.save_gif(path, dlg.result(), dlg.interlace.isChecked())
            self.statusBar().showMessage(f"Geëxporteerd: {path}", 4000)

    def export_jpeg(self):
        d = self.doc()
        dlg = dialogs.JpegExportDialog(self, int(self.settings.value("quality", 90)))
        if not dlg.exec():
            return
        path = self._export_path(d, ".jpg", "JPEG exporteren")
        if path:
            from PIL import Image
            arr = ops.qimage_to_rgba(d.flattened(QColor(255, 255, 255)))
            Image.fromarray(arr[..., :3]).save(path, "JPEG", quality=dlg.q.value(), progressive=dlg.prog.isChecked(),
                                              subsampling=[0, 1, 2][dlg.sub.currentIndex()], optimize=True)
            self.statusBar().showMessage(f"Geëxporteerd: {path}", 4000)

    # ================================================================ bewerken
    def _selection_image(self, merged=False):
        d = self.doc()
        r = d.selection_bbox() if d.sel is not None else d.rect()
        if r.isEmpty():
            return None, r
        src = self.canvas().cache if merged else d.layer().image
        img = src.copy(r)
        if d.sel is not None:
            p = QPainter(img)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            p.drawImage(0, 0, d.sel.copy(r))
            p.end()
        return img, r

    def edit_copy(self, merged=False):
        img, _ = self._selection_image(merged)
        if img is not None:
            QApplication.clipboard().setImage(img)

    def edit_cut(self):
        self.edit_copy()
        self.edit_clear(label="Knippen")

    def edit_clear(self, label="Wissen"):
        d = self.doc()
        r = d.selection_bbox() if d.sel is not None else d.rect()
        if r.isEmpty():
            return
        d.push_undo(label)
        # achtergrondlaag wordt gewist naar de achtergrondkleur, andere lagen naar transparant (zoals PSP)
        bg = d.active == 0 and d.layer().name == "Achtergrond"
        paint_layer(d.layer(), r, new_image(r.width(), r.height(), self.bg if bg else None), d.sel)
        d.changed.emit(r)
        d.structureChanged.emit()

    def _clip_image(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            self.statusBar().showMessage("Het klembord bevat geen afbeelding.", 3000)
            return None
        return img.convertToFormat(ops.FMT)

    def paste_new_image(self):
        img = self._clip_image()
        if img is None:
            return
        doc = Document(img.width(), img.height(), None)
        doc.layers[0].image = img
        self.add_document(doc)

    def _centered_layer(self, d, img, pos=None):
        layer_img = new_image(d.w, d.h)
        p = QPainter(layer_img)
        x, y = pos if pos else ((d.w - img.width()) // 2, (d.h - img.height()) // 2)
        p.drawImage(x, y, img)
        p.end()
        return layer_img, QRect(x, y, img.width(), img.height())

    def paste_new_layer(self):
        img, d = self._clip_image(), self.doc()
        if img is None or d is None:
            return
        layer_img, _ = self._centered_layer(d, img)
        d.add_layer(Layer(d.next_raster_name(), layer_img), label="Plakken als nieuwe laag")

    def paste_new_selection(self):
        img, d = self._clip_image(), self.doc()
        if img is None or d is None:
            return
        layer_img, r = self._centered_layer(d, img)
        d.add_layer(Layer(d.next_raster_name(), layer_img), label="Plakken als nieuwe selectie")
        a = ops.qimage_to_rgba(layer_img)[..., 3]
        d.set_selection(ops.mask_to_qimage(a))
        self.select_tool(self.tools[0xd021])

    def paste_into_selection(self):
        img, d = self._clip_image(), self.doc()
        if img is None or d is None or d.sel is None:
            return
        r = d.selection_bbox()
        scaled = img.scaled(r.width(), r.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        d.push_undo("Plakken in selectie")
        local = d.layer().image.copy(r)
        p = QPainter(local)
        p.drawImage(0, 0, scaled)
        p.end()
        paint_layer(d.layer(), r, local, d.sel)
        d.changed.emit(r)
        d.structureChanged.emit()

    # ================================================================ afbeelding
    def crop_to_selection(self):
        d = self.doc()
        if d.sel is not None:
            d.crop(d.selection_bbox())

    def image_resize(self):
        d = self.doc()
        dlg = dialogs.ResizeDialog(self, d.w, d.h)
        if dlg.exec():
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            d.resize_image(dlg.w.value(), dlg.h.value(), dlg.mode.currentIndex() == 0)
            QApplication.restoreOverrideCursor()

    def image_canvas(self):
        d = self.doc()
        dlg = dialogs.CanvasSizeDialog(self, d.w, d.h)
        if dlg.exec():
            ox, oy = dlg.offsets()
            d.canvas_size(dlg.w.value(), dlg.h.value(), ox, oy, self.bg)

    def free_rotate(self):
        d = self.doc()
        dlg = dialogs.FreeRotateDialog(self)
        if dlg.exec():
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            d.rotate_free(dlg.angle(), False, self.bg)
            QApplication.restoreOverrideCursor()

    def add_borders(self):
        dlg = dialogs.BordersDialog(self, self.bg)
        if dlg.exec():
            l, t, r, b = dlg.values()
            d = self.doc()
            if len(d.layers) > 1:
                d.flatten()
            d.add_borders(l, t, r, b, dlg.color)

    def image_info(self):
        d = self.doc()
        size = os.path.getsize(d.path) if d.path and os.path.exists(d.path) else 0
        mem = sum(l.image.sizeInBytes() for l in d.layers)
        QMessageBox.information(self, "Afbeeldingsgegevens", (
            f"<b>{d.title()}</b><br>Pad: {d.path or '(niet opgeslagen)'}<br>"
            f"Afmetingen: {d.w} × {d.h} pixels ({d.w * d.h / 1e6:.2f} megapixel)<br>"
            f"Kleurdiepte: RGB 8 bits/kanaal<br>Lagen: {len(d.layers)}<br>"
            f"Bestandsgrootte: {size / 1024:.0f} kB<br>Geheugen: {mem / 1048576:.1f} MB"))

    def count_colors(self, layer_only):
        d = self.doc()
        img = d.layer().image if layer_only else self.canvas().cache
        a = ops.qimage_to_rgba(img)
        n = len(np.unique(a[..., :3].reshape(-1, 3).view(np.dtype((np.void, 3)))))
        QMessageBox.information(self, APP, f"Aantal unieke kleuren: {n:,}".replace(",", "."))

    def adjust(self, title, fn, params):
        dialogs.AdjustDialog(self, self.doc(), title, fn, params).exec()

    # ================================================================ lagen
    def layer_properties(self):
        d = self.doc()
        l = d.layer()
        if l.adjust is not None:  # aanpassingslaag: instellingen van het effect bewerken
            eff = self.effects.get(l.adjust[0])
            if eff is None:
                return
            dlg = EffectDialog(self, d, eff, dict(l.adjust[1]), mode="params")
            if dlg.exec():
                d.push_undo("Aanpassingslaag bewerken")
                l.adjust = (l.adjust[0], dlg.params())
                d.changed.emit(QRect())
                d.structureChanged.emit()
            return
        dlg = dialogs.LayerPropertiesDialog(self, l, d)
        if dlg.exec():
            d.push_undo("Laageigenschappen")
            for k, v in dlg.values().items():
                setattr(l, k, v)
            d.structureChanged.emit()
            d.changed.emit(QRect())
            d.titleChanged.emit()

    def mask_from_image(self):
        dlg = dialogs.MaskFromImageDialog(self)
        if dlg.exec():
            src, inv = dlg.values()
            self.doc().add_mask(src, inv)

    def toggle_mask_overlay(self):
        self.mask_overlay = not getattr(self, "mask_overlay", False)
        a = self.actions_by_id.get(0x821f)
        if a:
            a.setChecked(self.mask_overlay)
        for sw in self.mdi.subWindowList():
            sw.canvas.recompose()
            sw.canvas.update()

    def load_mask(self):
        path, _ = QFileDialog.getOpenFileName(self, "Masker laden vanaf schijf", self.settings.value("lastdir", ""),
                                              "Afbeeldingen (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif)")
        if not path:
            return
        d = self.doc()
        img = QImage(path)
        if img.isNull():
            return
        img = img.scaled(d.w, d.h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        d.add_mask("show_all")
        d.layer().image = img.convertToFormat(ops.FMT)
        d.changed.emit(QRect())
        d.structureChanged.emit()

    def save_mask(self):
        d = self.doc()
        if d.layer().kind != "mask":
            self.statusBar().showMessage("Kies eerst een maskerlaag.", 4000)
            return
        path = self._export_path(d, ".png", "Masker opslaan op schijf")
        if path:
            d.layer().image.save(path)

    def new_raster_layer(self):
        d = self.doc()
        layer = Layer(f"Raster {d.raster_counter + 1}", new_image(d.w, d.h))
        dlg = dialogs.LayerPropertiesDialog(self, layer, None, "Nieuwe rasterlaag")
        if dlg.exec():
            d.raster_counter += 1
            for k, v in dlg.values().items():
                setattr(layer, k, v)
            d.add_layer(layer, label="Nieuwe rasterlaag")

    ADJ_LAYERS = {0x8144: 0x8052, 0x8147: 0x8062, 0x8145: 0x82dc, 0x8143: 0x8075, 0x8146: 0x8076,
                  0x8148: 0x804b, 0x8142: 0x8060, 0x814a: 0x804c, 0x8149: 0x8063}

    def new_adjustment_layer(self, eff_cid):
        d = self.doc()
        eff = self.effects.get(eff_cid)
        if eff is None:
            return
        layer = Layer(eff.name, new_image(d.w, d.h, QColor(255, 255, 255)))
        if eff.params:
            dlg = EffectDialog(self, d, eff, None, mode="params")
            if not dlg.exec():
                return
            params = dlg.params()
        else:
            params = {}
        layer.adjust = (eff_cid, params)
        d.add_layer(layer, label="Nieuwe aanpassingslaag")

    # ================================================================ snelmenu's (rechtsklik)
    CANVAS_MENU = [0xe12b, 0xe12c, None, 0xe123, 0xe122, 0x8105, 0x810d, 0x801e, 0x801f, 0xe120, None,
                   0x80dc, 0x80e2, 0x80dd, 0x8109, 0x80e4, 0x80e5, None,
                   "Selecties", "Lagen", "Afbeelding", "Aanpassen", "Effecten", None,
                   0x8132, 0x8136, 0x8007, 0x81d0]

    def _fill_menu(self, m, items):
        for it in items:
            if it is None:
                if m.actions() and not m.actions()[-1].isSeparator():
                    m.addSeparator()
            elif isinstance(it, str):
                if it in self.top_menus:
                    m.addMenu(self.top_menus[it])
            elif it in self.actions_by_id:
                m.addAction(self.actions_by_id[it])

    def show_canvas_menu(self, cv, pos):
        """Snelmenu op de afbeelding, met dezelfde opdrachten als de menubalk."""
        self.mdi.setActiveSubWindow(self._subwindow_of(cv))
        m = QMenu(self)
        extra = list(self.tool.context_actions(cv))
        d = cv.doc
        if d.layer().text is not None:
            extra.append(("Tekst bewerken", lambda: self.edit_text_layer(cv)))
            extra.append(("Omzetten in rasterlaag", self.convert_to_raster))
        for label, fn in extra:
            m.addAction(label, lambda f=fn: self._run(f))
        if extra:
            m.addSeparator()
        self._fill_menu(m, self.CANVAS_MENU)
        m.exec(cv.mapToGlobal(pos.toPoint()))

    def _subwindow_of(self, cv):
        w = cv.parentWidget()
        while w is not None and not isinstance(w, DocWindow):
            w = w.parentWidget()
        return w

    def edit_text_layer(self, cv):
        """Tekst bewerken via het snelmenu: tekstgereedschap kiezen en de actieve tekstlaag openen."""
        from .textlayer import bounds
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent
        t = self.tools[0xd0f0]
        self.select_tool(t)
        c = bounds(cv.doc.layer().text, cv.doc.px_per_pt).center()
        w = cv.to_widget(c)
        t.press(cv, c, QMouseEvent(QEvent.Type.MouseButtonPress, w, cv.mapToGlobal(w.toPoint()),
                                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    def show_tab_menu(self, pos):
        bar = self.sender()
        i = bar.tabAt(pos)
        subs = self.mdi.subWindowList()
        if i < 0 or i >= len(subs):
            return
        self.mdi.setActiveSubWindow(subs[i])
        m = QMenu(self)
        self._fill_menu(m, [0xe103, 0xe104, 0xe10b, None, 0xe102, 0x80d3, None, 0x80d4, 0xe130, None, 0x80ed])
        m.exec(bar.mapToGlobal(pos))

    def ensure_raster(self):
        """Tekstlaag eerst omzetten naar een rasterlaag (met bevestiging, zoals PSP)."""
        d = self.doc()
        if d is None or d.layer().text is None:
            return True
        r = QMessageBox.question(self, APP, "Dit is een tekstlaag. Om erop te schilderen of een effect toe te passen "
                                 "moet hij eerst een rasterlaag worden; de tekst is daarna niet meer bewerkbaar.\n\n"
                                 "Omzetten in rasterlaag?")
        if r != QMessageBox.StandardButton.Yes:
            return False
        self.convert_to_raster()
        return True

    def convert_to_raster(self):
        d = self.doc()
        if d.layer().text is None:
            return
        d.push_undo("Omzetten in rasterlaag")
        d.layer().text = None
        d.structureChanged.emit()

    def run_effect(self, cid):
        d = self.doc()
        if not self.ensure_raster():
            return
        eff = self.effects[cid]
        if d.layer().adjust is not None:
            self.statusBar().showMessage("Kies een rasterlaag; op een aanpassingslaag werken effecten niet.", 4000)
            return
        if not eff.params:
            from .effects import Ctx
            ctx = Ctx(fg=self.fg.getRgb()[:3], bg=self.bg.getRgb()[:3])
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                d.apply_to_layer(lambda a: eff.fn(a, ctx), eff.name)
            finally:
                QApplication.restoreOverrideCursor()
            return
        EffectDialog(self, d, eff).exec()

    # ================================================================ selecties
    def select_all(self):
        d = self.doc()
        d.push_undo("Alles selecteren")
        d.select_all()

    def select_none(self):
        d = self.doc()
        if d.sel is not None:
            d.push_undo("Niets selecteren")
            d.set_selection(None)

    def select_invert(self):
        d = self.doc()
        if d.sel is not None:
            d.push_undo("Selectie omkeren")
            d.invert_selection()

    def modify_selection(self, kind, title, label):
        d = self.doc()
        if d.sel is None:
            self.statusBar().showMessage("Er is geen selectie.", 3000)
            return
        n, ok = QInputDialog.getInt(self, title, label, 5, 1, 500)
        if ok:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            d.modify_selection(kind, n)
            QApplication.restoreOverrideCursor()

    def toggle_marquee(self):
        cv = self.canvas()
        cv.hide_marquee = not getattr(cv, "hide_marquee", False)
        cv.update()

    # ================================================================ beeld en venster
    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def toggle_grid(self):
        cv = self.canvas()
        if cv:
            cv.show_grid = not getattr(cv, "show_grid", False)
            cv.update()

    def set_tab_mode(self, on):
        self.mdi.setViewMode(QMdiArea.ViewMode.TabbedView if on else QMdiArea.ViewMode.SubWindowView)
        self.mdi.setTabsClosable(True)
        self.mdi.setTabsMovable(True)
        self.mdi.setDocumentMode(True)
        self._hook_tabbar()
        self.settings.setValue("tabs", "true" if on else "false")
        a = getattr(self, "actions_by_id", {}).get(0x82ce)
        if a:
            a.setChecked(on)

    def _hook_tabbar(self):
        """Snelmenu op de tabbladen (de tabbalk maakt Qt pas aan als er documenten zijn)."""
        from PySide6.QtWidgets import QTabBar
        for bar in self.mdi.findChildren(QTabBar):
            if bar.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu:
                bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                bar.customContextMenuRequested.connect(self.show_tab_menu)

    def _fill_window_menu(self):
        """Zoals PSP: genummerde lijst van open afbeeldingen onderaan, en vensterschikking grijs bij tabbladen."""
        m = self.window_menu
        for a in self._window_entries:
            m.removeAction(a)
        self._window_entries = []
        tabs = self.mdi.viewMode() == QMdiArea.ViewMode.TabbedView
        for cid in (0xe132, 0xe133, 0xe134, 0x80d5):
            a = self.actions_by_id.get(cid)
            if a:
                a.setEnabled(not tabs and bool(self.mdi.subWindowList()))
        if 0x82ce in self.actions_by_id:
            self.actions_by_id[0x82ce].setChecked(tabs)
        subs = self.mdi.subWindowList()
        if subs:
            self._window_entries.append(m.addSeparator())
        active = self.mdi.activeSubWindow()
        for i, sw in enumerate(subs):
            title = sw.windowTitle()
            a = m.addAction((f"&{i + 1} " if i < 9 else "") + title)
            a.setCheckable(True)
            a.setChecked(sw is active)
            a.triggered.connect(lambda _=False, w=sw: self.mdi.setActiveSubWindow(w))
            self._window_entries.append(a)

    def tile(self, side_by_side):
        subs = [s for s in self.mdi.subWindowList() if not s.isMinimized()]
        if not subs:
            return
        if self.mdi.viewMode() == QMdiArea.ViewMode.TabbedView:
            self.set_tab_mode(False)
        area = self.mdi.viewport().rect()
        n = len(subs)
        for i, s in enumerate(subs):
            s.showNormal()
            if side_by_side:
                w = area.width() // n
                s.setGeometry(i * w, 0, w, area.height())
            else:
                h = area.height() // n
                s.setGeometry(0, i * h, area.width(), h)

    def new_window(self):
        d = self.doc()
        self.add_document(d)

    def duplicate_image(self):
        d = self.doc()
        nd = Document(d.w, d.h, None)
        nd.layers = [l.clone() for l in d.layers]
        nd.active = d.active
        self.add_document(nd)

    def fit_window_to_image(self):
        sw = self.mdi.activeSubWindow()
        if sw and self.mdi.viewMode() == QMdiArea.ViewMode.SubWindowView:
            cv = sw.canvas
            sw.resize(int(cv.doc.w * cv.zoom) + (sw.width() - cv.width()) + 4,
                      int(cv.doc.h * cv.zoom) + (sw.height() - cv.height()) + 4)
            cv.center()

    def show_shortcuts(self):
        rows = []

        def walk(items, path):
            for it in items:
                if not it:
                    continue
                name = it["text"].replace("&", "")
                if it["items"]:
                    walk(it["items"], path + [name])
                elif it["keys"]:
                    rows.append((" > ".join(path + [name]), ", ".join(it["keys"])))
        walk(self.menu_tree, [])
        tools = [(f"Gereedschap: {t.name}", self.tool_key(t)) for t in self.tools.values() if self.tool_key(t)]
        html = "<table cellspacing=3>" + "".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a, b in tools + rows) + "</table>"
        box = QMessageBox(self)
        box.setWindowTitle("Toetsenbordlayout")
        box.setText(html)
        box.exec()

    def about(self):
        QMessageBox.about(self, "Over Brushwork", "<b>Brushwork</b><br>Een fotobewerker voor Linux met de vertrouwde "
                          "indeling van klassieke Windows fotobewerkers.<br>Python, Qt en NumPy.")

    def closeEvent(self, e):
        seen = set()
        for sw in list(self.mdi.subWindowList()):
            d = sw.canvas.doc
            if id(d) in seen:
                continue
            seen.add(id(d))
            self.mdi.setActiveSubWindow(sw)
            if not self.maybe_save(d):
                e.ignore()
                return
            d.set_modified(False)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state2", self.saveState())
        e.accept()


# ---------------------------------------------------------------- automatische correcties
def stretch(a, lo=0.5, hi=99.5):
    out = a.copy()
    for c in range(3):
        ch = a[..., c].astype(np.float32)
        l, h = np.percentile(ch, [lo, hi])
        if h - l > 1:
            out[..., c] = np.clip((ch - l) * 255 / (h - l), 0, 255)
    return out


def equalize(a):
    y = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114).astype(np.uint8)
    hist = np.bincount(y.ravel(), minlength=256)
    cdf = hist.cumsum()
    cdf = (cdf - cdf.min()) * 255 / max(1, cdf.max() - cdf.min())
    ny = cdf[y]
    ratio = (ny + 1) / (y.astype(np.float32) + 1)
    out = a.copy()
    out[..., :3] = np.clip(a[..., :3] * ratio[..., None], 0, 255)
    return out


def auto_fix(a):
    out = stretch(a, 0.3, 99.7)
    return ops.adj_hsl(out, 0, 8, 0)
