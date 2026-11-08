"""Hoofdvenster van PixelPickle, met de menu-, werkbalk- en gereedschapsindeling van PSP XI."""
import os
import traceback

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QDockWidget, QFileDialog, QHBoxLayout,
                               QInputDialog, QLabel,
                               QMainWindow, QMdiArea, QMdiSubWindow, QMenu, QMessageBox, QStyle,
                               QStatusBar, QToolBar, QToolButton, QVBoxLayout, QWidget)

from . import dialogs, fileio
from . import imageops as ops
from .canvas import Canvas
from .document import BG_NAMES, Document, Layer, apply_region, new_image, paint_layer, raster_name
from .i18n import tr
from .materials import MaterialsPalette
from .palettes import HistoryPalette, LayersPalette
from .psplayout import PALETTES_MENU, PHOTO_MENU, STANDARD_TOOLBAR, TOOLBAR, load_layout
from .tools import DEFAULT_OPTS, TextTool, create_tools, recorded_keys
from . import presets as psp_presets
from .effectdialog import EffectBrowser, EffectDialog
from . import effects as effects_pkg

APP = "PixelPickle"


def glyph_icon(glyph, enabled=True, size=24):
    """Icoon voor een gereedschap of werkbalkknop: een eigen lijnicoon in de accentkleur van het thema
    (zie icons.py); alleen als daar geen tekening voor is, het teken zelf."""
    from . import icons
    ic = icons.icon(glyph, enabled)
    if ic is not None:
        return ic
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
        from .canvas import CanvasView
        self.setWidget(CanvasView(canvas))  # canvas met schuifbalken
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # het ingebouwde vensterknopmenu van Qt heeft eigen sneltoetsen (Ctrl+F4, Ctrl+W ...); die botsen met de
        # menu's (Sluiten, Aanpassen aan afbeelding) en dan werkt geen van beide: hier weghalen
        if self.systemMenu() is not None:
            for a in self.systemMenu().actions():
                a.setShortcuts([])
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
                key = main.tool_key(t)
                # de letter alleen tonen (rechts in het menu), niet als tweede sneltoets: de sneltoets zit al op
                # het gereedschap zelf, en twee acties met dezelfde toets maakt Qt "dubbelzinnig" (dan werkt geen van beide)
                a = menu.addAction(glyph_icon(t.glyph, t.available), f"{t.name}\t{key}" if key else t.name)
                a.triggered.connect(lambda _=False, tool=t: main.select_tool(tool))
            self.setMenu(menu)
        self.clicked.connect(lambda: main.select_tool(self.current))
        self.show_tool(tools[0])

    def show_tool(self, t):
        self.current = t
        self.setIcon(glyph_icon(t.glyph, t.available))
        key = self.main.tool_key(t)
        self.setToolTip(f"{t.name}" + (f" ({key})" if key else "") + (f"\n{t.tip}" if t.tip else ""))


def restart_pixelpickle():
    """Start PixelPickle opnieuw: de geïnstalleerde starter, of anders vanuit de broncode."""
    import shutil
    import sys
    from PySide6.QtCore import QProcess, QProcessEnvironment
    launcher = shutil.which("pixelpickle")
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if launcher and pkg_parent == "/usr/share/pixelpickle":
        QProcess.startDetached(launcher, [])
        return
    p = QProcess()
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONPATH", pkg_parent + os.pathsep + env.value("PYTHONPATH", ""))
    p.setProcessEnvironment(env)
    p.setProgram(sys.executable)
    p.setArguments(["-m", "pixelpickle"])
    p.startDetached()


class TrStatusBar(QStatusBar):
    """Statusbalk die meldingen in de gekozen taal toont."""

    def showMessage(self, text, timeout=0):
        super().showMessage(tr(text), timeout)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStatusBar(TrStatusBar())
        self.setWindowTitle(APP)
        self.settings = QSettings("PixelPickle", "PixelPickle")
        from .materials import load_user_gradients
        load_user_gradients()
        from .viewaids import DEFAULTS as _VD
        import json as _json
        try:
            saved = _json.loads(self.settings.value("view_opts", "{}") or "{}")
        except ValueError:
            saved = {}
        self.view_opts = {**_VD, **{k: v for k, v in saved.items() if k in _VD}}
        QApplication.instance().installEventFilter(self)
        self.fg = QColor(0, 0, 0)
        self.bg = QColor(255, 255, 255)
        self.fg_none = self.bg_none = False
        self.fg_mat = self.bg_mat = None  # verloop of patroon in plaats van effen kleur
        self._last_mat = {}  # (voorgrond?, soort) -> laatst gekozen verloop/patroon
        self.opts = dict(DEFAULT_OPTS)
        self.menu_tree, self.tool_keys = load_layout()
        self.effects = effects_pkg.load_all()
        self.last_command = None

        self.mdi = QMdiArea()
        self.mdi.setBackground(QColor(112, 112, 112))
        self.mdi.subWindowActivated.connect(self.on_active)
        self.mdi.viewport().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mdi.viewport().customContextMenuRequested.connect(self.show_workspace_menu)
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
        from .autosave import AutoSaver
        self.autosaver = AutoSaver(self)
        # zonder afbeelding is er geen gereedschap actief (zoals in PSP); bij de eerste afbeelding
        # wordt het laatst gebruikte gereedschap weer gekozen, ook na een herstart
        try:
            last = int(str(self.settings.value("last_tool", "d001")), 16)
        except ValueError:
            last = 0xd001
        t = self.tools.get(last)
        self._last_tool = t if t is not None and t.available and last in self.group_buttons else self.tools[0xd001]

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
        # past de balk niet in het venster, dan valt de pijlknop op in de accentkleur van het thema
        tb.setStyleSheet("QToolButton#qt_toolbar_ext_button { background-color: palette(highlight);"
                         " border-radius: 4px; }")
        self.group_buttons = {}
        for group in TOOLBAR:
            tools = [self.tools[c] for c in group if self.tools[c].available]
            if not tools:  # nog niet gebouwde gereedschappen niet tonen
                continue
            btn = ToolGroupButton(self, tools)
            tb.addWidget(btn)
            for t in tools:
                self.group_buttons[t.cid] = btn
        # sneltoetsen van gereedschappen (uit de PSP instellingen van de gebruiker)
        for cid, keys in self.tool_keys.items():
            if cid in self.tools and self.tools[cid].available:
                a = QAction(self)
                a.setShortcuts([QKeySequence(k) for k in keys])
                a.triggered.connect(lambda _=False, t=self.tools[cid]: self.select_tool(t))
                self.addAction(a)

        self.opt_bar = QToolBar("Opties voor gereedschap")
        self.opt_bar.setObjectName("options")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.opt_bar)

    def _fit_tools(self):
        """Icoontjes van de gereedschapsbalk zo groot mogelijk, maar zo dat alles zichtbaar blijft."""
        tb = self.tools_toolbar
        if tb.orientation() != Qt.Orientation.Vertical:
            return
        buttons = list(dict.fromkeys(self.group_buttons.values()))
        avail = tb.height() - 14
        for size in (24, 22, 20, 18, 16):
            for b in buttons:
                b.setIconSize(QSize(size, size))
            need = sum(b.sizeHint().height() for b in buttons) + len(buttons) * tb.layout().spacing()
            if need <= avail:
                break

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "tools_toolbar"):
            QTimer.singleShot(0, self._fit_tools)

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
        from .palettes import BrushVariancePalette, HistogramPalette, OverviewPalette
        self.histogram = HistogramPalette(self)
        self.overview = OverviewPalette(self)
        self.brush_variance = BrushVariancePalette(self)
        self.dock_histogram = self._dock("Histogram", self.histogram, "histogram")
        self.dock_overview = self._dock("Overzicht", self.overview, "overview")
        self.dock_variance = self._dock("Penseelvariantie", self.brush_variance, "brush_variance")
        for dk in (self.dock_histogram, self.dock_overview, self.dock_variance):
            dk.hide()

    def handlers(self):
        D = lambda f: (lambda: f(self.doc()))  # noqa: E731
        adj = self.adjust
        return {
            # Bestand
            0xe100: self.file_new, 0xe101: self.file_open, 0xe102: self.close_active,
            0xe103: self.file_save, 0xe104: self.file_save_as, 0xe10b: lambda: self.file_save_as(copy=True),
            0xe141: self.close, 0x8012: self.preferences, 0x812d: self.export_gif, 0x814b: self.export_jpeg,
            0x8019: self.file_revert, 0x80d6: self.file_delete, 0x82ec: self.file_print, 0x812e: self.print_preview,
            0x80e0: self.capture_setup, 0x80e1: self.capture_start, 0x8203: self.import_brush,
            0x8201: self.export_brush, 0x815b: self.export_png, 0x8174: self.export_image_map,
            0x822c: self.export_frame, 0x815c: self.export_shape, 0x801b: self.batch_process,
            0x81ad: self.batch_rename, 0x8014: self.file_format_prefs, 0x8152: self.file_locations,
            0x8204: self.reset_preferences,
            # Bewerken
            0xe12b: D(lambda d: d.undo()), 0xe12c: D(lambda d: d.redo()), 0xe128: self.repeat_last,
            0xe123: self.edit_cut, 0xe122: self.edit_copy, 0x8105: lambda: self.edit_copy(merged=True),
            0x80e6: self.paste_new_image, 0x810d: self.paste_new_layer, 0x801e: self.paste_new_selection,
            0x801f: self.paste_into_selection, 0xe120: self.edit_clear,
            0x80f0: self.paste_transparent_selection, 0x8023: self.paste_vector_selection,
            0x8020: lambda: QApplication.clipboard().clear(),
            # Beeld
            0x8007: lambda: self.canvas().actual_size(), 0x8132: lambda: self.canvas().zoom_step(True),
            0x8136: lambda: self.canvas().zoom_step(False), 0x801d: self.toggle_fullscreen,
            0x8021: self.toggle_grid,
            0x8185: lambda: self.toggle_dock(self.dock_mat), 0x81ae: lambda: self.toggle_dock(self.dock_layers),
            0x8002: lambda: self.toggle_dock(self.dock_hist), 0x81ba: lambda: self.opt_bar.setVisible(not self.opt_bar.isVisible()),
            0x81f9: lambda: self.tools_toolbar.setVisible(not self.tools_toolbar.isVisible()),
            0x8216: self.toggle_magnifier,
            0x8022: lambda: self.toggle_dock(self.dock_histogram), 0x8159: lambda: self.toggle_dock(self.dock_overview),
            0x822d: lambda: self.toggle_dock(self.dock_variance),
            0x821d: lambda: self.effects_toolbar.setVisible(not self.effects_toolbar.isVisible()),
            0x821c: lambda: self.photo_toolbar.setVisible(not self.photo_toolbar.isVisible()),
            0x80ef: self.full_screen_preview, 0x8202: self.fit_to_screen,
            0x810a: lambda: self.toggle_view("rulers"), 0x817c: lambda: self.toggle_view("guides"),
            0x817a: lambda: self.toggle_view("snap_grid"), 0x817b: lambda: self.toggle_view("snap_guides"),
            0x8155: self.grid_guide_properties,
            **{cid: (lambda name=name: self.node_command(name)) for cid, name in self.NODE_COMMANDS.items()},
            **{cid: (lambda k=k, a=a: self.object_command(k, a)) for cid, (k, a) in self.OBJECT_COMMANDS.items()},
            0x8125: self.check_updates,
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
            0x8140: self.new_raster_layer, 0x8141: self.new_vector_layer, 0x80f7: D(lambda d: d.duplicate_layer()),
            0x80f6: D(lambda d: d.delete_layer()), 0x80fe: self.layer_properties,
            0x8101: D(lambda d: d.arrange_layer("top")), 0x8104: D(lambda d: d.move_layer(1)),
            0x8102: D(lambda d: d.move_layer(-1)), 0x8103: D(lambda d: d.arrange_layer("bottom")),
            0x81d4: D(lambda d: d.merge_down()), 0x80f8: D(lambda d: d.flatten()),
            0x8120: D(lambda d: d.merge_visible()),
            0x80ff: D(lambda d: d.layer_view("current")), 0x8100: D(lambda d: d.layer_view("all")),
            0x8177: D(lambda d: d.layer_view("none")), 0x8176: D(lambda d: d.layer_view("invert")),
            0x8178: D(lambda d: d.layer_view("link_show")), 0x8179: D(lambda d: d.layer_view("link_hide")), 0x815d: D(lambda d: d.promote_background()),
            0x8051: lambda: self.count_colors(True),
            0x8191: D(lambda d: d.new_group()), 0x8205: D(lambda d: d.ungroup()), 0x81d5: D(lambda d: d.merge_group()),
            0x81d6: D(lambda d: d.move_into_group()), 0x81d7: D(lambda d: d.move_out_of_group()),
            0x8107: D(lambda d: d.add_mask("hide_all")), 0x8108: D(lambda d: d.add_mask("show_all")),
            0x8106: D(lambda d: d.add_mask("hide_sel")), 0x80e9: D(lambda d: d.add_mask("show_sel")),
            0x80e8: self.mask_from_image, 0x80ec: D(lambda d: d.invert_mask()), 0x821f: self.toggle_mask_overlay,
            0x80ea: self.load_mask, 0x80eb: self.save_mask,
            0x810f: lambda: self.channel_save(selection=True), 0x810e: lambda: self.channel_load(selection=True),
            0x8111: lambda: self.channel_save(selection=False), 0x8110: lambda: self.channel_load(selection=False),
            0x81e4: self.channel_delete, 0x80f5: D(lambda d: d.selection_from_mask()),
            # Selecties
            0x80dc: self.select_all, 0x80e2: self.select_none, 0x80dd: self.select_invert,
            0x811b: lambda: self.modify_selection("expand", "Uitbreiden", "Aantal pixels:"),
            0x811c: lambda: self.modify_selection("contract", "Inkrimpen", "Aantal pixels:"),
            0x80e3: lambda: self.modify_selection("feather", "Doezelen", "Aantal pixels:"),
            0x8109: D(lambda d: d.promote_selection()), 0x811a: self.toggle_marquee,
            0x012f: self.picture_frame, 0x8058: lambda: self.reduce_colors(2), 0x8059: lambda: self.reduce_colors(16),
            0x805a: lambda: self.reduce_colors(256), 0x805d: lambda: self.reduce_colors(None),
            0x805b: lambda: self.reduce_bits((5, 5, 5)), 0x805c: lambda: self.reduce_bits((5, 6, 5)),
            0x80f3: lambda: self.split_channels("rgb"), 0x8116: lambda: self.split_channels("hsl"),
            0x8118: lambda: self.split_channels("cmyk"), 0x80f4: lambda: self.combine_channels("rgb"),
            0x8117: lambda: self.combine_channels("hsl"), 0x8123: lambda: self.combine_channels("cmyk"),
            0x80f2: self.image_arithmetic,
            0x8001: self.sel_from_vectors, 0x8114: self.sel_similar, 0x81eb: self.sel_color_range,
            0x8193: self.sel_feather_side, 0x81ee: self.sel_unfeather, 0x81e8: self.sel_antialias,
            0x81e7: self.sel_recover_aa, 0x81f6: self.sel_specks, 0x81f5: self.sel_smooth, 0x81ec: self.sel_borders,
            0x8283: self.sel_clip_canvas, 0x80de: self.sel_load_disk, 0x80df: self.sel_save_disk,
            0x81f4: self.sel_edit, 0x80e4: self.sel_float, 0x80e5: self.sel_defloat,
            # Venster
            0xe130: self.new_window, 0x82ce: lambda: self.set_tab_mode(self.mdi.viewMode() != QMdiArea.ViewMode.TabbedView),
            0xe132: self.mdi.cascadeSubWindows, 0xe133: lambda: self.tile(False), 0xe134: lambda: self.tile(True),
            0x80d3: self.mdi.closeAllSubWindows, 0x80d4: self.duplicate_image, 0x80d5: self.fit_window_to_image,
            0x81d0: lambda: self.canvas().fit(),
            # Help
            0x8028: self.show_shortcuts, 0xe140: self.about, 0xe142: self.show_manual, 0x8151: self.autosave_settings,
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

    # Opdrachten die ook zonder geopende afbeelding werken (o.a. voorkeuren, zoals in PSP)
    NO_DOC = {0x8012, 0x8125, 0x80e0, 0x80e1, 0x8203, 0x801b, 0x81ad, 0x8014, 0x8152, 0x8204, 0x8216, 0x8022, 0x8159, 0x822d, 0x821d, 0x821c, 0x810a, 0x817c, 0x817a, 0x817b, 0x8155, 0xe100, 0xe101, 0xe141, 0x80e6, 0x8020, 0x8185, 0x81ae, 0x8002, 0x81ba, 0x81f9, 0xe800, 0xe801,
              0x801d, 0x82ce, 0xe132, 0xe133, 0xe134, 0x80d3, 0x8028, 0xe140, 0xe142, 0x8151}
    CHECKABLE = {0x821f: None, 0x8185: "dock_mat", 0x81ae: "dock_layers", 0x8002: "dock_hist", 0x82ce: None, 0x8021: None,
                 0x811a: None, 0x81ba: "opt_bar", 0x8216: None, 0x81f4: None, 0x810a: None, 0x817c: None,
                 0x817a: None, 0x817b: None, 0x8022: "dock_histogram", 0x8159: "dock_overview",
                 0x822d: "dock_variance", 0x821d: None, 0x821c: None}

    @staticmethod
    def _tidy_menu(menu):
        """Lege submenu's weghalen en scheidingslijnen opruimen (geen dubbele, niet aan begin of eind)."""
        for a in list(menu.actions()):
            sub = a.menu()
            if sub is not None:
                MainWindow._tidy_menu(sub)
                if not sub.actions() and not sub.property("pp_dynamic"):
                    menu.removeAction(a)
        prev_sep = True
        for a in list(menu.actions()):
            if a.isSeparator():
                if prev_sep:
                    menu.removeAction(a)
                    continue
                prev_sep = True
            else:
                prev_sep = False
        acts = menu.actions()
        while acts and acts[-1].isSeparator():
            menu.removeAction(acts.pop())

    def _build_menus(self):
        self.top_menus = {}
        self.hidden_menu_items = 0
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
                    self.recent_menu.setProperty("pp_dynamic", True)
                    self.recent_menu.aboutToShow.connect(self._fill_recent)
                    continue
                cid = it["id"]
                fn = H.get(cid)
                if fn is None:  # nog niet gebouwd: niet tonen (komt vanzelf terug zodra het werkt)
                    self.hidden_menu_items += 1
                    continue
                a = QAction(it["text"], self)
                if it["keys"]:
                    a.setShortcuts([QKeySequence(k) for k in it["keys"]])
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
            self._tidy_menu(m)
            if not m.actions():  # bijvoorbeeld Objecten: nog niets beschikbaar
                mb.removeAction(m.menuAction())
                continue
            self.top_menus[top["text"].replace("&", "")] = m
            if top["text"].replace("&", "") == "Objecten":
                m.aboutToShow.connect(self.update_node_actions)
            if top["text"].replace("&", "") == "Venster":
                self.window_menu = m
                m.aboutToShow.connect(self._fill_window_menu)
        self._window_entries = []
        a = self.actions_by_id
        for cid, dock in ((0x8185, self.dock_mat), (0x81ae, self.dock_layers), (0x8002, self.dock_hist),
                          (0x8022, self.dock_histogram), (0x8159, self.dock_overview), (0x822d, self.dock_variance)):
            if cid in a:
                dock.visibilityChanged.connect(lambda v, act=a[cid]: act.setChecked(v))
                a[cid].setChecked(dock.isVisible() or cid in (0x8185, 0x81ae, 0x8002))
        self._build_extra_toolbars()
        if 0x81ba in a:  # optiebalk: vinkje volgt de zichtbaarheid (ook na sluiten via het balkmenu)
            self.opt_bar.visibilityChanged.connect(lambda v, act=a[0x81ba]: act.setChecked(v))
            a[0x81ba].setChecked(True)
        self.sync_view_checks()

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
        icons = {0xe100: glyph_icon("new"), 0xe101: glyph_icon("open"),
                 0xe103: glyph_icon("💾"), 0xe104: glyph_icon("save_as"), 0x82ec: glyph_icon("🖨"),
                 0xe12b: glyph_icon("↶"), 0xe12c: glyph_icon("↷"), 0x80d1: glyph_icon("⤢"),
                 0x8242: glyph_icon("↻"), 0x8243: glyph_icon("↺")}
        for item in STANDARD_TOOLBAR:
            if item is None:
                tb.addSeparator()
            elif isinstance(item, str):
                btn = QToolButton()
                btn.setText(tr(item) + " ")
                btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                m = QMenu(btn)
                for cid in (PHOTO_MENU if item == "Foto verbeteren" else PALETTES_MENU):
                    if cid is None:
                        m.addSeparator()
                    elif cid == 0x81ba and hasattr(self, "tools_toolbar"):
                        # ook de gereedschapsbalk aan- en uitzetten, net als via het balkmenu
                        act = self.tools_toolbar.toggleViewAction()
                        act.setText(tr("Gereedschappen"))
                        m.addAction(act)
                        m.addAction(self.actions_by_id[cid])
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

    def run_command(self, cid):
        """Een menu-opdracht uitvoeren alsof hij gekozen werd (als hij bestaat en beschikbaar is)."""
        a = self.actions_by_id.get(cid)
        if a is not None and a.isEnabled():
            a.trigger()

    def repeat_last(self):
        if self.last_command:
            self.last_command()

    def eventFilter(self, obj, e):
        """Pijltoetsen verschuiven de selectie of de laag ook als de focus net op een palet of werkbalk
        staat (bijvoorbeeld na het aanklikken van een laag). Invoervelden houden hun pijltoetsen."""
        if e.type() == QEvent.Type.KeyPress and e.key() in Canvas.ARROWS and isinstance(obj, QWidget) \
                and obj is QApplication.focusWidget() and obj.window() is self and not isinstance(obj, Canvas):
            from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QSlider, QTextEdit
            if not isinstance(obj, (QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QSlider)):
                cv = self.canvas()
                if cv is not None and cv._nudge_key(e):
                    return True
        return super().eventFilter(obj, e)

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
        self._tools_enabled(has or bool(self.mdi.subWindowList()))

    def _tools_enabled(self, on):
        """Gereedschapsbalk en optiebalk alleen actief als er een afbeelding open is."""
        self.tools_toolbar.setEnabled(on)
        self.opt_bar.setEnabled(on)
        if on and self.tool is None:
            self.select_tool(self._last_tool, force=True)
        elif not on:
            if self.tool is not None:
                self.tool.deactivate()
                self.tool = None
                for btn in set(self.group_buttons.values()):
                    btn.setChecked(False)
                self.statusBar().clearMessage()
            if not getattr(self, "_idle_opts", False):
                # zoals in PSP: de instellingen van het (laatste) gereedschap staan er grijs
                self._build_options(self._last_tool)
                self._idle_opts = True

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
        if hasattr(self, "actions_by_id"):
            self._sync_seledit_check()
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
        self.st_info.setText(tr("{} × {} px   lagen: {}").format(cv.doc.w, cv.doc.h, len(cv.doc.layers)))
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
    def select_tool(self, tool, force=False):
        if tool.cid in self.group_buttons:
            self._last_tool = tool
            self.settings.setValue("last_tool", f"{tool.cid:04x}")
        if not force and self.tool is None and not self.mdi.subWindowList():
            self._idle_opts = False
            self._tools_enabled(False)  # geen afbeelding open: onthouden en grijs tonen
            return
        if self.tool is not None:
            self.tool.deactivate()
        self.tool = tool
        for btn in set(self.group_buttons.values()):
            btn.setChecked(False)
        btn = self.group_buttons.get(tool.cid)
        if btn is None:  # gereedschap staat (nog) niet op de balk
            return
        btn.show_tool(tool)
        btn.setChecked(True)
        self._build_options(tool)
        self.statusBar().showMessage(f"{tool.name}: {tool.tip}")
        for sw in self.mdi.subWindowList():
            sw.canvas.apply_cursor()
            sw.canvas.update()

    def _build_options(self, tool):
        """Optiebalk vullen met de instellingen van een gereedschap."""
        self._idle_opts = False
        self.opt_bar.clear()
        widgets, self.tool_opt_keys = recorded_keys(tool)
        # vooraan alleen een groot icoon van het gereedschap (de naam staat in de tooltip en de statusbalk);
        # zo begint de rest van de opties bij elk gereedschap op dezelfde plek
        H = self._opt_height()
        head = QLabel()
        head.setFixedSize(H + 12, H)
        head.setPixmap(glyph_icon(tool.glyph, tool.available).pixmap(32, 32))
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setToolTip(tool.name)
        head.setContentsMargins(6, 0, 0, 0)
        self.opt_bar.addWidget(head)
        gap = QWidget()
        gap.setFixedWidth(8)  # wat lucht tussen het icoon en de voorinstellingen
        self.opt_bar.addWidget(gap)
        self.opt_bar.addWidget(self._presets_button(tool))
        i = 0
        while i < len(widgets):  # label boven het invoerveld, zoals in PSP
            w = widgets[i]
            if isinstance(w, QLabel) and i + 1 < len(widgets):
                j = i + 1
                if isinstance(widgets[j], QAbstractButton) and not isinstance(widgets[j], QCheckBox):
                    # een rij knoppen onder één label (bijvoorbeeld uitlijnen bij bijsnijden)
                    row = QWidget()
                    h = QHBoxLayout(row)
                    h.setContentsMargins(0, 0, 0, 0)
                    h.setSpacing(2)
                    while j < len(widgets) and isinstance(widgets[j], QAbstractButton) \
                            and not isinstance(widgets[j], QCheckBox):
                        h.addWidget(widgets[j])
                        j += 1
                    h.addStretch()
                    self.opt_bar.addWidget(self._opt_column(w, row))
                    i = j
                    continue
                self.opt_bar.addWidget(self._opt_column(w, widgets[i + 1]))
                i += 2
            elif isinstance(w, QCheckBox):
                # vinkjes per twee onder elkaar, zoals in PSP; zo blijft de balk compact
                pair = [w]
                if i + 1 < len(widgets) and isinstance(widgets[i + 1], QCheckBox):
                    pair.append(widgets[i + 1])
                self.opt_bar.addWidget(self._opt_column(pair[0], pair[1] if len(pair) > 1 else None, small=False))
                i += len(pair)
            else:  # los veld of knop: op de hoogte van de invoervelden
                self.opt_bar.addWidget(self._opt_column(None, w))
                i += 1

    def _opt_metrics(self):
        """Hoogte van een klein label, een invoerveld en een vinkje in deze stijl (eenmalig gemeten)."""
        if not hasattr(self, "_optm"):
            from PySide6.QtWidgets import QComboBox
            lab = QLabel("Xg")
            lab.setStyleSheet("font-size: 10px;")
            self._optm = (lab.sizeHint().height(), QComboBox().sizeHint().height(),
                          QCheckBox("Xg").sizeHint().height())
        return self._optm

    # vinkjes in de optiebalk: zelfde kleine letter als de labels en een kleiner vakje; het klikbare
    # gebied blijft de hele regel (vakje en tekst)
    CHECK_CSS = "QCheckBox { font-size: 10px; spacing: 4px; } QCheckBox::indicator { width: 11px; height: 11px; }"

    def _opt_height(self):
        """Vaste hoogte voor elke kolom, zodat de balk bij elk gereedschap even hoog is: label boven
        invoerveld. Twee vinkjes passen daar ook in (bovenste op de lijn van de labels, onderste op die
        van de invoervelden)."""
        lab, inp, cb = self._opt_metrics()
        return lab + inp

    def _opt_column(self, top, bottom, small=True):
        """Kolom in de optiebalk met vaste hoogte: klein label boven het invoerveld (onderaan uitgelijnd,
        zodat labels en velden van alle kolommen op dezelfde lijn staan), of twee vinkjes onder elkaar."""
        lab_h, inp_h, cb_h = self._opt_metrics()
        H = self._opt_height()
        box = QWidget()
        box.setFixedHeight(H)
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 0, 4, 0)
        v.setSpacing(0)
        if not small:  # vinkjes: bovenste (of een los vinkje) op de lijn van de labels, onderste bij de velden
            for w, hgt in ((top, lab_h), (bottom, inp_h)):
                if w is None:
                    spacer = QWidget()
                    spacer.setFixedHeight(hgt)
                    v.addWidget(spacer)
                    continue
                w.setStyleSheet(self.CHECK_CSS)
                w.setFixedHeight(hgt)
                v.addWidget(w)
            return box
        v.addStretch()
        if top is None:
            top = QLabel("")
        if isinstance(top, QLabel):
            top.setStyleSheet("font-size: 10px;")
        top.setFixedHeight(lab_h)
        v.addWidget(top)
        if isinstance(bottom, QLabel):
            # tekst even hoog als een invoerveld en verticaal gecentreerd
            bottom.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        # het veld staat altijd in een vak met de hoogte van een keuzelijst, zodat labels en velden van
        # alle kolommen precies op dezelfde lijn liggen, ook als een knop lager is dan een keuzelijst
        holder = QWidget()
        holder.setFixedHeight(inp_h)
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        if bottom is not None:
            bottom.setMaximumHeight(inp_h)
            hl.addWidget(bottom, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(holder, 0, Qt.AlignmentFlag.AlignLeft)
        return box

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
        b = QToolButton()
        b.setIcon(glyph_icon(tool.glyph, tool.available))
        inp_h = self._opt_metrics()[1]
        b.setFixedSize(inp_h + 14, inp_h)  # even hoog als de keuzelijsten (ruimte voor het pijltje)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setToolTip("Voorinstellingen voor dit gereedschap")
        m = QMenu(b)
        m.aboutToShow.connect(lambda: self._fill_tool_presets(m, tool))
        b.setMenu(m)
        return self._opt_column(QLabel("Voorinstellingen:"), b)  # label op dezelfde hoogte als 'Vorm:'

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
            sub = m.addMenu("Geïmporteerde voorinstellingen")
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

    def _materials_changed(self):
        """Palet bijwerken; een tekst die nog bewerkt wordt, neemt kleur, verloop of patroon meteen over."""
        self.materials.refresh()
        if isinstance(self.tool, TextTool):
            self.tool.refresh()

    def set_color(self, c, foreground=True):
        if foreground:
            self.fg = QColor(c)
        else:
            self.bg = QColor(c)
        self._materials_changed()

    def set_none(self, fg, value):
        if fg:
            self.fg_none = value
        else:
            self.bg_none = value
        self._materials_changed()

    def swap_colors(self):
        self.fg_none, self.bg_none = self.bg_none, self.fg_none
        self.fg, self.bg = self.bg, self.fg
        self.fg_mat, self.bg_mat = self.bg_mat, self.fg_mat
        self._materials_changed()

    def reset_colors(self):
        self.fg, self.bg = QColor(0, 0, 0), QColor(255, 255, 255)
        self.fg_mat = self.bg_mat = None
        self._materials_changed()

    # ---------------------------------------------------------------- verloop en patroon
    def material(self, fg=True):
        """Verloop of patroon voor voorgrond/achtergrond, of None bij een effen kleur."""
        return self.fg_mat if fg else self.bg_mat

    def set_material(self, fg, mat):
        if mat is not None:
            self._last_mat[(fg, mat["kind"])] = dict(mat)
        if fg:
            self.fg_mat = mat
        else:
            self.bg_mat = mat
        self._materials_changed()

    def set_material_kind(self, fg, kind):
        """Stijlknopjes onder het materiaalvak: 0 kleur, 1 verloop, 2 patroon (laatst gebruikte)."""
        from . import material as M
        if kind == 0:
            self.set_material(fg, None)
            return
        k = "gradient" if kind == 1 else "pattern"
        mat = self._last_mat.get((fg, k)) or (M.default_gradient() if kind == 1 else M.default_pattern())
        self.set_material(fg, dict(mat))

    def material_image(self, fg, rect, span=None):
        """Afbeelding van het verloop/patroon voor rect (documentcoördinaten), of None bij effen kleur."""
        from . import material as M
        return M.render(self.material(fg), rect, span, self.fg, self.bg)

    def material_brush(self, fg, span):
        from . import material as M
        return M.brush(self.material(fg), span, self.fg, self.bg)

    def pattern_sources(self):
        """Open afbeeldingen, te gebruiken als patroon."""
        out = []
        for s in self.mdi.subWindowList():
            cv = getattr(s, "canvas", None)
            if cv is not None:
                out.append((cv.doc.title().rstrip(" *"), cv.doc.composite()))
        return out

    # ================================================================ documenten
    def add_document(self, doc, canvas_of=None):
        self._tools_enabled(True)
        cv = Canvas(doc, self)
        sw = DocWindow(self, cv)
        self.mdi.addSubWindow(sw)
        sw.destroyed.connect(lambda *_: QTimer.singleShot(0, self._after_close))
        area = self.mdi.viewport().size()
        sw.resize(QSize(min(area.width() - 40, max(400, doc.w + 40)), min(area.height() - 40, max(300, doc.h + 60))))
        sw.show()
        self._hook_tabbar()
        cv.apply_cursor()
        cv.setFocus()
        self.on_active(sw)
        return sw

    def _after_close(self):
        self.update_actions()
        self.autosaver.cleanup()

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

    def _recent(self):
        """Recente bestanden als lijst. Qt geeft één bewaard item soms terug als tekst; die niet per
        letter opknippen. Losse letters uit oudere versies worden weggelaten."""
        v = self.settings.value("recent") or []
        if isinstance(v, str):
            v = [v]
        return [p for p in v if isinstance(p, str) and len(p) > 1 and os.path.isabs(p)]

    def _add_recent(self, path):
        rec = [p for p in self._recent() if p != path]
        self.settings.setValue("recent", [path] + rec[:9])

    def _fill_recent(self):
        self.recent_menu.clear()
        for i, p in enumerate(self._recent()):
            a = self.recent_menu.addAction(f"&{i + 1} {p}" if i < 9 else p)
            a.triggered.connect(lambda _=False, path=p: self.open_path(path))
        if self.recent_menu.isEmpty():
            self.recent_menu.addAction("(leeg)").setEnabled(False)

    def file_save(self):
        self.save_doc(self.doc())

    def file_save_as(self, copy=False):
        self.save_doc(self.doc(), ask=True, copy=copy)

    # ---------------------------------------------------------------- Bestand: overige opdrachten
    def file_revert(self):
        """Naar vorige versie: de laatst opgeslagen versie opnieuw inlezen (ongedaan te maken)."""
        d = self.doc()
        if not d.path or not os.path.exists(d.path):
            self.statusBar().showMessage(tr("Deze afbeelding is nog niet opgeslagen."), 4000)
            return
        if d.modified and QMessageBox.question(self, APP, tr("Alle wijzigingen sinds het laatste opslaan "
                                                             "weggooien en de opgeslagen versie terughalen?")) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            nd = fileio.load(d.path)
        except Exception as e:  # noqa: BLE001
            self.report_error(e)
            return
        d.push_undo("Naar vorige versie")
        size_changed = (nd.w, nd.h) != (d.w, d.h)
        d.w, d.h, d.layers, d.active, d.channels = nd.w, nd.h, nd.layers, nd.active, nd.channels
        d.px_per_pt = nd.px_per_pt
        d.set_selection(None)
        d.set_modified(False)
        if size_changed:
            d.sizeChanged.emit()
        d.structureChanged.emit()
        d.changed.emit(QRect())

    def file_delete(self):
        """Verwijderen: het bestand van de actieve afbeelding naar de prullenbak verplaatsen en sluiten."""
        from PySide6.QtCore import QFile
        d = self.doc()
        if not d.path or not os.path.exists(d.path):
            self.statusBar().showMessage(tr("Deze afbeelding is nog niet opgeslagen."), 4000)
            return
        if QMessageBox.question(self, APP, tr("Het bestand {} naar de prullenbak verplaatsen?").format(
                os.path.basename(d.path))) != QMessageBox.StandardButton.Yes:
            return
        if not QFile.moveToTrash(d.path):
            QMessageBox.warning(self, APP, tr("Het bestand kon niet naar de prullenbak worden verplaatst."))
            return
        d.set_modified(False)
        self.close_active()

    def _paint_page(self, printer, fit=True):
        """De afbeelding op de pagina: passend (midden) of op ware grootte volgens de resolutie."""
        from PySide6.QtGui import QPageLayout
        d = self.doc()
        img = d.flattened(QColor(255, 255, 255))
        p = QPainter(printer)
        page = printer.pageLayout().paintRectPixels(printer.resolution())
        page = QRectF(0, 0, page.width(), page.height())
        if fit:
            s = min(page.width() / img.width(), page.height() / img.height())
        else:
            dpi = 72 * d.px_per_pt
            s = printer.resolution() / max(dpi, 1)
        w, h = img.width() * s, img.height() * s
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF((page.width() - w) / 2, (page.height() - h) / 2, w, h), img)
        p.end()

    def file_print(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec():
            self._paint_page(printer)

    def print_preview(self):
        """Afdrukweergave: voorbeeld van de pagina, passend of op ware grootte, met afdrukken vanuit het voorbeeld."""
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        v = dialogs.ask_form(self, tr("Afdrukweergave"), [
            ("fit", tr("Afmeting:"), "choice", [tr("Passend op de pagina"), tr("Ware grootte (volgens de resolutie)")], 0)])
        if v is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintPreviewDialog(printer, self)
        dlg.paintRequested.connect(lambda pr: self._paint_page(pr, v["fit"] == 0))
        dlg.exec()

    def capture_setup(self):
        """Schermopname instellen: wat er wordt vastgelegd en na hoeveel seconden."""
        st = self.settings
        v = dialogs.ask_form(self, tr("Schermopname"), [
            ("kind", tr("Opname van:"), "choice", [tr("Volledig scherm"), tr("Gebied (zelf kiezen)"), tr("Actief venster")],
             int(st.value("cap_kind", 0))),
            ("delay", tr("Vertraging:"), "int", 0, 60, int(st.value("cap_delay", 2)), " s"),
            ("hide", tr("PixelPickle tijdens de opname verbergen"), "bool", st.value("cap_hide", "true") == "true")])
        if v is not None:
            st.setValue("cap_kind", v["kind"])
            st.setValue("cap_delay", v["delay"])
            st.setValue("cap_hide", "true" if v["hide"] else "false")

    def capture_start(self):
        """Schermopname maken; het resultaat opent als nieuwe afbeelding. Gebruikt het schermafdrukprogramma van
        het bureaublad (onder Wayland kan een programma zelf niet zomaar het scherm vastleggen)."""
        import shutil
        import subprocess
        import tempfile
        import time
        st = self.settings
        kind, delay = int(st.value("cap_kind", 0)), int(st.value("cap_delay", 2))
        hide = st.value("cap_hide", "true") == "true"
        out = os.path.join(tempfile.mkdtemp(prefix="pixelpickle-"), "opname.png")
        if hide:
            self.hide()
            QApplication.processEvents()
        img = QImage()
        try:
            if shutil.which("spectacle"):
                mode = ["-f", "-r", "-a"][kind]
                subprocess.run(["spectacle", "-b", "-n", mode, "-d", str(delay * 1000), "-o", out], timeout=120)
                img = QImage(out)
            elif shutil.which("grim") and kind == 0:
                time.sleep(delay)
                subprocess.run(["grim", out], timeout=60)
                img = QImage(out)
            else:
                time.sleep(delay)
                scr = QApplication.primaryScreen()
                img = scr.grabWindow(0).toImage() if scr else QImage()
        except Exception as e:  # noqa: BLE001
            self.report_error(e)
        finally:
            if hide:
                self.show()
                self.raise_()
        if img.isNull():
            QMessageBox.warning(self, APP, tr("De schermopname is niet gelukt."))
            return
        d = Document(img.width(), img.height(), None)
        d.layers[0].image = img.convertToFormat(ops.FMT)
        d.layers[0].name = tr("Achtergrond")
        d.untitled = tr("Schermopname")
        self.add_document(d)

    def import_brush(self):
        """Aangepast penseel importeren: een afbeelding wordt een eigen penseel (donker = verf)."""
        from . import userdata
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Aangepast penseel importeren"), "",
                                                tr("Afbeeldingen") + " (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
        done = []
        for path in paths:
            img = QImage(path)
            if not img.isNull():
                userdata.save_brush(os.path.splitext(os.path.basename(path))[0], userdata.brush_weight_from_image(img))
                done.append(os.path.basename(path))
        if done:
            self.statusBar().showMessage(tr("Penselen geïmporteerd: {}").format(", ".join(done)), 6000)
            if self.tool is not None:
                self._build_options(self.tool)

    def export_brush(self):
        """Aangepast penseel exporteren: de selectie (of de hele afbeelding) wordt een eigen penseel."""
        from . import userdata
        d = self.doc()
        r = d.selection_bbox() if d.sel is not None else d.rect()
        img = d.composite().copy(r)
        if d.sel is not None:  # buiten de selectie niets
            m = d.sel.copy(r)
            q = QPainter(img)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            q.drawImage(0, 0, m)
            q.end()
        if max(img.width(), img.height()) > 999:
            img = img.scaled(999, 999, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        name, ok = QInputDialog.getText(self, tr("Aangepast penseel exporteren"), tr("Naam van het penseel:"),
                                        text=d.title().rstrip(" *").rsplit(".", 1)[0])
        if ok and name.strip():
            userdata.save_brush(name, userdata.brush_weight_from_image(img))
            self.statusBar().showMessage(tr("Penseel bewaard; kies het bij Vorm in de optiebalk van het penseel."), 6000)
            if self.tool is not None:
                self._build_options(self.tool)

    def export_png(self):
        d = self.doc()
        dlg = dialogs.PngOptimizerDialog(self, ops.qimage_to_rgba(d.flattened()))
        if not dlg.exec():
            return
        path = self._export_path(d, ".png", tr("PNG-optimalisatie"))
        if path:
            dlg.save(path)

    def export_image_map(self):
        """Afbeelding met hyperlinks: gebieden met links op de afbeelding, bewaard als HTML-pagina met afbeelding."""
        d = self.doc()
        img = d.flattened()
        dlg = dialogs.ImageMapDialog(self, img)
        if not dlg.exec():
            return
        path = self._export_path(d, ".html", tr("Afbeelding met hyperlinks"))
        if not path:
            return
        base = os.path.splitext(path)[0]
        img_path = base + ".png"
        img.save(img_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(dlg.html(os.path.basename(img_path)))
        self.statusBar().showMessage(tr("Bewaard: {} en {}").format(os.path.basename(path), os.path.basename(img_path)), 6000)

    def export_frame(self):
        """Fotolijst exporteren: de afbeelding (met een doorzichtig midden) wordt een eigen lijst voor Fotolijst."""
        from . import userdata
        d = self.doc()
        img = d.composite()
        a = ops.qimage_to_rgba(img)[..., 3]
        if a[d.h // 2, d.w // 2] > 0:
            QMessageBox.information(self, APP, tr("Een fotolijst heeft een doorzichtig midden, waar de foto komt. "
                                                  "Maak het midden eerst doorzichtig (bijvoorbeeld met een selectie en Wissen)."))
            return
        name, ok = QInputDialog.getText(self, tr("Fotolijst exporteren"), tr("Naam van de lijst:"),
                                        text=d.title().rstrip(" *").rsplit(".", 1)[0])
        if ok and name.strip():
            userdata.save_frame(name, img)
            self.statusBar().showMessage(tr("Lijst bewaard; kies hem bij Afbeelding > Fotolijst."), 6000)

    def export_shape(self):
        """Vorm exporteren: de gekozen vectorobjecten (of alle op de vectorlaag) worden een eigen vorm voor
        het gereedschap Basisvormen."""
        from . import userdata
        d = self.doc()
        lay = d.layer()
        if lay.vector is None or not lay.vector:
            self.statusBar().showMessage(tr("Kies eerst een vectorlaag met objecten."), 4000)
            return
        objs = [lay.vector[i] for i in d.vsel] if d.vsel else list(lay.vector)
        name, ok = QInputDialog.getText(self, tr("Vorm exporteren"), tr("Naam van de vorm:"))
        if ok and name.strip():
            userdata.save_shape(name, objs)
            self.statusBar().showMessage(tr("Vorm bewaard; kies hem bij het gereedschap Basisvormen."), 6000)

    def batch_process(self):
        """Batchverwerking: bestanden omzetten naar een andere indeling (eventueel verkleind)."""
        files = [s.canvas.doc.path for s in self.mdi.subWindowList() if s.canvas.doc.path]
        dlg = dialogs.BatchDialog(self, files)
        if not dlg.exec():
            return
        v = dlg.values()
        done, failed = 0, []
        from PySide6.QtWidgets import QProgressDialog
        prog = QProgressDialog(tr("Bezig met verwerken..."), tr("Annuleren"), 0, len(v["files"]), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        for k, path in enumerate(v["files"]):
            prog.setValue(k)
            QApplication.processEvents()
            if prog.wasCanceled():
                break
            try:
                doc = fileio.load(path)
                if v["maxsize"] and max(doc.w, doc.h) > v["maxsize"]:
                    s_ = v["maxsize"] / max(doc.w, doc.h)
                    doc.resize_image(max(1, round(doc.w * s_)), max(1, round(doc.h * s_)))
                folder = v["outdir"] or os.path.dirname(path)
                target = os.path.join(folder, os.path.splitext(os.path.basename(path))[0] + v["ext"])
                if os.path.exists(target) and not v["overwrite"]:
                    stem = os.path.splitext(target)[0]
                    n = 2
                    while os.path.exists(f"{stem} ({n}){v['ext']}"):
                        n += 1
                    target = f"{stem} ({n}){v['ext']}"
                fileio.save(doc, target, v["quality"])
                done += 1
            except Exception as e:  # noqa: BLE001 - een kapot bestand overslaan
                failed.append(f"{os.path.basename(path)}: {e}")
        prog.setValue(len(v["files"]))
        msg = tr("{} bestanden verwerkt.").format(done)
        if failed:
            msg += "\n\n" + tr("Niet gelukt:") + "\n" + "\n".join(failed[:10])
        QMessageBox.information(self, APP, msg)

    def batch_rename(self):
        dlg = dialogs.BatchRenameDialog(self)
        if not dlg.exec():
            return
        pairs = dlg.new_names()
        targets = [n for _, n in pairs]
        if len(set(targets)) != len(targets) or any(os.path.exists(n) and n not in [o for o, _ in pairs] for n in targets):
            QMessageBox.warning(self, APP, tr("Sommige nieuwe namen bestaan al of komen dubbel voor; er is niets hernoemd."))
            return
        tmp = []
        for old, _new in pairs:  # eerst tijdelijke namen, zodat namen elkaar niet in de weg zitten
            t = old + ".pp-rename"
            os.rename(old, t)
            tmp.append(t)
        for t, (_old, new) in zip(tmp, pairs):
            os.rename(t, new)
        self.statusBar().showMessage(tr("{} bestanden hernoemd.").format(len(pairs)), 5000)

    def file_format_prefs(self):
        st = self.settings
        v = dialogs.ask_form(self, tr("Voorkeuren bestandsindelingen"), [
            ("q", tr("JPEG-kwaliteit:"), "int", 1, 100, int(st.value("quality", 90))),
            ("png", tr("PNG-compressie (0 tot 9):"), "int", 0, 9, int(st.value("png_compress", 6))),
            ("layered", tr("Standaardindeling met lagen:"), "choice", ["OpenRaster (.ora)", ".pspimage"],
             1 if st.value("layered_ext", ".ora") == ".pspimage" else 0)])
        if v is not None:
            st.setValue("quality", v["q"])
            st.setValue("png_compress", v["png"])
            st.setValue("layered_ext", ".pspimage" if v["layered"] == 1 else ".ora")

    def file_locations(self):
        dlg = dialogs.FileLocationsDialog(self)
        if dlg.exec():
            dlg.apply()
            from . import material
            material._psp_pat = None  # patronen opnieuw zoeken
            material._cache.clear() if hasattr(material, "_cache") else None
            if self.tool is not None:
                self._build_options(self.tool)

    def reset_preferences(self):
        if QMessageBox.question(self, APP, tr("Alle voorkeuren terugzetten naar de standaardwaarden? Eigen penselen, "
                                              "vormen, lijsten en verlopen in de mappen blijven bewaard. PixelPickle "
                                              "gebruikt de standaardwaarden na een herstart.")) != QMessageBox.StandardButton.Yes:
            return
        self.settings.clear()
        self.settings.sync()
        self._prefs_reset = True  # bij afsluiten niets meer terugschrijven
        QMessageBox.information(self, APP, tr("De voorkeuren zijn teruggezet. Start PixelPickle opnieuw."))

    def save_doc(self, doc, ask=False, copy=False):
        if doc.seledit_layer() is not None:  # eerst Selectie bewerken afronden (die laag hoort niet in het bestand)
            doc.toggle_selection_edit()
            self._sync_seledit_check()
        path = doc.path
        ext = os.path.splitext(path)[1].lower() if path else ""
        writable = {".pspimage", ".psp", ".ora", ".png", ".jpg", ".jpeg", ".jpe", ".tif", ".tiff", ".bmp", ".webp", ".gif", ".tga"}
        if ask or not path or ext not in writable:
            base = os.path.splitext(path)[0] if path else os.path.join(
                self.settings.value("lastdir", os.path.expanduser("~/Afbeeldingen")), doc.untitled)
            default_ext = self.settings.value("layered_ext", ".ora") if len(doc.layers) > 1 else ".png"
            path, flt = QFileDialog.getSaveFileName(self, "Opslaan als", base + default_ext, fileio.SAVE_FILTER,
                                                    "OpenRaster met lagen (*.ora)" if default_ext == ".ora" else "PNG (*.png)")
            if not path:
                return False
            if not os.path.splitext(path)[1]:
                path += "." + flt.split("*.")[1].split(" ")[0].rstrip(")")
            ext = os.path.splitext(path)[1].lower()
        if ext not in fileio.LAYERED and len(doc.layers) > 1:
            r = QMessageBox.question(self, APP, "Dit formaat kan geen lagen bewaren. De afbeelding wordt "
                                     "samengevoegd opgeslagen; uw lagen blijven in PixelPickle behouden.\n\n"
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
            QMessageBox.information(self, APP, "Opgeslagen, met deze aanpassingen voor het .pspimage formaat:\n\n• "
                                    + "\n• ".join(warnings) + "\n\nTip: bewaar ook een .ora om alles bewerkbaar te houden.")
        self.settings.setValue("lastdir", os.path.dirname(path))
        self._add_recent(path)
        if not copy:
            doc.path = path
            doc.set_modified(False)
            doc.titleChanged.emit()
            self.autosaver.cleanup()
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
        bg = d.active == 0 and d.layer().name in BG_NAMES
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

    def paste_transparent_selection(self):
        """Plakken als transparante selectie: zoals Plakken als nieuwe selectie, maar de pixels in de huidige
        achtergrondkleur worden doorzichtig (handig voor uitgeknipte voorwerpen op een effen achtergrond)."""
        img, d = self._clip_image(), self.doc()
        if img is None or d is None:
            return
        a = ops.qimage_to_rgba(img.convertToFormat(ops.FMT))
        bg = np.array([self.bg.red(), self.bg.green(), self.bg.blue()], np.int16)
        same = np.abs(a[..., :3].astype(np.int16) - bg).max(axis=2) <= 2
        a[same, 3] = 0
        layer_img, r = self._centered_layer(d, ops.rgba_to_qimage(a))
        d.add_layer(Layer(d.next_raster_name(), layer_img), label="Plakken als transparante selectie")
        d.set_selection(ops.mask_to_qimage(ops.qimage_to_rgba(layer_img)[..., 3]))
        self.select_tool(self.tools[0xd021])

    def paste_vector_selection(self):
        """Plakken als nieuwe vectorselectie: gekopieerde vectorobjecten op de actieve vectorlaag (of een nieuwe)
        plakken; ze zijn meteen gekozen, zodat je ze met Kiezen kunt verplaatsen."""
        from . import vectorlayer as V
        from .tools import PickTool
        d = self.doc()
        if d is None or not PickTool.clipboard:
            self.statusBar().showMessage(tr("Er zijn geen gekopieerde vectorobjecten. Kopieer ze eerst met Selecteren."), 5000)
            return
        if d.layer().vector is None:
            d.new_vector_layer()
            d.undo_stack[-1] = ("Plakken als nieuwe vectorselectie", d.undo_stack[-1][1])
        else:
            d.push_undo("Plakken als nieuwe vectorselectie")
        lay = d.layer()
        start = len(lay.vector)
        lay.vector.extend(V.copy_vector(PickTool.clipboard))
        d.render_vector(lay)
        d.vsel = list(range(start, len(lay.vector)))
        self.select_tool(self.tools[0xd011])
        self.tools[0xd011]._stale = True
        d.changed.emit(QRect())
        d.structureChanged.emit()

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

    # ------------------------------------------------------------ alfakanalen
    def _channel_name(self, d, base):
        names = set(d.channel_names())
        n = 1
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def channel_save(self, selection):
        """Selectie of masker opslaan in een alfakanaal van de afbeelding."""
        d = self.doc()
        if selection and d.sel is None:
            self.statusBar().showMessage(tr("Er is geen selectie om op te slaan."), 4000)
            return
        if not selection and d.layer().kind != "mask":
            self.statusBar().showMessage(tr("Kies eerst een maskerlaag."), 4000)
            return
        title = "Selectie opslaan in alfakanaal" if selection else "Masker opslaan in alfakanaal"
        dlg = dialogs.AlphaChannelDialog(self, title, d, "save",
                                         self._channel_name(d, tr("Selectie") if selection else tr("Masker")))
        if not dlg.exec():
            return
        arr = ops.qimage_to_mask(d.sel) if selection else d.mask_values()
        d.store_channel(dlg.values(), arr, title)

    def channel_load(self, selection):
        d = self.doc()
        if not d.channels:
            self.statusBar().showMessage(tr("Deze afbeelding heeft nog geen alfakanalen."), 4000)
            return
        if not selection and d.layer().kind == "mask":
            self.statusBar().showMessage(tr("Kies een gewone laag of groep om het masker op te zetten."), 4000)
            return
        title = "Selectie laden uit alfakanaal" if selection else "Masker laden uit alfakanaal"
        dlg = dialogs.AlphaChannelDialog(self, title, d, "load", selection_ops=selection and d.sel is not None)
        if not dlg.exec():
            return
        i, op, inv = dlg.values()
        if selection:
            d.selection_from_channel(i, op, inv)
        else:
            d.mask_from_channel(i, inv)

    def channel_delete(self):
        d = self.doc()
        if not d.channels:
            self.statusBar().showMessage(tr("Deze afbeelding heeft nog geen alfakanalen."), 4000)
            return
        dlg = dialogs.AlphaChannelDialog(self, "Alfakanaal verwijderen", d, "delete")
        if dlg.exec():
            d.delete_channels(dlg.values())

    def new_raster_layer(self):
        d = self.doc()
        layer = Layer(raster_name(d.raster_counter + 1), new_image(d.w, d.h))
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

    # ================================================================ voorkeuren
    def preferences(self):
        from . import i18n
        dlg = dialogs.PreferencesDialog(self, i18n.setting() or i18n.language())
        if not dlg.exec():
            return
        dlg.save_view_settings()
        for sw in self.mdi.subWindowList():  # ruitjespatroon en arcering meteen bijwerken
            sw.canvas.apply_view_settings()
        if self.tool is not None:
            self._build_options(self.tool)
        lang = dlg.language()
        if lang == (i18n.setting() or i18n.language()):
            return
        self.settings.setValue("language", lang)
        self.settings.sync()
        r = QMessageBox.question(self, APP, tr("De taal wordt gewijzigd na het herstarten van PixelPickle. Nu herstarten?"))
        if r == QMessageBox.StandardButton.Yes:
            self._restart = True
            self.close()

    # ================================================================ snelmenu's (rechtsklik)
    CANVAS_MENU = [0xe12b, 0xe12c, None, 0xe123, 0xe122, 0x810d, 0x801e, 0x801f, None,
                   0x80dd, 0x8109, None, 0x8007, 0x81d0]
    # rechtsklik op het lege werkvlak (naast of zonder afbeelding)
    WORKSPACE_MENU = [0xe100, 0xe101, None, 0x80d3, None, 0x80e6, 0x8020, None, 0x8216, None, 0x8012]

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
        build = getattr(self.tool, "build_context_menu", None)
        if build is not None and build(cv, m):  # gereedschap met een eigen snelmenu (zoals de Pen)
            m.exec(cv.mapToGlobal(pos.toPoint()))
            return
        extra = list(self.tool.context_actions(cv))
        d = cv.doc
        if d.layer().text is not None:
            extra.append(("Tekst bewerken", lambda: self.edit_text_layer(cv)))
            extra.append(("Omzetten in rasterlaag", self.convert_to_raster))
        elif d.layer().vector is not None:
            extra.append(("Omzetten in rasterlaag", self.convert_to_raster))
        for label, fn in extra:
            m.addAction(label, lambda f=fn: self._run(f))
        if extra:
            m.addSeparator()
        self._fill_menu(m, self.CANVAS_MENU)
        m.exec(cv.mapToGlobal(pos.toPoint()))

    # Objecten > Bewerken, Tekenpunttype en Geselecteerde tekenpunten transformeren: werken op de lijnen
    # van de Pen (ook op een opgepakt vectorobject); hetzelfde als het snelmenu van de Pen
    NODE_COMMANDS = {0x1770: "cut", 0x1771: "copy", 0x1772: "paste", 0x1773: "delete", 0x1774: "select_all",
                     0x1775: "select_none", 0x1776: "invert", 0x1777: "join", 0x1778: "merge", 0x1779: "break",
                     0x177a: "close", 0x177b: "reverse_contour", 0x177c: "reverse_path", 0x177d: "duplicate_offset",
                     0x177e: "duplicate", 0x177f: "asym", 0x1780: "sym", 0x1781: "cusp", 0x1782: "smooth",
                     0x1783: "to_line", 0x1784: "line_before", 0x1785: "line_after", 0x1786: "curve_before",
                     0x1787: "curve_after", 0x1788: "flip", 0x1789: "mirror", 0x178a: "rotate", 0x178b: "skew_x",
                     0x178c: "skew_y", 0x178d: "contract", 0x178e: "expand"}

    # menu Objecten: bewerkingen op hele vectorobjecten (gekozen met Kiezen op een vectorlaag)
    OBJECT_COMMANDS = {
        0x8163: ("align", "top"), 0x815e: ("align", "bottom"), 0x8160: ("align", "left"), 0x815f: ("align", "right"),
        0x8161: ("align", "vcenter"), 0x8162: ("align", "hcenter"), 0x8172: ("align", "canvas"),
        0x816e: ("align", "canvas_h"), 0x8170: ("align", "canvas_v"),
        0x816c: ("distribute", "v_top"), 0x8164: ("distribute", "v_center"), 0x8166: ("distribute", "v_bottom"),
        0x8165: ("distribute", "h_left"), 0x8168: ("distribute", "h_center"), 0x8167: ("distribute", "h_right"),
        0x816f: ("distribute", "h_space"), 0x8171: ("distribute", "v_space"),
        0x8169: ("same_size", "h"), 0x816a: ("same_size", "v"), 0x816b: ("same_size", "both"),
        0x8139: ("arrange", "top"), 0x813a: ("arrange", "up"), 0x813b: ("arrange", "down"), 0x813c: ("arrange", "bottom"),
        0x8154: ("group", None), 0x8156: ("ungroup", None), 0x81e6: ("properties", None),
        0x813d: ("text_on_path", None), 0x1793: ("detach", None), 0x814c: ("curves", "single"),
        0x814d: ("curves", "chars"), 0x82a8: ("to_path", None)}

    def object_command(self, kind, arg=None):
        from . import vectorops as VO, vectorlayer as V
        d = self.doc()
        if d is None:
            return
        layer = d.layer()
        if kind in ("curves", "to_path"):
            return self.text_to_curves("single" if kind == "to_path" else arg)
        if kind == "detach":
            if layer.text is None or not layer.text.get("on_path"):
                self.statusBar().showMessage(tr("Kies eerst een tekstlaag die op een pad staat."), 4000)
                return
            d.push_undo("Object loskoppelen van pad")
            layer.text = dict(layer.text)
            layer.text.pop("on_path", None)
            layer.text.pop("path_offset", None)
            d.render_text(layer)
            d.changed.emit(QRect())
            d.structureChanged.emit()
            return
        sel = d.vsel
        if layer.vector is None or not sel:
            self.statusBar().showMessage(tr("Kies eerst objecten op een vectorlaag met het gereedschap Selecteren."), 5000)
            return
        if kind == "text_on_path":
            return self.fit_text_to_path(layer.vector[sel[0]])
        if kind == "properties":
            dlg = dialogs.VectorPropertiesDialog(self, [layer.vector[i] for i in sel])
            if not dlg.exec():
                return
            d.push_undo("Eigenschappen")
            dlg.apply()
        else:
            label = {"align": "Uitlijnen", "distribute": "Verdelen", "same_size": "Even groot maken",
                     "arrange": "Schikken", "group": "Groeperen", "ungroup": "Groep opheffen"}[kind]
            d.push_undo(label)
            objs = layer.vector
            if kind == "align":
                VO.align(objs, sel, arg, QRectF(d.rect()))
            elif kind == "distribute":
                if not VO.distribute(objs, sel, arg):
                    d.drop_last_undo()
                    self.statusBar().showMessage(tr("Kies minstens drie objecten om te verdelen."), 4000)
                    return
            elif kind == "same_size":
                if not VO.same_size(objs, sel, arg):
                    d.drop_last_undo()
                    self.statusBar().showMessage(tr("Kies minstens twee objecten; het eerst gekozen object is de maat."), 4000)
                    return
            elif kind == "arrange":
                layer.vector, new = VO.arrange(objs, sel, arg)
                d.vsel = new
            elif kind == "group":
                if not VO.group(objs, sel):
                    d.drop_last_undo()
                    self.statusBar().showMessage(tr("Kies minstens twee objecten om te groeperen."), 4000)
                    return
            elif kind == "ungroup":
                if not VO.ungroup(objs, sel):
                    d.drop_last_undo()
                    return
        d.render_vector(layer)
        d.changed.emit(QRect())
        d.structureChanged.emit()
        self.tools[0xd011]._stale = True
        cv = self.canvas()
        if cv:
            cv.update()

    def text_to_curves(self, how):
        """Tekst omzetten in curven: de tekstlaag wordt een vectorlaag met bewerkbare vormen
        (als één vorm, of één vorm per letter)."""
        from . import textlayer, vectorlayer as V
        d = self.doc()
        layer = d.layer() if d else None
        if layer is None or layer.text is None:
            self.statusBar().showMessage(tr("Kies eerst een tekstlaag."), 4000)
            return
        t = layer.text
        parts = textlayer.glyph_paths(t, d.px_per_pt, per_char=(how == "chars"))
        objs = []
        style = dict(width=float(t.get("stroke_width", 1.0) if t.get("stroke") else 0.0), aa=t.get("antialias", True))
        if how == "chars":
            for path, stroke, fill, sw in parts:
                ob = V.object_from_path(path, list(stroke) + [255] if stroke else None,
                                        list(fill) + [255] if fill else None, sw if stroke else 0.0, aa=style["aa"])
                if ob:
                    objs.append(ob)
        else:
            from PySide6.QtGui import QPainterPath
            whole = QPainterPath()
            for path, *_ in parts:
                whole.addPath(path)
            first = parts[0] if parts else (None, t.get("stroke"), t.get("fill"), 1.0)
            ob = V.object_from_path(whole, list(first[1]) + [255] if first[1] else None,
                                    list(first[2]) + [255] if first[2] else None, first[3] if first[1] else 0.0,
                                    aa=style["aa"])
            if ob:
                objs.append(ob)
        if not objs:
            return
        d.push_undo("Tekst omzetten in curven")
        layer.text = None
        layer.vector = objs
        d.render_vector(layer)
        d.changed.emit(QRect())
        d.structureChanged.emit()

    def fit_text_to_path(self, obj):
        """Tekst inpassen in pad: een tekstlaag volgt het gekozen vectorobject."""
        d = self.doc()
        texts = [l for l in d.layers if l.text is not None]
        if not texts:
            self.statusBar().showMessage(tr("Maak eerst een tekst met het tekstgereedschap."), 5000)
            return
        target = texts[-1]
        if len(texts) > 1:
            from PySide6.QtWidgets import QInputDialog
            names = [l.name for l in reversed(texts)]
            name, ok = QInputDialog.getItem(self, tr("Tekst inpassen in pad"), tr("Welke tekst?"), names, 0, False)
            if not ok:
                return
            target = list(reversed(texts))[names.index(name)]
        d.push_undo("Tekst inpassen in pad")
        target.text = dict(target.text)
        target.text["on_path"] = {"nodes": [list(map(lambda q: list(q) if q is not None else None, n)) for n in obj["nodes"]],
                                  "closed": obj["closed"]}
        target.text["path_offset"] = 0.0
        d.render_text(target)
        d.changed.emit(QRect())
        d.structureChanged.emit()

    def node_command(self, name):
        pen = self.tools[0xd110]
        if self.tool is not pen or (not pen.paths and not (name == "paste" and pen.clipboard)):
            self.statusBar().showMessage(tr("Kies de Pen en teken of pak een lijn of vorm op (modus Bewerken)."), 5000)
            return
        pen.pen_command(name, self.canvas())

    def update_node_actions(self):
        """Beschikbaarheid van de knooppuntopdrachten volgens de Pen (voor het menu en het snelmenu)."""
        pen = self.tools[0xd110]
        active = self.tool is pen and self.doc() is not None
        state = pen.command_state() if active else {}
        for cid, name in self.NODE_COMMANDS.items():
            a = self.actions_by_id.get(cid)
            if a is not None:
                a.setEnabled(bool(state.get(name)))

    def show_workspace_menu(self, pos):
        """Rechtsklik op het lege werkvlak: bestanden, klembord, vergrootglas en voorkeuren (zoals PSP)."""
        m = QMenu(self)
        self._fill_menu(m, self.WORKSPACE_MENU)
        m.exec(self.mdi.viewport().mapToGlobal(pos))

    def toggle_magnifier(self):
        if getattr(self, "magnifier", None) is None:
            self.magnifier = dialogs.Magnifier(self)
            a = self.actions_by_id.get(0x8216)
            if a is not None:
                self.magnifier.closed.connect(lambda: a.setChecked(False))
        if self.magnifier.isVisible():
            self.magnifier.hide()
        else:
            self.magnifier.show()
        a = self.actions_by_id.get(0x8216)
        if a is not None:
            a.setChecked(self.magnifier.isVisible())

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
        """Tekst- of vectorlaag eerst omzetten naar een rasterlaag (met bevestiging, zoals PSP)."""
        d = self.doc()
        if d is None or (d.layer().text is None and d.layer().vector is None):
            return True
        if d.layer().vector is not None:
            msg = tr("Dit is een vectorlaag. Om erop te schilderen of een effect toe te passen moet hij eerst een "
                     "rasterlaag worden; de lijnen en vormen zijn daarna niet meer bewerkbaar.\n\nOmzetten in rasterlaag?")
        else:
            msg = tr("Dit is een tekstlaag. Om erop te schilderen of een effect toe te passen "
                     "moet hij eerst een rasterlaag worden; de tekst is daarna niet meer bewerkbaar.\n\n"
                     "Omzetten in rasterlaag?")
        r = QMessageBox.question(self, APP, msg)
        if r != QMessageBox.StandardButton.Yes:
            return False
        self.convert_to_raster()
        return True

    def convert_to_raster(self):
        d = self.doc()
        if d.layer().text is None and d.layer().vector is None:
            return
        tool = self.tool
        if hasattr(tool, "commit_pending"):  # een lijn die nog bewerkt wordt eerst afronden
            tool.commit_pending()
        d.push_undo("Omzetten in rasterlaag")
        d.layer().text = None
        d.layer().vector = None
        d.structureChanged.emit()

    def new_vector_layer(self):
        d = self.doc()
        if d is None:
            return
        d.new_vector_layer()
        d.changed.emit(QRect())

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

    # ---------------------------------------------------------------- menu Afbeelding
    METHOD_NAMES = ["Dichtstbijzijnde kleur", "Foutdiffusie", "Geordende dithering"]

    def _raster_layers(self, d):
        return [l for l in d.layers if l.kind == "raster" and l.adjust is None and l.text is None and l.vector is None
                and l.role is None]

    def reduce_colors(self, n):
        """Kleurdiepte verminderen naar een palet (2, 16, 256 of zelf gekozen aantal kleuren)."""
        from . import imgops
        d = self.doc()
        title = tr("Kleurdiepte verminderen")
        if n == 2:
            v = dialogs.ask_form(self, title, [("m", tr("Methode:"), "choice", [tr(x) for x in self.METHOD_NAMES], 1)])
        else:
            fields = [("pal", tr("Palet:"), "choice", [tr("Optimaal"), tr("Vast (standaard)")], 0),
                      ("m", tr("Methode:"), "choice", [tr(x) for x in self.METHOD_NAMES], 1)]
            if n is None:
                fields.insert(0, ("n", tr("Aantal kleuren:"), "int", 2, 256, 64))
            v = dialogs.ask_form(self, title, fields)
        if v is None:
            return
        layers = self._raster_layers(d)
        method = imgops.METHODS[v["m"]]

        def work():
            arrs = [ops.qimage_to_rgba(l.image) for l in layers]
            if n == 2:
                return [imgops.two_colors(a, method) for a in arrs]
            count = v.get("n", n)
            pal = imgops.make_palette(arrs, count, "optimal" if v["pal"] == 0 else "fixed")
            return [imgops.quantize(a, pal, method) for a in arrs]
        out = self._busy(work)
        d.push_undo("Kleurdiepte verminderen")
        for l, a in zip(layers, out):
            l.image = ops.rgba_to_qimage(a)
        d.changed.emit(QRect())
        d.structureChanged.emit()

    def reduce_bits(self, bits):
        from . import imgops
        d = self.doc()
        v = dialogs.ask_form(self, tr("Kleurdiepte verminderen"),
                             [("m", tr("Methode:"), "choice", [tr("Dichtstbijzijnde kleur"), tr("Geordende dithering")], 1)])
        if v is None:
            return
        layers = self._raster_layers(d)
        d.push_undo("Kleurdiepte verminderen")
        for l in layers:
            l.image = ops.rgba_to_qimage(imgops.reduce_bits(ops.qimage_to_rgba(l.image), bits, v["m"] == 1))
        d.changed.emit(QRect())
        d.structureChanged.emit()

    def _new_doc_from(self, rgba, name):
        nd = Document(rgba.shape[1], rgba.shape[0], None)
        nd.layers[0].image = ops.rgba_to_qimage(rgba)
        nd.layers[0].name = tr("Achtergrond")
        nd.untitled = name
        self.add_document(nd)
        return nd

    def split_channels(self, model):
        """Kanalen splitsen: elk kanaal wordt een eigen grijswaardenafbeelding."""
        from . import imgops
        d = self.doc()
        a = ops.qimage_to_rgba(d.composite())
        base = d.title().rstrip(" *")
        for name, g in imgops.split(a, model):
            self._new_doc_from(imgops.to_gray_rgba(g), f"{tr(name)} - {base}")

    def _doc_choices(self):
        docs = [s.canvas.doc for s in self.mdi.subWindowList()]
        return docs, [x.title().rstrip(" *") for x in docs]

    def combine_channels(self, model):
        """Kanalen combineren: kies voor elk kanaal een open (grijswaarden)afbeelding."""
        from . import imgops
        docs, names = self._doc_choices()
        labels = {"rgb": ["Rood", "Groen", "Blauw"], "hsl": ["Tint", "Verzadiging", "Lichtheid"],
                  "cmyk": ["Cyaan", "Magenta", "Geel", "Zwart"]}[model]

        def guess(lbl, k):  # een afbeelding met de kanaalnaam in de titel voorstellen
            for i, n in enumerate(names):
                if n.startswith(tr(lbl)):
                    return i
            return min(k, len(names) - 1)
        v = dialogs.ask_form(self, tr("Kanalen combineren"),
                             [(str(k), tr(lbl) + ":", "choice", names, guess(lbl, k)) for k, lbl in enumerate(labels)])
        if v is None:
            return
        chans = [imgops.gray_of(ops.qimage_to_rgba(docs[v[str(k)]].composite())) for k in range(len(labels))]
        if len({c.shape for c in chans}) != 1:
            QMessageBox.warning(self, APP, tr("De gekozen afbeeldingen moeten even groot zijn."))
            return
        self._new_doc_from(imgops.combine(chans, model), tr("Gecombineerd"))

    def image_arithmetic(self):
        """Berekeningen: twee open afbeeldingen met elkaar verrekenen; het resultaat wordt een nieuwe afbeelding."""
        from . import imgops
        docs, names = self._doc_choices()
        cur = docs.index(self.doc()) if self.doc() in docs else 0
        funcs = ["Optellen", "Aftrekken", "Vermenigvuldigen", "Verschil", "Lichter", "Donkerder", "Gemiddelde",
                 "EN", "OF", "XOF"]
        v = dialogs.ask_form(self, tr("Berekeningen"), [
            ("a", tr("Afbeelding 1:"), "choice", names, cur),
            ("b", tr("Afbeelding 2:"), "choice", names, (cur + 1) % len(names)),
            ("f", tr("Functie:"), "choice", [tr(x) for x in funcs], 0),
            ("c", tr("Kanaal:"), "choice", [tr("Alle kanalen"), tr("Rood"), tr("Groen"), tr("Blauw")], 0),
            ("div", tr("Deler:"), "int", 1, 255, 1), ("bias", tr("Verschuiving:"), "int", -255, 255, 0),
            ("clip", tr("Afkappen"), "bool", True)])
        if v is None:
            return
        a = ops.qimage_to_rgba(docs[v["a"]].composite())
        b = ops.qimage_to_rgba(docs[v["b"]].composite())
        if b.shape != a.shape:  # tweede afbeelding linksboven passend maken
            pad = np.zeros_like(a)
            hh, ww = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
            pad[:hh, :ww] = b[:hh, :ww]
            b = pad
        out = imgops.arithmetic(a, b, imgops.FUNCTIONS[v["f"]], None if v["c"] == 0 else v["c"] - 1,
                                v["div"], v["bias"], v["clip"])
        self._new_doc_from(out, tr("Resultaat"))

    def picture_frame(self):
        """Fotolijst: een lijst als nieuwe laag, binnen de afbeelding of eromheen (het doek wordt groter)."""
        from . import imgops
        d = self.doc()
        from . import userdata
        styles = ["Eenvoudig", "Hout", "Goud", "Zilver", "Passe-partout", "Polaroid", "Schaduw"]
        own = userdata.frame_names()  # eigen lijsten (Bestand > Exporteren > Fotolijst)
        v = dialogs.ask_form(self, tr("Fotolijst"), [
            ("s", tr("Lijst:"), "choice", [tr(x) for x in styles] + own, 2),
            ("t", tr("Breedte:"), "int", 1, 1000, max(4, min(d.w, d.h) // 20)),
            ("c", tr("Kleur:"), "color", QColor(70, 45, 25)),
            ("out", tr("Plaats:"), "choice", [tr("Lijst binnen de afbeelding"), tr("Lijst buiten de afbeelding")], 0)])
        if v is None:
            return
        if v["s"] >= len(styles):  # eigen lijst: over de hele afbeelding geschaald
            fimg = userdata.load_frame(own[v["s"] - len(styles)])
            if fimg is None:
                return
            if v["out"] == 1:
                d.canvas_size(d.w + 2 * v["t"], d.h + 2 * v["t"], v["t"], v["t"], QColor(0, 0, 0, 0))
            first = len(d.undo_stack)
            img = new_image(d.w, d.h)
            q = QPainter(img)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            q.drawImage(QRectF(0, 0, d.w, d.h), fimg)
            q.end()
            d.add_layer(Layer(tr("Fotolijst"), img), len(d.layers), label="Fotolijst")
            if v["out"] == 1:
                snap = d.undo_stack[first - 1][1]
                del d.undo_stack[first - 1:]
                d.undo_stack.append(("Fotolijst", snap))
                d.historyChanged.emit()
            return
        style, t = imgops.FRAMES[v["s"]], v["t"]
        outside = v["out"] == 1 or style == "shadow"
        if outside:
            bottom = t * 3 if style == "polaroid" else t
            d.canvas_size(d.w + 2 * t, d.h + t + bottom, t, t, QColor(0, 0, 0, 0))
            first = len(d.undo_stack)
        img = imgops.frame_image(d.w, d.h, style, t, v["c"])
        layer = Layer(tr("Fotolijst"), img)
        if style == "shadow":
            d.push_undo("Fotolijst")
            d.layers.insert(0, layer)
            d.active = 0
            d.normalize()
            d.structureChanged.emit()
            d.changed.emit(QRect())
        else:
            d.add_layer(layer, len(d.layers), label="Fotolijst")
        if outside:  # doek vergroten en lijst toevoegen is samen één stap
            snap = d.undo_stack[first - 1][1]
            del d.undo_stack[first - 1:]
            d.undo_stack.append(("Fotolijst", snap))
            d.historyChanged.emit()

    # ---------------------------------------------------------------- Selecties > Wijzigen en verwanten
    def _sel_array(self, d):
        if d.sel is None:
            self.statusBar().showMessage(tr("Er is geen selectie."), 3000)
            return None
        return ops.qimage_to_mask(d.sel)

    def _busy(self, fn):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn()
        finally:
            QApplication.restoreOverrideCursor()

    def _sel_source(self, d, merged):
        return ops.qimage_to_rgba(d.composite() if merged else d.layer().image)

    def sel_from_vectors(self):
        d = self.doc()
        lay = d.layer()
        if lay.vector is None or not lay.vector:
            self.statusBar().showMessage(tr("Kies eerst een vectorlaag met objecten."), 4000)
            return
        d.selection_from_vectors(indices=d.vsel or None)

    def sel_similar(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        v = dialogs.ask_form(self, tr("Alles met dezelfde kleur selecteren"),
                             [("tol", tr("Tolerantie:"), "int", 0, 200, 10), ("cont", tr("Aaneengesloten"), "bool", False),
                              ("merged", tr("Alle lagen gebruiken"), "bool", False)])
        if v is None:
            return

        def work():
            sim = selops.similar_colors(self._sel_source(d, v["merged"]), m, v["tol"])
            if v["cont"]:
                sim = selops.grow_from(sim, m > 127)
            return np.maximum(m, sim.astype(np.uint8) * 255)
        d.apply_selection_array(self._busy(work), "Alles met dezelfde kleur selecteren")

    def sel_color_range(self):
        from . import selops
        d = self.doc()
        v = dialogs.ask_form(self, tr("Kleurbereik selecteren"),
                             [("color", tr("Kleur:"), "color", self.fg), ("tol", tr("Tolerantie:"), "int", 0, 200, 20),
                              ("soft", tr("Zachtheid:"), "int", 0, 100, 10),
                              ("mode", tr("Modus:"), "choice", [tr("Vervangen"), tr("Toevoegen"), tr("Verwijderen")],
                               1 if d.sel is not None else 0),
                              ("merged", tr("Alle lagen gebruiken"), "bool", False)])
        if v is None:
            return
        c = v["color"]
        rng = self._busy(lambda: selops.color_range(self._sel_source(d, v["merged"]), (c.red(), c.green(), c.blue()),
                                                    v["tol"], v["soft"]))
        cur = ops.qimage_to_mask(d.sel) if d.sel is not None else np.zeros_like(rng)
        out = rng if v["mode"] == 0 else np.maximum(cur, rng) if v["mode"] == 1 else \
            np.clip(cur.astype(np.int16) - rng, 0, 255)
        d.apply_selection_array(out, "Kleurbereik selecteren")

    def sel_feather_side(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        v = dialogs.ask_form(self, tr("Binnen/buiten doezelen"),
                             [("n", tr("Doezelen:"), "int", 1, 200, 8),
                              ("side", tr("Richting:"), "choice", [tr("Binnen"), tr("Buiten"), tr("Beide")], 2)])
        if v is not None:
            out = self._busy(lambda: selops.feather_side(m, v["n"], ["inside", "outside", "both"][v["side"]]))
            d.apply_selection_array(out, "Binnen/buiten doezelen")

    def sel_unfeather(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        v = dialogs.ask_form(self, tr("Doezelen opheffen"), [("t", tr("Drempel:"), "int", 1, 100, 50, " %")])
        if v is not None:
            d.apply_selection_array(selops.unfeather(m, v["t"]), "Doezelen opheffen")

    def sel_antialias(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        v = dialogs.ask_form(self, tr("Op vorm gebaseerde anti-alias"),
                             [("w", tr("Plaats:"), "choice", [tr("Binnen"), tr("Buiten")], 1)])
        if v is not None:
            d.apply_selection_array(selops.antialias(m, ["inside", "outside"][v["w"]]), "Op vorm gebaseerde anti-alias")

    def sel_recover_aa(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is not None:
            alpha = ops.qimage_to_rgba(d.layer().image)[..., 3]
            d.apply_selection_array(selops.recover_antialias(m, alpha), "Anti-alias herstellen")

    def sel_specks(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        v = dialogs.ask_form(self, tr("Stippen en gaten verwijderen"),
                             [("what", tr("Verwijderen:"), "choice", [tr("Stippen"), tr("Gaten"), tr("Stippen en gaten")], 2),
                              ("size", tr("Kleiner dan (pixels):"), "int", 1, 1000000, 100)])
        if v is not None:
            out = self._busy(lambda: selops.remove_specks_holes(m, v["size"], v["what"] in (0, 2), v["what"] in (1, 2)))
            d.apply_selection_array(out, "Stippen en gaten verwijderen")

    def sel_smooth(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        v = dialogs.ask_form(self, tr("Vloeiend"), [("n", tr("Hoeveelheid:"), "int", 1, 50, 5)])
        if v is not None:
            d.apply_selection_array(self._busy(lambda: selops.smooth(m, v["n"])), "Vloeiend")

    def sel_borders(self):
        from . import selops
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        v = dialogs.ask_form(self, tr("Selectieranden selecteren"),
                             [("w", tr("Breedte:"), "int", 1, 200, 5),
                              ("side", tr("Plaats:"), "choice", [tr("Binnen"), tr("Buiten"), tr("Beide")], 2),
                              ("aa", tr("Anti-alias"), "bool", True)])
        if v is not None:
            out = self._busy(lambda: selops.borders(m, v["w"], ["inside", "outside", "both"][v["side"]], v["aa"]))
            d.apply_selection_array(out, "Selectieranden selecteren")

    def sel_clip_canvas(self):
        """Afknippen tot doek: het deel van het selectiekader dat (na verschuiven) buiten het doek viel, weghalen."""
        d = self.doc()
        m = self._sel_array(d)
        if m is not None:
            d.apply_selection_array(m, "Afknippen tot doek")

    def sel_load_disk(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Selectie laden vanaf schijf"), self.settings.value("lastdir", ""),
                                              tr("Afbeeldingen") + " (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif)")
        if not path:
            return
        d = self.doc()
        img = QImage(path)
        if img.isNull():
            return
        img = img.scaled(d.w, d.h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        a = ops.qimage_to_rgba(img).astype(np.float32)
        # met transparantie: de dekking is de selectie; anders de helderheid (wit = geselecteerd)
        v = a[..., 3] if (a[..., 3] < 255).any() else a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
        d.apply_selection_array(v, "Selectie laden vanaf schijf")

    def sel_save_disk(self):
        d = self.doc()
        m = self._sel_array(d)
        if m is None:
            return
        path = self._export_path(d, ".png", tr("Selectie opslaan op schijf"))
        if path:
            arr = np.ascontiguousarray(m)
            QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format.Format_Grayscale8).copy().save(path)

    def _sync_seledit_check(self):
        a = self.actions_by_id.get(0x81f4)
        d = self.doc()
        if a is not None:
            a.setChecked(bool(d is not None and d.seledit_layer() is not None))

    def sel_edit(self):
        self.doc().toggle_selection_edit()
        self._sync_seledit_check()

    def sel_float(self):
        d = self.doc()
        if d.sel is None:
            self.statusBar().showMessage(tr("Er is geen selectie."), 3000)
            return
        if not self.ensure_raster():
            return
        if not d.float_selection(self.bg):
            self.statusBar().showMessage(tr("Er is al een zwevende selectie, of de actieve laag is geen rasterlaag."), 4000)

    def sel_defloat(self):
        d = self.doc()
        if not d.defloat_selection():
            self.statusBar().showMessage(tr("Er is geen zwevende selectie."), 3000)

    def toggle_marquee(self):
        cv = self.canvas()
        cv.hide_marquee = not getattr(cv, "hide_marquee", False)
        cv.update()

    # ================================================================ beeld en venster
    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    # werkbalken Effecten en Foto (Beeld > Werkbalken): snelkoppelingen naar veelgebruikte opdrachten
    EFFECTS_BAR = [0x807b, None, 0x809e, 0x80b2, 0x80b3, 0x80a0, 0x809f, 0x80a2]
    PHOTO_BAR = [0x8240, 0x82d8, None, 0x82dc, 0x8052, 0x806a, None, 0x806e, 0x809b, 0x82f1]

    def _build_extra_toolbars(self):
        for attr, title, name, ids, cid in (("effects_toolbar", "Effecten", "effects_bar", self.EFFECTS_BAR, 0x821d),
                                            ("photo_toolbar", "Foto", "photo_bar", self.PHOTO_BAR, 0x821c)):
            tb = QToolBar(tr(title))
            tb.setObjectName(name)
            tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            for c in ids:
                if c is None:
                    tb.addSeparator()
                elif c in self.actions_by_id:
                    tb.addAction(self.actions_by_id[c])
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
            tb.hide()
            setattr(self, attr, tb)
            a = self.actions_by_id.get(cid)
            if a is not None:
                tb.visibilityChanged.connect(lambda v, act=a: act.setChecked(v))

    def full_screen_preview(self):
        """Schermvullend voorbeeld: de afbeelding passend op een zwart scherm; een toets of klik sluit het."""
        d = self.doc()
        img = d.flattened()
        w = QWidget(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        w.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        w.setStyleSheet("background: black;")

        def paint(e, w=w, img=img):
            p = QPainter(w)
            p.fillRect(w.rect(), QColor(0, 0, 0))
            s = min(w.width() / img.width(), w.height() / img.height(), 1.0 if img.width() < w.width() else 99)
            tw, th = img.width() * s, img.height() * s
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(QRectF((w.width() - tw) / 2, (w.height() - th) / 2, tw, th), img)
            p.end()
        w.paintEvent = paint
        w.keyPressEvent = lambda e, w=w: w.close()
        w.mousePressEvent = lambda e, w=w: w.close()
        self._preview = w
        w.showFullScreen()

    def fit_to_screen(self):
        """Schermvullend maken: het afbeeldingsvenster zo groot mogelijk en de afbeelding passend erin."""
        sw = self.mdi.activeSubWindow()
        if sw is None:
            return
        if self.mdi.viewMode() == QMdiArea.ViewMode.SubWindowView:
            sw.showMaximized()
        QApplication.processEvents()
        sw.canvas.fit()

    VIEW_IDS = {"rulers": 0x810a, "guides": 0x817c, "snap_grid": 0x817a, "snap_guides": 0x817b}

    def _save_view_opts(self):
        import json
        self.settings.setValue("view_opts", json.dumps(self.view_opts))

    def sync_view_checks(self):
        for key, cid in self.VIEW_IDS.items():
            a = getattr(self, "actions_by_id", {}).get(cid)
            if a is not None:
                a.setChecked(bool(self.view_opts.get(key)))

    def toggle_view(self, key):
        """Linialen, hulplijnen, uitlijnen op raster en uitlijnen op hulplijnen aan of uit."""
        self.view_opts[key] = not self.view_opts.get(key)
        self._save_view_opts()
        self.sync_view_checks()
        for sw in self.mdi.subWindowList():
            sw.canvas.update()

    def grid_guide_properties(self):
        o = self.view_opts
        v = dialogs.ask_form(self, tr("Eigenschappen Raster, Hulplijn en Uitlijnen wijzigen"), [
            ("grid_h", tr("Horizontale rasterafstand:"), "int", 2, 5000, o["grid_h"], " px"),
            ("grid_v", tr("Verticale rasterafstand:"), "int", 2, 5000, o["grid_v"], " px"),
            ("grid_color", tr("Rasterkleur:"), "color", QColor(o["grid_color"])),
            ("guide_color", tr("Kleur hulplijnen:"), "color", QColor(o["guide_color"])),
            ("snap_dist", tr("Uitlijnafstand:"), "int", 1, 50, o["snap_dist"], " px")])
        if v is None:
            return
        for k, val in v.items():
            o[k] = val.name() if isinstance(val, QColor) else val
        self._save_view_opts()
        for sw in self.mdi.subWindowList():
            sw.canvas.update()

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
        nd.channels = list(d.channels)
        self.add_document(nd)

    def fit_window_to_image(self):
        sw = self.mdi.activeSubWindow()
        if sw and self.mdi.viewMode() == QMdiArea.ViewMode.SubWindowView:
            cv = sw.canvas
            sw.resize(int(cv.doc.w * cv.zoom) + (sw.width() - cv.width()) + 4,
                      int(cv.doc.h * cv.zoom) + (sw.height() - cv.height()) + 4)
            cv.center()

    PROJECT_URL = "https://github.com/rene-timmermans/pixelpickle"

    def check_updates(self):
        """Op updates controleren: de projectpagina openen (daar staan de nieuwste versies)."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(self.PROJECT_URL))

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
                    # sneltoets in de taal van het systeem (bijvoorbeeld Strg in het Duits)
                    keys = [QKeySequence(k).toString(QKeySequence.SequenceFormat.NativeText) or k for k in it["keys"]]
                    rows.append((" > ".join(path + [tr(name)]), ", ".join(keys)))
        walk(self.menu_tree, [])
        tools = [(f"Gereedschap: {t.name}", self.tool_key(t)) for t in self.tools.values() if self.tool_key(t)]
        html = "<table cellspacing=3>" + "".join(f"<tr><td>{tr(a)}</td><td style='padding-left:16px'><b>{b}</b></td></tr>"
                                                 for a, b in tools + rows) + "</table>"
        dialogs.text_window(self, tr("Toetsenbordlayout"), html, (760, 720)).exec()

    def about(self):
        dialogs.AboutDialog(self, self.windowIcon()).exec()

    def manual_html(self):
        """Beknopte gebruikershandleiding (Nederlands of Engels), met de echte sneltoetsen."""
        from . import i18n
        folder = os.path.join(os.path.dirname(__file__), "data")
        path = os.path.join(folder, f"manual_{i18n.language()}.html")
        if not os.path.exists(path):  # taal zonder eigen handleiding: Engels
            path = os.path.join(folder, "manual_en.html")
        html = open(path, encoding="utf-8").read()
        rows = "".join(f"<tr><td>{tr(t.name)}</td><td style='padding-left:16px'><b>{self.tool_key(t)}</b></td></tr>"
                       for t in self.tools.values() if t.available and self.tool_key(t))
        return html.replace("{tools}", f"<table cellspacing=2>{rows}</table>")

    def show_manual(self):
        """Uitgebreide handleiding (per gereedschap, menu en effect); zonder die bestanden de beknopte."""
        from . import manual
        page = manual.build() if os.path.exists(os.path.join(manual.DATA, "prose_en.json")) else self.manual_html()
        dialogs.text_window(self, tr("Gebruikershandleiding"), page, (900, 820)).show()

    # ---------------------------------------------------------------- automatisch opslaan
    def autosave_settings(self):
        a = self.autosaver
        dlg = dialogs.AutosaveDialog(self, a.enabled(), a.minutes())
        if dlg.exec():
            self.settings.setValue("autosave/enabled", "true" if dlg.enabled.isChecked() else "false")
            self.settings.setValue("autosave/minutes", dlg.minutes.value())
            a.apply_settings()

    def offer_recovery(self):
        """Na een onverwachte afsluiting: automatisch opgeslagen afbeeldingen terughalen."""
        import shutil
        from .autosave import leftovers
        found = leftovers()
        if not found:
            return
        names = [i["title"] for _, items in found for i in items]
        r = QMessageBox.question(
            self, APP, tr("PixelPickle is de vorige keer niet normaal afgesloten. Er zijn automatisch "
                          "opgeslagen afbeeldingen gevonden:\n\n{}\n\nWilt u deze herstellen?").format(
                "\n".join("• " + n for n in names)))
        for d, items in found:
            if r == QMessageBox.StandardButton.Yes:
                for info in items:
                    try:
                        doc = fileio.load(info["file"])
                    except Exception as e:
                        QMessageBox.warning(self, APP, f"Kan het bestand niet openen:\n{info['title']}\n\n{e}")
                        continue
                    doc.path = info.get("path")
                    if not doc.path:
                        doc.untitled = info["title"]
                    self.add_document(doc)
                    doc.set_modified(True)
                    doc.titleChanged.emit()
            shutil.rmtree(d, ignore_errors=True)

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
        if getattr(self, "_restart", False):  # herstarten na taalwissel
            restart_pixelpickle()
        if not getattr(self, "_prefs_reset", False):  # na Voorkeuren herstellen niets terugschrijven
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("state2", self.saveState())
        self.autosaver.shutdown()
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
