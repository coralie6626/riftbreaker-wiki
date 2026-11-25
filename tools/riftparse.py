"""Parser for The Riftbreaker's text data format (.ent, .dat, .rt, .resource, .biome, .mission, .kvp ...).

The format is a tree of entries:
    key "value"          -> key/value (value may be quoted, bare, or typed like float:"1.0")
    key { ... }          -> block (the brace may be on the next line)
    key                  -> bare flag (no value)
    { ... }              -> anonymous block (key "")
Comments: // to end of line, /* ... */.

A parsed block is a list of [key, value] pairs (keys repeat, order matters).
`to_obj` turns that into plain dicts, collecting repeated keys into lists.
"""
import re

_TOKEN = re.compile(r'"((?:[^"\\\n]|\\.)*)"|(\{)|(\})|([^\s{}"]+)')
_NUM = re.compile(r'^-?\d+(\.\d+)?([eE][-+]?\d+)?$')
_TYPED = re.compile(r'^(string|float|int|bool|uint|vec3|vector):(.*)$', re.S)


def _strip_comments(text):
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == '"' or c == '\n':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True; out.append(c); i += 1
        elif text.startswith('//', i):
            j = text.find('\n', i)
            i = n if j < 0 else j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            seg = text[i:n if j < 0 else j + 2]
            out.append('\n' * seg.count('\n'))
            i = n if j < 0 else j + 2
        else:
            out.append(c); i += 1
    return ''.join(out)


def tokenize(text):
    text = _strip_comments(text.replace('\r\n', '\n').replace('\r', '\n'))
    toks, line = [], 1
    pos = 0
    skip_line = -1  # a stray quote can hide a // comment from _strip_comments
    for m in _TOKEN.finditer(text):
        line += text.count('\n', pos, m.start())
        pos = m.start()
        s, lb, rb, w = m.groups()
        if line == skip_line:
            continue
        if lb: toks.append(('{', '{', line))
        elif rb: toks.append(('}', '}', line))
        elif s is not None: toks.append(('s', s, line))
        elif w.startswith('//'):
            skip_line = line
        else:
            toks.append(('w', w, line))
    return toks


def _clean(v):
    m = _TYPED.match(v)
    if m:
        v = m.group(2).strip('"')
    return v


def parse(text):
    toks = tokenize(text)
    i, n = 0, len(toks)

    def block():
        nonlocal i
        items = []
        while i < n:
            kind, val, line = toks[i]
            if kind == '}':
                i += 1
                return items
            if kind == '{':  # anonymous block
                i += 1
                items.append(['', block()])
                continue
            key = val
            i += 1
            if i < n and toks[i][0] == '{':
                i += 1
                items.append([key, block()])
                continue
            # collect value tokens on the same line
            vals = []
            while i < n and toks[i][0] in ('s', 'w') and toks[i][2] == line:
                vals.append(toks[i][1]); i += 1
            if i < n and toks[i][0] == '{' and toks[i][2] == line and vals:
                # "key name {" -> treat as named block
                i += 1
                items.append([key, [['__name__', ' '.join(vals)]] + block()])
                continue
            if not vals:
                items.append([key, None])
            else:
                joined = ''.join(vals) if len(vals) == 2 and vals[0].endswith(':') else ' '.join(vals)
                items.append([key, _clean(joined)])
        return items

    return block()


def num(v):
    """Convert numeric strings to int/float, leave others."""
    if isinstance(v, str) and _NUM.match(v.strip()):
        f = float(v)
        return int(f) if f.is_integer() and '.' not in v and 'e' not in v.lower() else f
    return v


def to_obj(items, numbers=True):
    """[[k, v], ...] -> dict (repeated keys become lists). Flags become True."""
    if items is None:
        return True
    if not isinstance(items, list):
        return num(items) if numbers else items
    d = {}
    for k, v in items:
        if k == '__name__':
            d['__name__'] = v; continue
        v = to_obj(v, numbers)
        if k in d:
            if not isinstance(d[k], list) or not getattr(d[k], '_multi', False):
                d[k] = _Multi([d[k]])
            d[k].append(v)
        else:
            d[k] = v
    return {k: (list(v) if isinstance(v, _Multi) else v) for k, v in d.items()}


class _Multi(list):
    _multi = True


def as_list(v):
    if v is None: return []
    return v if isinstance(v, list) else [v]


def parse_file(path):
    import os
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        path = '\\\\?\\' + os.path.abspath(path)
    with open(path, 'rb') as f:
        data = f.read()
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return parse(data.decode(enc))
        except UnicodeDecodeError:
            continue
