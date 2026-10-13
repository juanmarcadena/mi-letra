"""Glyphs from the averaged letters (data/avg.pkl), previews, and the font.

  python avgfont.py sheet            -> out/avg_candidates.png (every group's average, per character)
  python avgfont.py sample           -> out/avg_sample.png (same text at blend 0, 0.5, 1)
  python avgfont.py font 0.5         -> out/LetraJuan.ttf at that blend
"""
import math, os, pickle, sys
import numpy as np
from PIL import Image, ImageDraw
from letra import smooth

A = pickle.load(open("data/avg.pkl", "rb"))
ACUTE = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U"}
OTHER = {"ñ": "n", "Ñ": "N", "ü": "u", "Ü": "U"}
GAP, SPACE = 0.27, 1.25   # letter gap and word space in x-heights (look chosen 12 Oct 2026)


BOLD, SLANT = 1.0, 0.0   # per font file: pen-width multiplier (Bold) and rightward lean in x per unit of height (Italic)
TAPER = 1.25   # pen pressure along each stroke in the fonts: 0 = constant line, 1 = Juan's measured swell and thinning; he chose 25% beyond measured on 12 Oct 2026
JITTER = 1.4   # extra size/lean/height difference between versions (0 = none, 1 = slight, 2 = clear); Juan chose between 1 and 1.8 on 12 Oct 2026
STYLE, PAIRS = "molde", set()     # "molde": separate letters. "cursiva": also joins the pairs Juan usually joins.


def use_style(style):
    """Switch between the two styles. The cursive one adds joined pairs on top of the same letters."""
    global STYLE, PAIRS
    STYLE = style
    for k in [k for k in A if len(k) == 2]:
        del A[k]
    PAIRS = set()
    if style == "cursiva":
        P = pickle.load(open("data/avg_pairs.pkl", "rb"))
        if os.path.exists("data/pairs_ok.pkl"):      # pairs_check.py drops the ones that hurt legibility
            ok = set(pickle.load(open("data/pairs_ok.pkl", "rb"))["ok"])
            P = {k: v for k, v in P.items() if k in ok}
        A.update(P)
        PAIRS = set(P)
    _prof_cache.clear()


def _code(ch):
    return sum(ord(c) * (i * 257 + 1) for i, c in enumerate(ch))


def _gname(ch):
    return "_".join("uni%04X" % ord(c) for c in ch)


NVAR = 7    # variants per character in the font and the writer (a prime, so the rotation does not fall into step with word lengths)
# Which samples of each letter's pool serve as its variants, most legible first (variants.py writes this).
VARSEL = pickle.load(open("data/variants.pkl", "rb")) if os.path.exists("data/variants.pkl") else {}
FORCE_POOL = None   # measuring only: use this pool index for every letter


def raw(ch, t=0.35, v=0, cand=None):
    e = A.get(ch)
    if e is None:
        return None
    c = e["cands"][e["chosen"] if cand is None else cand]
    n = len(c["insts"])
    if FORCE_POOL is not None:
        i = FORCE_POOL % n
    else:
        sel = [k for k in VARSEL.get(ch, []) if k < n][:NVAR] if cand is None else []
        i = sel[v % len(sel)] if sel else v % min(n, NVAR)
    g = c["mean"] + t * (c["insts"][i] - c["mean"])
    if FORCE_POOL is None and cand is None and n < NVAR and v % NVAR >= n:
        # Too few real samples for a full set: the extra variants are existing ones with a
        # slight lean, stretch and size change, the way a hand varies.
        import random
        r = random.Random(_code(ch) * 131 + v % NVAR)
        ang, sx, sy, sh = r.gauss(0, 0.035), 1 + r.gauss(0, 0.035), 1 + r.gauss(0, 0.03), r.gauss(0, 0.05)
        ca, sa = math.cos(ang), math.sin(ang)
        cx, cy = float(g[..., 0].mean()), float(g[..., 1].min())
        X, Y = (g[..., 0] - cx) * sx, (g[..., 1] - cy) * sy
        X = X + sh * Y
        g = np.stack((cx + ca * X - sa * Y, cy + sa * X + ca * Y), axis=-1)
    return [smooth(s, 1) for s in g]


def bbox(frs):
    p = np.vstack(frs)
    return p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()


ALIAS = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u00ab": '"', "\u00bb": '"',
         "\u2212": "-", "\u2010": "-", "\u2011": "-", "\u00a0": " ", "\u202f": " ", "\u2009": " "}
MARKS = {"\u0301": "acute", "\u0300": "grave", "\u0302": "circ", "\u0308": "diaer", "\u0303": "tilde", "\u0327": "cedilla"}


def _place(g, cx, cy, scale=1.0, shear=0.0, flipx=False):
    x0, y0, x1, y1 = bbox(g)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for s in g:
        sx, sy = (s[:, 0] - mx) * scale * (-1 if flipx else 1), (s[:, 1] - my) * scale
        out.append(np.column_stack((sx + shear * sy + cx, sy + cy)))
    return out


def _acute(t, v, height=0.4):
    m = raw("'", t, v) or [np.array([[0.0, 0.0], [0.1, 0.4]])]
    x0, y0, x1, y1 = bbox(m)
    return _place(m, 0, 0, scale=height / max(1e-3, y1 - y0), shear=0.5)


def _dot(x, y):
    return np.array([[x, y - 0.025], [x + 0.015, y + 0.025]])


def _composed(ch, t, v):
    """Characters built from Juan's own strokes. Returns strokes or None."""
    import unicodedata
    if ch in "¿¡":
        g = raw("?" if ch == "¿" else "!", t, v)
        if g is None:
            return None
        x0, y0, x1, y1 = bbox(g)
        return _place(g, 0, 1.1 - (y1 - y0) * 0.62 / 2, scale=-0.62)   # rotated half a turn, hanging below the line
    nfd = unicodedata.normalize("NFD", ch)
    if len(nfd) == 2 and nfd[1] in MARKS:
        base, kind = nfd[0], MARKS[nfd[1]]
        g = raw(base, t, v)
        if g is None:
            return None
        if base in "ij" and kind != "cedilla":
            g = [s for s in g if s[:, 1].min() < 0.9] or g      # drop the dot
        x0, y0, x1, y1 = bbox(g)
        cx = (x0 + x1) / 2
        y = max(y1 + 0.3, 1.36) if base.islower() else y1 + 0.3
        if kind == "acute":
            g += [s + [cx + 0.1, y] for s in _acute(t, v)]
        elif kind == "grave":
            g += [np.column_stack((-s[:, 0] + cx - 0.1, s[:, 1] + y)) for s in _acute(t, v)]
        elif kind == "circ":
            g.append(np.array([[cx - 0.22, y - 0.12], [cx, y + 0.12], [cx + 0.22, y - 0.12]]))
        elif kind == "tilde":
            tt = np.linspace(0, 1, 14)
            g.append(np.column_stack((cx - 0.34 + 0.68 * tt, y - 0.02 - 0.075 * np.sin(tt * 2 * math.pi))))
        elif kind == "diaer":
            g += [_dot(cx - 0.19, y), _dot(cx + 0.19, y)]
        elif kind == "cedilla":
            c = raw(",", t, v)
            if c:
                g += _place(c, cx + 0.05, y0 - 0.22, scale=0.7)
        return g
    if ch == '"':
        a = raw("'", t, v)
        return None if a is None else a + [s + [0.22, 0] for s in raw("'", t, v + 1)]
    hy = raw("-", t, v)
    if ch in "–—" and hy:
        x0, y0, x1, y1 = bbox(hy)
        k = 1.6 if ch == "–" else 2.4
        return [np.column_stack(((s[:, 0] - x0) * k, s[:, 1])) for s in hy]
    if ch == "…":
        d = raw(".", t, v)
        return None if d is None else d + [s + [0.42, 0] for s in raw(".", t, v + 1)] + [s + [0.84, 0] for s in raw(".", t, v + 2)]
    if ch in "·•":
        return [np.array([[0.0, 0.5], [0.02, 0.5]])] if ch == "·" else \
               [np.column_stack((0.09 * np.cos(a_), 0.5 + 0.09 * np.sin(a_))) for a_ in [np.linspace(0, 2 * math.pi, 10)]] + [np.array([[-0.03, 0.5], [0.03, 0.5]])]
    if ch in "°ºª":
        g = raw("a" if ch == "ª" else "o", t, v)
        return None if g is None else _place(g, 0, 1.55, scale=0.5)
    if ch == "<":
        g = raw(">", t, v)
        return None if g is None else _place(g, 0, (bbox(g)[1] + bbox(g)[3]) / 2, flipx=True)
    if ch == "\\":
        g = raw("/", t, v)
        return None if g is None else _place(g, 0, (bbox(g)[1] + bbox(g)[3]) / 2, flipx=True)
    if ch == "|":
        g = raw("l", t, v)
        if g is None:
            return None
        x0, y0, x1, y1 = bbox(g)
        return [np.array([[0.0, y1 + 0.1], [0.02, -0.45]])]
    if ch == "^":
        return [np.array([[-0.24, 1.45], [0.0, 1.85], [0.24, 1.45]])]
    if ch == "`":
        return [np.column_stack((-s[:, 0], s[:, 1] + 1.75)) for s in _acute(t, v)]
    if ch == "€":
        g = raw("C", t, v)
        if g is None or hy is None:
            return None
        x0, y0, x1, y1 = bbox(g)
        cy = (y0 + y1) / 2
        hx0, _, hx1, _ = bbox(hy)
        bar = lambda dy: _place(hy, x0 + 0.25, cy + dy, scale=0.75 * (0.9 / max(0.3, hx1 - hx0)))
        return g + bar(0.14) + bar(-0.14)
    if ch in "≥≤" and hy:
        g = raw(">", t, v)
        if g is not None and ch == "≤":
            g = _place(g, 0, (bbox(g)[1] + bbox(g)[3]) / 2, flipx=True)
        if g is None:
            return None
        x0, y0, x1, y1 = bbox(g)
        return g + _place(hy, (x0 + x1) / 2, y0 - 0.2, scale=(x1 - x0) / max(0.2, bbox(hy)[2] - bbox(hy)[0]))
    if ch == "≠":
        e, sl = raw("=", t, v), raw("/", t, v)
        if e is None or sl is None:
            return None
        x0, y0, x1, y1 = bbox(e)
        return e + _place(sl, (x0 + x1) / 2, (y0 + y1) / 2, scale=0.55)
    return None


# Single samples keep whatever size and height they had in the notes, which means nothing
# on a form line. Fit them: (bottom, top) in x-heights, or a width with a centre height.
FIT_H = {"[": (-0.35, 1.95), "]": (-0.35, 1.95), "{": (-0.4, 2.0), "}": (-0.4, 2.0), "✓": (0.0, 1.25), "✗": (0.0, 1.0), "×": (0.1, 0.9)}
FIT_W = {"_": (0.85, -0.18), "→": (2.0, 0.5), "~": (1.0, 0.5)}


def glyph(ch, t=0.35, v=0, cand=None):
    """-> list of strokes (x from 0, baseline y=0, x-height 1) or None."""
    ch = ALIAS.get(ch, ch)
    g = None
    if cand is None:
        g = _composed(ch, t, v)          # composed first: raw samples of accented letters are mis-reads
    if g is None:
        g = raw(ch, t, v, cand)
    if g is None:
        return None
    if JITTER > 0 and cand is None:
        # Each version also differs a little in size, lean, width and height on the line,
        # the way repeated letters do in real writing. Same values every time for a given version.
        import random
        r = random.Random(_code(ch) * 977 + (v % NVAR) * 31 + 5)
        s_, wd, ang, dy = 1 + r.gauss(0, 0.045) * JITTER, 1 + r.gauss(0, 0.04) * JITTER, r.gauss(0, 0.03) * JITTER, r.gauss(0, 0.04) * JITTER
        ca, sa = math.cos(ang), math.sin(ang)
        bx0, _, bx1, _ = bbox(g)
        cx = (bx0 + bx1) / 2
        g = [np.column_stack((cx + ca * (p[:, 0] - cx) * s_ * wd - sa * p[:, 1] * s_,
                              sa * (p[:, 0] - cx) * s_ * wd + ca * p[:, 1] * s_ + dy)) for p in g]
    x0, y0, x1, y1 = bbox(g)
    if ch in FIT_H:
        lo, hi = FIT_H[ch]
        k = (hi - lo) / max(1e-3, y1 - y0)
        g = [np.column_stack(((s[:, 0] - x0) * k, (s[:, 1] - y0) * k + lo)) for s in g]
    elif ch in FIT_W:
        wd, cy = FIT_W[ch]
        k = wd / max(1e-3, x1 - x0)
        g = [np.column_stack(((s[:, 0] - x0) * k, (s[:, 1] - (y0 + y1) / 2) * min(k, 1.0) + cy)) for s in g]
    if SLANT:
        g = [np.column_stack((s[:, 0] + SLANT * s[:, 1], s[:, 1])) for s in g]
    x0 = bbox(g)[0]
    return [s - [x0, 0] for s in g]


EXTRA = "_[]{}<>|\\~^`°ºª€×→✓✗–—…·•≤≥≠" + "àèìòùâêîôûäëïöãõçÀÈÌÒÙÂÊÎÔÛÄËÏÖÃÕÇ" + '"'
FONT_CHARS = None   # filled in font()


# ---- spacing by shape -------------------------------------------------------------
# The gap between two letters is set so the white space between their facing sides,
# measured across the x-height band, is the same for every pair. SHAPE_T and SHAPE_D
# are fitted to the gaps Juan leaves between unjoined letters in his notes
# (spacing.py); TIGHT scales the result to taste. MIN_CLEAR keeps strokes from touching.
SPACING = "shape"            # "shape" or "fixed" (the old constant GAP)
SHAPE_T, SHAPE_D, MIN_CLEAR, TIGHT = 0.80, 0.35, 0.16, 1.0
_YS = np.round(np.arange(-0.7, 2.31, 0.1), 2)
_CORE = (_YS >= 0.05) & (_YS <= 0.95)
_prof_cache = {}


def profile(g):
    """Left indent l[y] and right indent r[y] of the ink at each height (nan = no ink), plus width."""
    pts = []
    for s in g:
        s = np.asarray(s, dtype="f8")
        if len(s) == 1:
            pts.append(s)
            continue
        seg = np.hypot(*np.diff(s, axis=0).T)
        n = np.maximum(1, np.ceil(seg / 0.03).astype(int))
        for (p, q), k in zip(zip(s[:-1], s[1:]), n):
            tt = np.linspace(0, 1, k + 1)[:, None]
            pts.append(p + (q - p) * tt)
    P = np.vstack(pts)
    x0, x1 = P[:, 0].min(), P[:, 0].max()
    l = np.full(len(_YS), np.nan)
    r = np.full(len(_YS), np.nan)
    for i, y in enumerate(_YS):
        m = np.abs(P[:, 1] - y) <= 0.06
        if m.any():
            l[i], r[i] = P[m, 0].min() - x0, x1 - P[m, 0].max()
    return l, r, x1 - x0


def _prof(ch, t, v):
    key = (ch, round(t, 3), v % NVAR, FORCE_POOL, JITTER, SLANT)
    if key not in _prof_cache:
        g = glyph(ch, t, v)
        _prof_cache[key] = None if g is None else profile(g)
    return _prof_cache[key]


def side(ind):
    """Mean indent of one side across the x-height band, capped at SHAPE_D (open space counts as SHAPE_D)."""
    c = ind[_CORE]
    return float(np.mean(np.minimum(np.where(np.isnan(c), SHAPE_D, c), SHAPE_D)))


def pair_gap(a, b, t=0.35, va=0, vb=0):
    """Distance from the right edge of a's ink to the left edge of b's ink, in x-heights."""
    pa, pb = _prof(a, t, va), _prof(b, t, vb)
    if pa is None or pb is None or SPACING != "shape":
        return GAP
    d = TIGHT * (SHAPE_T - side(pa[1]) - side(pb[0]))
    both = ~np.isnan(pa[1]) & ~np.isnan(pb[0])
    if both.any():                       # never let two strokes touch, at any height
        d = max(d, MIN_CLEAR - float(np.min(pa[1][both] + pb[0][both])))
    return d


def layout(text, t, seed=0):
    import random
    rnd, last = random.Random(seed * 7919 + 13), {}
    out, x, prev, i = [], 0.0, None, 0
    while i < len(text):
        ch = text[i]
        if ch == " " or ALIAS.get(ch) == " ":
            x += SPACE
            prev = None
            i += 1
            continue
        if text[i:i + 2] in PAIRS:            # cursive style: a pair he usually writes in one stroke
            ch = text[i:i + 2]
        i += len(ch)
        v = rnd.randrange(NVAR)
        if last.get(ch) == v:                 # never the same version of a letter twice running
            v = (v + 1 + rnd.randrange(NVAR - 1)) % NVAR
        last[ch] = v
        g = glyph(ch, t, v)
        if g is None:
            continue
        if prev is not None:
            x += pair_gap(prev[0], ch, t, prev[1], v)
        for s in g:
            out.append(s + [x, 0])
        x += bbox(g)[2]
        prev = (ch, v)
    return out, x


def draw(d, strokes, ox, oy, xh, w, fill=(15, 25, 115)):
    for s in strokes:
        pts = [(ox + x * xh, oy - y * xh) for x, y in s]
        d.line(pts, fill=fill, width=w, joint="curve")
        for p in (pts[0], pts[-1]):
            d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=fill)


def draw_pdf(page, text, rect, xh_pt=4.5, t=0.35, color=(0.05, 0.1, 0.45), seed=0, line_gap=None, pen=0.14):
    """Write text in the smoothed hand inside rect (x0, y0, x1, y1) of a PyMuPDF page; returns height used."""
    import random
    r = random.Random(seed)
    line_gap = line_gap or 4.2 * xh_pt
    width = (rect[2] - rect[0]) / xh_pt
    sh = page.new_shape()
    y, n = 2.3 * xh_pt, 0
    for para in text.split("\n"):
        x = 0.0
        for word in para.split():
            st, adv = layout(word, t, seed=seed + n)
            n += 1
            if x > 0 and x + adv > width:
                x, y = 0.0, y + line_gap
            dy, sc = r.gauss(0, 0.04), 1 + r.gauss(0, 0.02)
            for s in st:
                P = [(rect[0] + (x + px * sc) * xh_pt, rect[1] + y - (py * sc + dy) * xh_pt) for px, py in s]
                ink(sh, P, pen * xh_pt, color, r)
            x += adv * sc + SPACE + r.gauss(0, 0.08)
        y += line_gap
    sh.commit()
    return y - line_gap + 1.2 * xh_pt


def ink(sh, P, width, color, rnd):
    """Draw one pen stroke (points P, in PDF points) on a PyMuPDF shape: with Juan's pen pressure
    when TAPER is on (a filled outline), else as a plain line."""
    ext = max(max(a for a, _ in P) - min(a for a, _ in P), max(b for _, b in P) - min(b for _, b in P))
    if ext < 0.85 * width:        # a dot: zero-length lines do not print, so draw a filled circle
        cx, cy = sum(a for a, _ in P) / len(P), sum(b for _, b in P) / len(P)
        sh.draw_circle((cx, cy), max(width * 0.62, ext / 2))
        sh.finish(color=color, fill=color, width=0)
        return
    if TAPER <= 0:
        sh.draw_polyline(P)
        sh.finish(color=color, width=width, closePath=False, lineCap=1, lineJoin=1)
        return
    import make_font as MF
    g = MF.stroke_shape(P, width / 2, TAPER, rnd, 0.04 * width / 0.14).simplify(width * 0.03)
    for poly in ([g] if g.geom_type == "Polygon" else [x for x in g.geoms if x.geom_type == "Polygon"]):
        for ring in [poly.exterior] + list(poly.interiors):
            sh.draw_polyline(list(ring.coords))
        sh.finish(color=color, fill=color, width=0, even_odd=True, closePath=True)


def write_line(page, text, x, baseline, xh_pt=4.5, **kw):
    """One line of text starting at x with its baseline at `baseline` (PDF points, y down)."""
    return draw_pdf(page, text, (x, baseline - 2.3 * xh_pt, x + 2000, baseline + 50), xh_pt=xh_pt, **kw)


def sheet(chars=None, name="out/avg_candidates.png", cols=4):
    """Every group's average per character, numbered; the one in use is blue."""
    from PIL import ImageFont
    chars = [c for c in (chars or "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$/@.,*#()-:;%&+=?!'\"") if c in A]
    cw, rh, S = 400, 120, 2
    big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30 * S)
    small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13 * S)
    rows = (len(chars) + cols - 1) // cols
    img = Image.new("RGB", (cols * cw * S, rows * rh * S), "white")
    d = ImageDraw.Draw(img)
    for i, ch in enumerate(chars):
        ox, oy = (i % cols) * cw * S, (i // cols) * rh * S
        d.rectangle([ox, oy, ox + cw * S - 1, oy + rh * S - 1], outline=(215, 215, 215))
        d.text((ox + 8 * S, oy + 6 * S), ch, fill=(200, 0, 0), font=big)
        base = oy + 78 * S
        x = ox + 62 * S
        for k, c in enumerate(A[ch]["cands"]):
            on = k == A[ch]["chosen"]
            g = glyph(ch, 0.0, 0, cand=k)
            draw(d, g, x + 8 * S, base, 24 * S, 3 * S, fill=(15, 25, 115) if on else (150, 150, 150))
            d.text((x + 8 * S, oy + 98 * S), f"{k + 1}" + ("  (en uso)" if on else ""), fill=(15, 25, 115) if on else (120, 120, 120), font=small)
            x += 82 * S
    img.resize((cols * cw, rows * rh), Image.LANCZOS).save(name)


LINES = ["El 4 de octubre de 2026 intenté pagar una compra en línea",
         "con mi tarjeta de siempre. El pago no se completó.",
         "¿Pueden confirmar la fecha? Juan Martín Cadena",
         "Ciudad de México, 55 1234 5678, $1,250.00 MXN ¡Gracias!"]


def sample(name="out/avg_sample.png", blends=(0.0, 0.5, 1.0)):
    S, xh = 2, 15
    H = (len(LINES) * 62 + 50) * len(blends) + 20
    img = Image.new("RGB", (1500 * S, H * S), "white")
    d = ImageDraw.Draw(img)
    y = 20
    for t in blends:
        from PIL import ImageFont
        d.text((20 * S, (y - 8) * S), f"OPCION {int(t * 100)}%", fill=(200, 0, 0), font=ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24 * S))
        y += 50
        for i, ln in enumerate(LINES):
            st, _ = layout(ln, t, seed=i)
            draw(d, st, 30 * S, y * S, xh * S, int(2.0 * S))
            y += 62
    img.resize((1500, H), Image.LANCZOS).save(name)


def font(t, path="out/LetraJuan.ttf", face="Regular"):
    """face: Regular, Bold, Italic or Bold Italic. Bold is a heavier pen; Italic leans the writing."""
    import string
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    import make_font as MF
    global BOLD, SLANT, MIN_CLEAR
    bold, italic = "Bold" in face, "Italic" in face
    # Bold: 50% heavier pen. Italic: 20 degree lean and a pen 20% lighter (Juan, 12 Oct 2026).
    BOLD, SLANT = (1.5 if bold else 1.0) * (0.8 if italic else 1.0), (0.364 if italic else 0.0)
    base_pen, base_clear = MF.PEN, MIN_CLEAR
    MF.PEN = base_pen * BOLD
    MIN_CLEAR = base_clear + (MF.PEN - base_pen)        # a heavier pen needs more room before strokes touch
    _prof_cache.clear()
    XH = MF.XH
    shape = SPACING == "shape"
    chars = string.ascii_letters + string.digits + "$/@.,*#()-:;%&+=?!'áéíóúñüÁÉÍÓÚÑÜ¿¡" + EXTRA
    names, glyphs, metrics, cmap, classes = [".notdef", "space"], {}, {}, {32: "space", 160: "space"}, [[] for _ in range(NVAR)]
    glyphs[".notdef"], metrics[".notdef"] = TTGlyphPen(None).glyph(), (500, 0)
    prof, sides = {}, {}
    for ch in list(chars) + sorted(PAIRS):
        if glyph(ch, t, 0) is None:
            continue
        base = _gname(ch)
        for v in range(NVAR):
            g = glyph(ch, t, v)
            name = base if v == 0 else f"{base}.alt{v}"
            w = bbox(g)[2]
            if shape:     # side margins from the shape model: half the target minus this side's own white space
                l_, r_, _ = profile(g)
                lsb_x, rsb_x = TIGHT * (SHAPE_T / 2 - side(l_)), TIGHT * (SHAPE_T / 2 - side(r_))
                prof[name], sides[name] = (l_, r_), (lsb_x, rsb_x)
            else:
                lsb_x = rsb_x = GAP / 2
            lsb = int(round(lsb_x * XH))
            glyphs[name] = MF.glyph(MF.outline([(s, None) for s in g], taper=TAPER, seed=_code(ch) * 7 + v), lsb)
            metrics[name] = (max(1, int(round((lsb_x + w + rsb_x) * XH))), lsb)
            names.append(name)
            classes[v].append(name)
        if len(ch) == 1:
            cmap[ord(ch)] = base
    for a_, b_ in ALIAS.items():      # curly quotes, minus sign, odd spaces -> the same glyphs
        tgt = "space" if b_ == " " else "uni%04X" % ord(b_)
        if tgt in glyphs or tgt == "space":
            cmap[ord(a_)] = tgt
    mean_sb = float(np.mean([sum(sides[n]) for n in sides if n[:7] in ("uni0061", "uni0065", "uni006F", "uni006E", "uni0073")])) if shape else GAP
    sp_adv = int(round((SPACE + 0.27 - mean_sb) * XH))   # same word gap, ink to ink, as the fixed-gap font had
    # The space takes part in the rotation too (identical copies), so the cycle runs on across
    # words instead of restarting: otherwise every word would begin with the same version.
    for v in range(NVAR):
        name = "space" if v == 0 else f"space.alt{v}"
        glyphs[name], metrics[name] = TTGlyphPen(None).glyph(), (sp_adv, 0)
        if v:
            names.append(name)
        classes[v].append(name)
    fea = "".join("@s%d=[%s];\n" % (v, " ".join(c)) for v, c in enumerate(classes))
    if PAIRS:     # joined pairs replace the two letters first; the version rotation then runs over the result
        fea += "feature liga {\n" + "".join("  sub %s %s by %s;\n" % (_gname(p[0]), _gname(p[1]), _gname(p)) for p in sorted(PAIRS) if _gname(p) in glyphs) + "} liga;\n"
    fea += "feature calt {\n" + "".join("  sub @s%d @s0' by @s%d;\n" % (v, v + 1) for v in range(NVAR - 1)) + "} calt;\n"
    nk = 0
    if shape:     # kerning only where the side margins alone would let two strokes touch
        gl = list(prof)
        Rm = np.stack([np.where(np.isnan(prof[n][1]), 9.0, prof[n][1]) for n in gl])
        Lm = np.stack([np.where(np.isnan(prof[n][0]), 9.0, prof[n][0]) for n in gl])
        rs = np.array([sides[n][1] for n in gl]); ls = np.array([sides[n][0] for n in gl])
        rows = []
        for i in range(len(gl)):
            closest = (Rm[i][None, :] + Lm).min(axis=1)          # nearest approach to every following glyph
            need = MIN_CLEAR - closest - (rs[i] + ls)
            for j in np.where(need > 0.05)[0]:
                rows.append("  pos %s %s %d;" % (gl[i], gl[j], int(round(need[j] * XH))))
        nk = len(rows)
        if rows:
            fea += "feature kern {\n" + "\n".join(rows) + "\n} kern;\n"
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names); fb.setupCharacterMap(cmap); fb.setupGlyf(glyphs); fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=1050, descent=-520)
    fam = "Letra Juan Cursiva" if STYLE == "cursiva" else "Letra Juan"
    ps = fam.replace(" ", "") + "-" + face.replace(" ", "")
    fb.setupNameTable({"familyName": fam, "styleName": face, "fullName": fam + " " + face,
                       "psName": ps, "uniqueFontIdentifier": ps + ";1.12;2026-10-12",
                       "version": "Version 1.920"})   # apps look fonts up by PostScript name; without it Pages shows boxes
    # Style linking: these flags are what make an app's Bold and Italic buttons pick the right file.
    fs = (0x20 if bold else 0) | (0x01 if italic else 0) or 0x40
    fb.setupOS2(sTypoAscender=1050, sTypoDescender=-520, usWinAscent=1100, usWinDescent=560, sxHeight=XH, sCapHeight=int(1.9 * XH),
                usWeightClass=700 if bold else 400, fsSelection=fs)
    fb.setupPost(italicAngle=-20 if italic else 0)
    fb.font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
    fb.addOpenTypeFeatures(fea)
    fb.save(path)
    MF.PEN, MIN_CLEAR, BOLD, SLANT = base_pen, base_clear, 1.0, 0.0
    _prof_cache.clear()
    print("font saved:", path, "|", fam, face, "| characters:", len(cmap), "| kerning pairs", nk)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sample"
    if cmd == "sheet":
        sheet("abcdefghijklmnopqrstuvwxyz", "out/revision_1_minusculas.png")
        sheet("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "out/revision_2_mayusculas.png")
        sheet("0123456789$/@.,*#()-:;%&+=?!'", "out/revision_3_numeros_simbolos.png")
    elif cmd == "all":        # both families, four faces each
        t_ = float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
        for style, stem in (("molde", "LetraJuan"), ("cursiva", "LetraJuanCursiva")):
            use_style(style)
            for face in ("Regular", "Bold", "Italic", "Bold Italic"):
                font(t_, "out/%s%s.ttf" % (stem, "" if face == "Regular" else "-" + face.replace(" ", "")), face)
    elif cmd == "cursiva":
        use_style("cursiva")
        font(float(sys.argv[2]) if len(sys.argv) > 2 else 0.35, "out/LetraJuanCursiva.ttf")
    elif cmd == "font":
        font(float(sys.argv[2]) if len(sys.argv) > 2 else 0.35, *(sys.argv[3:4]))
    else:
        sample()
