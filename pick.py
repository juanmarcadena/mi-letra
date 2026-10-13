"""Numbered sheet of every raw sample of one or more characters, each scaled to
its own cell, for picking by eye.   python pick.py 'J' out/pick_J.png [max]
Also saves the samples to data/pick.pkl (merged with what is there)."""
import os, pickle, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import avg
chars, name = sys.argv[1], sys.argv[2]
MAXN = int(sys.argv[3]) if len(sys.argv) > 3 else 120
B = pickle.load(open("data/bank.pkl", "rb"))
by = {}
for w in B["words"]:
    for ci, ch in enumerate(w["label"]):
        if ch in chars and w["cbox"][ci] is not None:
            frs, _ = avg.char_fragments(w, ci)
            by.setdefault(ch, []).append([np.asarray(f, dtype="f8") for f in frs])
P = pickle.load(open("data/pick.pkl", "rb")) if os.path.exists("data/pick.pkl") else {}
P.update(by); pickle.dump(P, open("data/pick.pkl", "wb"))
S, cw, rh, per = 2, 110, 120, 12
num = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15 * S)
big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30 * S)
rows = sum((min(len(by.get(c, [])), MAXN) + per - 1) // per for c in chars)
img = Image.new("RGB", ((per * cw + 60) * S, max(1, rows) * rh * S), "white"); d = ImageDraw.Draw(img)
r = 0
for ch in chars:
    v = by.get(ch, [])[:MAXN]
    d.text((8 * S, r * rh * S + 8 * S), ch, fill=(200, 0, 0), font=big)
    for i, frs in enumerate(v):
        rr, cc = r + i // per, i % per
        ox, oy = (60 + cc * cw) * S, rr * rh * S
        d.rectangle([ox, oy, ox + cw * S - 1, oy + rh * S - 1], outline=(215, 215, 215))
        p = np.vstack(frs); x0, y0, x1, y1 = p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()
        k = min((cw - 30) * S / max(x1 - x0, 0.3), (rh - 44) * S / max(y1 - y0, 0.3), 30 * S)
        for f in frs:
            pts = [(ox + 15 * S + (x - x0) * k, oy + (rh - 28) * S - (y - y0) * k) for x, y in f]
            if len(pts) > 1: d.line(pts, fill=(15, 25, 115), width=2 * S, joint="curve")
            else: d.ellipse([pts[0][0] - 3, pts[0][1] - 3, pts[0][0] + 3, pts[0][1] + 3], fill=(15, 25, 115))
        d.text((ox + 5 * S, oy + (rh - 22) * S), str(i), fill=(200, 0, 0), font=num)
    r += (len(v) + per - 1) // per
img.resize((img.width // S, img.height // S), Image.LANCZOS).save(name)
print({c: len(by.get(c, [])) for c in chars})
