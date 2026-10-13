"""Joined letter pairs for the cursive style.

Finds every pair of neighbouring letters Juan wrote in one connected stroke, keeps the
pairs he joins more often than not, and averages each one the same way single letters
are averaged. Writes data/avg_pairs.pkl ({pair: same structure as avg.pkl}).
   python pairs.py            build
   python pairs.py stats      only print the counts
"""
import pickle, sys
from collections import Counter, defaultdict
import numpy as np
import avg
from bank import char_fragments

MIN_JOINED, MIN_RATE = 14, 0.45


def collect():
    B = pickle.load(open("data/bank.pkl", "rb"))
    joined, total, items = Counter(), Counter(), defaultdict(list)
    for w in B["words"]:
        L = w["label"]
        shared = set()
        for pc in w["pc"]:
            u = np.unique(pc)
            for a, b in zip(u[:-1], u[1:]):
                if b == a + 1:
                    shared.add(int(a))
        for i in range(len(L) - 1):
            p = L[i:i + 2]
            if not (p.isalpha() and p.islower() and p.isascii()):
                continue
            if w["cbox"][i] is None or w["cbox"][i + 1] is None or w["q"][i] >= 1 or w["q"][i + 1] >= 1:
                continue
            total[p] += 1
            if i in shared:
                joined[p] += 1
                frs, _ = char_fragments(w, i, i + 1)
                frs = [np.asarray(f, dtype="f8") for f in frs]
                big = [f for f in frs if avg.plen(f) >= 0.15]
                # keep dots (i, j) even though they are short
                dots = [f for f in frs if avg.plen(f) < 0.15 and f[:, 1].min() > 0.9] if any(c in "ij" for c in p) else []
                frs = (big + dots) or frs
                if 1 <= len(frs) <= 4:
                    items[p].append((frs, w["ver"], max(w["q"][i], w["q"][i + 1])))
    return joined, total, items


def main():
    joined, total, items = collect()
    keep = sorted((p for p in joined if joined[p] >= MIN_JOINED and joined[p] / total[p] >= MIN_RATE), key=lambda p: -joined[p])
    print(f"pairs seen: {len(total)} | joined at least once: {len(joined)} | kept (joined {MIN_JOINED}+ times and {int(MIN_RATE * 100)}%+ of the time): {len(keep)}")
    print("kept  pair:joined/seen ->", "  ".join(f"{p}:{joined[p]}/{total[p]}" for p in keep))
    often = sorted((p for p in joined if joined[p] >= MIN_JOINED and p not in keep), key=lambda p: -joined[p])[:25]
    print("often seen but usually NOT joined:", "  ".join(f"{p}:{joined[p]}/{total[p]}" for p in often))
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        return
    rng = np.random.default_rng(11)
    out = {}
    for p in keep:
        e = avg.build_char(items[p], rng)
        if e["cands"][0]["n"] >= 6:
            e["rate"] = joined[p] / total[p]
            out[p] = e
    pickle.dump(out, open("data/avg_pairs.pkl", "wb"))
    print("pairs averaged:", len(out), "|", " ".join(f"{p}:{e['cands'][0]['n']}" for p, e in out.items()))


if __name__ == "__main__":
    main()
