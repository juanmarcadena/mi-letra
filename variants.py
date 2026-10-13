"""Choose which samples of each letter's pool become its variants, by legibility.

Writes the test text once per pool position (every letter using its k-th sample), has
Apple's recogniser read it back, and ranks each letter's samples by how often that letter
was misread. Saves data/variants.pkl; avgfont uses the first NVAR of each list.
   python variants.py"""
import pickle
import avgfont as F, measure as M
POOL = 10
err = {}
for k in range(POOL):
    F.FORCE_POOL = k
    F._prof_cache.clear()
    cer, e, n = M.read_back(seeds=(0,), verbose=False, detail=True)
    print(f"pool position {k}: {100 * (1 - cer):.1f}% read correctly", flush=True)
    for ch in n:
        err.setdefault(ch, {})[k] = (e[ch] / n[ch], n[ch])
F.FORCE_POOL = None
sel, dropped = {}, []
for ch, d in err.items():
    e = F.A.get(ch)
    if e is None or ch == " ":
        continue
    npool = len(e["cands"][e["chosen"]]["insts"])
    if npool < 2 or min(n for _, n in d.values()) < 12:
        continue
    ranked = sorted(range(npool), key=lambda k: (round(d[k][0], 3), k))
    best = d[ranked[0]][0]
    keep = [k for k in ranked if d[k][0] <= best + 0.20] or ranked[:1]     # drop samples clearly harder to read
    if len(keep) < len(ranked[:F.NVAR]):
        dropped.append(f"{ch}:{len(ranked) - len(keep)}")
    sel[ch] = keep[:F.NVAR]
pickle.dump(sel, open("data/variants.pkl", "wb"))
print("letters ranked:", len(sel), "| samples dropped as clearly harder to read:", " ".join(dropped) or "none")
print("variants per letter after selection:", " ".join(f"{ch}:{len(v)}" for ch, v in sorted(sel.items()) if len(v) < F.NVAR) or "all have 7")
