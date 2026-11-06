"""Automatisch opslaan: bewaart gewijzigde afbeeldingen op gezette tijden in een herstelmap, zodat ze na
een crash of stroomstoring terug te halen zijn. De eigen bestanden van de gebruiker worden niet
overschreven. Bij normaal afsluiten, opslaan of sluiten van een afbeelding verdwijnt de herstelkopie.

Elk lopend PixelPickle gebruikt een eigen map (procesnummer), zodat twee vensters naast elkaar elkaars
kopieën niet als 'achtergebleven' zien."""
import json
import os
import shutil
import uuid

from PySide6.QtCore import QObject, QTimer


def base_dir():
    data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(data, "PixelPickle", "autosave")


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def leftovers():
    """Herstelkopieën van een PixelPickle dat niet meer draait: [(map, [info, ...])]."""
    out = []
    root = base_dir()
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d) or (name.isdigit() and int(name) != os.getpid() and _alive(int(name))):
            continue
        if name == str(os.getpid()):
            continue
        items = []
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                try:
                    info = json.load(open(os.path.join(d, f), encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                info["file"] = os.path.join(d, f[:-5] + ".ora")
                if os.path.exists(info["file"]):
                    items.append(info)
        if items:
            out.append((d, items))
        else:
            shutil.rmtree(d, ignore_errors=True)
    return out


class AutoSaver(QObject):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.dir = os.path.join(base_dir(), str(os.getpid()))
        self.saved = {}  # id(doc) -> (doc-sleutel, document)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.apply_settings()

    def enabled(self):
        return str(self.main.settings.value("autosave/enabled", "false")).lower() == "true"

    def minutes(self):
        try:
            return max(1, min(999, int(self.main.settings.value("autosave/minutes", 5))))
        except (TypeError, ValueError):
            return 5

    def apply_settings(self):
        self.timer.stop()
        if self.enabled():
            self.timer.start(self.minutes() * 60 * 1000)

    def _docs(self):
        out = {}
        for sw in self.main.mdi.subWindowList():
            d = sw.canvas.doc
            out[id(d)] = d
        return out

    def tick(self):
        """Gewijzigde afbeeldingen bewaren; kopieën van opgeslagen of gesloten afbeeldingen weghalen."""
        from . import fileio
        docs = self._docs()
        for key, d in docs.items():
            if not d.modified:
                continue
            if not hasattr(d, "_autosave_key"):
                d._autosave_key = uuid.uuid4().hex[:12]
            os.makedirs(self.dir, exist_ok=True)
            base = os.path.join(self.dir, d._autosave_key)
            try:
                fileio.save_ora(d, base + ".tmp.ora")
                os.replace(base + ".tmp.ora", base + ".ora")
                with open(base + ".json", "w", encoding="utf-8") as f:
                    json.dump({"path": d.path, "title": d.title().rstrip(" *")}, f)
                self.saved[key] = (d._autosave_key, d)
            except Exception:  # opslaan in de herstelmap mag het werk nooit onderbreken
                continue
        self.cleanup(docs)

    def cleanup(self, docs=None):
        docs = self._docs() if docs is None else docs
        for key, (k, d) in list(self.saved.items()):
            if key not in docs or docs[key] is not d or not d.modified:
                self._remove(k)
                del self.saved[key]

    def _remove(self, k):
        for ext in (".ora", ".json"):
            try:
                os.remove(os.path.join(self.dir, k + ext))
            except OSError:
                pass

    def shutdown(self):
        """Normaal afsluiten: alle herstelkopieën van deze sessie weg."""
        self.timer.stop()
        shutil.rmtree(self.dir, ignore_errors=True)
        self.saved.clear()
