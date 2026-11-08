"""Microsoft-kernlettertypen (Arial, Times New Roman, Courier New, Verdana, Georgia, Trebuchet MS, Comic Sans MS,
Impact, Webdings, Andale Mono) downloaden en installeren in de eigen lettertypemap van de gebruiker.

Ze mogen niet met PixelPickle worden meegeleverd, maar de gebruiker mag de originele installatiebestanden zelf
bij de bron ophalen (zoals ttf-mscorefonts-installer op Debian doet). Uitpakken gaat met cabextract of 7z;
daarna worden ze meteen in PixelPickle bruikbaar gemaakt (zonder herstart)."""
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
    """Zijn de kernlettertypen al beschikbaar (ergens op het systeem)?"""
    from PySide6.QtGui import QFontDatabase
    fams = set(QFontDatabase.families())
    return all(f in fams for f in ("Arial", "Times New Roman", "Courier New", "Verdana"))


def extractor():
    """Programma om de installatiebestanden uit te pakken, of None."""
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
    """Download en installatie op de achtergrond. Volg de voortgang met done, step, total, error en result."""

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
            for f in glob.glob(os.path.join(dest, "*.TTF")):  # kleine letters, zoals gebruikelijk
                os.replace(f, f[:-4] + ".ttf")
            if shutil.which("fc-cache"):
                subprocess.run(["fc-cache", "-f", dest], check=False, capture_output=True, timeout=120)
            self.result = sorted(glob.glob(os.path.join(dest, "*.ttf")))
            if not self.result:
                self.error = "empty"
            self.step = self.total
        except OSError as e:  # geen internet, schrijffout...
            self.error = str(e)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self.done = True


def register(paths):
    """Nieuwe lettertypen meteen in PixelPickle bruikbaar maken (zonder herstart)."""
    from PySide6.QtGui import QFontDatabase
    n = 0
    for p in paths:
        if QFontDatabase.addApplicationFont(p) >= 0:
            n += 1
    return n
