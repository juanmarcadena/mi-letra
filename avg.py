"""Clean, averaged version of each letter.

For every character: gather its samples, even out their size and baseline,
group them by how they were drawn (number of strokes, then shape), and average
within each group. Writes data/avg.pkl:
  {char: {"cands": [{"mean": [M x 2 arrays], "insts": [[...], ...], "n": size}], "chosen": 0}}
A glyph at blend t is  mean + t * (instance - mean):  t=0 is the pure average,
t=1 a real (size-evened) sample from the same group.
"""
import itertools, pickle, sys
from collections import defaultdict
import numpy as np
from bank import char_fragments

M = 32
POOL = 10     # samples kept per letter; avgfont uses the most legible NVAR of them
import os
MERGE = os.environ.get("MERGE") == "1"   # experiment: merge look-alike groups
TAU = float(os.environ.get("TAU", "0.13"))   # x-heights, RMS distance between group averages
OUT = "data/avg_merged.pkl" if MERGE else "data/avg.pkl"
DOTTY = set("ij.:;!?'\",")


def plen(p):
    d = np.diff(p, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def resample(p, m=M):
    p = np.asarray(p, dtype="f8")
    if len(p) == 1:
        return np.repeat(p, m, axis=0)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    if d[-1] < 1e-9:
        return np.repeat(p[:1], m, axis=0)
    t = np.linspace(0, d[-1], m)
    return np.column_stack((np.interp(t, d, p[:, 0]), np.interp(t, d, p[:, 1])))


def collect(words):
    by = defaultdict(list)
    for w in words:
        for ci, ch in enumerate(w["label"]):
            b = w["cbox"][ci]
            if b is None or w["q"][ci] >= 1.0:
                continue
            frs, _ = char_fragments(w, ci)
            frs = [np.asarray(f, dtype="f8") for f in frs]
            if ch not in DOTTY:
                big = [f for f in frs if plen(f) >= 0.15]
                frs = big or frs
            if not frs or len(frs) > 4:
                continue
            by[ch].append((frs, w["ver"], w["q"][ci]))
    return by


def even_geometry(insts):
    """Same height and baseline for every sample of a character."""
    B = np.array([[np.vstack(f)[:, 1].min(), np.vstack(f)[:, 1].max()] for f in insts])
    y0m, y1m = np.median(B[:, 0]), np.median(B[:, 1])
    hm = y1m - y0m
    out = []
    for frs, (y0, y1) in zip(insts, B):
        allp = np.vstack(frs)
        cx = (allp[:, 0].min() + allp[:, 0].max()) / 2
        if hm >= 0.5 and y1 - y0 > 1e-3:
            s = min(1.3, max(0.75, hm / (y1 - y0)))
            out.append([np.column_stack(((f[:, 0] - cx) * s, (f[:, 1] - y0) * s + y0m)) for f in frs])
        else:
            cy = (y0 + y1) / 2
            out.append([np.column_stack((f[:, 0] - cx, f[:, 1] - cy + (y0m + y1m) / 2)) for f in frs])
    return out


def align(vecs, k):
    """vecs: n x k x M x 2. Reorder / reverse strokes of each sample to best match the running mean."""
    n = len(vecs)
    V = vecs.copy()
    tot = np.array([sum(plen(s) for s in v) for v in V])
    ref = V[np.argsort(tot)[n // 2]].copy()
    perms = list(itertools.permutations(range(k)))
    flips = list(itertools.product((False, True), repeat=k))
    for _ in range(2):
        for i in range(n):
            best, bv = None, None
            for pm in perms:
                for fl in flips:
                    c = np.stack([vecs[i][pm[j]][::-1] if fl[j] else vecs[i][pm[j]] for j in range(k)])
                    d = ((c - ref) ** 2).sum()
                    if best is None or d < best:
                        best, bv = d, c
            V[i] = bv
        ref = V.mean(axis=0)
    return V


def kmeans(X, K, rng, it=25, restarts=6):
    best = None
    for _ in range(restarts):
        C = X[rng.choice(len(X), K, replace=False)]
        for _ in range(it):
            lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
            C = np.stack([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(K)])
        cost = ((X - C[lab]) ** 2).sum()
        if best is None or cost < best[0]:
            best = (cost, lab.copy())
    return best[1]


def build_char(items, rng):
    ver = [it for it in items if it[1]]
    use = ver if len(ver) >= 25 else items
    by_k = defaultdict(list)
    for frs, _, q in use:
        by_k[len(frs)].append(frs)
    cands = []
    n_all = len(use)
    for k, insts in by_k.items():
        if len(insts) < max(3, 0.08 * n_all):
            continue
        insts = even_geometry(insts)
        vecs = np.stack([np.stack([resample(f) for f in frs]) for frs in insts])
        V = align(vecs, k)
        X = V.reshape(len(V), -1)
        K = 1 if len(X) < 12 else (2 if len(X) < 40 else 3)
        lab = kmeans(X, K, rng) if K > 1 else np.zeros(len(X), dtype=int)
        if MERGE:   # join groups whose averages are nearly the same shape
            while True:
                ids = [j for j in np.unique(lab)]
                means = {j: V[lab == j].mean(axis=0) for j in ids}
                best = None
                for a in ids:
                    for b in ids:
                        if a < b:
                            rms = float(np.sqrt(((means[a] - means[b]) ** 2).sum(-1).mean()))
                            if rms < TAU and (best is None or rms < best[0]):
                                best = (rms, a, b)
                if best is None:
                    break
                lab[lab == best[2]] = best[1]
        for j in np.unique(lab):
            m = lab == j
            if m.sum() < max(3, 0.1 * n_all):
                continue
            G = V[m]
            mean = G.mean(axis=0)
            # tighten: average again over the half closest to the mean
            d = ((G - mean) ** 2).reshape(len(G), -1).sum(1)
            core = G[d <= np.quantile(d, 0.6)]
            mean = core.mean(axis=0)
            d = ((G - mean) ** 2).reshape(len(G), -1).sum(1)
            order = d.argsort()
            # a pool of real samples, from very typical to moderately unusual, to draw variants from
            idxs = list(dict.fromkeys(int(qt * (len(G) - 1)) for qt in np.linspace(0.05, 0.65, POOL)))
            pick = [G[order[i]] for i in idxs]
            cands.append(dict(mean=mean, insts=pick, n=int(m.sum()), k=k, spread=float(np.median(d))))
    if not cands:  # too few samples: fall back to the single most typical one
        frs = min(items, key=lambda it: it[2])[0]
        frs = even_geometry([frs])[0]
        v = np.stack([resample(f) for f in frs])
        cands = [dict(mean=v, insts=[v, v, v], n=1, k=len(frs), spread=0.0)]
    cands.sort(key=lambda c: -c["n"])
    return dict(cands=cands[:4], chosen=0, n=n_all)


def main():
    B = pickle.load(open("data/bank.pkl", "rb"))
    by = collect(B["words"])
    rng = np.random.default_rng(7)
    out = {}
    for ch, items in sorted(by.items()):
        if len(ch) != 1 or ord(ch) > 0x2FF:
            continue
        out[ch] = build_char(items, rng)
    # Manual corrections made by eye from out/avg_candidates.png and out/pick.png (12 Oct 2026):
    # which group to use, and for J which raw samples are really a J.
    import os
    # Lowercase forms chosen with Juan on 12 Oct 2026 (decision 2): r3, n2, u2, v2.
    # Uppercase forms chosen on 12 Oct 2026 (decision 3): Y2, V2, N2, Z2, B2, D3.
    for ch, k in {"/": 1, "(": 1, "r": 2, "n": 1, "u": 1, "v": 1, "Y": 1, "V": 1, "N": 1, "Z": 1, "B": 1, "D": 2,
                  "1": 1, "5": 1, "-": 1}.items():   # digits and symbols (decision 4): 1 with flag, 5 with top bar, short hyphen
        if ch in out and len(out[ch]["cands"]) > k:
            out[ch]["chosen"] = k
    # The index choices above only hold while the grouping comes out the same. data/choices.pkl
    # keeps the approved shape of every character; when present, each character uses whichever
    # group is closest to its approved shape, so a rebuild cannot silently swap a letter's form.
    if os.path.exists("data/choices.pkl") and os.environ.get("LETRA_IGNORE_CHOICES") != "1":
        refs = pickle.load(open("data/choices.pkl", "rb"))
        drift = []
        for ch, e in out.items():
            ref = refs.get(ch)
            if ref is None or ch in "J*&#[]>×→✓✗_~{}":   # those come from hand-picked raw samples, below
                continue
            best = None
            for k, c in enumerate(e["cands"]):
                if c["mean"].shape != ref.shape:
                    continue
                V = align(np.stack([ref, c["mean"]]), ref.shape[0]) if ref.shape[0] <= 4 else np.stack([ref, c["mean"]])
                rms = float(np.sqrt(((V[0] - V[1]) ** 2).sum(-1).mean()))
                if best is None or rms < best[0]:
                    best = (rms, k)
            if best is not None:
                e["chosen"] = best[1]
                if best[0] > 0.12:
                    drift.append(f"{ch}:{best[0]:.2f}")
        print("characters whose closest group drifted from the approved shape:", " ".join(drift) or "none")
    if os.path.exists("data/pick.pkl"):
        P = pickle.load(open("data/pick.pkl", "rb"))
        # Raw samples picked with Juan from out/decision_5_*.png (12 Oct 2026, decision 5).
        # The first index is the glyph itself; the others only lend it some variation.
        # Extra characters picked by eye from out/pick_extra.png (12 Oct 2026).
        for ch, idx in {"J": [4, 1, 11], "*": [34, 6, 31], "&": [41], "#": [13],
                        "[": [1, 3, 4], "]": [0, 1, 2], ">": [1, 10, 11], "×": [5, 7, 13], "→": [3, 19, 20],
                        "✓": [1, 17, 0], "✗": [3, 5, 7], "_": [1, 0, 7], "~": [1, 2],
                        "{": [3, 11, 12], "}": [2, 4, 11]}.items():
            insts = [P[ch][i] for i in idx if i < len(P.get(ch, []))]
            if not insts:
                continue
            insts = [[f for f in fr if plen(f) >= 0.15] or fr for fr in insts]
            k = len(insts[0])
            insts = [fr for fr in insts if len(fr) == k]
            if k > 5:
                insts = insts[:1]
            ev = even_geometry(insts)
            V = np.stack([np.stack([resample(f) for f in fr]) for fr in ev])
            if len(V) > 1:
                V = align(V, k)
            pick = list(V)
            out[ch] = dict(cands=[dict(mean=V[0], insts=pick, n=len(V), k=k, spread=0.0)], chosen=0, n=len(V))
    pickle.dump(out, open(OUT, "wb"))
    row = lambda s: " ".join(f"{c}:{out[c]['cands'][0]['n']}/{out[c]['n']}({len(out[c]['cands'])})" for c in s if c in out)
    print("chars:", len(out))
    print("a-z  main-group size / samples (groups):", row("abcdefghijklmnopqrstuvwxyz"))
    print("A-Z:", row("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    print("0-9 sym:", row("0123456789$/@.,*#()-:;%&+=?!'\""))


if __name__ == "__main__":
    main()
