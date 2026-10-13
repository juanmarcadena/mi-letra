"""Score every letter instance and index all runs of 1-6 letters.

Reads data/words.pkl, writes data/bank.pkl:
  words  - as extracted, plus per-letter quality percentile `q` (0 = most typical)
  index  - {text run: [(word_idx, start, worst_q, at_word_start, at_word_end), ...]}
"""
import pickle, sys
from collections import defaultdict
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

GW, GH = 20, 26          # descriptor grid
X_HALF, Y0, Y1 = 1.3, -1.0, 2.2   # frame in x-height units
MAXN = 6


def char_fragments(w, c0, c1=None):
    """Stroke pieces (arrays) and widths for letters c0..c1 of word w."""
    c1 = c0 if c1 is None else c1
    out, ws = [], []
    for s, pc, wd in zip(w["strokes"], w["pc"], w["widths"]):
        m = (pc >= c0) & (pc <= c1)
        if not m.any():
            continue
        i, n = 0, len(m)
        while i < n:
            if m[i]:
                j = i
                while j + 1 < n and m[j + 1]:
                    j += 1
                a, b = max(0, i - 1) if c0 > 0 and i > 0 and False else i, j
                out.append(s[a:b + 1])
                ws.append(wd)
                i = j + 1
            else:
                i += 1
    return out, ws


def descriptor(frags):
    allp = np.vstack(frags)
    cx = (allp[:, 0].min() + allp[:, 0].max()) / 2
    S = 4
    img = Image.new("L", (GW * S, GH * S), 0)
    d = ImageDraw.Draw(img)
    fx = lambda x: (x - cx + X_HALF) / (2 * X_HALF) * GW * S
    fy = lambda y: (Y1 - y) / (Y1 - Y0) * GH * S
    for f in frags:
        pts = [(fx(x), fy(y)) for x, y in f]
        if len(pts) == 1:
            d.ellipse([pts[0][0] - 3, pts[0][1] - 3, pts[0][0] + 3, pts[0][1] + 3], fill=255)
        else:
            d.line(pts, fill=255, width=5)
    img = img.filter(ImageFilter.GaussianBlur(3)).resize((GW, GH), Image.BILINEAR)
    v = np.asarray(img, dtype="f4").ravel()
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def cboxes(w):
    out = []
    for ci in range(len(w["label"])):
        fr, _ = char_fragments(w, ci)
        if not fr:
            out.append(None)
            continue
        p = np.vstack(fr)
        out.append((float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())))
    return out


XSET = set("acemnorsuvwxz")


def main():
    D = pickle.load(open("data/words.pkl", "rb"))
    words = D["words"]
    # Pass 1: the recogniser's rectangles are padded line boxes, so re-normalise
    # each note from the ink itself: x-letter ink height -> 1, ink bottom -> 0.
    per_note, allh, ally = defaultdict(lambda: ([], [])), [], []
    for w in words:
        w["cbox"] = cboxes(w)
        for ch, b in zip(w["label"], w["cbox"]):
            if ch in XSET and b and 0.05 < b[3] - b[1] < 1.5:
                per_note[w["note"]][0].append(b[3] - b[1])
                per_note[w["note"]][1].append(b[1])
                allh.append(b[3] - b[1])
                ally.append(b[1])
    gk, gs = float(np.median(allh)), float(np.median(ally))
    per_line = defaultdict(lambda: ([], []))
    for w in words:
        for ch, b in zip(w["label"], w["cbox"]):
            if ch in XSET and b and 0.05 < b[3] - b[1] < 1.5:
                per_line[w.get("line")][0].append(b[3] - b[1])
                per_line[w.get("line")][1].append(b[1])
    for w in words:
        hs, ys = per_note[w["note"]]
        k, sh = (float(np.median(hs)), float(np.median(ys))) if len(hs) >= 15 else (gk, gs)
        lh, ly = per_line[w.get("line")]
        if len(lh) >= 5:   # enough x-letters on this line: use the line's own size and baseline
            k, sh = 0.5 * k + 0.5 * float(np.median(lh)), float(np.median(ly))
        w["strokes"] = [np.column_stack((s[:, 0] / k, (s[:, 1] - sh) / k)).astype("f4") for s in w["strokes"]]
        w["widths"] = [x / k for x in w["widths"]]
        w["w"] /= k
        w["xh"] *= k
        w["cbox"] = cboxes(w)
    D["word_gaps"] = [g / gk for g in D["word_gaps"]]
    by_label = defaultdict(list)   # char -> [(word_idx, char_idx, descriptor)]
    for wi, w in enumerate(words):
        w["q"] = [1.0] * len(w["label"])
        for ci, ch in enumerate(w["label"]):
            b = w["cbox"][ci]
            if b is None or b[2] - b[0] > 6 or b[3] - b[1] > 7:
                continue
            fr, _ = char_fragments(w, ci)
            by_label[ch].append((wi, ci, descriptor(fr)))
    for ch, items in by_label.items():
        V = np.stack([d for _, _, d in items])
        if len(items) < 6:
            for wi, ci, _ in items:
                words[wi]["q"][ci] = 0.5
            continue
        mean = V.mean(axis=0)
        for _ in range(3):   # trimmed mean: recentre on the closest 60%
            dist = np.linalg.norm(V - mean, axis=1)
            mean = V[dist <= np.quantile(dist, 0.6)].mean(axis=0)
        dist = np.linalg.norm(V - mean, axis=1)
        rank = dist.argsort().argsort() / (len(items) - 1)
        for (wi, ci, _), r in zip(items, rank):
            words[wi]["q"][ci] = float(r)
    # Geometry check: an instance sitting off the baseline, or much bigger or
    # wider than that letter usually is, was mis-read or comes from a formula.
    geo = defaultdict(list)
    for wi, w in enumerate(words):
        for ci, ch in enumerate(w["label"]):
            if w["cbox"][ci]:
                geo[ch].append((wi, ci))
    dropped = 0
    for ch, items in geo.items():
        if len(items) < 4:
            continue
        B = np.array([words[wi]["cbox"][ci] for wi, ci in items])
        y0m, y1m, wm = np.median(B[:, 1]), np.median(B[:, 3]), np.median(B[:, 2] - B[:, 0])
        for (wi, ci), b in zip(items, B):
            tol = 0.35 + 0.2 * (y1m - y0m)
            if abs(b[1] - y0m) > tol or abs(b[3] - y1m) > tol or (b[2] - b[0]) > 1.8 * wm + 0.35 or (b[2] - b[0]) < 0.35 * wm - 0.05:
                words[wi]["q"][ci] = 1.0
                dropped += 1
    print("geometry outliers dropped:", dropped)
    # Second opinion from Apple's recogniser (verify.py), when available.
    import os
    ocr = pickle.load(open("data/ocr.pkl", "rb")) if os.path.exists("data/ocr.pkl") else {}
    norm = lambda s: "".join(s.split()).casefold()
    for wi, w in enumerate(words):
        w["ver"] = wi in ocr and norm(ocr[wi][0]) == norm(w["label"])
    print("verified words:", sum(w["ver"] for w in words), "of", len(words))
    index = defaultdict(list)
    for wi, w in enumerate(words):
        L = len(w["label"])
        for a in range(L):
            for n in range(1, min(MAXN, L - a) + 1):
                if any(w["cbox"][k] is None for k in range(a, a + n)):
                    break
                q = max(w["q"][a:a + n])
                index[w["label"][a:a + n]].append((wi, a, q, a == 0, a + n == L, w["ver"]))
    pickle.dump(dict(words=words, index=dict(index), word_gaps=D["word_gaps"]), open("data/bank.pkl", "wb"))
    print("labels scored:", len(by_label), "| index keys:", len(index),
          "| runs:", sum(len(v) for v in index.values()))
    wd = [x for w in words for x in w["widths"]]
    print("pen width / x-height: median %.3f" % np.median(wd), "| x-height median %.1f doc units" % np.median([w["xh"] for w in words]))


if __name__ == "__main__":
    main()
