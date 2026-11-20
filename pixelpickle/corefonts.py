"""Microsoft core fonts (Arial, Times New Roman, Courier New, Verdana, Georgia, Trebuchet MS, Comic Sans MS,
Impact, Webdings, Andale Mono): download and install into the user's own font folder.

They may not be shipped with PixelPickle, but users may fetch the original installation files from the source
themselves (as ttf-mscorefonts-installer does on Debian). Extraction uses cabextract or 7z;
afterwards the fonts are made available in PixelPickle immediately (no restart)."""
import glob
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request

FILES = ["andale32", "arial32", "arialb32", "comic32", "courie32", "georgi32", "impact32", "times32", "trebuc32",
         "verdan32", "webdin32"]
URL = "https://downloads.sourceforge.net/corefonts/{}.exe"
FAMILIES = ["Arial", "Times New Roman", "Courier New", "Verdana", "Georgia", "Trebuchet MS", "Comic Sans MS",
            "Impact", "Webdings", "Andale Mono"]


def target_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "fonts", "msttcorefonts")


def installed():
    """Are the core fonts already available (anywhere on the system)?"""
    from PySide6.QtGui import QFontDatabase
    fams = set(QFontDatabase.families())
    return all(f in fams for f in ("Arial", "Times New Roman", "Courier New", "Verdana"))


def extractor():
    """Program to extract the installation files, or None."""
    for name in ("cabextract", "7z", "7za", "bsdtar"):
        if shutil.which(name):
            return name
    return None


def _extract(tool, exe, dest):
    if tool == "cabextract":
        cmd = ["cabextract", "-q", "-L", "-F", "*.ttf", "-d", dest, exe]
    elif tool in ("7z", "7za"):
        cmd = [tool, "e", "-y", f"-o{dest}", exe, "*.ttf", "*.TTF"]
    else:
        cmd = ["bsdtar", "-xf", exe, "-C", dest, "*.ttf"]
    subprocess.run(cmd, check=False, capture_output=True, timeout=120)


class Installer:
    """Download and install in the background. Follow progress with done, step, total, error and result."""

    def __init__(self):
        self.step, self.total = 0, len(FILES) + 1
        self.done, self.error, self.result = False, None, []
        self.cancel = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        tool = extractor()
        if tool is None:
            self.error = "noextractor"
            self.done = True
            return
        work = tempfile.mkdtemp(prefix="pixelpickle-fonts-")
        dest = target_dir()
        try:
            os.makedirs(dest, exist_ok=True)
            for name in FILES:
                if self.cancel:
                    self.error = "cancel"
                    return
                exe = os.path.join(work, name + ".exe")
                req = urllib.request.Request(URL.format(name), headers={"User-Agent": "PixelPickle"})
                with urllib.request.urlopen(req, timeout=60) as r, open(exe, "wb") as f:
                    shutil.copyfileobj(r, f)
                _extract(tool, exe, dest)
                self.step += 1
            for f in glob.glob(os.path.join(dest, "*.TTF")):  # lowercase, as is usual
                os.replace(f, f[:-4] + ".ttf")
            if shutil.which("fc-cache"):
                subprocess.run(["fc-cache", "-f", dest], check=False, capture_output=True, timeout=120)
            self.result = sorted(glob.glob(os.path.join(dest, "*.ttf")))
            if not self.result:
                self.error = "empty"
            self.step = self.total
        except OSError as e:  # no internet, write error...
            self.error = str(e)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self.done = True


def register(paths):
    """Make new fonts available in PixelPickle immediately (no restart)."""
    from PySide6.QtGui import QFontDatabase
    n = 0
    for p in paths:
        if QFontDatabase.addApplicationFont(p) >= 0:
            n += 1
    return n
