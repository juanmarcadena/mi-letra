"""Build out/LetraJuan.ttf from the letter bank: three real variants of every
character, rotated automatically (OpenType calt) so repeated letters differ.
Accents, ñ, ¿ and ¡ are composed from Juan's own strokes."""
import random, string, sys
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from letra import Hand

XH, PEN, NVAR = 400, 0.115, 3            # font units per x-height; pen width in x-heights
CHARS = string.ascii_letters + string.digits + "$/@.,*#()-:;%&+=?!'\"_áéíóúñüÁÉÍÓÚÑÜ¿¡"


# Juan's typical pen-width profile from the start to the end of a stroke, measured over
# 37,000 strokes in his notes: the pen lands thin, swells through the middle, lifts thin.
TAPER_PROFILE = np.array([0.57, 0.88, 1.06, 1.13, 1.16, 1.18, 1.21, 1.16, 0.64])


def stroke_shape(p, r0, taper, rnd, step):
    """One pen stroke (centre line p, any units) -> shapely shape with Juan's pressure profile.
    r0 is the average half-width, step the resampling distance, both in the same units as p."""
    p = np.asarray(p, dtype="f8")
    if len(p) == 1 or np.ptp(p, axis=0).max() < 1e-6:
        return Point(p[0]).buffer(r0, 6)
    if taper <= 0:
        return LineString(p).buffer(r0, 6, cap_style=1, join_style=1)
    seg = np.hypot(*np.diff(p, axis=0).T)
    d = np.r_[0, np.cumsum(seg)]
    L = d[-1]
    n = max(2, int(L / step) + 1)
    t = np.linspace(0, L, n)
    q = np.column_stack((np.interp(t, d, p[:, 0]), np.interp(t, d, p[:, 1])))
    k = taper * min(1.0, max(0.3, (L / (step / 0.04)) / 0.6)) * (1 + rnd.gauss(0, 0.15))   # short strokes taper less
    w = 1 + k * (np.interp(t / L, np.linspace(0, 1, 9), TAPER_PROFILE) - 1)
    r = np.maximum(0.28, w) * r0
    parts = [Point(q[i]).buffer(r[i], 3) for i in range(n)]
    for i in range(n - 1):
        v = q[i + 1] - q[i]
        ln = np.hypot(*v)
        if ln < 1e-9:
            continue
        nx, ny = -v[1] / ln, v[0] / ln
        parts.append(Polygon([(q[i][0] + nx * r[i], q[i][1] + ny * r[i]), (q[i + 1][0] + nx * r[i + 1], q[i + 1][1] + ny * r[i + 1]),
                              (q[i + 1][0] - nx * r[i + 1], q[i + 1][1] - ny * r[i + 1]), (q[i][0] - nx * r[i], q[i][1] - ny * r[i])]))
    return unary_union(parts)


def outline(frs, taper=0.0, seed=0):
    """Stroke centre lines (x-height units) -> filled outline in font units. taper=0: constant
    pen width. taper=1: Juan's measured swell and thinning along each stroke; larger exaggerates it."""
    import random
    rnd = random.Random(seed)
    shapes = [stroke_shape(np.asarray(f, dtype="f8") * XH, PEN * XH / 2, taper, rnd, 0.04 * XH) for f, _ in frs]
    g = unary_union(shapes).simplify(0.6)
    return [g] if g.geom_type == "Polygon" else [x for x in g.geoms if x.geom_type == "Polygon"]


def glyph(polys, dx):
    pen = TTGlyphPen(None)
    for poly in polys:
        poly = orient(poly, sign=-1.0)       # outer clockwise, holes counter-clockwise
        for ring in [poly.exterior] + list(poly.interiors):
            pts = [(int(round(x + dx)), int(round(y))) for x, y in list(ring.coords)[:-1]]
            if len(pts) < 3:
                continue
            pen.moveTo(pts[0])
            for q in pts[1:]:
                pen.lineTo(q)
            pen.closePath()
    return pen.glyph()


def main():
    names, glyphs, metrics, cmap, classes = [".notdef", "space"], {}, {}, {32: "space", 160: "space"}, [[] for _ in range(NVAR)]
    empty = TTGlyphPen(None).glyph()
    glyphs[".notdef"], metrics[".notdef"] = empty, (500, 0)
    glyphs["space"], metrics["space"] = TTGlyphPen(None).glyph(), (int(1.05 * XH), 0)
    missing = []
    for ch in CHARS:
        made = []
        for v in range(NVAR):
            h = Hand(seed=1000 * v + ord(ch))
            frs, adv = h._word(ch)
            if not frs:
                continue
            made.append((frs, adv))
        if not made:
            missing.append(ch)
            continue
        while len(made) < NVAR:
            made.append(made[len(made) % len(made)])
        base = "uni%04X" % ord(ch)
        for v, (frs, adv) in enumerate(made):
            name = base if v == 0 else f"{base}.alt{v}"
            lsb = int(0.07 * XH)
            glyphs[name] = glyph(outline(frs), lsb)
            metrics[name] = (int(adv * XH + 0.2 * XH), lsb)
            names.append(name)
            classes[v].append(name)
        cmap[ord(ch)] = base
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=1050, descent=-520)
    fb.setupNameTable({"familyName": "Letra Juan", "styleName": "Regular", "fullName": "Letra Juan Regular",
                       "psName": "LetraJuan-Regular", "uniqueFontIdentifier": "LetraJuan-Regular;1.1;2026-10-12",
                       "version": "Version 1.100"})   # apps look fonts up by PostScript name; without it Pages shows boxes
    fb.setupOS2(sTypoAscender=1050, sTypoDescender=-520, usWinAscent=1100, usWinDescent=560, sxHeight=XH, sCapHeight=int(1.9 * XH))
    fb.setupPost()
    fea = "@s0=[%s];\n@s1=[%s];\n@s2=[%s];\nfeature calt {\n  sub @s0 @s0' by @s1;\n  sub @s1 @s0' by @s2;\n} calt;\n" % tuple(" ".join(c) for c in classes)
    fb.addOpenTypeFeatures(fea)
    fb.save("out/LetraJuan.ttf")
    print("glyphs:", len(names), "| characters:", len(cmap), "| missing:", missing)


if __name__ == "__main__":
    main()
