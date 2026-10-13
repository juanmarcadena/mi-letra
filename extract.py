"""Extract labelled handwriting units (single letters and joined groups) from Notability notes.

Reads every .nbn bundle (read-only), pairs pen strokes with the per-character
rectangles of Notability's handwriting index, and writes data/units.pkl.
Coordinates are normalised: x from the unit's ink left edge, y up from the
baseline, both in x-height units.
"""
import glob, math, os, pickle, plistlib, struct, sys
import numpy as np

# The live Notability notes, or the frozen copy made by snapshot_raw.py when LETRA_RAW=1
# (use the copy to rebuild if the notes have changed or are gone).
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw") if os.environ.get("LETRA_RAW") == "1" \
    else os.path.expanduser("~/Library/Mobile Documents/ZP9ZJ4EF3S~com~gingerlabs~Notability/Documents")
XSET = set("acemnorsuvwxz")
MAXW = 6.0  # wider strokes are highlighter


def load_strokes(nbn):
    with open(os.path.join(nbn, "Session.plist"), "rb") as f:
        p = plistlib.load(f)
    objs = p["$objects"]
    c = next((o for o in objs if isinstance(o, dict) and "curvespoints" in o), None)
    if c is None:
        return [], []

    def data(k):
        v = c.get(k)
        if isinstance(v, plistlib.UID):
            v = objs[v.data]
        if isinstance(v, dict) and "NS.data" in v:
            v = v["NS.data"]
        return v

    pts, num, w = data("curvespoints"), data("curvesnumpoints"), data("curveswidth")
    if not pts or not num:
        return [], []
    P = np.frombuffer(pts, dtype="<f4").reshape(-1, 2)
    N = np.frombuffer(num, dtype="<i4")
    W = np.frombuffer(w, dtype="<f4") if w else np.ones(len(N), dtype="f4")
    out, i = [], 0
    for n in N:
        out.append(P[i:i + n])
        i += n
    return out, W


def load_chars(nbn, strokes=None):
    """-> list of pages; each page is list of (char, rect or None) in document coordinates.

    pageContentOrigin is relative to its own page, so later pages need the page
    height added. The height differs between notes; it is calibrated per note
    by maximising how many character centres land on ink.
    """
    f = os.path.join(nbn, "HandwritingIndex", "index.plist")
    if not os.path.exists(f):
        return []
    h = plistlib.load(open(f, "rb"))
    raw = []
    for key in sorted(h.get("pages", {}), key=lambda k: int(k) if k.isdigit() else 0):
        pg = h["pages"][key]
        t, cr = pg.get("text", ""), pg.get("characterRects", b"")
        if not t or len(cr) != 8 * len(t):
            continue
        ox, oy = pg.get("pageContentOrigin", [0, 0])
        R = np.frombuffer(cr, dtype="<f2").reshape(-1, 4).astype("f8")
        raw.append((int(key), t, R, ox, oy))
    H = 789.41
    if strokes and any(k > 1 for k, *_ in raw):
        cell = 3.0
        occ = set()
        for s in strokes:
            for x, y in s[:: max(1, len(s) // 40)]:
                occ.add((int(x // cell), int(y // cell)))
        samples = []
        for k, t, R, ox, oy in raw:
            if k < 2:
                continue
            ok = np.isfinite(R[:, 0]) & (R[:, 2] > 0)
            Rk = R[ok][:: max(1, int(ok.sum()) // 40)]
            samples += [(ox + r[0] + r[2] / 2, oy + r[1] + r[3] / 2, k - 1) for r in Rk]
        if samples:
            best = (-1, H)
            for cand in np.arange(600, 1000.01, 0.5):
                sc = sum((int(x // cell), int((y + m * cand) // cell)) in occ for x, y, m in samples)
                if sc > best[0]:
                    best = (sc, float(cand))
            H = best[1]
    pages = []
    for k, t, R, ox, oy in raw:
        oy = oy + (k - 1) * H
        page = []
        for ch, (x, y, w, hh) in zip(t, R):
            if not np.isfinite(x) or w <= 0 or hh <= 0:
                page.append((ch, None))
            else:
                page.append((ch, (ox + x, oy + y, ox + x + w, oy + y + hh)))
        pages.append(page)
    return pages


def path_len(s):
    d = np.diff(s, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def process(nbn, stats):
    """-> (words, gaps). A word keeps its strokes whole plus, for every point,
    the index of the character it belongs to, so any run of letters can be cut
    out later with its natural joins."""
    strokes, W = load_strokes(nbn)
    pages = load_chars(nbn, strokes)
    if not strokes or not pages:
        return [], []
    keep = [i for i, s in enumerate(strokes) if len(s) >= 1 and W[i] <= MAXW]
    sb = np.array([[strokes[i][:, 0].min(), strokes[i][:, 1].min(), strokes[i][:, 0].max(), strokes[i][:, 1].max()] for i in keep])
    scx, scy = (sb[:, 0] + sb[:, 2]) / 2, (sb[:, 1] + sb[:, 3]) / 2
    words, gaps = [], []
    stats["strokes"] += len(keep)
    used = set()
    for page in pages:
        idx = [k for k, (ch, r) in enumerate(page) if r is not None]
        if not idx:
            continue
        xh_all = [page[k][1][3] - page[k][1][1] for k in idx if page[k][0] in XSET]
        if len(xh_all) < 5:
            continue
        xh_note = float(np.median(xh_all))
        # lines -> baseline fit
        lines, start = [], 0
        for k, (ch, r) in enumerate(page + [("\n", None)]):
            if ch == "\n":
                lines.append((start, k))
                start = k + 1
        prev = None  # (x1, xh, word) of previous word on this line
        for a, b in lines:
            ks = [k for k in range(a, b) if page[k][1] is not None]
            xs = [k for k in ks if page[k][0] in XSET]
            if len(xs) < 3:
                continue
            cx = np.array([(page[k][1][0] + page[k][1][2]) / 2 for k in xs])
            by = np.array([page[k][1][3] for k in xs])
            xh = float(np.median([page[k][1][3] - page[k][1][1] for k in xs]))
            if not (0.5 * xh_note <= xh <= 1.8 * xh_note):
                continue
            sl, ic = 0.0, float(np.median(by))
            if len(xs) >= 6 and np.ptp(cx) > 30:
                s1, i1 = np.polyfit(cx, by, 1)
                if abs(s1) <= 0.15:
                    sl, ic = float(s1), float(i1)
            # words on this line
            prev = None
            k = a
            while k < b:
                if page[k][1] is None or page[k][0].isspace():
                    k += 1
                    continue
                e = k
                while e + 1 < b and page[e + 1][1] is not None and not page[e + 1][0].isspace():
                    e += 1
                ck = list(range(k, e + 1))
                k = e + 1
                R = np.array([page[c][1] for c in ck])
                pad = 0.25 * xh
                bx0, by0, bx1, by1 = R[:, 0].min() - pad, R[:, 1].min() - pad, R[:, 2].max() + pad, R[:, 3].max() + pad
                cand = np.where((scx >= bx0) & (scx <= bx1) & (scy >= by0) & (scy <= by1))[0]
                js = []
                for j in cand:
                    if j in used:
                        continue
                    p = strokes[keep[j]]
                    inside = ((p[:, 0] >= bx0) & (p[:, 0] <= bx1) & (p[:, 1] >= by0) & (p[:, 1] <= by1)).mean()
                    if inside >= 0.6:
                        js.append(j)
                if not js:
                    prev = None
                    continue
                bad = False
                for j in js:
                    p, bb = strokes[keep[j]], sb[j]
                    diag = math.hypot(bb[2] - bb[0], bb[3] - bb[1]) + 1e-6
                    if len(p) > 12 and path_len(p) / diag > 7:  # scribble / cross-out
                        bad = True
                if bad:
                    prev = None
                    continue
                used.update(js)
                stats["assigned"] += len(js)
                js.sort()
                allp = np.vstack([strokes[keep[j]] for j in js])
                x0, x1 = float(allp[:, 0].min()), float(allp[:, 0].max())
                base = sl * (x0 + x1) / 2 + ic
                ccx = (R[:, 0] + R[:, 2]) / 2
                st, pc = [], []
                for j in js:
                    p = strokes[keep[j]]
                    x = p[:, 0][:, None]
                    inside = (x >= R[:, 0]) & (x <= R[:, 2])
                    d = np.abs(x - ccx)
                    d = np.where(inside, d, d + 1e3)  # prefer rects containing the point
                    ci = d.argmin(axis=1)
                    # smooth: runs shorter than 3 points take the neighbour's label
                    if len(ci) > 4:
                        runs, s0 = [], 0
                        for t in range(1, len(ci) + 1):
                            if t == len(ci) or ci[t] != ci[s0]:
                                runs.append((s0, t))
                                s0 = t
                        for (r0, r1) in runs:
                            if r1 - r0 < 3 and len(runs) > 1:
                                ci[r0:r1] = ci[r0 - 1] if r0 > 0 else ci[r1]
                    st.append(np.column_stack(((p[:, 0] - x0) / xh, (base - p[:, 1]) / xh)).astype("f4"))
                    pc.append(ci.astype("i2"))
                wd = dict(label="".join(page[c][0] for c in ck), strokes=st, pc=pc,
                          widths=[float(W[keep[j]]) / xh for j in js], w=(x1 - x0) / xh, xh=xh,
                          rects=[((r[0] - x0) / xh, (base - r[3]) / xh, (r[2] - x0) / xh, (base - r[1]) / xh) for r in R],
                          note=os.path.basename(nbn), line=(os.path.basename(nbn), id(page), a))
                words.append(wd)
                if prev is not None:
                    g = (x0 - prev) / xh
                    if 0 < g < 5:
                        gaps.append(g)
                prev = x1
    return words, gaps


def main():
    stats = dict(strokes=0, assigned=0)
    words, gaps = [], []
    notes = sorted(glob.glob(BASE + "/*.nbn"))
    for n in notes:
        try:
            u, g = process(n, stats)
            words += u
            gaps += g
        except FileNotFoundError:
            continue
        except Exception as e:
            print("skip", os.path.basename(n), repr(e)[:100], file=sys.stderr)
    os.makedirs("data", exist_ok=True)
    pickle.dump(dict(words=words, word_gaps=gaps), open("data/words.pkl", "wb"))
    from collections import Counter
    import string
    c = Counter(ch for w in words for ch in w["label"])
    print(f"notes {len(notes)} | strokes {stats['strokes']} | used {stats['assigned']} | words {len(words)} "
          f"| letters {sum(c.values())} | word gaps {len(gaps)} (median {np.median(gaps):.2f} x-heights)")
    print("lower:", {ch: c[ch] for ch in string.ascii_lowercase})
    print("upper:", {ch: c[ch] for ch in string.ascii_uppercase})
    print("digits/sym:", {ch: c[ch] for ch in string.digits + "$/@.,*#()-:;%&+=?!\'\"~_"})


if __name__ == "__main__":
    main()
