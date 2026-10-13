"""Which joined pairs hurt legibility? Writes the test text with one pair joined at a time
(everything else fixed) and counts how many more characters the recogniser gets wrong.
Saves data/pairs_ok.pkl: the pairs worth keeping.   python pairs_check.py"""
import pickle
import avgfont as F, measure as M
F.use_style("cursiva")
allp = sorted(F.PAIRS)
text = open("corpus.txt", encoding="utf-8").read()
def errs():
    """Capped errors (see measure.LAST) summed over two fixed renderings."""
    tot = 0.0
    for pool in (1, 9):
        F.FORCE_POOL = pool
        F._prof_cache.clear()
        cer, e, n = M.read_back(seeds=(0,), verbose=False, detail=True)
        tot += M.LAST["robust"] * sum(n.values())
    return tot
F.PAIRS = set(); base = errs()
print(f"separate letters only: {base:.0f} capped errors", flush=True)
res = {}
for p in allp:
    uses = 2 * text.count(p)
    if uses == 0:
        res[p] = (0, 0); continue
    F.PAIRS = {p}; res[p] = (errs() - base, uses)
    print(f"{p}: {res[p][0]:+.0f} over {uses} uses", flush=True)
bad = sorted(p for p, (d, u) in res.items() if u and d / u > 0.3 and d >= 4)
ok = [p for p in allp if p not in bad]
pickle.dump(dict(ok=ok, bad=bad, detail=res), open("data/pairs_ok.pkl", "wb"))
print("dropped (each use costs more than 0.3 of a misread on average):", " ".join(bad) or "none")
print("kept:", len(ok), "| never appear in the test text (kept, untested):", " ".join(p for p, (d, u) in res.items() if u == 0))
