"""Write text in Juan's handwriting by reusing real pen strokes from his notes.

    from letra import Hand
    hand = Hand(seed=1)
    lines = hand.layout("texto", width_pt=400, xh_pt=4.2)   # -> strokes in points
    hand.draw_pdf(page, "texto", rect, xh_pt=4.2)             # onto a PyMuPDF page

Text is matched greedily against the longest runs of letters that exist in
the notes (whole words when possible), so natural joins are kept. Spanish
accents, ñ, ¿ and ¡ are composed from Juan's own strokes.
"""
import math, os, pickle, random, unicodedata
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACUTE = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U"}
OTHER = {"ñ": "n", "Ñ": "N", "ü": "u", "Ü": "U"}
QMAX = 0.55   # "in the middle": only the more typical half of his letters


def smooth(p, it=2):
    """Chaikin corner cutting: rounds the coarse pen samples, keeps the end points."""
    p = np.asarray(p, dtype="f8")
    for _ in range(it):
        if len(p) < 3:
            break
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        mid = np.empty((2 * len(q), 2))
        mid[0::2], mid[1::2] = q, r
        p = np.vstack((p[:1], mid, p[-1:]))
    return p


class Hand:
    def __init__(self, seed=None, bank=os.path.join(HERE, "data", "bank.pkl"), qmax=QMAX):
        B = pickle.load(open(bank, "rb"))
        self.words, self.index, self.word_gaps = B["words"], B["index"], np.array(B["word_gaps"])
        self.rng = random.Random(seed)
        self.qmax = qmax
        self.missing = set()

    # ---------- cutting pieces out of source words ----------
    def _cut(self, wi, a, n):
        w = self.words[wi]
        frs, ws, cidx = [], [], []
        for s, pc, wd in zip(w["strokes"], w["pc"], w["widths"]):
            m = (pc >= a) & (pc < a + n)
            i, L = 0, len(m)
            while i < L:
                if m[i]:
                    j = i
                    while j + 1 < L and m[j + 1]:
                        j += 1
                    frs.append(s[i:j + 1].astype("f8").copy())
                    ws.append(wd)
                    cidx.append(pc[i:j + 1] - a)
                    i = j + 1
                else:
                    i += 1
        allp = np.vstack(frs)
        x0, x1 = allp[:, 0].min(), allp[:, 0].max()
        for f in frs:
            f[:, 0] -= x0
        boxes = []
        for k in range(a, a + n):
            b = w["cbox"][k]
            boxes.append((b[0] - x0, b[1], b[2] - x0, b[3]))
        # natural gaps to the neighbours this piece had in its own word
        gl = gr = None
        if a > 0 and w["cbox"][a - 1]:
            gl = w["cbox"][a][0] - w["cbox"][a - 1][2]
        if a + n < len(w["label"]) and w["cbox"][a + n]:
            gr = w["cbox"][a + n][0] - w["cbox"][a + n - 1][2]
        return dict(frs=frs, ws=ws, cidx=cidx, width=x1 - x0, boxes=boxes, gl=gl, gr=gr)

    def _pick(self, key, at_start, at_end):
        cands = self.index.get(key)
        if not cands:
            return None
        good = [c for c in cands if c[2] <= self.qmax]
        ver = [c for c in good if c[5]]   # read the same way by two recognisers
        if ver:
            good = ver
        elif len(key) >= 3:
            return None
        elif len(key) == 2:
            good = [c for c in good if c[2] <= 0.3]
            if not good:
                return None
        if not good:
            good = sorted(cands, key=lambda c: c[2])[: max(1, len(cands) // 3)]
        ctx = [c for c in good if c[3] == at_start and c[4] == at_end] or \
              [c for c in good if c[3] == at_start] or good
        ctx = sorted(ctx, key=lambda c: c[2])
        return self.rng.choice(ctx[: max(3, len(ctx) // 2)])

    # ---------- composed marks ----------
    def _mark(self, kind):
        """Small mark normalised so its centre is (0,0); returns fragments+widths or None."""
        src = {"acute": "'", "dot": ".", "tilde": "~"}[kind]
        c = self._pick(src, False, False) or self._pick(src, True, True)
        if c is None:
            if kind == "tilde":
                t = np.linspace(0, 1, 9)
                f = np.column_stack((t * 0.7 - 0.35, 0.07 * np.sin(t * 2 * math.pi) * -1))
                return [f], [0.09]
            return None
        p = self._cut(c[0], c[1], 1)
        allp = np.vstack(p["frs"])
        cx, cy = (allp[:, 0].min() + allp[:, 0].max()) / 2, (allp[:, 1].min() + allp[:, 1].max()) / 2
        frs = [f - [cx, cy] for f in p["frs"]]
        if kind == "tilde":
            wdt = max(1e-3, np.ptp(allp[:, 0]))
            frs = [f * [0.7 / wdt, min(1.0, 0.7 / wdt)] for f in frs]
        if kind == "acute":
            h = max(1e-3, np.ptp(allp[:, 1]))
            k = min(1.0, 0.42 / h)
            frs = [f * k for f in frs]
            # make it lean like an acute accent: shear right going up
            frs = [np.column_stack((f[:, 0] + 0.45 * f[:, 1], f[:, 1])) for f in frs]
        return frs, p["ws"]

    def _decorate(self, piece, k, ch):
        """Add accent/tilde/dieresis over letter k of the piece, for target char ch."""
        b = piece["boxes"][k]
        cx, top = (b[0] + b[2]) / 2, b[3]
        base = ACUTE.get(ch) or OTHER.get(ch)
        if ch in ACUTE and base == "i":
            # drop the dot of the i (a small separate fragment above the x-height)
            keep = []
            for f, w_, ci in zip(piece["frs"], piece["ws"], piece["cidx"]):
                if (ci == k).all() and f[:, 1].min() > 0.95 and np.ptp(f[:, 1]) < 0.35 and np.ptp(f[:, 0]) < 0.35:
                    continue
                keep.append((f, w_, ci))
            if keep:
                piece["frs"], piece["ws"], piece["cidx"] = map(list, zip(*keep))
            top = max(f[:, 1].max() for f, ci in zip(piece["frs"], piece["cidx"]) if (ci == k).any()) if keep else top
        kind = "acute" if ch in ACUTE else ("tilde" if base in "nN" else "dot")
        y = max(top + 0.32, 1.38 if base.islower() else top + 0.32)
        marks = []
        if kind == "dot":
            for dx in (-0.2, 0.2):
                m = self._mark("dot")
                if m:
                    marks.append((m, cx + dx + 0.05))
        else:
            m = self._mark(kind)
            if m:
                marks.append((m, cx + (0.12 if kind == "acute" else 0.02)))
        for (frs, ws), mx in marks:
            for f, w_ in zip(frs, ws):
                piece["frs"].append(f + [mx + self.rng.gauss(0, 0.03), y + self.rng.gauss(0, 0.02)])
                piece["ws"].append(w_)
                piece["cidx"].append(np.full(len(f), k))

    def _inverted(self, ch):
        src = "?" if ch == "¿" else "!"
        c = self._pick(src, False, True) or self._pick(src, True, True)
        if c is None:
            return None
        p = self._cut(c[0], c[1], 1)
        allp = np.vstack(p["frs"])
        cx, cy = p["width"] / 2, (allp[:, 1].min() + allp[:, 1].max()) / 2
        h = np.ptp(allp[:, 1])
        p["frs"] = [np.column_stack((2 * cx - f[:, 0], 2 * cy - f[:, 1] - (cy - (1.0 - h / 2)))) for f in p["frs"]]
        p["gl"] = p["gr"] = None
        return p

    # ---------- words and lines ----------
    def _word(self, word):
        """-> list of placed fragments [(xy array, width)], total advance. Units: x-heights."""
        base = "".join(ACUTE.get(c) or OTHER.get(c) or c for c in word)
        pieces, i, n = [], 0, len(base)
        while i < n:
            if word[i] in "¿¡":
                p = self._inverted(word[i])
                if p:
                    pieces.append(p)
                else:
                    self.missing.add(word[i])
                i += 1
                continue
            got = None
            for L in range(min(6, n - i), 0, -1):
                if any(ch in "¿¡" for ch in word[i:i + L]):
                    continue
                c = self._pick(base[i:i + L], i == 0, i + L == n)
                if c:
                    got = (c, L)
                    break
            if not got:
                self.missing.add(word[i])
                i += 1
                continue
            c, L = got
            p = self._cut(c[0], c[1], L)
            for k in range(L):
                if word[i + k] != base[i + k]:
                    self._decorate(p, k, word[i + k])
            pieces.append(p)
            i += L
        for p in pieces:
            p["frs"] = [smooth(f) for f in p["frs"]]
        out, x, prev = [], 0.0, None
        for p in pieces:
            if prev is not None:
                gs = [g for g in (prev["gr"], p["gl"]) if g is not None]
                gap = float(np.mean(gs)) if gs else 0.12
                gap = min(0.45, max(-0.12, gap))
                x += gap
            for f, w_ in zip(p["frs"], p["ws"]):
                out.append((f + [x, 0.0], w_))
            x += p["width"]
            prev = p
        return out, x

    def layout(self, text, width_pt, xh_pt=4.2, line_gap=None, jitter=1.0):
        """-> (list of (points Nx2 in pt, y down, origin top-left of block; pen width pt), height_pt)."""
        r = self.rng
        line_gap = line_gap or xh_pt * 4.4
        strokes, y_line = [], xh_pt * 2.2
        for para in text.split("\n"):
            x = r.uniform(0, 0.4) * xh_pt
            slope = r.gauss(0, 0.004) * jitter
            for word in para.split():
                frs, adv = self._word(word)
                sc = xh_pt * (1 + r.gauss(0, 0.03) * jitter)
                if x > 0 and x + adv * sc > width_pt:
                    x, y_line = r.uniform(0, 0.4) * xh_pt, y_line + line_gap
                    slope = r.gauss(0, 0.004) * jitter
                dy = r.gauss(0, 0.05) * xh_pt * jitter
                for f, w_ in frs:
                    px = x + f[:, 0] * sc
                    py = y_line + dy + slope * px - f[:, 1] * sc
                    strokes.append((np.column_stack((px, py)), w_ * sc))
                x += adv * sc + min(1.9, max(1.05, r.gauss(1.4, 0.2))) * xh_pt
            y_line += line_gap
        return strokes, y_line - line_gap + xh_pt * 1.2

    def draw_pdf(self, page, text, rect, xh_pt=4.2, color=(0.05, 0.1, 0.45), pen_pt=None, **kw):
        """Write text inside rect (x0, y0, x1, y1) on a PyMuPDF page. Returns the height used."""
        strokes, h = self.layout(text, rect[2] - rect[0], xh_pt, **kw)
        sh = page.new_shape()
        for pts, w_ in strokes:
            w_ = pen_pt or min(0.17 * xh_pt, max(0.11 * xh_pt, w_ * 0.6))
            P = [(rect[0] + x, rect[1] + y) for x, y in pts]
            if len(P) == 1:
                sh.draw_circle(P[0], w_ / 2)
                sh.finish(color=color, fill=color, width=0)
            else:
                sh.draw_polyline(P)
                sh.finish(color=color, width=w_, closePath=False, lineCap=1, lineJoin=1)
        sh.commit()
        return h
