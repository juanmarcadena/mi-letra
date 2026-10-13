"""Objective checks for the handwriting.

  python measure.py read   -> writes corpus.txt in the hand, has Apple's recogniser read it back,
                              prints the error rate and the most confused letters
  python measure.py gaps   -> compares letter gaps in generated text with the gaps in Juan's notes
"""
import difflib, os, pickle, sys, tempfile
from collections import Counter, defaultdict
import numpy as np
from PIL import Image, ImageDraw
import avgfont as F

XH, PENPX, ROWH, WIDTH = 26, 3, 120, 2600
LAST = {}


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def read_back(seeds=(0, 1, 2), t=0.35, verbose=True, detail=False):
    from verify import read
    lines = [l.strip() for l in open("corpus.txt", encoding="utf-8") if l.strip()]
    tmp = tempfile.mkdtemp()
    tot_e = tot_n = 0
    conf, per_char_err, per_char_n = Counter(), Counter(), Counter()
    line_err = []
    for seed in seeds:
        for b0 in range(0, len(lines), 8):
            batch = lines[b0:b0 + 8]
            img = Image.new("L", (WIDTH, ROWH * len(batch)), 255)
            d = ImageDraw.Draw(img)
            for r, ln in enumerate(batch):
                st, _ = F.layout(ln, t, seed=seed * 101 + b0 + r)
                F.draw(d, st, 30, r * ROWH + 78, XH, PENPX, fill=0)
            p = os.path.join(tmp, "m.png")
            img.save(p)
            rows = defaultdict(list)
            for x, yc, txt, cf in read(p):
                rows[min(len(batch) - 1, int(yc * len(batch)))].append((x, txt))
            for r, ln in enumerate(batch):
                got = " ".join(t_ for _, t_ in sorted(rows.get(r, [])))
                a, b = " ".join(ln.split()), " ".join(got.split())
                le = lev(a, b)
                tot_e += le
                tot_n += len(a)
                line_err.append((le, len(a)))
                per_char_n.update(a)
                for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
                    if op == "replace" and i2 - i1 == j2 - j1:
                        for x_, y_ in zip(a[i1:i2], b[j1:j2]):
                            conf[(x_, y_)] += 1
                            per_char_err[x_] += 1
                    elif op in ("replace", "delete"):
                        per_char_err.update(a[i1:i2])
    cer = tot_e / tot_n
    # The recogniser sometimes loses a whole line over one odd letter, which swamps everything
    # else. LAST holds a robust figure: each line's errors are capped at 30% of its length.
    global LAST
    LAST = dict(robust=sum(min(e, 0.3 * n) for e, n in line_err) / tot_n,
                lost_lines=sum(e > 0.3 * n for e, n in line_err), lines=len(line_err))
    if detail:
        return cer, per_char_err, per_char_n
    if verbose:
        print(f"read-back: {100 * (1 - cer):.1f}% of characters read correctly  ({tot_e} errors in {tot_n} characters, {len(seeds)} passes)")
        print(f"  without lost lines: {100 * (1 - LAST['robust']):.1f}%  (lines the recogniser lost entirely: {LAST['lost_lines']} of {LAST['lines']})")
        print("most confused (written -> read):", "  ".join(f"{a}->{b}:{n}" for (a, b), n in conf.most_common(18)))
        worst = sorted(((per_char_err[c] / per_char_n[c], c, per_char_n[c]) for c in per_char_n if per_char_n[c] >= 12 and c != " "), reverse=True)[:12]
        print("letters most often misread:", "  ".join(f"{c}:{100 * e:.0f}%" for e, c, n in worst))
    return cer


def note_gaps():
    """Median ink gap (x-heights) per adjacent pair that Juan wrote WITHOUT joining the two letters."""
    B = pickle.load(open("data/bank.pkl", "rb"))
    gaps, joined_n, all_n = defaultdict(list), 0, 0
    for w in B["words"]:
        if not w.get("ver"):
            continue
        L = w["label"]
        shared = set()
        for pc in w["pc"]:
            u = np.unique(pc)
            for a, b in zip(u[:-1], u[1:]):
                if b == a + 1:
                    shared.add(int(a))
        for i in range(len(L) - 1):
            a, b = w["cbox"][i], w["cbox"][i + 1]
            if a is None or b is None or w["q"][i] >= 1 or w["q"][i + 1] >= 1:
                continue
            all_n += 1
            if i in shared:
                joined_n += 1
                continue
            g = b[0] - a[2]
            if -0.6 < g < 1.2:
                gaps[L[i] + L[i + 1]].append(g)
    return gaps, joined_n, all_n


def gap_report(model=None, verbose=True):
    gaps, joined_n, all_n = note_gaps()
    pairs = {p: float(np.median(v)) for p, v in gaps.items() if len(v) >= 6}
    allg = np.concatenate([v for v in gaps.values()])
    if verbose:
        print(f"adjacent letter pairs in checked words: {all_n}; written joined: {joined_n} ({100 * joined_n / all_n:.0f}%); unjoined with a measurable gap: {len(allg)}")
        print(f"his unjoined gap: median {np.median(allg):.2f} x-heights (quartiles {np.percentile(allg, 25):.2f} to {np.percentile(allg, 75):.2f}); pairs with 6+ samples: {len(pairs)}")
    err = []
    for p, obs in pairs.items():
        ga, gb = F.glyph(p[0], 0.0, 0), F.glyph(p[1], 0.0, 0)
        if ga is None or gb is None:
            continue
        pred = F.pair_gap(p[0], p[1], 0.0, 0, 0) if model else F.GAP
        err.append((pred - obs, p))
    e = np.array([x for x, _ in err])
    if verbose:
        print(f"{'shape model' if model else 'fixed gap'}: average miss per pair {np.mean(np.abs(e)):.3f} x-heights (bias {np.mean(e):+.3f})")
    return pairs, err


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "read"
    if cmd == "read":
        read_back()
    else:
        gap_report(model=len(sys.argv) > 2)
