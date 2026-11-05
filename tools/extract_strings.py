"""Verzamelt alle (vermoedelijke) schermteksten van PixelPickle voor de vertaalcatalogus.
Gebruik: .venv/bin/python -I tools/extract_strings.py > strings.json"""
import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
SKIP_RE = re.compile(r"^([a-z0-9_.\-]+|#[0-9a-fA-F]{3,8}|[<>=!@]?[0-9A-Za-z]{1,4}|svg:.*|pixelpickle[-:].*|pigment[-:].*|"
                     r"brushwork[-:].*|.*\.(png|json|ora|py|qm)|~BK.*|[A-Z_]+)$")
out = {}


def add(s, why):
    if not isinstance(s, str):
        return
    s2 = s.strip()
    if not s2 or not re.search(r"[A-Za-zÀ-ÿ]", s2) or len(s) > 600 or SKIP_RE.match(s2):
        return
    if "/" in s2 and " " not in s2:
        return
    out.setdefault(s, why)


def template(node):
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant):
            parts.append(str(v.value).replace("{", "{{").replace("}", "}}"))
        else:
            parts.append("{}")
    t = "".join(parts).replace("{{", "{").replace("}}", "}")
    return t


for path in glob.glob(os.path.join(ROOT, "pixelpickle", "**", "*.py"), recursive=True):
    tree = ast.parse(open(path, encoding="utf-8").read())
    docstrings = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    joined_parts = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr):
            for v in n.values:
                joined_parts.add(id(v))
            t = template(n)
            if t.strip("{} :") and re.search(r"[A-Za-z]{2}", t.replace("{}", "")):
                add(t, os.path.basename(path))
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings and id(n) not in joined_parts:
            add(n.value, os.path.basename(path))

# menu's
data = json.load(open(os.path.join(ROOT, "pixelpickle", "data", "pp_menus.json"), encoding="utf-8"))


def walk(items):
    for it in items:
        if it:
            add(it["text"], "menu")
            walk(it["items"])


walk(data["menus"])
# effecten en gereedschappen
from pixelpickle import effects  # noqa: E402
from pixelpickle.psplayout import TOOL_NAMES  # noqa: E402

for eff in effects.load_all().values():
    add(eff.name, "effect")
    for p in eff.params:
        add(p["label"], "effectparameter")
        add(p["label"] + ":", "effectparameter")
        for o in p.get("options", []):
            add(o, "effectkeuze")
for n in TOOL_NAMES.values():
    add(n, "gereedschap")
json.dump(out, sys.stdout, ensure_ascii=False, indent=0)
