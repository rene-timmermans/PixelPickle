"""Autosave: stores modified images at regular intervals in a recovery folder so they can be restored after
a crash or power failure. The user's own files are never overwritten. The recovery copy disappears on a
normal exit, when saving, or when closing an image.

Each running PixelPickle uses its own folder (process number), so two windows side by side do not see each
other's copies as 'left behind'."""
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
    """Recovery copies of a PixelPickle that is no longer running: [(folder, [info, ...])]."""
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
        self.saved = {}  # id(doc) -> (doc key, document)
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
        """Store modified images; remove copies of saved or closed images."""
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
            except Exception:  # saving to the recovery folder must never interrupt the work
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
        """Normal exit: remove all recovery copies of this session."""
        self.timer.stop()
        shutil.rmtree(self.dir, ignore_errors=True)
        self.saved.clear()
