"""Leest de menu- en sneltoetsindeling uit het PSP XI register (Wine bottle) en schrijft
brushwork/data/psp_menus.json. Gebruik: python tools/import_psp_layout.py <pad naar user.reg>"""
import json, os, re, struct, sys

REG = sys.argv[1]
OUT = os.path.join(os.path.dirname(__file__), '..', 'brushwork', 'data', 'psp_menus.json')
KEY = r'Software\\\\Corel\\\\Paint Shop Pro\\\\11\\\\UI Customization\\\\'

txt = open(REG, encoding='utf-8', errors='replace').read()


def values(section):
    m = re.search(r'\[' + KEY + re.escape(section) + r'\][^\n]*\n(.*?)(?=\n\[|\Z)', txt, re.S)
    out = {}
    for vm in re.finditer(r'"([^"]+)"=hex:([0-9a-f,\\\s]+)', m.group(1)):
        out[vm.group(1)] = bytes(int(x, 16) for x in re.findall(r'[0-9a-f]{2}', vm.group(2)))
    return out


VK = {0x70 + i: f'F{i+1}' for i in range(12)}
VK.update({0x2e: 'Del', 0x2d: 'Ins', 0x08: 'Backspace', 0x6b: 'Num++', 0x6d: 'Num+-', 0x21: 'PgUp',
           0x22: 'PgDown', 0x09: 'Tab', 0x1b: 'Esc', 0x24: 'Home', 0x23: 'End', 0xbb: '=', 0xbd: '-'})


def accelerators():
    acc = values('BCGKeyboard-0')['Accelerators']
    keys = {}
    for i in range(0, len(acc) - 5, 6):
        f, k, c = acc[i], int.from_bytes(acc[i+2:i+4], 'little'), int.from_bytes(acc[i+4:i+6], 'little')
        mods = ('Ctrl+' if f & 8 else '') + ('Alt+' if f & 0x10 else '') + ('Shift+' if f & 4 else '')
        kn = chr(k) if 0x30 <= k <= 0x5a else VK.get(k)
        if kn:
            keys.setdefault(c, []).append(mods + kn)
    return keys


def menutree(data, keys):
    pos = 0
    classes = {}
    count = [1]

    def rd(fmt):
        nonlocal pos
        v = struct.unpack_from(fmt, data, pos)[0]
        pos += struct.calcsize(fmt)
        return v

    def obj():
        nonlocal pos
        tag = rd('<H')
        if tag == 0xffff:
            rd('<H'); L = rd('<H'); classes[count[0]] = data[pos:pos+L]; pos += L; count[0] += 1
        count[0] += 1
        cid = rd('<I'); rd('<I'); rd('<I')
        L = data[pos]; pos += 1
        text = data[pos:pos+L].decode('cp1252'); pos += L
        pos += 32
        kids = [obj() for _ in range(rd('<H'))]
        if cid == 0 and not text:
            return None  # scheidingslijn
        return {'text': text, 'id': cid if cid != 0xffffffff else 0, 'keys': keys.get(cid, []), 'items': kids}

    rd('<I'); rd('<I')
    return [obj() for _ in range(rd('<H'))]


v = values('BCGToolBar-593980')
blob = v['Buttons'] + v.get('Buttons_EX1', b'')[1:] + v.get('Buttons_EX2', b'')[1:]
keys = accelerators()
tools = {f'{c:#06x}': k for c, k in keys.items() if 0xd000 <= c < 0xd200}
json.dump({'menus': menutree(blob, keys), 'tool_keys': tools}, open(OUT, 'w'), ensure_ascii=False, indent=1)
print('geschreven:', os.path.abspath(OUT))
