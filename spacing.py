"""Fit the shape-spacing parameters to the gaps in Juan's notes, and report the fit.
   python spacing.py"""
import numpy as np
import avgfont as F, measure as M
pairs, _ = M.gap_report(model=None, verbose=True)
obs = {p: g for p, g in pairs.items() if F.glyph(p[0], 0.0, 0) is not None and F.glyph(p[1], 0.0, 0) is not None}
P = {p: (F._prof(p[0], 0.0, 0), F._prof(p[1], 0.0, 0)) for p in obs}
best = None
for D in np.arange(0.10, 0.81, 0.05):
    F.SHAPE_D = float(D)
    base = {p: F.side(pa[1]) + F.side(pb[0]) for p, (pa, pb) in P.items()}
    for T in np.arange(0.3, 1.81, 0.02):
        e = np.mean([abs((T - base[p]) - obs[p]) for p in obs])
        if best is None or e < best[0]:
            best = (float(e), float(T), float(D))
e, T, D = best
print(f"best fit: SHAPE_T={T:.2f} SHAPE_D={D:.2f} -> average miss per pair {e:.3f} x-heights over {len(obs)} pairs")
const = np.median(list(obs.values()))
print(f"for comparison, the best single fixed gap ({const:.2f}) misses by {np.mean([abs(const - g) for g in obs.values()]):.3f}")
